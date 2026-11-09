"""SPEC (sieve_lang_prereg.md): spectral learning of an observable-operator model (Hsu, Kakade & Zhang 2009) from the
MT 27M training counts; no neural network, no gradient descent. Vocabulary: the 8,191 most frequent training words +
a rare-word bucket (rare words by unigram share within it, as HSSM). P21[c, a] = Pr[x_{t+1} = c, x_t = a];
P3x1[c, a] = Pr[x_{t+2} = c, x_{t+1} = x, x_t = a]; U = top-k left singular vectors of P21; V = (U^T P21)^+;
b1 = U^T P1, binf = (P21^T U)^+ P1, B_x = U^T P3x1 V (accumulated from trigram counts). Prediction:
p(x | h) proportional to max(binf^T B_x b_t, floor) (floored mass reported), b_{t+1} = B_x b_t / (binf^T B_x b_t).
Evaluation = HSSM's: 300 held-out chunks of 512 words, positions 128..511, bits per word, vs the interpolated trigram,
mixtures alpha 0.1..0.95; k chosen on odd positions, reported on even and all.
Run: py -3.12 sieve_spec.py DATA_DIR OUT_JSON [k1,k2,..]"""
import sys, time, json, numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import svds
T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
z = np.load(sys.argv[1] + "/books_data.npz"); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); VV = int(S.max()) + 1
KS = [int(k) for k in (sys.argv[3] if len(sys.argv) > 3 else "50,100,200").split(",")]
Str = S[:ntr]; NV = 8192; cntw = np.bincount(Str, minlength=VV); top = np.argsort(-cntw)[:NV - 1]; vid = np.full(VV, NV - 1, np.int64); vid[top] = np.arange(NV - 1)
oov_tot = cntw[vid == NV - 1].sum(); p_in_oov = np.maximum(cntw, 1) / max(oov_tot, 1)
T = 512; WARM = 128
# trigram baseline (identical to sieve_hssm_kernel.py)
def keyn(a, b): return a * VV + b
D_ = 0.75; u1 = (cntw + 0.5) / (cntw.sum() + 0.5 * VV)
k2, n2 = np.unique(keyn(Str[:-1], Str[1:]), return_counts=True); c1 = np.bincount(Str[:-1], minlength=VV).astype(np.float64); t1 = np.bincount(k2 // VV, minlength=VV).astype(np.float64)
k3, n3 = np.unique(keyn(keyn(Str[:-2], Str[1:-1]), Str[2:]), return_counts=True); h3 = k3 // VV; uh, c2 = np.unique(keyn(Str[:-2], Str[1:-1]), return_counts=True); _, t2 = np.unique(h3, return_counts=True); uh3 = np.unique(h3)
def look(keys, vals, x):
    i = np.minimum(np.searchsorted(keys, x), len(keys) - 1); return np.where(keys[i] == x, vals[i], 0)
def p_tri(a, b, y):
    pb = np.where(c1[b] > 0, np.maximum(look(k2, n2, keyn(b, y)) - D_, 0) / np.maximum(c1[b], 1) + D_ * t1[b] / np.maximum(c1[b], 1) * u1[y], u1[y])
    h = keyn(a, b); ch = look(uh, c2, h).astype(np.float64); th_ = look(uh3, t2, h).astype(np.float64)
    return np.where(ch > 0, np.maximum(look(k3, n3, keyn(h, y)) - D_, 0) / np.maximum(ch, 1) + D_ * th_ / np.maximum(ch, 1) * pb, pb)
ev = S[ntr:]; NE = 300; es = np.linspace(0, len(ev) - T - 1, NE).astype(int); EV = np.stack([ev[s:s + T + 1] for s in es])
pos_a, pos_b, pos_y = EV[:, WARM - 2:T - 2].ravel(), EV[:, WARM - 1:T - 1].ravel(), EV[:, WARM:T].ravel()
ptri = p_tri(pos_a, pos_b, pos_y); R = dict(trigram_bits=float(-np.log2(ptri).mean()), eval_positions=int(len(ptri))); log(f"SPEC trigram bits/word {R['trigram_bits']:.4f}")
del k2, n2, k3, n3, h3, uh, c2, t2, uh3
# spectral statistics over the reduced vocabulary
X = vid[Str]; N1 = len(X)
P1 = np.bincount(X, minlength=NV) / N1
P21 = coo_matrix((np.ones(N1 - 1), (X[1:], X[:-1])), shape=(NV, NV)).tocsr() / (N1 - 1)
tk, tn = np.unique((X[:-2] * NV + X[1:-1]) * NV + X[2:], return_counts=True); ta, tx, tc = tk // (NV * NV), (tk // NV) % NV, tk % NV; tp = tn / (N1 - 2)
order = np.argsort(tx, kind="stable"); ta, tx, tc, tp = ta[order], tx[order], tc[order], tp[order]; gs = np.searchsorted(tx, np.arange(NV + 1)); log(f"SPEC statistics: {len(tk):,} distinct trigrams")
U_all, sv, _ = svds(P21, k=max(KS)); o = np.argsort(-sv); U_all = U_all[:, o]; log(f"SPEC SVD top {max(KS)} singular values {sv[o][:5]}")
YV = vid[EV]                                                                                                  # reduced ids of the evaluation chunks
def run(k):
    U = U_all[:, :k]; UP = (P21.T @ U).T                                                                      # U^T P21 (k, NV)
    V = np.linalg.pinv(UP); b1 = U.T @ P1; binf = np.linalg.pinv(P21.T @ U) @ P1                             # V (NV, k), binf (k,)
    B = np.zeros((NV, k, k), np.float32)
    for x in range(NV):
        a0, a1 = gs[x], gs[x + 1]
        if a1 > a0: B[x] = ((U[tc[a0:a1]] * tp[a0:a1, None]).T @ V[ta[a0:a1]]).astype(np.float32)
    Wm = np.einsum("k,xkj->xj", binf.astype(np.float32), B)                                                   # binf^T B_x, (NV, k)
    Wsum = Wm.sum(0); b = np.repeat(b1[None].astype(np.float32), NE, 0); out = np.zeros((NE, T - WARM)); floored = 0.0; tot = 0.0
    for t in range(T):
        s = b @ Wm.T                                                                                           # (NE, NV) unnormalised next-word scores
        fl = 1e-6 * np.abs(s).sum(1, keepdims=True); sp = np.maximum(s, fl); floored += float((sp - np.maximum(s, 0)).sum()); tot += float(sp.sum())
        p = sp / sp.sum(1, keepdims=True); y = YV[:, t]
        if t >= WARM:
            py = p[np.arange(NE), y] * np.where(y == NV - 1, p_in_oov[EV[:, t]], 1.0); out[:, t - WARM] = py
        nb = np.einsum("njk,nk->nj", B[y], b); tt = nb @ Wsum; b = (nb / np.where(np.abs(tt) > 1e-30, tt, 1e-30)[:, None]).astype(np.float32)   # amendment: normalise so the next prediction sums to +1 (per-word normalisation drifts and flips sign)
        bn = np.abs(b).sum(1, keepdims=True); b = np.where(bn > 1e6, b / bn, b)                                  # guard against blow-up (rare)
    return out.ravel(), floored / max(tot, 1e-30)
odd = (np.arange(T - WARM) % 2 == 1); oddm = np.tile(odd, NE); AL = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
for k in KS:
    pk, fm = run(k); pk = np.maximum(pk, 1e-12); bits = -np.log2(pk)
    mix = {a: float(-np.log2(a * pk + (1 - a) * ptri).mean()) for a in AL}
    R[f"k{k}"] = dict(bits=float(bits.mean()), bits_odd=float(bits[oddm].mean()), bits_even=float(bits[~oddm].mean()), floored_share=fm, mix_with_trigram=mix)
    log(f"SPEC k {k}: bits/word {bits.mean():.4f} (odd {bits[oddm].mean():.4f}, even {bits[~oddm].mean():.4f}); best mixture {min(mix.values()):.4f}; floored share {fm:.4f}")
kb = min(KS, key=lambda k: R[f"k{k}"]["bits_odd"]); R["chosen_k"] = kb; log(f"SPEC chosen k {kb}: even bits {R[f'k{kb}']['bits_even']:.4f}")
json.dump(R, open(sys.argv[2], "w"), indent=1); log("saved")
