"""SC (sieve_lang_prereg.md): does Sieve derive counting? Given only generic primitives over a token stream -- a
context matcher (k previous tokens equal), the follower map, the distance d, a weight-term grammar over {1, d} with
+ * / (deduplicated by normalised behaviour, core.generate.SignatureBank), aggregators (last, first, set, group-sum of
a weight term, argmax of it), combinators (orelse, mix) and an escape to the uniform token -- Sieve selects programs
by minimum description length (training bits + program bits), beam search over chains of <= 3 components. Counting
is group-sum with weight 1; nothing ranks it. Run: py -3.12 sieve_count.py markov|real|shuffled|determ [--clean]"""
import os, sys, time, math, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from core.generate import SignatureBank, compress_recurring
import numpy as np
LX = os.path.join(HERE, "learned", "lx"); t0 = time.time()
TOPV, H, NTR, NSC, BEAM = 2000, 50_000, 300_000, 3000, 30
LAMS, ESCS = (0.5, 0.7, 0.9), (0.5, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01)
def log(*a): print(*a, f"({time.time() - t0:.0f} s)", flush=True)

# ---------------- weight terms: enumerated, deduplicated by normalised behaviour ----------------
DS = np.array([1, 2, 3, 5, 10, 100, 1000], float)
leaves = [("1", lambda d: np.ones_like(d)), ("d", lambda d: d)]
OPS = [("+", np.add), ("*", np.multiply), ("/", np.divide)]
bank = SignatureBank(); by_size = {1: []}
def sig(f):
    v = f(DS)
    if not np.all(np.isfinite(v)) or np.any(v <= 0): return None
    return tuple(np.round(v / v[0], 9))
for nm, f in leaves:
    s = sig(f)
    if s and bank.add(nm, s): by_size[1].append((nm, f))
for size in (3, 5):
    by_size[size] = []
    for ls in range(1, size - 1, 2):
        for a in by_size[ls]:
            for b in by_size[size - 1 - ls]:
                for on, of in OPS:
                    nm = f"({a[0]}{on}{b[0]})"; f = (lambda fa, fb, of: lambda d: of(fa(d), fb(d)))(a[1], b[1], of); s = sig(f)
                    if s and bank.add(nm, s): by_size[size].append((nm, f))
W = [t for s in (1, 3, 5) for t in by_size[s]]
log(f"weight terms (distinct behaviours, size <= 5): {len(W)}: {[n for n, _ in W]}")

# ---------------- streams ----------------
def real_stream():
    Z = np.load(os.path.join(LX, "lx_tokens.npz"))
    def mk(tok, sid, n):
        tok, sid = tok[:n].astype(np.int64), sid[:n]; tok = np.where(tok <= TOPV, tok, TOPV + 1)
        b = np.nonzero(sid[1:] != sid[:-1])[0] + 1; return np.insert(tok, b, 0)
    return mk(Z["tr"], Z["trs"], NTR), mk(Z["te"], Z["tes"], 60_000)
def markov_stream(n, nv=20, seed=0):                                                # 20 tokens: 400 contexts fit the 50,000-token memory (200 did not; harness fix)
    rng = np.random.default_rng(seed); T = rng.dirichlet(np.full(nv, 0.3), size=(nv, nv)).cumsum(-1); s = [1, 2]; u = rng.random(n)
    for i in range(n): s.append(int(np.searchsorted(T[s[-2] - 1, s[-1] - 1], u[i])) + 1)
    return np.array(s, np.int64)
def determ_stream(n, nv=20, seed=0):
    rng = np.random.default_rng(seed); F = rng.integers(1, nv + 1, (nv + 1, nv + 1))
    if "--clean" in sys.argv:                                                          # post hoc: one uninterrupted run, truly a function of the previous two
        s = [int(rng.integers(1, nv + 1)), int(rng.integers(1, nv + 1))]
        while len(s) < n: s.append(int(F[s[-2], s[-1]]))
        return np.array(s, np.int64)
    s = []
    while len(s) < n:
        s += [0, int(rng.integers(1, nv + 1)), int(rng.integers(1, nv + 1))]
        for _ in range(17): s.append(int(F[s[-2], s[-1]]))
    return np.array(s[:n], np.int64)

# ---------------- component cache: (matched?, P(true token)) per scored position ----------------
AGG = ("last", "first", "set", "sum", "argmax")
COMPS = [(k, a, w) for k in (0, 1, 2) for a in AGG for w in (range(len(W)) if a in ("sum", "argmax") else (None,))]
def cdesc(c):
    k, a, w = c; return f"k={k} {a}" + (f"[{W[w][0]}]" if w is not None else "")
