"""PH1-PH5 (sieve_lang_prereg.md): phrasing and long-range link components on the MT data.
K = skip n-gram P(y | last content word before t-1, w[t-1]); X = the trigram extended to an 8-gram (hashed contexts);
G = distance pairs d=3..12; R = agreement memory (last pronoun x number of the last noun); P / P0 = pending words with /
without removal-on-use. Writes mtest/<c>_ph_<mode>.npz (T and the components at sieve_mtest's eval positions); sieve_mtest
eval mixes them. Run: py -3.12 -I sieve_mtph.py count <c> ; MT_EVAL=content|all py -3.12 -I sieve_mtph.py comp <c>"""
import os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
T0 = time.time(); V, VV, D, UNK = MT.V, MT.VV, MT.D, MT.UNK; M64 = np.uint64(0x9E3779B97F4A7C15); NG = 3_000_000; DS = range(3, 13)
NORD = range(4, 7)
PRON = "he she it they i you we his her him them its their".split()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def load(c):
    z = np.load(MT.fp(c, "data")); S = z["S"].astype(np.int64); return z, S, z["D"], int(z["ntr"]), (S > 100) & (S <= V)
def c1of(S, Dc, kp, t):
    """the last content word before t-1, same document (0 = none)"""
    i = np.searchsorted(kp, t - 1) - 1; ok = (i >= 0) & (Dc[kp[np.maximum(i, 0)]] == Dc[t]); return np.where(ok, S[kp[np.maximum(i, 0)]], 0)
def hashes(S, t, n):
    """64-bit hash of the n-1 words before t"""
    h = np.zeros(len(t), np.uint64)
    with np.errstate(over="ignore"):
        for j in range(1, n): h = h * M64 + S[t - j].astype(np.uint64) + np.uint64(1)
    return h
def regs(S, Dc, vw, t, nounpl):
    """agreement context: last pronoun (distance >= 3, within 50) x number of the last noun (distance >= 3, within 30)"""
    pid = np.full(VV, -1); wi = {w: i for i, w in enumerate(vw)}
    for k, p in enumerate(PRON):
        if p in wi: pid[wi[p]] = k
    pp = np.nonzero(pid[S] >= 0)[0]; npos = np.nonzero(nounpl[S] >= 0)[0]
    i = np.searchsorted(pp, t - 2) - 1; okp = (i >= 0) & (t - pp[np.maximum(i, 0)] <= 50) & (Dc[pp[np.maximum(i, 0)]] == Dc[t]); pr = np.where(okp, pid[S[pp[np.maximum(i, 0)]]], len(PRON))
    j = np.searchsorted(npos, t - 2) - 1; okn = (j >= 0) & (t - npos[np.maximum(j, 0)] <= 30) & (Dc[npos[np.maximum(j, 0)]] == Dc[t]); nm = np.where(okn, nounpl[S[npos[np.maximum(j, 0)]]], 2)
    return pr * 3 + nm
def nouns(vw):
    import sieve_dict as SD
    syn, index, exc = SD.parse(); out = np.full(VV, -1)
    for i in range(101, V + 1):
        w = str(vw[i]); b = [bse for p, bse in SD.base_forms(w, index, exc) if p == "n"]
        if b: out[i] = int(b[0] != w and w.endswith("s"))
    return out
