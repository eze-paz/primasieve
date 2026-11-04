"""SR2 (sieve_lang_prereg.md): word representations from training + library text.
cooc <topic|syntax>  co-occurrence counts (resumable, one lag / offset per step) into a dense uint32 matrix
svd <topic|syntax>   PPMI (context ^0.75) and a 150-dimension randomised SVD (torch, seed 0)
nmf                  100 non-negative parts of the topic PPMI (60 multiplicative updates), named by their top words
trig <svd|svdr>      association table from the topic SVD: association(j, w) = (u_j sqrt s) . (u_w sqrt s); each word's
                     100 strongest partners by count x association; "svdr" adds rare-word vectors (R3)
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_vec.py <mode> [name]"""
import os, sys, json, time
import numpy as np
NC, K_SVD, K_NMF, ROWMIN = 10_000, 150, 100, 20
def base(F, P):
    import sieve_fast as FS
    d = os.path.join(FS.IDX, "vec"); os.makedirs(d, exist_ok=True); C = P.ccount(); o = np.argsort(-C, kind="stable")
    ok = (C >= ROWMIN); ok[0] = False; ok[F.Vt - 1:] = False; rid = np.full(F.Vt, -1, np.int64); rows = np.nonzero(ok)[0]; rid[rows] = np.arange(len(rows))
    tid = np.full(F.Vt, -1, np.int64); top = [w for w in o if w != 0 and w < F.Vt - 1]; tid[np.array(top[100:100 + NC])] = np.arange(NC)
    sid = np.full(F.Vt, -1, np.int64); sid[np.array(top[:2500])] = np.arange(2500)
    return d, C, rid, rows, tid, sid, np.array(top)
def jobs(name): return [("f", d) for d in range(1, 21)] + [("b", d) for d in range(1, 21)] if name == "topic" else [("o", o) for o in (-2, -1, 1, 2)]
def cooc(F, P, name):
    d, C, rid, rows, tid, sid, _ = base(F, P); S = P.corpus(); f = os.path.join(d, f"{name}_cnt.npy"); fj = os.path.join(d, f"{name}_done.json")
    M = np.lib.format.open_memmap(f, mode="r+" if os.path.exists(f) else "w+", dtype=np.uint32, shape=(len(rows), NC)); done = json.load(open(fj)) if os.path.exists(fj) else []; t0 = time.time()
    for kd, lag in jobs(name):
        if [kd, lag] in done: continue
        if time.time() - t0 > 200: break
        if kd == "f": r, c = rid[S[:-lag]], tid[S[lag:]]
        elif kd == "b": r, c = rid[S[lag:]], tid[S[:-lag]]
        else: a, b = (S[:len(S) - lag], S[lag:]) if lag > 0 else (S[-lag:], S[:len(S) + lag]); r, c = rid[a], sid[b]; c = np.where(c >= 0, c + 2500 * (0, 1, None, 2, 3)[lag + 2], -1)
        ok = (r >= 0) & (c >= 0); uk, n = np.unique(r[ok] * NC + c[ok], return_counts=True); M.reshape(-1)[uk] += n.astype(np.uint32); M.flush(); done.append([kd, lag]); json.dump(done, open(fj, "w"))
        print(f"   {name} {kd}{lag}: {len(uk):,} cells ({time.time() - t0:.0f} s)", flush=True)
    F.log(f"SR2 cooc {name}: {len(done)} of {len(jobs(name))} steps done")
def ppmi(M):
    M = M.astype(np.float64); N = M.sum(); r = M.sum(1, keepdims=True); c = M.sum(0) ** 0.75; pc = c / c.sum(); X = np.zeros(M.shape, np.float32)
    for a in range(0, M.shape[0], 4000): B = M[a:a + 4000]; X[a:a + 4000] = np.maximum(0, np.log(np.maximum(B, 1e-30) / (np.maximum(r[a:a + 4000], 1) * pc[None, :]))) * (B > 0)
    return X
def svd(F, P, name):
    import torch
    d = base(F, P)[0]; X = ppmi(np.load(os.path.join(d, f"{name}_cnt.npy"), mmap_mode="r")); torch.manual_seed(0); t0 = time.time()
    U, S_, V = torch.svd_lowrank(torch.from_numpy(X), q=K_SVD, niter=4); np.savez(os.path.join(d, f"{name}_svd.npz"), U=U.numpy(), S=S_.numpy(), V=V.numpy())
    F.log(f"SR2 svd {name}: PPMI nonzero {np.mean(X > 0):.4f}; top singular values {S_[:5].numpy().round(1).tolist()} ({time.time() - t0:.0f} s)")