def cache(s, T, need=None):
    need = range(len(COMPS)) if need is None else need; Vt = int(s.max()) + 1
    ne = np.zeros((len(COMPS), len(T)), bool); P = np.zeros((len(COMPS), len(T)))
    for k in (0, 1, 2):
        key = np.zeros(len(s), np.int64)
        for j in range(k): key[k:] = key[k:] * 1_000_003 + s[j:len(s) - k + j]
        key[:k] = -1; order = np.argsort(key, kind="stable"); ks = key[order]
        idx = [i for i in need if COMPS[i][0] == k]
        if not idx: continue
        for n, t in enumerate(T):
            lo, hi = np.searchsorted(ks, key[t]), np.searchsorted(ks, key[t], "right"); pos = order[lo:hi]
            pos = pos[(pos < t) & (pos >= t - H)]
            if len(pos) == 0: continue
            F = s[pos]; d = (t - pos).astype(float); y = s[t]; uq, inv = np.unique(F, return_inverse=True)
            for i in idx:
                _, a, w = COMPS[i]; ne[i, n] = True
                if a == "last": P[i, n] = float(F[-1] == y)
                elif a == "first": P[i, n] = float(F[0] == y)
                elif a == "set": P[i, n] = (1.0 / len(uq)) if y in uq else 0.0
                else:
                    sm = np.bincount(inv, weights=W[w][1](d), minlength=len(uq))
                    if a == "sum": j = np.searchsorted(uq, y); P[i, n] = sm[j] / sm.sum() if j < len(uq) and uq[j] == y else 0.0
                    else: P[i, n] = float(uq[np.argmax(sm)] == y)
    return ne, P, Vt
# ---------------- programs: chains of components, MDL ----------------
def term_bits(nm):
    """log2 of the choices at each node of the weight term: leaf-or-operator (1 bit), which leaf (1 bit), which op (log2 3)"""
    leaves = nm.count("1") + nm.count("d"); ops = sum(nm.count(o) for o in "+*/"); return (leaves + ops) + leaves + ops * math.log2(3)
DLc = lambda c: math.log2(3) + math.log2(len(AGG)) + (term_bits(W[c[2]][0]) if c[2] is not None else 0)   # (first run: a flat log2(15) per term, which ignored term size)
def run(chain, ne, P, Vt):
    m, p = ne[chain[0][0]].copy(), P[chain[0][0]].copy()
    for c, comb in chain[1:]:
        if comb == "orelse": p = np.where(m, p, P[c])
        else: p = np.where(m & ne[c], comb * p + (1 - comb) * P[c], np.where(m, p, P[c]))
        m = m | ne[c]
    return m, p
def score(chain, ne, P, Vt, esc=None):
    m, p = run(chain, ne, P, Vt); best = None
    for e in ((esc,) if esc is not None else ESCS):
        b = -np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt)).sum()
        if best is None or b < best[0]: best = (b, e)
    dl = sum(DLc(COMPS[c]) for c, _ in chain) + 2 * (len(chain) - 1) + math.log2(len(ESCS))
    return best[0] + dl, best[0], best[1]
def pdesc(chain, e):
    out = cdesc(COMPS[chain[0][0]])
    for c, comb in chain[1:]: out += (" ORELSE " if comb == "orelse" else f" MIX{comb} ") + cdesc(COMPS[c])
    return out + f" (escape {e})"
def search(ne, P, Vt):
    progs = {}
    beam = []
    for c in range(len(COMPS)):
        if ne[c].any(): sc, b, e = score([(c, None)], ne, P, Vt); progs[((c, None),)] = (sc, b, e)
    beam = sorted(progs, key=lambda q: progs[q][0])[:BEAM]
    for _ in range(2):
        new = []
        for ch in beam:
            for c in range(len(COMPS)):
                if any(c == x for x, _ in ch) or not ne[c].any(): continue
                for comb in ("orelse",) + LAMS:
                    q = ch + ((c, comb),)
                    if q not in progs: progs[q] = score(list(q), ne, P, Vt); new.append(q)
        beam = sorted(set(beam) | set(new), key=lambda q: progs[q][0])[:BEAM]
    return progs
def is_count(c): k, a, w = COMPS[c]; return a in ("sum", "argmax") and W[w][0] == "1"
def weighted(c): return COMPS[c][1] in ("sum", "argmax")

