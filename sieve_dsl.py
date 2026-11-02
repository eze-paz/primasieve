"""SY (sieve_lang_prereg.md): Sieve generates its own component families from a small expression language.
Atoms: Gather(joint context, source, span 1) = the count components; Gather(BAG of recent tokens (last B, corpus count
<= thr), library | training+library, span) = trigger-like; recency, graded, long-match. Operators: Factor(A, B) (form
from A, word within form from B; A, B any pool members, nesting allowed) and Gate(c) ((n/(n+T))^g). Description length
per the prereg; every fitted number (1/2) log2 n. Generator: gradient at zero weight for every unused atom, factor pair
and ungated member; the 3 best of each kind are fitted; the best that pays is added; stop when none pays.
Start: SW2's 25 components (no triggers, factors or gates). Run (each resumable, < 5 min):
  py -3.12 -W ignore sieve_dsl.py bags fit30|eval ; search ; rw ; eval"""
import os, sys, json, math, time, hashlib
import numpy as np
import sieve_fs2 as F
T0 = time.time(); CX = "fit30"; CK = os.path.join(F.HERE, "sieve_dsl_fit30.json")
BS_, THR_, SPAN_, SRC_ = (10, 50, 200, 1000), (100, 1000), (1, 2, 5, 10, 50), ("library", "trainlib")
BAGS = [f"bag_{src}_{B}_{thr}_{sp}" for src in SRC_ for B in BS_ for thr in THR_ for sp in SPAN_]
BASE = F.names_of("count") + F.names_of("book") + F.names_of("recency") + [f"graded_id_{w}" for w in F.GW] + F.names_of("long")
def atom_bits(n):
    p = n.split("_"); k = math.log2(5)
    if p[0] == "count": return k + math.log2(21) + math.log2(4)
    if p[0] == "bag": return k + math.log2(len(BS_)) + math.log2(len(THR_)) + math.log2(len(SRC_)) + math.log2(len(SPAN_))
    if p[0] == "graded": return k + math.log2(len(F.GW))
    if p[0] == "long": return k + 1
    return k
def desc(n):
    if n.startswith("F("): a, b = split_fac(n); return f"Factor[{desc(a)} | {desc(b)}]"
    if n.startswith("bag_"): _, src, B, thr, sp = n.split("_"); return f"Gather(bag of last {B} with count <= {thr}, {src}, span {sp})"
    return F.desc(n)
def split_fac(n):
    s = n[2:-1]; d = 0
    for i, ch in enumerate(s):
        d += ch == "("; d -= ch == ")"
        if ch == "," and d == 0: return s[:i], s[i + 1:]
def fname(cx, n): return os.path.join(F.CD, f"{cx}_dsl_{hashlib.md5(n.encode()).hexdigest()[:16]}.npz") if n.startswith("F(") else None
# ---------------- bag atoms ----------------
def bag_pass(cx, B, src):
    out = {n: os.path.join(F.CD, f"{cx}_{n}.npz") for n in BAGS if n.split("_")[1] == src and int(n.split("_")[2]) == B}
    if all(os.path.exists(f) for f in out.values()): return
    S = F.lib() if src == "library" else np.r_[F.tr, F.lib()]; cnt = np.bincount(S, minlength=F.Vt); order = np.argsort(S, kind="stable"); st = np.r_[0, np.cumsum(cnt)]
    s, T, _ = F.ctx(cx); rare = (cnt > 0) & (cnt <= max(THR_)); rare[0] = False
    R = [np.unique(w[rare[w]]) for w in (s[max(0, t - B):t] for t in T)]; need = sorted(set(np.concatenate(R).tolist()))
    wanted = {}
    for t, rr in zip(T, R):
        for r in rr.tolist(): wanted.setdefault(r, set()).add(int(s[t]))
    stat = {}
    for r in need:
        p = order[st[r]:st[r + 1]]; idx = p[:, None] + np.arange(1, max(SPAN_) + 1); idx = idx[(idx < len(S)).all(1)]; tok = S[idx]; ys = np.array(sorted(wanted[r])); stat[r] = {}
        for sp in SPAN_:
            tw = tok[:, :sp].ravel(); u, c = np.unique(tw, return_counts=True); j = np.clip(np.searchsorted(u, ys), 0, len(u) - 1)
            stat[r][sp] = (len(tw), np.bincount(F.FORM[tw], minlength=F.NF), dict(zip(ys.tolist(), np.where(u[j] == ys, c[j], 0).tolist())))
    y = s[T]
    for thr in THR_:
        for sp in SPAN_:
            n_ = len(T); ne = np.zeros(n_, bool); P = np.zeros(n_); N = np.zeros(n_); TD = np.zeros(n_); Q = np.zeros((n_, F.NF), np.float32)
            for i, (t, rr) in enumerate(zip(T, R)):
                rr = [r for r in rr.tolist() if cnt[r] <= thr]
                if not rr: continue
                tot = sum(stat[r][sp][0] for r in rr); ne[i] = True; P[i] = sum(stat[r][sp][2].get(int(y[i]), 0) for r in rr) / tot; N[i] = tot; TD[i] = len(rr); Q[i] = sum(stat[r][sp][1] for r in rr) / tot
            assert np.all(np.abs(Q[ne].sum(1) - 1) <= 1e-4) and np.all(Q[ne, F.FORM[y[ne]]] >= P[ne] - 1e-4)
            np.savez(out[f"bag_{src}_{B}_{thr}_{sp}"], ne=ne, P=P, N=N, TD=TD, Q=Q.astype(np.float16))
    F.log(f"{cx}: bags B={B} {src} cached")
