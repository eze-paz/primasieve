"""L6 (sieve_lang_prereg.md): a hidden-state model over the self-grown tree's nodes. Observations: left-tree node at depth
d (4 or 6) of each token; H hidden states (16 or 32); Baum-Welch on 400 chunks x 1,000 tokens of training text (batched
over chunks, 12 iterations, deterministic start). Its forward state is carried through the whole stream (no reset) and
predicts the next token's node; spread over the node's words by count it is a component (kind "hmm") offered to the SO
move loop on top of the SO combination. Run: SZ_EXACT=1 py -3.12 -W ignore sieve_hmm.py train | offer | eval"""
import os, sys, json, math, time
import numpy as np
argv = sys.argv[:]; sys.argv = [sys.argv[0], "none"]
import sieve_fs2 as F
import sieve_prim as P
import sieve_onto as O
T0 = time.time(); HD = os.path.join(F.SC.LX, "sieve_tree")
def train(H, d):
    f = os.path.join(HD, f"hmm_H{H}_d{d}.npz")
    if os.path.exists(f): z = np.load(f); return z["pi"], z["A"], z["B"]
    obs = F.AT[f"hl{d}"][F.tr]; C = int(F.AT[f"hl{d}"].max()) + 1; NCH, LEN = 400, 1000; starts = np.linspace(0, len(obs) - LEN - 1, NCH).astype(int); X = np.stack([obs[a:a + LEN] for a in starts])
    rng = np.random.default_rng(0); pi = np.full(H, 1 / H); A = rng.dirichlet(np.ones(H) * 5, H); Bm = rng.dirichlet(np.ones(C) * 5, H)
    for it in range(12):
        al = np.zeros((LEN, NCH, H)); sc = np.zeros((LEN, NCH)); a = pi[None, :] * Bm[:, X[:, 0]].T
        for t in range(LEN):
            if t: a = (al[t - 1] @ A) * Bm[:, X[:, t]].T
            sc[t] = a.sum(1); al[t] = a / sc[t][:, None]
        be = np.ones((NCH, H)); gam_sum = np.zeros(H); xi_sum = np.zeros((H, H)); emit = np.zeros((H, C)); g0 = np.zeros(H)
        for t in range(LEN - 1, -1, -1):
            g = al[t] * be; g /= g.sum(1, keepdims=True); np.add.at(emit.T, X[:, t], g)
            if t == 0: g0 += g.sum(0)
            else:
                bb = Bm[:, X[:, t]].T * be; xi = al[t - 1][:, :, None] * A[None] * bb[:, None, :]; xi /= xi.sum((1, 2), keepdims=True); xi_sum += xi.sum(0)
                be = (bb @ A.T) / sc[t][:, None]
        pi = g0 / g0.sum(); A = xi_sum / xi_sum.sum(1, keepdims=True); Bm = (emit + 1e-3) / (emit + 1e-3).sum(1, keepdims=True)
        print(f"   H={H} d={d} EM {it + 1}: training log-likelihood {np.log2(sc).sum() / sc.size:.4f} bits/token (node)", flush=True)
    np.savez(f, pi=pi, A=A, B=Bm); return pi, A, Bm
def forward_pred(cx, H, d):
    """predicted node distribution for every scored position, forward state carried through the stream"""
    pi, A, Bm = train(H, d); s, T, _ = F.ctx(cx); Hd = F.AT[f"hl{d}"]; obs = Hd[s]; want = set(T.tolist()); start = int(T.min()) - 20000
    a = pi.copy(); out = {}
    for t in range(start, int(T.max()) + 1):
        if t in want: out[t] = (a @ A) @ Bm
        a = (a @ A) * Bm[:, obs[t]]; a /= a.sum()
    return out
_vote = P.vote
def vote(cx, sp):
    if sp.get("kind") != "hmm": return _vote(cx, sp)
    r = O.cached(cx, sp)
    if r is not None: return r
    pred = forward_pred(cx, sp["H"], sp["d"]); s, T, _ = F.ctx(cx); D, ne = O.spread(cx, lambda i: pred[int(T[i])], F.AT[f"hl{sp['d']}"])
    return O.save(cx, sp, D, ne, np.ones(len(T)) * 10, np.ones(len(T)))
P.vote = vote; import sieve_prim3 as P3; P3.vote = vote
_d = P.describe; P.describe = P3.describe = lambda sp: f"HMM[{sp['H']} hidden states over left-tree nodes at depth {sp['d']}]" if sp.get("kind") == "hmm" else _d(sp)
_b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "hmm" else _b(sp)
_vl = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "hmm" else _vl(sp)
CANDS = [dict(kind="hmm", H=H, d=d) for H in (16, 32) for d in (4, 6)]
mode = argv[1] if len(argv) > 1 else "train"
if mode == "train":
    for sp in CANDS:
        if time.time() - T0 > 200: break
        train(sp["H"], sp["d"]); F.log(f"trained {P.describe(sp)}")
elif mode == "offer":
    O.setup_attrs(); out = os.path.join(F.HERE, "sieve_hmm_offer.json"); st = json.load(open(os.path.join(F.HERE, "sieve_onto_all.json")))
    for sp in CANDS: vote("fit9", sp)
    st, acc, fit = O.move_loop(st, CANDS); json.dump(st, open(out, "w")); F.log(f"L6: {len(acc)} accepted; fit {fit:.4f} bits/word (SO all 7.3631)")
else:
    O.setup_attrs(); st = json.load(open(os.path.join(F.HERE, "sieve_hmm_offer.json"))); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"L6 scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word (SO all 7.7153)")
