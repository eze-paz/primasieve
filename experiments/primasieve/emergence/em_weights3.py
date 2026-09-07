"""EMERGENCE E-11c -- (B') the causal test, scaled to the residual stream's own norm (|d| = 0.099 against residual
norms in the tens was the reason nothing moved); (C) BUILD THE SOURCE: the weights as an offline knowledge base the
stdlib engine can consult -- for every whole-word token its nearest neighbours and the morphology operators verified
on it, written to sqlite like KAIKKI. The engine reads geometry the way it reads a dictionary: ATTRIBUTED, cited."""
import os, sys, json, random, sqlite3, time
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qwen_fwd import Qwen
from em_weights import morphology_pairs

SNAP = r"C:/Users/aezequiel/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B/snapshots/060db6499f32faf8b98477b0a26969ef7d8b9987"
OUT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_nldata", "qwen_geometry.sqlite")
rng = random.Random(3)
m = Qwen(SNAP)
E = m.w["model.embed_tokens.weight"].numpy()
vocab = m.tok.get_vocab()
words = {t[1:]: i for t, i in vocab.items() if t.startswith("Ġ") and t[1:].isalpha() and t[1:].islower()}
inv = {i: w for w, i in words.items()}
ids = np.array(sorted(words.values()))
pairs = morphology_pairs(words, "N;PL"); plural_of = dict(pairs); sing_of = {f: l for l, f in pairs}
d_emb = np.stack([E[words[f]] - E[words[l]] for l, f in pairs]).mean(0)

# ---------------------------------------------------------------- (B') residual-relative injection
prompts = ["I looked at the", "She picked up the", "He pointed at the", "We talked about the", "They found the",
           "There was a problem with the", "I need to buy a new", "Please pass me the", "The child drew a",
           "Yesterday I saw a", "He wrote about his", "She thanked her", "We visited the old", "Tell me about your",
           "The museum displayed a", "I forgot my", "He lost his", "The teacher praised the", "My neighbour owns a",
           "In the garden there is a"]


def resid_norm(ids_p, L):
    """mean norm of the residual stream at the last position after layer L (probe via a zero injection hook)."""
    w = m.w; x = w["model.embed_tokens.weight"][torch.tensor(ids_p)]
    # cheap: re-run hidden() with a recorder
    norms = {}
    orig = m.hidden
    def rec(ids_, inject=None):
        return orig(ids_, inject)
    # simpler: compute by running layers manually through m.hidden with inject=(L, zeros) is identical; instead scale by
    # the embedding->layer growth measured once on a neutral prompt
    return None


def plural_mass(ids_p, inject):
    p = torch.softmax(m.logits(ids_p, inject), -1)
    top = torch.topk(p, 40).indices.tolist()
    return (sum(float(p[t]) for t in top if inv.get(t) in sing_of), sum(float(p[t]) for t in top if inv.get(t) in plural_of),
            [m.decode([t]) for t in top[:4]])


# measure residual norms per layer on the prompts (one pass with a recording copy of hidden)
def residual_norms(ids_p):
    w = m.w; T = len(ids_p); import math
    x = w["model.embed_tokens.weight"][torch.tensor(ids_p)]; pos = torch.arange(T); mask = torch.full((T, T), float("-inf")).triu(1)
    out = {}
    with torch.no_grad():
        for l in range(m.L):
            p = f"model.layers.{l}."
            h = m.rms(x, w[p + "input_layernorm.weight"])
            q = (h @ w[p + "self_attn.q_proj.weight"].T + w[p + "self_attn.q_proj.bias"]).view(T, m.H, m.hd)
            k = (h @ w[p + "self_attn.k_proj.weight"].T + w[p + "self_attn.k_proj.bias"]).view(T, m.KV, m.hd)
            v = (h @ w[p + "self_attn.v_proj.weight"].T + w[p + "self_attn.v_proj.bias"]).view(T, m.KV, m.hd)
            q, k = m.rope(q, pos), m.rope(k, pos); rep = m.H // m.KV
            k = k.repeat_interleave(rep, 1); v = v.repeat_interleave(rep, 1)
            att = torch.softmax(torch.einsum("thd,shd->hts", q, k) / math.sqrt(m.hd) + mask, -1)
            x = x + torch.einsum("hts,shd->thd", att, v).reshape(T, m.D) @ w[p + "self_attn.o_proj.weight"].T
            h = m.rms(x, w[p + "post_attention_layernorm.weight"])
            x = x + (torch.nn.functional.silu(h @ w[p + "mlp.gate_proj.weight"].T) * (h @ w[p + "mlp.up_proj.weight"].T)) @ w[p + "mlp.down_proj.weight"].T
            out[l] = float(x[-1].norm())
    return out