# ---------------- evaluation of any expression ----------------
def comp(cx, n, q=False):
    """(ne, P, N, TD[, Q]) of an expression"""
    if not n.startswith("F("):
        if n.startswith("bag_") and not os.path.exists(os.path.join(F.CD, f"{cx}_{n}.npz")): bag_pass(cx, int(n.split("_")[2]), n.split("_")[1])
        r = F.load(cx, n, q); F.MEMO.pop((cx, n, q), None); return r
    f = fname(cx, n)
    if not os.path.exists(f):
        a, b = split_fac(n); neA, PA, NA, TA, QA = comp(cx, a, True); neB, PB, NB, TB, QB = comp(cx, b, True)
        ne, P, Q = factor(neA, QA, neB, PB, QB, cx); np.savez(f, ne=ne, P=P, N=NB, TD=TB, Q=Q.astype(np.float16))
    z = np.load(f); return (z["ne"], z["P"], z["N"], z["TD"]) + ((z["Q"].astype(np.float32),) if q else ())
def factor(neA, QA, neB, PB, QB, cx, onlyP=False):
    s, T, _ = F.ctx(cx); fy = F.FORM[s[T]]; ix = np.arange(len(T)); cov = QB > 0; Z = (QA * cov).sum(1); ne = neA & neB & (Z > 0); qb = QB[ix, fy]
    P = np.minimum(np.where(ne & (qb > 0), QA[ix, fy] * PB / np.where(qb > 0, qb, 1) / np.where(Z > 0, Z, 1), 0.0), 1.0)
    return (ne, P) if onlyP else (ne, P, np.where(ne[:, None], QA * cov / np.where(Z > 0, Z, 1)[:, None], 0))
# ---------------- the mixture with gates ----------------
def lgate(c): return np.where(c[0], np.log(np.maximum(c[2], 1) / (np.maximum(c[2], 1) + np.maximum(c[3], 1))), 0)
def bits(th, ga, P, M, LG):
    lw = th[:, None] + ga[:, None] * LG; w = np.exp(lw - lw.max(0)) * M; num = (w * P).sum(0); den = w.sum(0)
    d = (w * P / num - w / den) / math.log(2); return -(np.log2(num) - np.log2(den)).sum(), -d.sum(1), -(d * LG).sum(1)
def fit(th, ga, act, P, M, LG, iters=150):
    b, gt, gg = bits(th, ga, P, M, LG); lr = 1.0; n = P.shape[1]
    for _ in range(iters):
        while lr > 1e-9:
            t2 = th - lr * gt / n; g2 = ga - lr * gg * act / n; r = bits(t2, g2, P, M, LG)
            if r[0] < b - 1e-9: th, ga, (b, gt, gg) = t2, g2, r; lr *= 1.5; break
            lr *= 0.5
        else: break
    return th, ga, b
def state():
    if not os.path.exists(CK):
        sw2 = json.load(open(os.path.join(F.HERE, "sieve_free_fit30_sw2.json")))
        json.dump(dict(pool=sw2["sel"], th=sw2["th"], ga=[0.0] * (len(sw2["sel"]) + 1), act=[], rejected=[], log=[]), open(CK, "w"))
    return json.load(open(CK))
def rows(cx, pool):
    C = [comp(cx, n) for n in pool]; n = len(C[0][0])
    return (np.vstack([np.full(n, 1 / F.Vt)] + [c[1] for c in C]), np.vstack([np.ones(n, bool)] + [c[0] for c in C]), np.vstack([np.zeros(n)] + [lgate(c) for c in C]))
