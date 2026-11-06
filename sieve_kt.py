"""KT (sieve_lang_prereg.md): complementarity kill test. Control + book cache vs Sieve + control, same 50,114 positions.
Run: py -3.12 -I sieve_kt.py"""
import os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
z = np.load(os.path.join(HERE, "ctxw_base.npz")); s, T, b = z["s"].astype(np.int64), z["T"], z["b"]
e = np.load(os.path.join(HERE, "learned", "lx", "sieve_prim_cache", "bits_paq_sieve_tc2_offer.npy")); k = np.load(os.path.join(HERE, "kaggle_fair_control", "fair_control_bits_S.npz"))
assert len(np.unique(k["pos"] - T)) == 1 and np.array_equal(k["y"], s[T]); c = k["bits"]; y = s[T]
bs = np.searchsorted(b, b[T]) if np.all(np.diff(b) >= 0) else None; assert bs is not None                  # book start (books are contiguous)
tok = np.nonzero(s != 0)[0]; key = b[tok].astype(np.int64) * (int(s.max()) + 1) + s[tok]; cmb = np.sort((key << 26) | tok)
kt = b[T].astype(np.int64) * (int(s.max()) + 1) + y; hist = np.searchsorted(cmb, (kt << 26) | T) - np.searchsorted(cmb, kt << 26)     # earlier same-book occurrences
nh = np.searchsorted(tok, T) - np.searchsorted(tok, bs); pC = hist / np.maximum(nh, 1)
P = dict(S=2.0 ** -e, N=2.0 ** -c, C=pC); odd = np.arange(len(T)) % 2 == 1; ev = ~odd
def mix(keys):
    M = np.stack([P[q] for q in keys], 1); w = np.full(len(keys), 1 / len(keys))
    for _ in range(200): r = M[odd] * w; r /= r.sum(1, keepdims=True); w = r.mean(0)
    return -np.log2(M @ w), w
R = {}; out = {}
for nm, keys in (("control", ("N",)), ("sieve", ("S",)), ("a control+cache", ("N", "C")), ("b control+cache+sieve", ("N", "C", "S")), ("c sieve+control", ("S", "N"))):
    bits, w = mix(keys); out[nm] = bits; R[nm] = dict(even=float(bits[ev].mean()), weights=[round(float(v), 3) for v in w])
    print(f"KT {nm}: even positions {bits[ev].mean():.4f} bits (weights {R[nm]['weights']})")
g = np.random.default_rng(0); blk = np.arange(len(T)) // 500; ub = np.unique(blk[ev])
def boot(a_, b_):
    dlt = (a_ - b_)[ev]; sm = np.bincount(blk[ev], weights=dlt, minlength=blk.max() + 1)[ub]; n = np.bincount(blk[ev], minlength=blk.max() + 1)[ub]
    sam = [(sm[i].sum() / n[i].sum()) for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [float(np.percentile(sam, 2.5)), float(np.percentile(sam, 97.5))]
for x_, y_ in (("b control+cache+sieve", "a control+cache"), ("c sieve+control", "a control+cache")):
    ci = boot(out[x_], out[y_]); R[f"{x_} minus {y_} 95% CI"] = ci; print(f"KT paired 95% interval, {x_} minus {y_}: [{ci[0]:.4f}, {ci[1]:.4f}] bits")
print(f"KT cache coverage: share of even targets seen earlier in the same book {(hist[ev] > 0).mean():.3f}")
json.dump(R, open(os.path.join(HERE, "sieve_kt.json"), "w"), indent=1)
