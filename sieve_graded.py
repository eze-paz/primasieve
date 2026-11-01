"""SP3 + SP6 (sieve_lang_prereg.md): graded matching and an entity atom, small scale (SM's 1,000 positions).
Graded component: every past position j in the 50,000-token memory scored by agreement of the 3 tokens before it with
the 3 before t (attr identity or most-frequent-follower class; weight per offset in {0,1,2}); the top-K agreeing
positions (K in 100, 1000) vote for their follower with weight 2^agreement. Entity atom: the most recent capitalised
mid-sentence word (<= 30 tokens back) is the same (alone, or with the previous token). Offered beside SP0's
components (sieve_wide.py); the same search without them is the control. Components cached in sieve_gr_cache/.
Run: py -3.12 -W ignore sieve_graded.py cache-base | cache-graded | search | eval"""
import os, sys, math, json, itertools
import numpy as np
import sieve_count as SC, sieve_match as SMM, sieve_trust as ST, sieve_wide as SW
log = SC.log; CD = os.path.join(SC.HERE, "learned", "lx", "sieve_gr_cache"); os.makedirs(CD, exist_ok=True)
NSC = 1000; Vt = SW.Vt; s, held = SW.s, SW.held
rng = np.random.default_rng(1); T = np.sort(rng.choice(np.arange(len(s) // 2, len(s)), NSC, replace=False)); AT = SMM.attrs(s, Vt)
full = np.r_[s, held]; fbook = np.r_[SW.sbook, SW.hbook]; fcap = np.r_[SW.scap, SW.hcap]; Th = np.arange(len(s) + 2, len(s) + 2 + NSC)
WS = [w for w in itertools.product((0, 1, 2), repeat=3) if any(w)]
GR = [("graded", attr, w, K) for attr in ("id", "mff") for w in WS for K in (100, 1000)]
ENT = [("entity", ()), ("entity", (("id", 1),))]
def graded_all(stream, T, attr):
    """all graded components for one attr: dict (w, K) -> (ne, P, N, TD)"""
    A = AT[attr][stream]; out = {(w, K): [np.zeros(len(T), bool), np.zeros(len(T)), np.zeros(len(T)), np.zeros(len(T))] for w in WS for K in (100, 1000)}
    for i, t in enumerate(T):
        j = np.arange(max(3, t - SC.H), t); eq = np.stack([A[j - a] == A[t - a] for a in (1, 2, 3)]).astype(np.int8); F = stream[j]; y = stream[t]
        for w in WS:
            sc = (np.array(w, np.int8) @ eq).astype(np.int64); pos = np.nonzero(sc > 0)[0]
            if len(pos) == 0: continue
            for K in (100, 1000):
                sel = pos if len(pos) <= K else pos[np.argpartition(-(sc[pos] * 10**7 + pos), K)[:K]]
                wt = 2.0 ** sc[sel]; f = F[sel]; o = out[(w, K)]; o[0][i] = True; o[1][i] = wt[f == y].sum() / wt.sum(); o[2][i] = len(sel); o[3][i] = len(np.unique(f))
    return out
def ent_key(stream, cap, st):
    idx = np.arange(len(stream)); last = np.maximum.accumulate(np.where(cap.astype(bool) & (stream != 0), idx, -1))
    prev = np.r_[-1, last[:-1]]; E = np.where((prev >= 0) & (idx - prev <= 30), stream[np.maximum(prev, 0)], -1).astype(np.int64)
    key = E.copy()
    for a, o in st: v = np.full(len(stream), -1, np.int64); v[o:] = AT[a][stream[:len(stream) - o]]; key = np.where((key == -1) | (v == -1), -1, key * 1_000_003 + v)
    return key
def ent_build(stream, book, cap, T, st):
    key = ent_key(stream, cap, st); order = np.argsort(key, kind="stable"); ks = key[order]; ne = np.zeros(len(T), bool); P = np.zeros((2, len(T))); N = np.zeros(len(T)); TD = np.zeros(len(T))
    for i, t in enumerate(T):
        if key[t] == -1: continue
        lo, hi = np.searchsorted(ks, key[t]), np.searchsorted(ks, key[t], "right"); pos = order[lo:hi]; pos = pos[(pos < t) & (pos >= t - SC.H)]
        if len(pos) == 0: continue
        F = stream[pos]; d = (t - pos).astype(float); y = stream[t]; ne[i] = True; N[i] = len(pos); TD[i] = len(np.unique(F))
        P[0, i] = (F == y).mean(); r = 1 / (1 + d); P[1, i] = r[F == y].sum() / r.sum()
    return ne, P, N, TD
def save(name, ne, P, N, TD): np.savez(os.path.join(CD, name), ne=ne, P=P, N=N, TD=TD)
def load(name): z = np.load(os.path.join(CD, name)); return z["ne"], z["P"], z["N"], z["TD"]
mode = (sys.argv[1] if len(sys.argv) > 1 else "search") if __name__ == "__main__" else None      # importable (sieve_loglin.py)
if mode == "cache-base":
    seen = set(); names = []
    for mi, m in enumerate(SW.MATCHERS):
        ne, P, N, TD = SW.build(s, SW.sbook, T, m, AT); sig = (ne.tobytes(), np.round(P, 12).tobytes(), N.tobytes())
        if sig in seen: continue
        seen.add(sig)
        for ti in range(2): save(f"base_{mi}_{ti}.npz", ne, P[ti], N, TD); names.append(f"base_{mi}_{ti}")
    for ei, (_, st) in enumerate(ENT):
        ne, P, N, TD = ent_build(s, SW.sbook, SW.scap, T, st)
        for ti in range(2): save(f"ent_{ei}_{ti}.npz", ne, P[ti], N, TD)
    log(f"cached {len(names)} base + {2 * len(ENT)} entity components")
elif mode == "cache-graded":
    for attr in ("id", "mff"):
        for (w, K), (ne, P, N, TD) in graded_all(s, T, attr).items(): save(f"gr_{attr}_{''.join(map(str, w))}_{K}.npz", ne, P, N, TD)
        log(f"graded components cached for {attr}")
elif mode is not None:
    names = sorted(f[:-4] for f in os.listdir(CD))
    def desc(n):
        p = n.split("_")
        if p[0] == "base": m = SW.MATCHERS[int(p[1])]; return f"[{SW.mname(m)}] {('count', 'recency')[int(p[2])]}"
        if p[0] == "ent": return f"[entity{' & token(t-1)' if p[1] == '1' else ''}] {('count', 'recency')[int(p[2])]}"
        return f"[graded {p[1]}, offset weights {p[2]}, top {p[3]}]"
    def bits_of(n):
        p = n.split("_")
        if p[0] == "base": return 1 + len(SW.MATCHERS[int(p[1])][0]) * math.log2(len(SW.ATOMS)) + math.log2(len(SW.BOUNDS)) + 1
        if p[0] == "ent": return 1 + 1 + int(p[1]) * math.log2(len(SW.ATOMS)) + 1
        return 1 + 1 + 3 * math.log2(3) + 1
    if mode == "search":
        res = {}
        for label, use in (("with graded + entity", names), ("control (SP0 components only)", [n for n in names if n.startswith("base")])):
            C = [load(n + ".npz") for n in use]; NE, PP, NN, TT = (np.array([c[j] for c in C]) for j in range(4))
            progs = ST.search(NE, PP, NN, TT, Vt, lambda c: bits_of(use[c]), len(use)); best = min(progs, key=lambda q: (round(progs[q][0], 9), repr(q)))
            sc, b, e = progs[best]; res[label] = dict(chain=[[use[c], cb] for c, cb in best], escape=e)
            print(f"   {label}: " + desc(use[best[0][0]]) + "".join(ST.cbname(cb) + desc(use[c]) for c, cb in best[1:]) + f" (escape {e}) -- training {b / NSC:.4f}, description {sc - b:.1f} bits", flush=True)
        json.dump(res, open(os.path.join(SC.HERE, "sieve_graded_best.json"), "w")); log("searches done")
    else:
        res = json.load(open(os.path.join(SC.HERE, "sieve_graded_best.json")))
        for label, prog in res.items():
            C = []
            for n, cb in prog["chain"]:
                p = n.split("_")
                if p[0] == "base": ne, P, N, TD = SW.build(full, fbook, Th, SW.MATCHERS[int(p[1])], AT); C.append((ne, P[int(p[2])], N, TD))
                elif p[0] == "ent": ne, P, N, TD = ent_build(full, fbook, fcap, Th, ENT[int(p[1])][1]); C.append((ne, P[int(p[2])], N, TD))
                else:
                    w = tuple(int(x) for x in p[2]); C.append(tuple(graded_all_one(full, Th, p[1], w, int(p[3]))) if False else None)
            if any(c is None for c in C):
                for k, (n, cb) in enumerate(prog["chain"]):
                    p = n.split("_")
                    if p[0] == "gr": C[k] = tuple(graded_all(full, Th, p[1])[(tuple(int(x) for x in p[2]), int(p[3]))])
            NE, PP, NN, TT = (np.array([c[j] for c in C]) for j in range(4))
            chain = [(k, None if cb is None else tuple(cb)) for k, (_, cb) in enumerate(prog["chain"])]; m, p = ST.run(chain, NE, PP, NN, TT); e = prog["escape"]
            log(f"held-out {label}: {(-np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt))).mean():.4f} bits/token")
