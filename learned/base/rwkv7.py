"""RWKV-7 ("Goose") in plain torch, trainable on the CPU, built from a BlinkDL rwkv-7-world checkpoint. Written for the
subtractive critical-engine plan (step 1): the recurrence is the published one (Peng et al. 2025, arXiv 2503.14456):
    S_t = S_{t-1} * diag(w_t) + S_{t-1} (a_t b_t^T) + v_t k_t^T ,   y_t = S_t r_t        (per head, N x N state)
computed by a sequential loop over time with autograd (reference form; chunking is a later optimisation).
Tokenizer: the RWKV World trie tokenizer shipped in the `rwkv` pip package. Weights are loaded with weights_only=True.
Usage: m = RWKV7.load(path); logits = m(ids)  # ids (B, T) int64"""
import os, torch, torch.nn as nn, torch.nn.functional as F


CHUNK = 16          # recurrence steps per checkpoint: autograd keeps the N x N state only at chunk borders and recomputes inside


def _steps(state, r, w, k, v, a, b):
    """run the recurrence over one chunk; inputs (B, Tc, H, N); returns the outputs (B, Tc, H, N) and the final state"""
    out = []
    for t in range(r.shape[1]):
        state = state * w[:, t, :, None, :] + state @ a[:, t, :, :, None] @ b[:, t, :, None, :] + v[:, t, :, :, None] @ k[:, t, :, None, :]
        out.append(state @ r[:, t, :, :, None])
    return torch.stack(out, 1)[..., 0], state


def wkv7(r, w, k, v, a, b, head_size, state=None, return_state=False):
    B, T, C = r.shape; H = C // head_size; N = head_size
    r, k, v, a, b = (x.view(B, T, H, N).float() for x in (r, k, v, a, b))
    w = torch.exp(-torch.exp(w.view(B, T, H, N).float()))
    state = torch.zeros(B, H, N, N) if state is None else state; outs = []
    need_grad = torch.is_grad_enabled() and any(x.requires_grad for x in (r, w, k, v, a, b))
    for s in range(0, T, CHUNK):
        sl = slice(s, s + CHUNK); args = (state, r[:, sl], w[:, sl], k[:, sl], v[:, sl], a[:, sl], b[:, sl])
        if need_grad:
            from torch.utils.checkpoint import checkpoint
            o, state = checkpoint(_steps, *args, use_reentrant=False)
        else:
            o, state = _steps(*args)
        outs.append(o)
    y = torch.cat(outs, 1).reshape(B, T, C)
    return (y, state) if return_state else y


def shift(x, prev=None):                        # token shift: x_{t-1}; zero at t = 0, or the carried last token
    s = F.pad(x, (0, 0, 1, -1))
    if prev is not None: s[:, 0] = prev
    return s


class TMix(nn.Module):
    def __init__(s, sd, p, head_size):
        super().__init__(); s.N = head_size; C = sd[p + "receptance.weight"].shape[0]; s.H = C // head_size
        for n in ("x_r", "x_w", "x_k", "x_v", "x_a", "x_g", "w0", "w1", "w2", "a0", "a1", "a2", "g1", "g2", "k_k", "k_a", "r_k"):
            setattr(s, n, nn.Parameter(sd[p + n].float()))
        s.has_v = p + "v0" in sd
        if s.has_v:
            for n in ("v0", "v1", "v2"): setattr(s, n, nn.Parameter(sd[p + n].float()))
        for n in ("receptance", "key", "value", "output"):
            lin = nn.Linear(C, C, bias=False); lin.weight = nn.Parameter(sd[p + n + ".weight"].float()); setattr(s, n, lin)
        s.ln_x = nn.GroupNorm(s.H, C, eps=64e-5); s.ln_x.weight = nn.Parameter(sd[p + "ln_x.weight"].float()); s.ln_x.bias = nn.Parameter(sd[p + "ln_x.bias"].float())

    def forward(s, x, v_first, st=None):
        """st: None (stateless) or a dict with 'x' (B, C) the previous token's input and 'S' (B, H, N, N); updated in place"""
        B, T, C = x.shape; xx = shift(x, None if st is None else st.get("x")) - x
        if st is not None: st["x"] = x[:, -1].clone()
        xr, xw, xk, xv, xa, xg = (x + xx * m for m in (s.x_r, s.x_w, s.x_k, s.x_v, s.x_a, s.x_g))
        r = s.receptance(xr)
        w = -F.softplus(-(s.w0 + torch.tanh(xw @ s.w1) @ s.w2)) - 0.5
        k = s.key(xk); v = s.value(xv)
        if not s.has_v: v_first = v
        else: v = v + (v_first - v) * torch.sigmoid(s.v0 + (xv @ s.v1) @ s.v2)
        a = torch.sigmoid(s.a0 + (xa @ s.a1) @ s.a2)
        g = torch.sigmoid(xg @ s.g1) @ s.g2
        kk = F.normalize((k * s.k_k).view(B, T, s.H, -1), dim=-1, p=2.0).view(B, T, C)
        k = k * (1 + (a - 1) * s.k_a)
        if st is None: y = wkv7(r, w, k, v, -kk, kk * a, s.N)
        else: y, st["S"] = wkv7(r, w, k, v, -kk, kk * a, s.N, state=st.get("S"), return_state=True)
        y = s.ln_x(y.view(B * T, C)).view(B, T, C)
        y = y + ((r.view(B, T, s.H, -1) * k.view(B, T, s.H, -1) * s.r_k).sum(-1, keepdim=True) * v.view(B, T, s.H, -1)).view(B, T, C)
        return s.output(y * g), v_first


