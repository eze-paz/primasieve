"""SB (sieve_lang_prereg.md): a graded, labeled ontology with multiplicative links. Every word w has memberships m(w)
over A = 309 named axes (Sieve's tree nodes: lw8 94, r8 97, scene5 10, frame9 23, hybrid8 39, WordNet lexfile 46); the
context t has q(t) = sum of named feature vectors (t-1 word or node, t-2 node, scene shares of the last 200, last verb's /
noun's lexfile, sentence-position bucket); score = q . m(w) + b(w), softmax over the vocabulary. Variant L: m starts at the
word's one-hot nodes and is pulled toward them; control U: random start, no pull. Kind "bilin" (v = L | U) is the Vote.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_bilin.py prep | train L|U | show | standalone | offer | eval"""
import os, sys, json, math, time
import numpy as np
AXES = (("hlw8", 94), ("hr8", 97), ("hs5", 10), ("hf9", 23), ("hy8", 39), ("wlex", 46)); A = sum(n for _, n in AXES)
NTOP, NS, BATCH, NEG, LR, LAM = 5000, 6_000_000, 2048, 4096, 3e-3, 1e-3
G = {}
def paths(F):
    import sieve_fast as FS
    d = os.path.join(FS.IDX, "bilin"); os.makedirs(d, exist_ok=True); return d
def feats(s, T, F, P):
    """the named context features of positions T in sequence s (past only)"""
    C = P.ccount(); rank = np.empty(F.Vt, np.int64); rank[np.argsort(-C, kind="stable")] = np.arange(F.Vt); H = F.AT["hlw8"]
    p1 = s[T - 1]; a = np.where(rank[p1] < NTOP, rank[p1], NTOP + H[p1]).astype(np.int32)
    p2 = s[T - 2]; b2 = np.where(p2 != 0, H[p2], 94).astype(np.int16)
    hs = F.AT["hs5"][s]; oh = np.zeros((len(s), 10), np.int32); m = s != 0; oh[np.nonzero(m)[0], hs[m]] = 1; cum = np.cumsum(oh, 0, dtype=np.int32); del oh
    w = cum[T - 1] - cum[np.maximum(T - 201, 0)]; sc = (w / np.maximum(w.sum(1, keepdims=True), 1)).astype(np.float16); del cum
    idx = np.arange(len(s)); last0 = np.maximum.accumulate(np.where(s == 0, idx, 0)); lb = last0[T - 1]; out = {}
    for nm, bit in (("v", 1), ("n", 0)):
        mm = ((F.AT["wpos"][s] & (1 << bit)) > 0) & (s != 0); j = np.maximum.accumulate(np.where(mm, idx, -1))[T - 1]
        out[nm] = np.where(j > lb, F.AT["wlex"][s[np.maximum(j, 0)]], 46).astype(np.int8)
    pb = np.digitize(T - lb, [2, 4, 11, 21]).astype(np.int8)
    return dict(a=a, b=b2, sc=sc, v=out["v"], n=out["n"], pb=pb)
def m0(F):
    M = np.zeros((F.Vt, A), np.float32); o = 0
    for nm, k in AXES: M[np.arange(F.Vt), o + np.minimum(F.AT[nm], k - 1)] = 1.0; o += k
    M[0] = 0; return M
def build_model(F, P, v):
    import torch
    torch.manual_seed(0); nn = torch.nn
    class BL(nn.Module):
        def __init__(s_):
            super().__init__()
            s_.M = nn.Embedding(F.Vt, A, sparse=True); s_.b = nn.Embedding(F.Vt, 1, sparse=True)
            s_.Ua = nn.Embedding(NTOP + 94, A); s_.Ub = nn.Embedding(95, A); s_.Us = nn.Linear(10, A, bias=False); s_.Uv = nn.Embedding(47, A); s_.Un = nn.Embedding(47, A); s_.Up = nn.Embedding(5, A)
            with torch.no_grad():
                s_.M.weight.copy_(torch.from_numpy(m0(F)) if v == "L" else 0.3 * torch.randn(F.Vt, A))
                u = P.ccount().astype(np.float64) + 0.5; s_.b.weight.copy_(torch.from_numpy(np.log(u / u.sum())).float()[:, None])
                for e in (s_.Ua, s_.Ub, s_.Uv, s_.Un, s_.Up): e.weight.normal_(0, 0.01)
                s_.Us.weight.normal_(0, 0.01)
        def q(s_, f):
            return s_.Ua(f["a"]) + s_.Ub(f["b"]) + s_.Us(f["sc"]) + s_.Uv(f["v"]) + s_.Un(f["n"]) + s_.Up(f["pb"])
    return BL()
