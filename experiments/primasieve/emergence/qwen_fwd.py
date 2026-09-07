"""A minimal Qwen2 forward pass from safetensors (CPU torch), so the engine can use the model as an ORACLE:
run it, intervene on its residual stream, observe its next-token behaviour. No transformers library.

    from qwen_fwd import Qwen; m = Qwen(SNAP); logits = m(ids, inject=(layer, vector, position))"""
import os, json, math
import torch
from safetensors import safe_open
from tokenizers import Tokenizer


class Qwen:
    def __init__(self, snap):
        self.cfg = json.load(open(os.path.join(snap, "config.json")))
        self.tok = Tokenizer.from_file(os.path.join(snap, "tokenizer.json"))
        f = safe_open(os.path.join(snap, "model.safetensors"), "pt")
        self.w = {k: f.get_tensor(k).float() for k in f.keys()}
        c = self.cfg
        self.L, self.H, self.KV = c["num_hidden_layers"], c["num_attention_heads"], c["num_key_value_heads"]
        self.D = c["hidden_size"]; self.hd = self.D // self.H; self.eps = c["rms_norm_eps"]; self.theta = c.get("rope_theta", 1000000.0)
        self.tied = c.get("tie_word_embeddings", True)

    def rms(self, x, w): return w * (x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps))

    def rope(self, x, pos):
        # x: (T, nh, hd); rotate halves
        hd = x.shape[-1]
        inv = 1.0 / (self.theta ** (torch.arange(0, hd, 2).float() / hd))
        ang = pos[:, None].float() * inv[None, :]                      # (T, hd/2)
        cos, sin = torch.cos(ang)[:, None, :], torch.sin(ang)[:, None, :]
        x1, x2 = x[..., : hd // 2], x[..., hd // 2:]
        return torch.cat([x1 * cos - x2 * sin, x1 * sin + x2 * cos], -1)

    @torch.no_grad()
    def hidden(self, ids, inject=None):
        """residual stream after every layer; `inject` = (layer index, vector, token position): the vector is
        ADDED to the residual at that position right after that layer."""
        w = self.w; T = len(ids)
        x = w["model.embed_tokens.weight"][torch.tensor(ids)]
        pos = torch.arange(T)
        mask = torch.full((T, T), float("-inf")).triu(1)
        for l in range(self.L):
            p = f"model.layers.{l}."
            h = self.rms(x, w[p + "input_layernorm.weight"])
            q = (h @ w[p + "self_attn.q_proj.weight"].T + w[p + "self_attn.q_proj.bias"]).view(T, self.H, self.hd)
            k = (h @ w[p + "self_attn.k_proj.weight"].T + w[p + "self_attn.k_proj.bias"]).view(T, self.KV, self.hd)
            v = (h @ w[p + "self_attn.v_proj.weight"].T + w[p + "self_attn.v_proj.bias"]).view(T, self.KV, self.hd)
            q, k = self.rope(q, pos), self.rope(k, pos)
            rep = self.H // self.KV
            k = k.repeat_interleave(rep, dim=1); v = v.repeat_interleave(rep, dim=1)
            att = torch.einsum("thd,shd->hts", q, k) / math.sqrt(self.hd) + mask
            att = torch.softmax(att, -1)
            o = torch.einsum("hts,shd->thd", att, v).reshape(T, self.D)
            x = x + o @ w[p + "self_attn.o_proj.weight"].T
            h = self.rms(x, w[p + "post_attention_layernorm.weight"])
            g = h @ w[p + "mlp.gate_proj.weight"].T; u = h @ w[p + "mlp.up_proj.weight"].T
            x = x + (torch.nn.functional.silu(g) * u) @ w[p + "mlp.down_proj.weight"].T
            if inject is not None and inject[0] == l:
                x = x.clone(); x[inject[2]] = x[inject[2]] + inject[1]
        return self.rms(x, w["model.norm.weight"])

    @torch.no_grad()
    def logits(self, ids, inject=None):
        h = self.hidden(ids, inject)
        W = self.w["model.embed_tokens.weight"] if self.tied or "lm_head.weight" not in self.w else self.w["lm_head.weight"]
        return h[-1] @ W.T

    @torch.no_grad()
    def generate(self, ids, max_new=16, stop=("\n",)):
        """greedy decoding with a KEY-VALUE CACHE: the prompt is encoded once, each new token attends to cached
        keys/values (without this, every token re-ran the whole 160-token few-shot prompt: ~10 s per sentence)."""
        w = self.w; T0 = len(ids); pos_all = torch.arange(T0)
        K = [None] * self.L; V = [None] * self.L
        def step(x_tokens, pos, first):
            x = w["model.embed_tokens.weight"][torch.tensor(x_tokens)]; T = x.shape[0]
            for l in range(self.L):
                p = f"model.layers.{l}."
                h = self.rms(x, w[p + "input_layernorm.weight"])
                q = (h @ w[p + "self_attn.q_proj.weight"].T + w[p + "self_attn.q_proj.bias"]).view(T, self.H, self.hd)
                k = (h @ w[p + "self_attn.k_proj.weight"].T + w[p + "self_attn.k_proj.bias"]).view(T, self.KV, self.hd)
                v = (h @ w[p + "self_attn.v_proj.weight"].T + w[p + "self_attn.v_proj.bias"]).view(T, self.KV, self.hd)
                q, k = self.rope(q, pos), self.rope(k, pos)
                K[l] = k if first else torch.cat([K[l], k], 0); V[l] = v if first else torch.cat([V[l], v], 0)
                rep = self.H // self.KV
                kk = K[l].repeat_interleave(rep, 1); vv = V[l].repeat_interleave(rep, 1)
                att = torch.einsum("thd,shd->hts", q, kk) / math.sqrt(self.hd)
                if first: att = att + torch.full((T, T), float("-inf")).triu(1)
                att = torch.softmax(att, -1)
                o = torch.einsum("hts,shd->thd", att, vv).reshape(T, self.D)
                x = x + o @ w[p + "self_attn.o_proj.weight"].T
                h = self.rms(x, w[p + "post_attention_layernorm.weight"])
                x = x + (torch.nn.functional.silu(h @ w[p + "mlp.gate_proj.weight"].T) * (h @ w[p + "mlp.up_proj.weight"].T)) @ w[p + "mlp.down_proj.weight"].T
            hN = self.rms(x[-1], w["model.norm.weight"])
            Wo = self.w["model.embed_tokens.weight"] if self.tied or "lm_head.weight" not in self.w else self.w["lm_head.weight"]
            return int(torch.argmax(hN @ Wo.T))
        t = step(ids, pos_all, True); out = []
        for i in range(max_new):
            s = self.decode([t])
            if any(x in s for x in stop) or t == self.tok.token_to_id("<|endoftext|>"): break
            out.append(t)
            t = step([t], torch.tensor([T0 + i]), False)
        return out

    def encode(self, text): return self.tok.encode(text).ids
    def decode(self, ids): return self.tok.decode(ids)

    def top(self, ids, k=5, inject=None):
        lg = self.logits(ids, inject)
        v, i = torch.topk(lg, k)
        return [(self.decode([int(t)]), float(s)) for s, t in zip(v, i)]


if __name__ == "__main__":
    import sys, time
    snap = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/aezequiel/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B/snapshots/060db6499f32faf8b98477b0a26969ef7d8b9987"
    t = time.time(); m = Qwen(snap); print(f"loaded in {time.time()-t:.0f}s: {m.L} layers, hidden {m.D}, heads {m.H}/{m.KV}")
    for s in ["The capital of France is", "One cat, two", "She has three", "He walked to the store and then he"]:
        t = time.time(); print(f"{s!r:45s} -> {m.top(m.encode(s), 5)}   ({time.time()-t:.1f}s)")