norms = residual_norms(m.encode(prompts[0]))
print("(B') residual norm at the last position by layer:", {l: round(n, 1) for l, n in norms.items() if l in (0, 3, 6, 10, 14, 18, 22)})
rand = np.random.RandomState(3).randn(*d_emb.shape).astype(np.float32); rand *= np.linalg.norm(d_emb) / np.linalg.norm(rand)
print("inject the operator scaled to a FRACTION of the residual norm at that layer; knockouts: random direction, negated operator\n")
best = None
for L in (2, 6, 10, 14, 18):
    for frac in (0.3, 0.6, 1.0):
        scale = frac * norms[L] / np.linalg.norm(d_emb); row = {}
        for name, vec in (("plural d", d_emb), ("random", rand), ("-d", -d_emb)):
            flips = 0; shift = 0.0
            for pr in prompts:
                ip = m.encode(pr); pl0, sg0, t0 = plural_mass(ip, None); pl1, sg1, t1 = plural_mass(ip, (L, torch.tensor(vec * scale), len(ip) - 1))
                shift += (pl1 - sg1) - (pl0 - sg0)
                tok1 = m.encode(t1[0])[-1] if t1[0].strip() else None
                flips += (t1[0] != t0[0]) and (inv.get(tok1) in sing_of)
            row[name] = (shift / len(prompts), flips)
        print(f"  layer {L:2d} frac {frac:.1f}:  plural d shift {row['plural d'][0]:+.3f} flips {row['plural d'][1]:2d}/20   random {row['random'][0]:+.3f} {row['random'][1]:2d}   -d {row['-d'][0]:+.3f} {row['-d'][1]:2d}")
        score = row["plural d"][1] - row["random"][1]
        if best is None or score > best[0]: best = (score, L, frac, row)
_, L, frac, row = best
scale = frac * norms[L] / np.linalg.norm(d_emb)
print(f"\nbest: layer {L} frac {frac}: flips {row['plural d'][1]}/20 vs random {row['random'][1]}/20, -d {row['-d'][1]}/20")
for pr in prompts[:8]:
    ip = m.encode(pr)
    print(f"    {pr!r:32s} {plural_mass(ip, None)[2][:3]}  ->  {plural_mass(ip, (L, torch.tensor(d_emb * scale), len(ip) - 1))[2][:3]}")
causal = row["plural d"][1] >= 10 and row["random"][1] <= 2
print("\nE11c CAUSAL: " + ("the operator read off the weights STEERS the model's next word to the plural; a random direction of the same size does not"
                        if causal else "not at the bar (>= 10/20 flips with random <= 2/20)"))

# ---------------------------------------------------------------- (C) the weights as an offline SOURCE for the stdlib engine
print(f"\n(C) building the geometry source -> {os.path.basename(OUT_DB)}")
t0 = time.time()
U = E[ids] / (np.linalg.norm(E[ids], axis=1, keepdims=True) + 1e-9)
ops = {}
for feat, label in (("N;PL", "plural"), ("V;PRS;3;SG", "3sg"), ("V;V.PTCP;PRS", "prog"), ("V;PST", "past")):
    prs = morphology_pairs(words, feat)
    if len(prs) >= 20:
        d = np.stack([E[words[f]] - E[words[l]] for l, f in prs]).mean(0); ops[label] = d
con = sqlite3.connect(OUT_DB + ".tmp") if not os.path.exists(OUT_DB + ".tmp") else None
if con is None: os.remove(OUT_DB + ".tmp"); con = sqlite3.connect(OUT_DB + ".tmp")
con.execute("create table nn (w text primary key, neighbours text)")
con.execute("create table op (w text, op text, form text, rank integer)")
rows_nn = []; rows_op = []
B = 2048
for s in range(0, len(ids), B):
    blk = U[s:s + B] @ U.T
    for r in range(blk.shape[0]):
        i = s + r; blk[r, i] = -1
        top = np.argpartition(-blk[r], 12)[:12]; top = top[np.argsort(-blk[r][top])]
        rows_nn.append((inv[ids[i]], json.dumps([[inv[ids[j]], round(float(blk[r][j]), 3)] for j in top])))
for label, d in ops.items():
    Q = E[ids] + d; Qn = Q / (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-9)
    for s in range(0, len(ids), B):
        blk = Qn[s:s + B] @ U.T
        for r in range(blk.shape[0]):
            i = s + r; blk[r, i] = -1; j = int(np.argmax(blk[r]))
            rows_op.append((inv[ids[i]], label, inv[ids[j]], 0))
con.executemany("insert into nn values (?,?)", rows_nn); con.executemany("insert into op values (?,?,?,?)", rows_op); con.commit(); con.close()
if os.path.exists(OUT_DB): os.remove(OUT_DB)
os.replace(OUT_DB + ".tmp", OUT_DB)
print(f"  {len(rows_nn)} words with 12 neighbours, {len(rows_op)} operator applications ({list(ops)}) in {time.time()-t0:.0f}s")