def nmf(F, P):
    import torch
    d, C, rid, rows, tid, sid, top = base(F, P); X = torch.from_numpy(ppmi(np.load(os.path.join(d, "topic_cnt.npy"), mmap_mode="r"))); g = torch.Generator().manual_seed(0); t0 = time.time()
    W = torch.rand(X.shape[0], K_NMF, generator=g) + 0.01; H = torch.rand(K_NMF, X.shape[1], generator=g) + 0.01
    for it in range(60):
        H *= (W.T @ X) / (W.T @ W @ H + 1e-9); W *= (X @ H.T) / (W @ (H @ H.T) + 1e-9)
        if time.time() - t0 > 220: break
    err = float(((X - W @ H) ** 2).sum() / (X ** 2).sum()); np.savez(os.path.join(d, "topic_nmf.npz"), W=W.numpy(), H=H.numpy())
    words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; ctxw = top[100:100 + NC]; Hn = H.numpy()
    names = [" / ".join(words[ctxw[j] - 1] for j in np.argsort(-Hn[k])[:5]) for k in range(K_NMF)]; json.dump(names, open(os.path.join(d, "topic_nmf_names.json"), "w"), indent=0)
    F.log(f"SR2 nmf: {it + 1} iterations, relative error {err:.4f} ({time.time() - t0:.0f} s); parts e.g.: " + " | ".join(names[:6]))
def vectors(F, P, rare):
    """(Vt, k) topic vectors u sqrt(s); with rare: words < 20 uses from dictionary relatives, else 4-letter suffix mates"""
    d, C, rid, rows, tid, sid, top = base(F, P); z = np.load(os.path.join(d, "topic_svd.npz")); X = np.zeros((F.Vt, K_SVD), np.float32); X[rows] = z["U"] * np.sqrt(z["S"])[None, :]; has = np.zeros(F.Vt, bool); has[rows] = True
    if rare:
        import sieve_dict as SD; SD.load(F); words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; suf = {}
        for w in rows: suf.setdefault(words[w - 1][-4:], []).append(w)
        n1 = n2 = 0; Xr = X.copy()
        for w in range(1, F.Vt - 1):
            if has[w] or C[w] == 0: continue
            rel = np.concatenate([SD.related(r, w) for r in ("syn", "hyper")]); rel = rel[has[rel]] if len(rel) else rel
            if len(rel): Xr[w] = X[rel].mean(0); n1 += 1; continue
            m = suf.get(words[w - 1][-4:], [])
            if len(words[w - 1]) >= 6 and len(m) >= 3: Xr[w] = X[np.array(m)].mean(0); n2 += 1
        F.log(f"SR2 rare vectors: {n1:,} from dictionary relatives, {n2:,} from suffix mates"); X = Xr
    return X
def trig(F, P, tab):
    import torch, sieve_fast as FS
    X = vectors(F, P, tab == "svdr"); C = P.ccount().astype(np.float32); has = np.abs(X).sum(1) > 0; ids = np.nonzero(has)[0]; Xt = torch.from_numpy(X[ids]); Ct = torch.from_numpy(C[ids]); t0 = time.time()
    A, B, Pm = [], [], []
    for a in range(0, len(ids), 2000):
        s_ = Xt[a:a + 2000] @ Xt.T; s_[torch.arange(s_.shape[0]), torch.arange(a, a + s_.shape[0])] = 0; sc = torch.where(s_ > 0, s_ * Ct[None, :], torch.zeros(()))
        v, j = torch.topk(sc, 100, dim=1); keep = v > 0; rr = torch.arange(a, a + s_.shape[0])[:, None].expand_as(j)
        A.append(ids[rr[keep].numpy()]); B.append(ids[j[keep].numpy()]); Pm.append(s_.gather(1, j)[keep].numpy())
    a_, b_, p_ = np.concatenate(A), np.concatenate(B), np.concatenate(Pm); o = np.lexsort((-p_, a_)); a_, b_, p_ = a_[o], b_[o], p_[o]
    ptr = np.r_[0, np.cumsum(np.bincount(a_, minlength=F.Vt))]; np.savez(os.path.join(FS.IDX, f"sg_trig_{tab}.npz"), ptr=ptr, tgt=b_, pmi=p_.astype(np.float32))
    F.log(f"SR2 trig {tab}: {len(a_):,} pairs over {int((np.diff(ptr) > 0).sum()):,} words ({time.time() - t0:.0f} s)")
def books(F):
    """book id of every corpus position (training books 0..358, library books 1000+), boundaries included"""
    z = np.load(os.path.join(F.SC.LX, "lx_tokens.npz")); dd = np.load(os.path.join(F.SC.LX, "lx_docs.npz")); L = np.load(os.path.join(F.SC.LX, "lx_library.npz")); lb = np.load(os.path.join(F.SC.LX, "lx_library_books.npz"))
    return np.r_[F.mkb(z["tr"], z["trs"], dd["trb"]), F.mkb(L["lib"], L["libs"], lb["book"] + 1000)]