mode = sys.argv[1] if len(sys.argv) > 1 else "search"
if mode == "bags":
    cx = sys.argv[2]
    for B in BS_:
        for src in SRC_:
            if time.time() - T0 > 200: F.log("   time budget: rerun to continue"); sys.exit(0)
            bag_pass(cx, B, src)
    F.log(f"{cx}: all bag atoms cached")
elif mode == "search":
    st = state(); pool = st["pool"]; P, M, LG = rows(CX, pool); n = P.shape[1]; half = 0.5 * math.log2(n)
    th, ga = np.array(st["th"]), np.array(st["ga"]); act = np.zeros(len(pool) + 1); act[st["act"]] = 1; cur = bits(th, ga, P, M, LG)[0]
    F.log(f"SY: pool {len(pool)}, {int(act.sum())} gates; fit {cur / n:.4f} bits/word")
    QF = {}
    def qa(nm):
        if nm not in QF: QF[nm] = comp(CX, nm, True)[4].astype(np.float16)
        return QF[nm]
    while True:
        lw = th[:, None] + ga[:, None] * LG; w = np.exp(lw - lw.max(0)) * M; num = (w * P).sum(0); den = w.sum(0); rej = set(st["rejected"])
        cands = []                                                                                    # (kind, name or index, gradient, bits)
        for nm in BASE + BAGS:
            if nm in pool or nm in rej: continue
            c = comp(CX, nm); cands.append(("atom", nm, (c[0] * (c[1] / num - 1 / den)).sum(), math.log2(3) + atom_bits(nm) + half))
        for k in range(1, len(pool) + 1):
            if not act[k] and f"gate:{pool[k - 1]}" not in rej:
                g_ = (w[k] * P[k] / num - w[k] / den) @ LG[k]; cands.append(("gate", k, abs(g_), math.log2(3) + math.log2(len(pool)) + half))
        if time.time() - T0 > 150: st.update(th=th.tolist(), ga=ga.tolist()); json.dump(st, open(CK, "w")); F.log("   time budget (before factor pairs): rerun"); sys.exit(0)
        for a in pool:
            for b in pool:
                nm = f"F({a},{b})"
                if a == b or nm in pool or nm in rej: continue
                pf = os.path.join(F.CD, f"{CX}_dslpair_{hashlib.md5(nm.encode()).hexdigest()[:16]}.npz")   # pair values cached across runs (time)
                if os.path.exists(pf): z_ = np.load(pf); ne_, P_ = z_["ne"], z_["P"]
                else:
                    ca, cb = comp(CX, a), comp(CX, b); ne_, P_ = factor(ca[0], qa(a).astype(np.float32), cb[0], cb[1], qa(b).astype(np.float32), CX, onlyP=True); np.savez(pf, ne=ne_, P=P_.astype(np.float32))
                cands.append(("factor", nm, (ne_ * (P_ / num - 1 / den)).sum(), math.log2(3) + 2 * math.log2(len(pool)) + half))
                if time.time() - T0 > 230: st.update(th=th.tolist(), ga=ga.tolist()); json.dump(st, open(CK, "w")); F.log("   time budget (factor pairs): rerun"); sys.exit(0)
        best = None; tried = 0
        for kind in ("atom", "factor", "gate"):
            for kd, x, g_, bb in sorted((c for c in cands if c[0] == kind and c[2] > 0), key=lambda c: -c[2])[:3]:
                if time.time() - T0 > 260: break
                if kd == "gate":
                    a2 = act.copy(); a2[x] = 1; t2, g2, b2 = fit(th, ga, a2, P, M, LG); new = ("gate", x, t2, g2, a2, P, M, LG)
                else:
                    c = comp(CX, x); P2, M2, LG2 = np.vstack([P, c[1]]), np.vstack([M, c[0]]), np.vstack([LG, lgate(c)]); a2 = np.r_[act, 0]
                    t2, g2, b2 = fit(np.r_[th, math.log(1e-3) + th.max()], np.r_[ga, 0.0], a2, P2, M2, LG2); new = (kd, x, t2, g2, a2, P2, M2, LG2)
                gain = cur - b2 - bb; tried += 1
                if gain > 0 and (best is None or gain > best[0]): best = (gain, b2, new)
                elif gain <= 0: st["rejected"].append(f"gate:{pool[x - 1]}" if kd == "gate" else x)
        if best is None:
            if tried == 0 or not any(c[2] > 0 and (f"gate:{pool[c[1] - 1]}" if c[0] == "gate" else c[1]) not in set(st["rejected"]) for c in cands): break
            st.update(th=th.tolist(), ga=ga.tolist()); json.dump(st, open(CK, "w")); continue
        _, cur, (kd, x, th, ga, act, P, M, LG) = best
        if kd == "gate": st["act"] = [int(i) for i in np.nonzero(act)[0]]; label = f"Gate[{desc(pool[x - 1])}]"
        else: pool.append(x); label = desc(x)
        st.update(pool=pool, th=th.tolist(), ga=ga.tolist(), act=[int(i) for i in np.nonzero(act)[0]], rejected=[]); st["log"].append(f"{kd}: {label} -> fit {cur / n:.4f}")
        json.dump(st, open(CK, "w")); F.log(f"   + {kd}: {label}: fit {cur / n:.4f} bits/word (pool {len(pool)}, gates {int(act.sum())})")
    st.update(done=True, fit=cur / n); json.dump(st, open(CK, "w")); F.log(f"SY search done: pool {len(pool)}, gates {int(act.sum())}; fit {cur / n:.4f} bits/word")