def tens(f, ix):
    import torch
    return {k: (torch.from_numpy(f[k][ix].astype(np.float32)) if k == "sc" else torch.from_numpy(f[k][ix].astype(np.int64))) for k in ("a", "b", "sc", "v", "n", "pb")}
def train(F, P, v):
    import torch
    d = paths(F); z = dict(np.load(os.path.join(d, "train.npz"))); ck = os.path.join(d, f"model_{v}.pt"); model = build_model(F, P, v)
    sp = [model.M.weight, model.b.weight]; dn = [p for n_, p in model.named_parameters() if n_ not in ("M.weight", "b.weight")]
    o1 = torch.optim.SparseAdam(sp, lr=LR); o2 = torch.optim.Adam(dn, lr=LR); pos = 0; hist = []
    if os.path.exists(ck): c = torch.load(ck, weights_only=False); model.load_state_dict(c["m"]); o1.load_state_dict(c["o1"]); o2.load_state_dict(c["o2"]); pos = c["pos"]; hist = c["hist"]
    if pos >= NS: F.log(f"SB train {v}: done ({pos:,} positions)"); return
    u = P.ccount().astype(np.float64) ** 0.75; u[0] = 0; qs = u / u.sum(); M0 = torch.from_numpy(m0(F)); rng = np.random.default_rng(pos); t0 = time.time(); tl = []
    while time.time() - t0 < 190 and pos < NS:
        ix = np.arange(pos, min(pos + BATCH, NS)); pos = int(ix[-1]) + 1; f = tens(z, ix); y = torch.from_numpy(z["y"][ix].astype(np.int64))
        neg = torch.from_numpy(rng.choice(F.Vt, NEG, p=qs)); cand, inv = torch.unique(torch.cat([y, neg]), return_inverse=True); yi = inv[:len(ix)]
        lq = torch.from_numpy(np.log(np.maximum(qs, 1e-30))).float()[cand]                        # sampled-softmax correction
        Mc = model.M(cand); logit = model.q(f) @ Mc.T + model.b(cand).T - lq[None, :]; loss = torch.nn.functional.cross_entropy(logit, yi)
        reg = LAM * ((Mc - M0[cand]) ** 2).sum(1).mean() if v == "L" else 0.0
        o1.zero_grad(); o2.zero_grad(); (loss + reg).backward(); o1.step(); o2.step(); tl.append(float(loss))
    hist.append((pos, float(np.mean(tl)))); torch.save(dict(m=model.state_dict(), o1=o1.state_dict(), o2=o2.state_dict(), pos=pos, hist=hist), ck)
    F.log(f"SB train {v}: {pos:,} of {NS:,} positions; sampled loss {np.mean(tl) / math.log(2):.4f} bits this run ({len(tl)} batches)")
def load(F, P, v):
    import torch
    if v not in G: m = build_model(F, P, v); m.load_state_dict(torch.load(os.path.join(paths(F), f"model_{v}.pt"), weights_only=False)["m"]); m.eval(); G[v] = m
    return G[v]