def filt(F, P):
    """RD4: the second-order table filtered by book dispersion (>= 3 books with a direct co-occurrence within 50 tokens),
    ranked by a lower confidence bound on direct PMI; pairs without that support kept only if WordNet relates them"""
    import sieve_fast as FS, sieve_sg as SG, sieve_dict as SD
    t0 = time.time(); S = P.corpus(); B = books(F); assert len(B) == len(S), (len(B), len(S)); ptr, tgt, pmi = SG.trig_rows(F, P, "svd"); a = np.repeat(np.arange(F.Vt), np.diff(ptr))
    key = a * np.int64(F.Vt) + tgt; o = np.argsort(key); ks = key[o]; fs = os.path.join(FS.IDX, "vec", "rd4_state.npz")
    if os.path.exists(fs): z = np.load(fs); ndir, ub, lag0 = z["ndir"], [z["ub"]], int(z["lag"])
    else: ndir, ub, lag0 = np.zeros(len(ks)), [np.zeros(0, np.int64)], 0
    for lag in range(lag0 + 1, 51):                                                                    # resumable: state saved every 5 lags
        q = S[:-lag] * np.int64(F.Vt) + S[lag:]; i = np.minimum(np.searchsorted(ks, q), len(ks) - 1); h = (ks[i] == q) & (B[:-lag] == B[lag:]); ih = i[h]
        ndir += np.bincount(ih, minlength=len(ks)); ub.append(np.unique(ih.astype(np.int64) * 2000 + (B[:-lag][h] % 2000)))
        if lag % 5 == 0 or lag == 50:
            ub = [np.unique(np.concatenate(ub))]; np.savez(fs, ndir=ndir, ub=ub[0], lag=lag); print(f"   lag {lag} ({time.time() - t0:.0f} s)", flush=True)
            if time.time() - t0 > 200 and lag < 50: F.log(f"RD4 filter: {lag} of 50 lags; rerun"); return
    N = float(len(S)); del S, B; u = np.concatenate(ub); del ub; nb = np.bincount(u // 2000, minlength=len(ks)); del u; C = P.ccount().astype(float)   # ub is already unique; free memory first
    A_, W_ = ks // F.Vt, ks % F.Vt; lb = np.log(np.maximum(ndir - 1.96 * np.sqrt(ndir), 0.5) * N / (C[A_] * C[W_] * 50.0)); disp = (nb >= 3) & (lb > 0)
    DZ = SD.load(F); rk = []
    for r in ("syn", "hyper"):
        pr, ids = DZ[f"{r}_ptr"], DZ[f"{r}_ids"]; rk.append(np.repeat(np.arange(len(pr) - 1), np.diff(pr)).astype(np.int64) * F.Vt + ids)
    rk = np.unique(np.concatenate(rk)); i = np.minimum(np.searchsorted(rk, ks), len(rk) - 1); wn = rk[i] == ks                          # WordNet relation, vectorised
    val = np.where(disp, lb, pmi[o]); keep = disp | wn; A_, W_, val = A_[keep], W_[keep], val[keep]
    oo = np.lexsort((-val, A_)); A_, W_, val = A_[oo], W_[oo], val[oo]; first = np.r_[True, A_[1:] != A_[:-1]]; g = np.cumsum(first) - 1; rank = np.arange(len(A_)) - np.nonzero(first)[0][g]; k2 = rank < 100
    A_, W_, val = A_[k2], W_[k2], val[k2]; ptr2 = np.r_[0, np.cumsum(np.bincount(A_, minlength=F.Vt))]
    np.savez(os.path.join(FS.IDX, "sg_trig_svdf.npz"), ptr=ptr2, tgt=W_, pmi=val.astype(np.float32))
    F.log(f"RD4 filter: {len(ks):,} second-order pairs; kept by >= 3 books {int(disp.sum()):,}, by WordNet only {int((wn & ~disp).sum()):,}; table svdf {len(A_):,} pairs over {int((np.diff(ptr2) > 0).sum()):,} words ({time.time() - t0:.0f} s)")
def main(argv):
    import sieve_attn2 as SA2; F, P, P3, O = SA2.setup(); m = argv[1]
    if m == "cooc": cooc(F, P, argv[2])
    elif m == "svd": svd(F, P, argv[2])
    elif m == "nmf": nmf(F, P)
    elif m == "trig": trig(F, P, argv[2])
    elif m == "filter": filt(F, P)
if __name__ == "__main__": main(sys.argv[:])
