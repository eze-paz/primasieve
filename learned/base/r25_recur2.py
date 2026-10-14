"""R25-cr: which curve shape describes how a word recurs, per word type; then a copy memory where each word type uses
its own fitted curve. Families: power, exponential, log decay, stretched exponential, two exponentials summed.
Types by training frequency rank: function (top 150), frequent (150-2,000), middle (2,000-20,000), rare (beyond).
Fit: every 50th of the first 300,000 training tokens; score = mean log2 of the copy probability of the next word
when it has occurred before, per type of that word. Run: py -3.12 r25_recur2.py"""
import os, sys, time, collections, itertools
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
ARGV0 = list(sys.argv); sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
t0 = time.time(); np.seterr(all="ignore")
rank = {w: i for i, (w, _) in enumerate(g["uni"].most_common())}
TYPES = ["function", "frequent", "middle", "rare"]
def typ(w):
    r = rank.get(w, 10 ** 9); return 0 if r < 150 else 1 if r < 2000 else 2 if r < 20000 else 3
FAM = {"power": [("power", b, c) for b, c in itertools.product((0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5), (1, 3, 10, 30, 100, 300))],
       "exponential": [("exponential", r) for r in (0.9, 0.97, 0.99, 0.995, 0.999, 0.9995, 0.9999, 0.99995)],
       "log decay": [("log decay", b, c) for b, c in itertools.product((0.5, 1, 2, 4, 8, 16), (2, 10, 100))],
       "stretched exp": [("stretched exp", tau, be) for tau, be in itertools.product((1, 10, 100, 1000, 10000), (0.1, 0.2, 0.3, 0.5, 0.7))],
       "two exponentials": [("two exponentials", r1, r2, w) for r1, r2, w in itertools.product((0.9, 0.97, 0.99), (0.999, 0.9999, 0.99995), (0.3, 0.5, 0.7, 0.9))]}
def kern(k, d):
    d = np.asarray(d, dtype=np.float64); f = k[0]
    if f == "power": return (d + k[2]) ** -k[1]
    if f == "exponential": return np.power(k[1], d - 1)
    if f == "log decay": return np.log(d + k[2]) ** -k[1]
    if f == "stretched exp": return np.exp(-(d / k[1]) ** k[2])
    return k[3] * np.power(k[1], d - 1) + (1 - k[3]) * np.power(k[2], d - 1)


def sample(stream, queries):
    occ = collections.defaultdict(list); qs = set(queries); num, seg, tt, ty = [], [], [], []
    for t, w in enumerate(stream):
        if t in qs and occ[w]:
            seg.append(len(num)); num.extend((t - np.array(occ[w])).tolist()); tt.append(t); ty.append(typ(w))
        occ[w].append(t)
    return np.array(num, dtype=np.float64), np.array(seg), np.array(tt), np.array(ty)


def plain(D, k):
    num, seg, tt, _ = D; n = np.add.reduceat(kern(k, num), seg); cs = np.cumsum(kern(k, np.arange(1, tt.max() + 2))); return n / cs[tt - 1]


train = [w for p in g["trp"] for s in p for w in s][:300000]
D = sample(train, list(range(1, len(train), 50))); best = {}
print(f"R25-cr sample: {len(D[2])} predictions whose word occurred before ({time.time() - t0:.0f} s)", flush=True)
for ti, tn in enumerate(TYPES):
    m = D[3] == ti; row = []
    for fn, ks in FAM.items():
        sc = {k: np.log2(np.clip(plain(D, k)[m], 1e-300, None)).mean() for k in ks}; kb = max(sc, key=sc.get); row.append((sc[kb], fn, kb))
    row.sort(reverse=True); best[ti] = row[0][2]
    print(f"R25-cr {tn} ({m.sum()} predictions): " + "; ".join(f"{fn} {s:.3f} {kb[1:]}" for s, fn, kb in row), flush=True)
# held-out: each earlier word weighted by its own type's curve; normalised over all earlier words
stream, qpos, A = [], [], []
for pi, p in enumerate(g["tep"][:1000]):
    for s in p:
        for i, w in enumerate(s):
            if i >= 1: qpos.append(len(stream)); A.append(pi)
            stream.append(w)
N = len(stream); ty = np.array([typ(w) for w in stream]); den = np.zeros(N + 1); denT = {}
for ti in range(4):                                                                            # den[t] = sum_{j<t, type j = ti} k_ti(t - j), by FFT convolution
    ind = (ty == ti).astype(np.float64); kv = np.r_[0.0, kern(best[ti], np.arange(1, N + 1))]
    L = 1 << int(np.ceil(np.log2(2 * N + 2))); c = np.fft.irfft(np.fft.rfft(ind, L) * np.fft.rfft(kv, L), L)[:N + 1]; den += c[:N + 1]; denT[ti] = c[:N + 1]
TYPED2 = "--per-type" in ARGV0; pi_t = np.zeros(4); occ = collections.defaultdict(list); P = np.zeros(len(qpos)); qi = 0; qset = dict((t, i) for i, t in enumerate(qpos))
for t, w in enumerate(stream):
    if t in qset and occ[w]:
        P[qset[t]] = kern(best[typ(w)], t - np.array(occ[w])).sum() / (den[t] if not TYPED2 else denT[typ(w)][t] / pi_t[typ(w)] * pi_t.sum())
    occ[w].append(t); pi_t *= 0.99; pi_t[typ(w)] += 1.0
A = np.array(A); np.savez("r25_recur_typed2_probs.npz" if TYPED2 else "r25_recur_typed_probs.npz", p=P, para=A)
print(f"R25-cr held-out typed copy memory: nonzero {np.mean(P > 0):.3f}, mean bits where nonzero (500-999) {-np.log2(P[(P > 0) & (A >= 500)]).mean():.3f} ({time.time() - t0:.0f} s)", flush=True)