def count(c):
    z, S, Dc, ntr, con = load(c); kp = np.nonzero(con[:ntr])[0]; t = np.arange(8, ntr); t = t[S[t] != 0]; y = S[t]; out = {}
    c1 = c1of(S, Dc, kp, t); out["k2u"], out["k2n"] = np.unique((c1 * VV + S[t - 1]) * VV + y, return_counts=True); out["k1u"], out["k1n"] = np.unique(c1 * VV + y, return_counts=True); log(f"PH count {c}: skip n-grams")
    for n in NORD:
        h = hashes(S, t, n); ux, idx = np.unique(h, return_inverse=True); up, npr = np.unique(idx.astype(np.int64) * VV + y, return_counts=True)
        out[f"x{n}u"], out[f"x{n}c"], out[f"x{n}d"], out[f"x{n}pu"], out[f"x{n}pn"] = ux, np.bincount(idx), np.bincount(up // VV, minlength=len(ux)), up, npr
    log(f"PH count {c}: orders {list(NORD)}"); np.savez(MT.fp(c, "phcount" + ("" if NORD[0] == 4 else "b")), **out); out = {}
def count2(c):
    z, S, Dc, ntr, con = load(c); t = np.arange(8, ntr); t = t[S[t] != 0]; y = S[t]; out = {}
    g = np.random.default_rng(3); tg = np.sort(g.choice(t, NG, replace=False))
    for d in DS:
        ok = Dc[tg - d] == Dc[tg]; out[f"g{d}u"], out[f"g{d}n"] = np.unique(S[tg[ok] - d] * VV + S[tg[ok]], return_counts=True)
    npl = nouns(z["vw"]); r = regs(S, Dc, z["vw"], t, npl); out["R"] = np.bincount(r * VV + y, minlength=(len(PRON) + 1) * 3 * VV).reshape(-1, VV); out["npl"] = npl
    np.savez(MT.fp(c, "phcount2"), **out); log(f"PH count {c}: distance pairs, agreement memory; saved")
def comp(c):
    z, S, Dc, ntr, con = load(c); T = MT.targets(S, ntr, con); y = S[T]; q = dict(np.load(MT.fp(c, "phcount"))); q.update(np.load(MT.fp(c, "phcount2"))); q.update(np.load(MT.fp(c, "phcountb"))); g = np.load(MT.fp(c, "ngram")); n1 = g["n1"]
    look = MT.look; pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV); kp = np.nonzero(con)[0]
    u2, n2 = g["u2"], g["n2"]; b2 = u2 // VV; cb = np.bincount(b2, weights=n2, minlength=VV); db = np.bincount(b2, minlength=VV); b = S[T - 1]; a = S[T - 2]          # L, as sieve_mtest
    c2 = look(u2, n2, b * VV + y); p = np.where(cb[b] > 0, np.maximum(c2 - D, 0) / np.maximum(cb[b], 1) + D * db[b] / np.maximum(cb[b], 1) * pU, pU)
    u3, n3 = g["u3"], g["n3"]; x3 = u3 // VV; ux, st = np.unique(x3, return_index=True); cx = np.add.reduceat(n3, st); dx = np.diff(np.r_[st, len(u3)]); ab = a * VV + b
    cab = look(ux, cx, ab); p = np.where(cab > 0, np.maximum(look(u3, n3, ab * VV + y) - D, 0) / np.maximum(cab, 1) + D * look(ux, dx, ab) / np.maximum(cab, 1) * p, p)
    for n in range(4, 9):                                                                                # PH2: orders 4..8
        h = hashes(S, T, n); xu = q[f"x{n}u"]; i = np.minimum(np.searchsorted(xu, h), len(xu) - 1); f = xu[i] == h; cc = np.where(f, q[f"x{n}c"][i], 0)
        pc = np.where(f, look(q[f"x{n}pu"], q[f"x{n}pn"], i.astype(np.int64) * VV + y), 0); p = np.where(cc > 0, np.maximum(pc - D, 0) / np.maximum(cc, 1) + D * q[f"x{n}d"][i] / np.maximum(cc, 1) * p, p)
    X = p
    c1 = c1of(S, Dc, kp, T); k1u, k1n = q["k1u"], q["k1n"]; r1 = k1u // VV; c1t = np.bincount(r1, weights=k1n, minlength=VV); d1 = np.bincount(r1, minlength=VV)    # PH1
    pk1 = np.where(c1t[c1] > 0, np.maximum(look(k1u, k1n, c1 * VV + y) - D, 0) / np.maximum(c1t[c1], 1) + D * d1[c1] / np.maximum(c1t[c1], 1) * pU, pU)
    k2u, k2n = q["k2u"], q["k2n"]; x2 = k2u // VV; uk, sk = np.unique(x2, return_index=True); ck = np.add.reduceat(k2n, sk); dk = np.diff(np.r_[sk, len(k2u)]); cx2 = c1 * VV + b
    cc = look(uk, ck, cx2); K = np.where(cc > 0, np.maximum(look(k2u, k2n, cx2 * VV + y) - D, 0) / np.maximum(cc, 1) + D * look(uk, dk, cx2) / np.maximum(cc, 1) * pk1, pk1)
    Gs = np.zeros(len(T)); ng = np.zeros(len(T))                                                          # PH3
    for d in DS:
        gu, gn = q[f"g{d}u"], q[f"g{d}n"]; ok = Dc[T - d] == Dc[T]; w = S[T - d]; rt = np.bincount(gu // VV, weights=gn, minlength=VV)
        pd = (look(gu, gn, w * VV + y) + pU) / (rt[w] + 1); Gs += np.where(ok, pd, 0); ng += ok
    G = np.where(ng > 0, Gs / np.maximum(ng, 1), pU)
    Rt = q["R"]; r = regs(S, Dc, z["vw"], T, q["npl"]); R = (Rt[r, y] + pU) / (Rt.sum(1)[r] + 1)                                                 # PH4
    tg = np.load(MT.fp(c, "trig")); tu, tn = tg["u"], tg["n"]; cw_ = tu // VV; yw = tu % VV; rc = np.bincount(cw_, weights=tn, minlength=VV)            # PH5
    uc = np.bincount(S[:ntr][con[:ntr]], minlength=VV).astype(float); uc /= uc.sum(); keep = tn >= 5
    lift = np.where(keep, (tn / np.maximum(rc[cw_], 1)) / np.maximum(uc[yw], 1e-12), 0); sel = np.nonzero(keep & (lift > 1))[0]; o = sel[np.lexsort((-lift[sel], cw_[sel]))]
    first = np.r_[True, cw_[o][1:] != cw_[o][:-1]]; rank = np.arange(len(o)) - np.maximum.accumulate(np.where(first, np.arange(len(o)), 0)); o = o[rank < 20]
    PT = np.zeros((VV, 20), np.int64); PW = np.zeros((VV, 20)); rk = (np.arange(len(o)) - np.maximum.accumulate(np.where(np.r_[True, cw_[o][1:] != cw_[o][:-1]], np.arange(len(o)), 0)))
    PT[cw_[o], rk] = yw[o]; PW[cw_[o], rk] = np.log(lift[o])
    ckey = Dc[kp].astype(np.int64) * VV + S[kp]; cmb = np.sort((ckey << 26) | kp); num = np.zeros(len(T)); den = np.zeros(len(T)); num0 = np.zeros(len(T)); den0 = np.zeros(len(T))
    k = np.searchsorted(kp, T - 2); kb = np.searchsorted(kp, np.searchsorted(Dc, Dc[T]))
    for j in range(MT.W):
        ix = k - 1 - j; okr = ix >= kb
        if not okr.any(): continue
        rr = np.nonzero(okr)[0]; pc = kp[ix[okr]]; cw = S[pc]; cand = PT[cw]; wt = PW[cw]; hasw = wt > 0
        key = (Dc[T[rr]].astype(np.int64) * VV)[:, None] + cand; seen = np.searchsorted(cmb, (key << 26) | T[rr][:, None]) - np.searchsorted(cmb, (key << 26) | (pc + 1)[:, None])   # used after c, before t
        live = hasw & (seen == 0); hit = cand == y[rr][:, None]
        num[rr] += (wt * (live & hit)).sum(1); den[rr] += (wt * live).sum(1); num0[rr] += (wt * hit).sum(1); den0[rr] += (wt * hasw).sum(1)
    P = num / np.maximum(den, 1e-12); P0 = num0 / np.maximum(den0, 1e-12)
    np.savez(MT.fp(c, "ph_" + MT.MODE), T=T, X=X, K=K, G=G, R=R, P=P, P0=P0)
    log(f"PH comp {c} {MT.MODE}: saved; pending set live share {float(den.sum() / max(den0.sum(), 1e-12)):.4f}")
if __name__ == "__main__":
    if sys.argv[1] == "countb": NORD = range(7, 9); sys.argv[1] = "count"
    dict(count=count, count2=count2, comp=comp)[sys.argv[1]](sys.argv[2])
