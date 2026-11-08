"""KC (sieve_lang_prereg.md): keyed matrix memory with no training.
  py -3.12 -I sieve_kc.py synth   -> sieve_kc_synth.json (step 1: zero-training recall on the KM synthetic task, CPU)
Step 2 (rank) runs as a Kaggle CPU kernel: sieve_kc_rank_kernel.py."""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
DIM = 256; NS = (4, 8, 16, 32, 64)
def mqar(rng, Bn, T, n, far=0):                                                     # = sieve_km_synth.py
    x = np.zeros((Bn, T), np.int64); y = np.full((Bn, T), -100, np.int64)
    for b in range(Bn):
        ks = rng.choice(255, n, replace=False) + 1; vs = rng.integers(256, 512, n); x[b, 0:2 * n:2] = ks; x[b, 1:2 * n:2] = vs
        lo = max(2 * n, T - far) if far else 2 * n; qp = rng.choice(np.arange(lo, T), n, replace=False); o = rng.permutation(n)
        x[b, qp] = ks[o]; y[b, qp] = vs[o]
    return x, y
def memory_acc(R, x, y, rule, halves):
    """write every transition x[t-1] -> x[t]; at query positions read with R[x[t]] before writing; answer = best-matching value"""
    Bn, T = x.shape; S = len(halves); lam = np.array([1.0 if h is None else 2.0 ** (-1.0 / h) for h in halves], np.float32)[:, None, None, None]
    M = np.zeros((S, Bn, DIM, DIM), np.float32); Rv = R[256:512]; c = t_ = 0; decay = (lam != 1.0).any()
    for t in range(1, T):
        q = y[:, t] >= 0
        if q.any():
            r = np.matmul(M[:, q], R[x[q, t]][None, :, :, None])[..., 0].sum(0); p = (r @ Rv.T).argmax(1) + 256; c += int((p == y[q, t]).sum()); t_ += int(q.sum())
        k = R[x[:, t - 1]]; v = R[x[:, t]]
        if decay: M *= lam
        w = (v[None] - np.matmul(M, k[None, :, :, None])[..., 0]) if rule == "delta" else np.broadcast_to(v[None], (S,) + v.shape)
        M += w[..., :, None] * k[None, :, None, :]
    return c / t_
def synth():
    R = np.random.default_rng(0).standard_normal((512, DIM)).astype(np.float32); R /= np.linalg.norm(R, axis=1, keepdims=True)
    arms = {"KH": ("hebb", [None]), "KD": ("delta", [None]), "KDL": ("delta", [16, 64, 256, 1024, None])}; out = {}
    for a, (rule, halves) in arms.items():
        er = np.random.default_rng(2); r = {}
        for n in NS:
            acc = [memory_acc(R, *mqar(er, 64, 256, n), rule, halves) for _ in range(8)]; r[f"n{n}"] = float(np.mean(acc))
        r["far1024_n16"] = float(np.mean([memory_acc(R, *mqar(er, 64, 1024, 16, far=256), rule, halves) for _ in range(2)]))
        out[a] = r; log(f"{a}: {json.dumps(r)}")
    json.dump(out, open(os.path.join(HERE, "sieve_kc_synth.json"), "w"), indent=1)
if __name__ == "__main__": dict(synth=synth)[sys.argv[1]]()
