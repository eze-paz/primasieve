"""PS (sieve_lang_prereg.md): predictive-state merging. Two-word contexts are merged into K states by hard EM on their
next-word counts (pure counting); S_K predicts from the pooled counts of a context's state. Compute knob = K.
Run: py -3.12 -I sieve_mts.py prep <c> ; fit <c> <K> (repeat until done) ; score <c> <K> ; curve <c>"""
import os, sys, json, time
import numpy as np, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
T0 = time.time(); V, VV, D = MT.V, MT.VV, MT.D; NM = 50_000; F = 2000; IT = 15; SM = 0.01; KS = (256, 1024, 4096, 16384)
torch.set_num_threads(os.cpu_count())
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def ctxs(c):
    g = np.load(MT.fp(c, "ngram")); u3, n3 = g["u3"], g["n3"]; cx = u3 // VV; y3 = u3 % VV
    st = np.r_[0, np.nonzero(cx[1:] != cx[:-1])[0] + 1]; uc = cx[st]; ci = np.repeat(np.arange(len(uc)), np.diff(np.r_[st, len(cx)]))
    return g, uc, ci, y3, n3, np.where((y3 >= 1) & (y3 <= F), y3 - 1, F)                                  # feature column: top-F word or "other"
def feats(rows_of_ctx, ci, cols, n3, nrows):
    r = rows_of_ctx[ci]; s = r >= 0; return r[s], cols[s], n3[s].astype(np.float32), nrows
def dense(trip, a, b):
    r, cl, v, _ = trip; m = (r >= a) & (r < b); X = np.bincount((r[m] - a) * (F + 1) + cl[m], weights=v[m], minlength=(b - a) * (F + 1)); return X.reshape(b - a, F + 1).astype(np.float32)
def prep(c):
    g, uc, ci, y3, n3, cols = ctxs(c); cnt = np.bincount(ci, weights=n3); mi = np.sort(np.argsort(-cnt, kind="stable")[:NM])
    mrow = np.full(len(uc), -1, np.int64); mrow[mi] = np.arange(NM); X = dense(feats(mrow, ci, cols, n3, NM), 0, NM)
    z = np.load(MT.fp(c, "data")); S, ntr = z["S"].astype(np.int64), int(z["ntr"]); con = (S > 100) & (S <= V); T = MT.targets(S, ntr, con, "content")
    ec = S[T - 2] * VV + S[T - 1]; i = np.minimum(np.searchsorted(uc, ec), len(uc) - 1); seen = uc[i] == ec
    np.savez(MT.fp(c, "ps_prep"), X=X, mi=mi, b=uc[mi] % VV, T=T, eidx=np.where(seen, i, -1), share_member=np.isin(np.where(seen, i, -1), mi).mean())
    log(f"PS prep {c}: {len(uc):,} training contexts; members cover {cnt[mi].sum() / cnt.sum():.3f} of trigram tokens; eval contexts seen {seen.mean():.3f}, member {np.isin(np.where(seen, i, -1), mi).mean():.3f}")
def phis(X, zz, K):
    ph = torch.zeros(K, F + 1).index_add_(0, torch.tensor(zz), torch.tensor(X)) + SM; return torch.log(ph / ph.sum(1, keepdim=True))
def assign(X, lph, B=4000):
    out = np.empty(len(X), np.int64); ll = 0.0
    for a in range(0, len(X), B):
        sc = torch.tensor(X[a:a + B]) @ lph.T; m, ix = sc.max(1); out[a:a + B] = ix.numpy(); ll += float(m.sum())
    return out, ll
def fit(c, K):
    q = np.load(MT.fp(c, "ps_prep")); X = q["X"]; sf = MT.fp(c, f"ps_fit{K}")
    if os.path.exists(sf):
        with np.load(sf) as s: zz, it0 = s["z"].copy(), int(s["it"])
    else: zz, it0 = (q["b"] % K).astype(np.int64), 0
    if it0 >= IT: log(f"PS fit {c} K{K}: already done"); return
    last = 0.0
    for it in range(it0, IT):
        if time.time() - T0 + 1.2 * last > 250: np.savez(sf, z=zz, it=it); log(f"PS fit {c} K{K}: at iteration {it}; rerun"); return
        t1 = time.time(); new, ll = assign(X, phis(X, zz, K)); last = time.time() - t1; ch = int((new != zz).sum()); zz = new
        log(f"PS fit {c} K{K}: iteration {it + 1}, moved {ch:,}, states in use {len(np.unique(zz)):,}, bits/feature-count {-ll / X.sum() / np.log(2):.4f}")
    np.savez(sf, z=zz, it=IT); log(f"PS fit {c} K{K}: done")