else:
    import sieve_free as SF
    st = state(); pool = st["pool"]; cx = CX if mode == "rw" else "eval"; s, T, _ = F.ctx(cx); y = s[T]; nn = len(T); half = 0.5 * math.log2(nn)
    def weights_q():
        P, M, LG = rows(cx, pool); lw = np.array(st["th"])[:, None] + np.array(st["ga"])[:, None] * LG; w = np.exp(lw - lw.max(0)) * M; den = w.sum(0)
        pm = (w * P).sum(0) / den; Q = w[0][:, None] * F.U[None, :]
        for k, nme in enumerate(pool): Q += w[k + 1][:, None] * comp(cx, nme, True)[4]
        return pm, Q / den[:, None]
    if mode == "rw":
        MC = os.path.join(F.CD, "dsl_fit30_model.npz")
        if not os.path.exists(MC): pm, Q = weights_q(); np.savez(MC, pm=pm, Q=Q.astype(np.float32)); F.log("   mixture outputs cached, rerun"); sys.exit(0)
        z = np.load(MC); pm, Q = z["pm"], z["Q"].astype(np.float64); ws, bs = st.get("ws", []), st.get("bs", []); cur = st.get("rwcur", -np.log2(pm).sum()); tried = st.get("tried", {})
        while True:
            for W in SF.WS:
                if W in ws or str(W) in tried: continue
                if time.time() - T0 > 230: st.update(ws=ws, bs=bs, rwcur=cur, tried=tried); json.dump(st, open(CK, "w")); F.log("   time budget: reweight checkpoint"); sys.exit(0)
                b2s, b2 = SF.fit_beta(pm, Q, None, ws + [W], y, cx, bs + [0.25], only_last=len(ws) > 0); tried[str(W)] = [b2, b2s]
            best = min(((W, *tried[str(W)]) for W in SF.WS if str(W) in tried), key=lambda r: r[1], default=None)
            if best is None or cur - best[1] <= math.log2(len(SF.WS)) + half: break
            W = best[0] if best[0] == "book" else int(best[0]); ws.append(W); bs, cur = SF.fit_beta(pm, Q, None, ws, y, cx, best[2]) if len(ws) > 1 else (best[2], best[1]); tried = {}
            F.log(f"   + reweight {W}: betas {np.round(bs, 3).tolist()}, fit {cur / nn:.4f}"); st.update(ws=ws, bs=bs, rwcur=cur, tried=tried); json.dump(st, open(CK, "w"))
        st.update(ws=ws, bs=bs, rwcur=cur, tried={}, rwdone=True); json.dump(st, open(CK, "w")); F.log(f"SY reweight: {ws}; fit {cur / nn:.4f} bits/word")
    else:
        pm, Q = weights_q(); ix = np.arange(nn); b = np.ones_like(Q)
        for W, be in zip(st["ws"], st["bs"]): b = b * ((SF.win(cx, W) + 1e-4) / F.PG) ** be
        bits_ = -np.log2(pm * b[ix, F.FORM[y]] / (Q * b).sum(1)); np.savez(os.path.join(F.CD, "bits_dsl_fit30.npz"), bits=bits_, y=y, Qf=(Q * b / (Q * b).sum(1, keepdims=True)).astype(np.float16))
        F.log(f"SY scored on the {nn:,} positions: {bits_.mean():.4f} bits/word (without reweight {(-np.log2(pm)).mean():.4f}; SW2 7.8984, hand-built 7.7205, Stack 8.1507, LM 6.026)")