def logprobs(cx, v, F, P, cols):
    """exact log P(w | t) over the vocabulary, gathered at cols (n, k) word ids"""
    import torch
    s, T, _ = F.ctx(cx); f = feats(s, T, F, P); m = load(F, P, v); out = np.zeros(cols.shape, np.float64)
    with torch.no_grad():
        W = m.M.weight; bb = m.b.weight[:, 0]
        for a0 in range(0, len(T), 500):
            ix = np.arange(a0, min(a0 + 500, len(T))); lg = m.q(tens(f, ix)) @ W.T + bb; lg[:, 0] = -1e9; lz = torch.logsumexp(lg, 1, keepdim=True)
            out[ix] = torch.gather(lg - lz, 1, torch.from_numpy(np.minimum(cols[ix], F.Vt - 1))).numpy()
    return out
def vote(cx, sp, F, P):
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; y = s[T]
    lp = logprobs(cx, sp["v"], F, P, np.c_[SL, y]); pS = np.where(SL < F.Vt, np.exp(lp[:, :K]), 0); D = np.zeros((n, K + 1), np.float32); D[:, :K] = pS; D[:, K] = np.maximum(0, 1 - pS.sum(1))
    EX = np.exp(lp[:, K]); ne = np.ones(n, bool)
    if P.EXACT: D = P.exactify(D, EX, ans, K)
    return D, ne, np.ones(n), np.ones(n)
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    old = P.vote
    def v_(cx, sp):
        if sp.get("kind") != "bilin": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *vote(cx, sp, F, P))
    P.vote = P3.vote = v_
    _d = P.describe; P.describe = P3.describe = lambda sp: f"Bilinear[{'labeled' if sp['v'] == 'L' else 'unlabeled'} graded ontology, {A} axes]" if sp.get("kind") == "bilin" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "bilin" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "bilin" else _v(sp)
CANDS = [dict(kind="bilin", v="L", ver=1), dict(kind="bilin", v="U", ver=1)]
def setup():
    import sieve_sg as SG; F, P, P3, O = SG.setup(); install(); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); d = paths(F); out = os.path.join(F.HERE, "sieve_sb_offer.json")
    if argv[1] == "prep":
        t0 = time.time(); tr = F.tr; T = np.arange(2, len(tr)); T = T[(tr[T] != 0) & (tr[T - 1] != 0)]; T = np.sort(np.random.default_rng(0).choice(T, NS, replace=False)); f = feats(tr, T, F, P)
        o = np.random.default_rng(1).permutation(NS); np.savez(os.path.join(d, "train.npz"), y=tr[T][o].astype(np.int32), **{k: x[o] for k, x in f.items()}); F.log(f"SB prep: {NS:,} training positions ({time.time() - t0:.0f} s)"); return
    if argv[1] == "train": train(F, P, argv[2]); return
    if argv[1] == "show":
        words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; wid = {w: i + 1 for i, w in enumerate(words)}
        names = [f"{nm}:{j}" for nm, k in AXES for j in range(k)]; M = load(F, P, "L").M.weight.detach().numpy(); M0 = m0(F)
        for w in ("ship", "drink", "sword", "happy", "london", "said", "slowly"):
            i = wid[w]; o = np.argsort(-M[i])[:5]; print(f"   {w}: " + ", ".join(f"{names[j]} {M[i, j]:.2f}{'*' if M0[i, j] else ''}" for j in o), flush=True)
        return
    if argv[1] == "standalone":
        for v in argv[2:] or ["L", "U"]:
            for cx in ("fit9", "eval"):
                s, T, _ = F.ctx(cx); lp = logprobs(cx, v, F, P, s[T][:, None])[:, 0]; F.log(f"SB standalone {v} on {cx}: {-lp.mean() / math.log(2):.4f} bits/word")
        return
    if argv[1] == "offer":
        for sp in CANDS:
            for cx in ("fit9", "eval"):
                if O.cached(cx, sp) is None: t = time.time(); P.vote(cx, sp); print(f"   built {P.describe(sp)} on {cx}: {time.time() - t:.0f} s", flush=True)
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_sg_offer.json")))
        st, acc, fit = O.move_loop(st, CANDS, budget=150, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w"))
        F.log(f"SB: {len(acc)} accepted; fit {fit:.4f} bits/word (SG 7.2717)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SB scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SG 7.6331)")
if __name__ == "__main__": main(sys.argv[:])
