"""R25-cq: fit how a word's chance of recurring falls with distance, and use the fitted curve in the copy memories.
Kernels: power law k(d) = (d + c)^-b and exponential k(d) = r^d. Plain copy: P(w) = sum over earlier occurrences of w of
k(distance) / sum over all earlier words of k(distance). Keyed copy: the same over earlier occurrences of the previous
word, counting those followed by w. Fitted on the first 300,000 training tokens in book order (log-probability of the
next word when it has occurred before / its context has occurred before; every 50th position, to keep it to minutes);
then run on the usual held-out stream and saved for r25_em.py. Run: py -3.12 r25_recur.py"""
import os, sys, time, collections, itertools
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
t0 = time.time()
POW = [("pow", b, c) for b, c in itertools.product((0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5), (1, 3, 10, 30, 100, 300))]
EXP = [("exp", r, None) for r in (0.97, 0.99, 0.995, 0.999, 0.9995, 0.9999)]
def kern(k, d):
    return (d + k[2]) ** -k[1] if k[0] == "pow" else np.power(k[1], d - 1.0)


def distances(stream, queries, keyed):
    """for each query position t (target stream[t]): distances of the matching earlier occurrences (numerator) and,
    for keyed, of all earlier occurrences of the context (denominator). Returns concatenated arrays + segment starts."""
    occ = collections.defaultdict(list); ctx = collections.defaultdict(list)
    num, nseg, den, dseg, tt = [], [], [], [], []; qs = set(queries); qi = 0
    for t, w in enumerate(stream):
        if t in qs:
            if keyed:
                pv = stream[t - 1]; cpos = ctx[pv]
                if cpos:
                    a = np.array(cpos); nseg.append(len(num)); dseg.append(len(den))
                    num.extend((t - a[np.array([stream[p] == w for p in a])]).tolist()); den.extend((t - a).tolist()); tt.append(t)
            else:
                if occ[w]:
                    nseg.append(len(num)); num.extend((t - np.array(occ[w])).tolist()); tt.append(t)
        occ[w].append(t)
        if keyed and t >= 1: ctx[stream[t - 1]].append(t)                                    # position t follows context stream[t-1]
    return (np.array(num, dtype=np.float64), np.array(nseg), np.array(den, dtype=np.float64), np.array(dseg), np.array(tt))


def probs(D, k, keyed):
    num, nseg, den, dseg, tt = D
    kn = np.append(kern(k, num), 0.0)
    n = np.add.reduceat(kn, nseg); n[np.r_[nseg[1:], len(num)] == nseg] = 0.0                                               # empty numerator segments
    if keyed:
        d = np.add.reduceat(kern(k, den), dseg)
    else:
        cs = np.cumsum(kern(k, np.arange(1, tt.max() + 2, dtype=np.float64))); d = cs[tt - 1]
    return n / d


train = [w for p in g["trp"] for s in p for w in s][:300000]
for keyed in (False, True):
    D = distances(train, list(range(1, len(train), 50)), keyed)
    best = {}
    for fam in (POW, EXP):
        sc = {k: np.log2(np.clip(probs(D, k, keyed), 1e-30, None)).mean() for k in fam}
        best[fam[0][0]] = max(sc, key=sc.get)
        print(f"R25-cq {'keyed' if keyed else 'plain'} {fam[0][0]}: best {best[fam[0][0]]} mean log2 P (when seen before) {sc[best[fam[0][0]]]:.4f} ({time.time() - t0:.0f} s)", flush=True)
    stream, qpos, A = [], [], []
    for pi, p in enumerate(g["tep"][:1000]):
        for s in p:
            for i, w in enumerate(s):
                if i >= 1: qpos.append(len(stream)); A.append(pi)
                stream.append(w)
    A = np.array(A); qpos = np.array(qpos)
    D = distances(stream, qpos.tolist(), keyed)
    for name, k in best.items():
        P = np.zeros(len(qpos)); idx = np.searchsorted(qpos, D[4]); P[idx] = probs(D, k, keyed)
        tag = f"r25_recur_{'keyed' if keyed else 'plain'}_{name}_probs.npz"; np.savez(tag, p=P, para=A)
        print(f"R25-cq held-out {'keyed' if keyed else 'plain'} {name} {k}: nonzero {np.mean(P > 0):.3f}, mean bits where nonzero (500-999) {-np.log2(P[(P > 0) & (A >= 500)]).mean():.3f} -> {tag}", flush=True)