def score(c, K, tag=None):
    q = np.load(MT.fp(c, "ps_prep")); T = q["T"]; eidx = q["eidx"]
    if tag is None:
        X = q["X"]; mi = q["mi"]
        with np.load(MT.fp(c, f"ps_fit{K}")) as s: zz = s["z"].copy(); assert int(s["it"]) == IT
    else:                                                                                                  # PS2: states fitted on Kaggle
        with np.load(os.path.join(MT.OUT, "kaggle_ps2", "out", f"{c}_{tag}.npz")) as s: mi, zz, lph_ext = s["mi"].astype(np.int64), s["z"].astype(np.int64), torch.tensor(s["lph"])
        if tag in ("A1", "B50000"): assert np.array_equal(mi, q["mi"]), "member set differs from the local PS prep"
    g, uc, ci, y3, n3, cols = ctxs(c); n1, u2, n2 = g["n1"], g["u2"], g["n2"]
    stt = np.full(len(uc), -1, np.int64); stt[mi] = zz                                                    # member contexts keep their state
    ue = np.unique(eidx[(eidx >= 0)]); ue = ue[stt[ue] < 0]                                               # seen non-member eval contexts: one E-step
    erow = np.full(len(uc), -1, np.int64); erow[ue] = np.arange(len(ue)); tr = feats(erow, ci, cols, n3, len(ue)); lph = phis(X, zz, K) if tag is None else lph_ext
    for a in range(0, len(ue), 20000): stt[ue[a:a + 20000]] = assign(dense(tr, a, min(a + 20000, len(ue))), lph)[0]
    z = np.load(MT.fp(c, "data")); S = z["S"].astype(np.int64); y = S[T]; b = S[T - 1]
    pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV); b2 = u2 // VV; cb = np.bincount(b2, weights=n2, minlength=VV); db = np.bincount(b2, minlength=VV)
    c2 = MT.look(u2, n2, b * VV + y); p2 = np.where(cb[b] > 0, np.maximum(c2 - D, 0) / np.maximum(cb[b], 1) + D * db[b] / np.maximum(cb[b], 1) * pU, pU)
    sel = np.isin(ci, mi); key = stt[ci[sel]] * VV + y3[sel]          # state x word counts over member contexts
    ks, inv = np.unique(key, return_inverse=True); ns = np.bincount(inv, weights=n3[sel]); sid = ks // VV
    tot = np.bincount(sid, weights=ns, minlength=K); dis = np.bincount(sid, minlength=K)
    es = np.where(eidx >= 0, stt[np.maximum(eidx, 0)], -1); cs = np.where(es >= 0, MT.look(ks, ns, np.maximum(es, 0) * VV + y), 0)
    ok = (es >= 0) & (tot[np.maximum(es, 0)] > 0); te = tot[np.maximum(es, 0)]; de = dis[np.maximum(es, 0)]
    pS = np.where(ok, np.maximum(cs - D, 0) / np.maximum(te, 1) + D * de / np.maximum(te, 1) * p2, p2)
    np.savez(MT.fp(c, f"ps_S{K}" if tag is None else f"ps2_S{tag}"), T=T, S=pS, has_state=ok); log(f"PS score {c} K{K} {tag or ''}: eval targets with a state {ok.mean():.3f}")
TAGS = ("A1", "A4", "A16", "A64", "B50000", "B200000", "B1000000")
def curve(c, ps2=False):
    bz = np.load(MT.fp(c, "base_content")); n = len(bz["T"]); odd = np.arange(n) % 2 == 1; ev = ~odd; blk = np.arange(n) // 500; ub = np.unique(blk[ev]); g = np.random.default_rng(0)
    def mix(cols):
        M = np.stack(cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(100): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return -np.log2(M @ w), [round(float(v), 3) for v in w]
    def boot(a_, b_):
        dl = (a_ - b_)[ev]; sm = np.bincount(blk[ev], weights=dl)[ub]; nn = np.bincount(blk[ev])[ub]
        s_ = [sm[i].sum() / nn[i].sum() for i in (g.integers(0, len(ub), len(ub)) for _ in range(2000))]; return [float(np.percentile(s_, 2.5)), float(np.percentile(s_, 97.5))]
    ltc, w = mix([bz["L"], bz["Tg"], bz["C"]]); lo, _ = mix([bz["L"]]); R = {"L": float(lo[ev].mean()), "L+T+C": dict(bits=float(ltc[ev].mean()), weights=w)}; out = {}
    for K in (TAGS if ps2 else KS):
        q = np.load(MT.fp(c, f"ps2_S{K}" if ps2 else f"ps_S{K}")); assert np.array_equal(q["T"], bz["T"])
        b4, w4 = mix([bz["L"], bz["Tg"], bz["C"], q["S"]]); b2, w2 = mix([bz["L"], q["S"]]); out[K] = b4
        R[f"K{K}"] = {"L+T+C+S": dict(bits=float(b4[ev].mean()), weights=w4), "L+S": dict(bits=float(b2[ev].mean()), weights=w2)}
        log(f"PS {c} K{K}: L+S {b2[ev].mean():.4f}; L+T+C+S {b4[ev].mean():.4f} (weights {w4})")
    if ps2:
        R["H_A A64 minus A1 CI"] = boot(out["A64"], out["A1"]); R["H_B B1000000 minus B50000 CI"] = boot(out["B1000000"], out["B50000"]); R["B1000000 minus L+T+C CI"] = boot(out["B1000000"], ltc)
        log(f"PS2 {c}: L+T+C {R['L+T+C']['bits']:.4f}; H_A interval {R['H_A A64 minus A1 CI']}; H_B interval {R['H_B B1000000 minus B50000 CI']}")
    else:
        R["H1 S16384 minus S256 CI"] = boot(out[16384], out[256]); R["H2 S16384 minus L+T+C CI"] = boot(out[16384], ltc)
        log(f"PS {c}: L {R['L']:.4f}; L+T+C {R['L+T+C']['bits']:.4f}; H1 interval {R['H1 S16384 minus S256 CI']}; H2 interval {R['H2 S16384 minus L+T+C CI']}")
    f = os.path.join(HERE, "sieve_mts2.json" if ps2 else "sieve_mts.json"); A = json.load(open(f)) if os.path.exists(f) else {}; A[c] = R; json.dump(A, open(f, "w"), indent=1)
if __name__ == "__main__":
    cmd, c = sys.argv[1], sys.argv[2]
    if cmd == "ps2":                                                                                      # score every Kaggle tag, then the curve
        for t in TAGS: score(c, 256, t)
        curve(c, ps2=True)
    else: dict(prep=prep, curve=curve)[cmd](c) if cmd in ("prep", "curve") else dict(fit=fit, score=score)[cmd](c, int(sys.argv[3]))