# ---------------- run ----------------
if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "markov"; rng = np.random.default_rng(1)
    if kind == "real": s, held = real_stream()
    elif kind == "shuffled": s, _ = real_stream(); s = rng.permutation(s)
    elif kind == "markov": s = markov_stream(NTR)
    else: s = determ_stream(NTR)
    cand = np.arange(len(s) // 2, len(s))
    T = np.sort(rng.choice(cand, NSC, replace=False))
    ne, P, Vt = cache(s, T); log(f"{kind}: stream {len(s):,} tokens, {Vt} token types; {len(COMPS)} components cached on {NSC} positions")
    progs = search(ne, P, Vt); rank = sorted(progs, key=lambda q: progs[q][0])
    def show(nm, q):
        sc, b, e = progs[q]; print(f"   {nm}: {pdesc(q, e)} -- training {b / NSC:.4f} bits/token, description {sc - b:.1f} bits")
    single = sorted([q for q in progs if len(q) == 1], key=lambda q: progs[q][0])
    print("   single components, best 6:", "; ".join(f"{cdesc(COMPS[q[0][0]])} {progs[q][1] / NSC:.3f}" for q in single[:6]))
    for want in ("k=2 sum[1]", "k=1 sum[1]", "k=0 sum[1]", "k=2 last", "k=2 set"):
        q = [q for q in single if cdesc(COMPS[q[0][0]]) == want]
        if q: print(f"   {want}: {progs[q[0]][1] / NSC:.4f} bits/token")
    best = rank[0]; show("MDL-best", best)
    nc = [q for q in rank if not any(is_count(c) for c, _ in q)]; show("best without a count component", nc[0])
    nk = [q for q in rank if all(COMPS[c][0] == 0 for c, _ in q)]; show("best without context (k = 0 only)", nk[0])
    nw = [q for q in rank if not any(weighted(c) for c, _ in q)]; show("best without any group-sum/argmax", nw[0])
    top, n = compress_recurring(rank[:20], lambda q: {cdesc(COMPS[c]) for c, _ in q}); print(f"   COMPRESS over the top 20 programs: recurring fragment '{top}' in {n}")
    uses_count = all(is_count(c) for c, _ in best if weighted(c)) and any(weighted(c) for c, _ in best)
    log(f"{kind}: MDL-best weighted components all weight 1 (counting): {uses_count}; uses context k >= 1: {any(COMPS[c][0] >= 1 for c, _ in best)}; "
        f"uses any group-sum/argmax: {any(weighted(c) for c, _ in best)}")
    if kind == "real":
        full = np.r_[s, held]; Th = np.arange(len(s) + 2, len(s) + 2 + NSC)
        for nm, q in (("MDL-best", best), ("best without a count component", nc[0]), ("best without context", nk[0])):
            need = sorted({c for c, _ in q}); neh, Ph, _ = cache(full, Th, need)
            m, p = run(list(q), neh, Ph, Vt); e = progs[q][2]
            print(f"   held-out {nm}: {(-np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt))).mean():.4f} bits/token")
        # reference: interpolated Witten-Bell trigram over the same tokens and history bound
        c1, c2, c3 = collections.Counter(), collections.Counter(), collections.Counter(); n1, n2 = collections.Counter(), collections.Counter()
        d1, d2 = collections.defaultdict(set), collections.defaultdict(set); want = set(Th.tolist()); bits = []
        for t in range(len(full)):
            y = int(full[t]); a = int(full[t - 1]) if t >= 1 else -1; b = int(full[t - 2]) if t >= 2 else -1
            if t in want:
                p0 = (c1[y] + 1) / (sum(c1.values()) + Vt) if False else (c1[y] + 1) / (t + Vt)
                T1 = len(d1[a]); p1 = (c2[(a, y)] + T1 * p0) / (n1[a] + T1) if n1[a] else p0
                T2 = len(d2[(b, a)]); p2 = (c3[(b, a, y)] + T2 * p1) / (n2[(b, a)] + T2) if n2[(b, a)] else p1
                bits.append(-math.log2(p2))
            c1[y] += 1; c2[(a, y)] += 1; n1[a] += 1; d1[a].add(y); c3[(b, a, y)] += 1; n2[(b, a)] += 1; d2[(b, a)].add(y)
        print(f"   held-out reference, Witten-Bell trigram (all history): {np.mean(bits):.4f} bits/token")