class CMix(nn.Module):
    def __init__(s, sd, p):
        super().__init__(); s.x_k = nn.Parameter(sd[p + "x_k"].float())
        kw, vw = sd[p + "key.weight"], sd[p + "value.weight"]
        s.key = nn.Linear(kw.shape[1], kw.shape[0], bias=False); s.key.weight = nn.Parameter(kw.float())
        s.value = nn.Linear(vw.shape[1], vw.shape[0], bias=False); s.value.weight = nn.Parameter(vw.float())

    def forward(s, x, st=None):
        k = x + (shift(x, None if st is None else st.get("x")) - x) * s.x_k
        if st is not None: st["x"] = x[:, -1].clone()
        return s.value(torch.relu(s.key(k)) ** 2)


def _ln(sd, p):
    ln = nn.LayerNorm(sd[p + "weight"].shape[0]); ln.weight = nn.Parameter(sd[p + "weight"].float()); ln.bias = nn.Parameter(sd[p + "bias"].float()); return ln


class Block(nn.Module):
    def __init__(s, sd, i, head_size):
        super().__init__(); p = f"blocks.{i}."
        s.ln0 = _ln(sd, p + "ln0.") if i == 0 else None
        s.ln1 = _ln(sd, p + "ln1."); s.ln2 = _ln(sd, p + "ln2.")
        s.att = TMix(sd, p + "att.", head_size); s.ffn = CMix(sd, p + "ffn.")

    def forward(s, x, v_first, st=None):
        if s.ln0 is not None: x = s.ln0(x)
        y, v_first = s.att(s.ln1(x), v_first, None if st is None else st["att"]); x = x + y
        return x + s.ffn(s.ln2(x), None if st is None else st["ffn"]), v_first


class RWKV7(nn.Module):
    def __init__(s, sd, head_size=64):
        super().__init__()
        s.emb = nn.Embedding(*sd["emb.weight"].shape); s.emb.weight = nn.Parameter(sd["emb.weight"].float())
        n_layer = 1 + max(int(k.split(".")[1]) for k in sd if k.startswith("blocks."))
        s.blocks = nn.ModuleList(Block(sd, i, head_size) for i in range(n_layer))
        s.ln_out = _ln(sd, "ln_out."); s.head = nn.Linear(*reversed(sd["head.weight"].shape), bias=False); s.head.weight = nn.Parameter(sd["head.weight"].float())
        s.n_layer = n_layer; s.n_embd = s.emb.weight.shape[1]

    def forward(s, idx, state=None):
        """state: None, or a list (one dict per block, from new_state()) carried across calls and updated in place"""
        x = s.emb(idx); v_first = None
        for i, b in enumerate(s.blocks): x, v_first = b(x, v_first, None if state is None else state[i])
        return s.head(s.ln_out(x))

    def new_state(s):
        return [dict(att={}, ffn={}) for _ in s.blocks]

    @torch.no_grad()
    def greedy(s, ids, n, stop="\n", tok=None):
        """incremental greedy decoding with the carried state: the prompt once, then one step per token"""
        st = s.new_state(); logits = s(ids, st); out = []
        for _ in range(n):
            nxt = logits[0, -1].argmax().item(); out.append(nxt)
            if tok is not None and stop in tok.decode([nxt]): break
            logits = s(torch.tensor([[nxt]]), st)
        return out

    @staticmethod
    def load(path):
        sd = torch.load(path, map_location="cpu", weights_only=True)
        return RWKV7(sd)

    @torch.no_grad()
    def generate(s, ids, n, temp=1.0, top_k=40, gen=None):
        for _ in range(n):
            logits = s(ids)[:, -1] / temp
            if top_k:
                v, _ = torch.topk(logits, top_k); logits[logits < v[:, [-1]]] = -1e9
            ids = torch.cat([ids, torch.multinomial(F.softmax(logits, -1), 1, generator=gen)], 1)
        return ids


def tokenizer():
    import rwkv
    from rwkv.rwkv_tokenizer import TRIE_TOKENIZER
    return TRIE_TOKENIZER(os.path.join(os.path.dirname(rwkv.__file__), "rwkv_vocab_v20230424.txt"))
