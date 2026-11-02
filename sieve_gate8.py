"""SX8 (sieve_lang_prereg.md): a second gate feature. Weight of component c at position i = w_c (n/(n+T))^g_c (1+n)^h_c,
on SX7's program (sieve_gate7_fit30.json); h_c added component by component in gradient order, fitted jointly with
the log-weights and g by gradient, kept while it saves more than (1/2) log2 n + log2(46) bits. Reweight stage and
score as sieve_gate.py. Run: py -3.12 -W ignore sieve_gate8.py gate | rw | eval   (resumable). SX9: env SX9=1 -> the second
feature is -H(Q_c), the component's own form entropy (log-weight term h_c * sum Q log2 Q)."""
import os, sys, json, math, time
import numpy as np
import sieve_fs2 as F, sieve_free as SF
T0 = time.time(); CX = "fit30"; V9 = os.environ.get("SX9") == "1"                                      # SX9: confidence gate instead of count gate
CK = os.path.join(F.HERE, "sieve_gate9_fit30.json" if V9 else "sieve_gate8_fit30.json")
if not os.path.exists(CK):
    s7 = json.load(open(os.path.join(F.HERE, "sieve_gate7_fit30.json")))
    json.dump(dict(sel=s7["sel"], th=s7["th"], ga=s7["ga"], act=s7["act"], gb=[0.0] * (len(s7["sel"]) + 1), actb=[], rejected=[]), open(CK, "w"))
ST_ = json.load(open(CK)); SEL = ST_["sel"]
def arrays(cx):
    C = [F.load(cx, n) for n in SEL]; n = len(C[0][0]); z = np.zeros(n)
    P = np.vstack([np.full(n, 1 / F.Vt)] + [c[1] for c in C]); M = np.vstack([np.ones(n, bool)] + [c[0] for c in C])
    L1 = np.vstack([z] + [np.where(c[0], np.log(np.maximum(c[2], 1) / (np.maximum(c[2], 1) + np.maximum(c[3], 1))), 0) for c in C])
    if V9:
        def negH(nme, ne):
            Q = F.load(cx, nme, True)[4].astype(np.float64); F.MEMO.pop((cx, nme, True), None); return np.where(ne, (Q * np.log2(np.maximum(Q, 1e-12))).sum(1), 0)
        L2 = np.vstack([z] + [negH(nme, c[0]) for nme, c in zip(SEL, C)]); return P, M, L1, L2
    L2 = np.vstack([z] + [np.where(c[0], np.log1p(np.maximum(c[2], 0)), 0) for c in C]); return P, M, L1, L2
def bits(th, ga, gb, P, M, L1, L2):
    lw = th[:, None] + ga[:, None] * L1 + gb[:, None] * L2; w = np.exp(lw - lw.max(0)) * M; num = (w * P).sum(0); den = w.sum(0)
    d = (w * P / num - w / den) / math.log(2); return -(np.log2(num) - np.log2(den)).sum(), -d.sum(1), -(d * L1).sum(1), -(d * L2).sum(1)
def fit(th, ga, gb, a1, a2, A, iters=150):
    b, gt, gg, gh = bits(th, ga, gb, *A); lr = 1.0; n = A[0].shape[1]
    for _ in range(iters):
        while lr > 1e-9:
            t2, g2, h2 = th - lr * gt / n, ga - lr * gg * a1 / n, gb - lr * gh * a2 / n; r = bits(t2, g2, h2, *A)
            if r[0] < b - 1e-9: th, ga, gb, (b, gt, gg, gh) = t2, g2, h2, r; lr *= 1.5; break
            lr *= 0.5
        else: break
    return th, ga, gb, b
def weights_q(cx, st):
    P, M, L1, L2 = arrays(cx); lw = np.array(st["th"])[:, None] + np.array(st["ga"])[:, None] * L1 + np.array(st["gb"])[:, None] * L2
    w = np.exp(lw - lw.max(0)) * M; den = w.sum(0); pm = (w * P).sum(0) / den; Q = w[0][:, None] * F.U[None, :]
    for k, nme in enumerate(SEL): F.load(cx, nme, True); Q += w[k + 1][:, None] * F.MEMO.pop((cx, nme, True))[4]   # one at a time (memory)
    return pm, Q / den[:, None]
mode = sys.argv[1] if len(sys.argv) > 1 else "gate"; st = ST_
if mode == "more":                                                                                    # SX10: new components offered with their own trust gate
    NEW = [f"trig{b}_{W}_{thr}" for b in (200, 1000) for W in (10, 50) for thr in (100, 1000)]; GRAM = 137 + len(NEW)
    A = arrays(CX); n = A[0].shape[1]; half = 0.5 * math.log2(n); pick = math.log2(GRAM)
    th, ga, gb = (np.array(st[k]) for k in ("th", "ga", "gb")); a1 = np.zeros(len(SEL) + 1); a1[st["act"]] = 1; a2 = np.zeros(len(SEL) + 1); a2[st["actb"]] = 1
    cur = bits(th, ga, gb, *A)[0]; F.log(f"SX10: {len(SEL)} components; fit {cur / n:.4f} bits/word"); tried = set(st.get("new_rejected", []))
    while True:
        P, M, L1, L2 = A; lw = th[:, None] + ga[:, None] * L1 + gb[:, None] * L2; w = np.exp(lw - lw.max(0)) * M; num = (w * P).sum(0); den = w.sum(0)
        cand = {nm: (F.load(CX, nm)[0] * (F.load(CX, nm)[1] / num - 1 / den)).sum() for nm in NEW if nm not in SEL and nm not in tried}; added = False
        for nm in sorted(cand, key=lambda k: (-cand[k], k)):
            if cand[nm] <= 0: break
            if time.time() - T0 > 230: st.update(th=th.tolist(), ga=ga.tolist(), gb=gb.tolist(), new_rejected=sorted(tried)); json.dump(st, open(CK, "w")); F.log("   time budget: checkpoint"); sys.exit(0)
            c = F.load(CX, nm); l1 = np.where(c[0], np.log(np.maximum(c[2], 1) / (np.maximum(c[2], 1) + np.maximum(c[3], 1))), 0)
            Qn = F.load(CX, nm, True)[4].astype(np.float64); F.MEMO.pop((CX, nm, True), None); l2 = np.where(c[0], (Qn * np.log2(np.maximum(Qn, 1e-12))).sum(1), 0) if V9 else np.zeros(n); del Qn
            A2 = (np.vstack([P, c[1]]), np.vstack([M, c[0]]), np.vstack([L1, l1]), np.vstack([L2, l2])); b1 = np.r_[a1, 1]; b2_ = np.r_[a2, 0]
            t2, g2, h2, bb = fit(np.r_[th, math.log(1e-3) + th.max()], np.r_[ga, 0.0], np.r_[gb, 0.0], b1, b2_, A2)
            if cur - bb > pick + 2 * half:
                SEL.append(nm); A, th, ga, gb, a1, a2, cur = A2, t2, g2, h2, b1, b2_, bb; st["act"].append(len(SEL)); tried = set(); added = True
                F.log(f"   + {F.desc(nm)} (gated, g = {ga[-1]:.3f}): fit {cur / n:.4f}"); st.update(sel=SEL, th=th.tolist(), ga=ga.tolist(), gb=gb.tolist(), new_rejected=[]); json.dump(st, open(CK, "w")); break
            tried.add(nm)
        if not added: break
    st.update(sel=SEL, th=th.tolist(), ga=ga.tolist(), gb=gb.tolist(), more_done=True, rwdone=False, ws=[], bs=[], tried={}); st.pop("rwcur", None); json.dump(st, open(CK, "w"))
    MC = os.path.join(F.CD, "gate9_fit30_model.npz" if V9 else "gate8_fit30_model.npz")
    if os.path.exists(MC): os.remove(MC)
    F.log(f"SX10: {len(SEL)} components; fit {cur / n:.4f} bits/word")
elif mode == "gate":
    A = arrays(CX); n = A[0].shape[1]; half = 0.5 * math.log2(n); pick = math.log2(len(SEL))
    th, ga, gb = (np.array(st[k]) for k in ("th", "ga", "gb")); a1 = np.zeros(len(SEL) + 1); a1[st["act"]] = 1; a2 = np.zeros(len(SEL) + 1); a2[st["actb"]] = 1
    cur = bits(th, ga, gb, *A)[0]; F.log(f"SX8: {len(SEL)} components, {int(a1.sum())} trust gates, {int(a2.sum())} count gates; fit {cur / n:.4f} bits/word")
    while True:
        gh = bits(th, ga, gb, *A)[3]; added = False
        for k in sorted(range(1, len(SEL) + 1), key=lambda k: -abs(gh[k])):
            if a2[k] or k in st["rejected"] or abs(gh[k]) < 1e-9: continue
            if time.time() - T0 > 240: st.update(th=th.tolist(), ga=ga.tolist(), gb=gb.tolist()); json.dump(st, open(CK, "w")); F.log("   time budget: checkpoint saved"); sys.exit(0)
            b2_ = a2.copy(); b2_[k] = 1; t2, g2, h2, b2 = fit(th, ga, gb, a1, b2_, A)
            if cur - b2 > half + pick:
                th, ga, gb, a2, cur = t2, g2, h2, b2_, b2; st["actb"].append(int(k)); st["rejected"] = []; added = True
                F.log(f"   + count gate on {F.desc(SEL[k - 1])}: h = {gb[k]:.3f}, fit {cur / n:.4f}"); st.update(th=th.tolist(), ga=ga.tolist(), gb=gb.tolist()); json.dump(st, open(CK, "w")); break
            st["rejected"].append(int(k))
        if not added: break
    st.update(th=th.tolist(), ga=ga.tolist(), gb=gb.tolist(), done=True, fit=cur / n); json.dump(st, open(CK, "w")); F.log(f"SX8 count gates: {len(st['actb'])}; fit {cur / n:.4f} bits/word")
elif mode == "rw":
    s, T, _ = F.ctx(CX); y = s[T]; n = len(T); half = 0.5 * math.log2(n); MC = os.path.join(F.CD, "gate9_fit30_model.npz" if V9 else "gate8_fit30_model.npz")
    if not os.path.exists(MC): pm, Q = weights_q(CX, st); np.savez(MC, pm=pm, Q=Q.astype(np.float32)); F.log("   mixture outputs cached, rerun"); sys.exit(0)
    z = np.load(MC); pm, Q = z["pm"], z["Q"].astype(np.float64); ws, bs = st.get("ws", []), st.get("bs", []); cur = st.get("rwcur", -np.log2(pm).sum()); tried = st.get("tried", {})
    while True:
        for W in SF.WS:
            if W in ws or str(W) in tried: continue
            if time.time() - T0 > 230: st.update(ws=ws, bs=bs, rwcur=cur, tried=tried); json.dump(st, open(CK, "w")); F.log("   time budget: reweight checkpoint"); sys.exit(0)
            b2s, b2 = SF.fit_beta(pm, Q, None, ws + [W], y, CX, bs + [0.25], only_last=len(ws) > 0); tried[str(W)] = [b2, b2s]
        best = min(((W, *tried[str(W)]) for W in SF.WS if str(W) in tried), key=lambda r: r[1], default=None)
        if best is None or cur - best[1] <= math.log2(len(SF.WS)) + half: break
        W = best[0] if best[0] == "book" else int(best[0]); ws.append(W); bs, cur = SF.fit_beta(pm, Q, None, ws, y, CX, best[2]) if len(ws) > 1 else (best[2], best[1]); tried = {}
        F.log(f"   + reweight {W}: betas {np.round(bs, 3).tolist()}, fit {cur / n:.4f}"); st.update(ws=ws, bs=bs, rwcur=cur, tried=tried); json.dump(st, open(CK, "w"))
    st.update(ws=ws, bs=bs, rwcur=cur, tried={}, rwdone=True); json.dump(st, open(CK, "w")); F.log(f"SX8 reweight: {ws}; fit {cur / n:.4f} bits/word")
else:
    pm, Q = weights_q("eval", st); y = F.ev_s[F.Te]; ix = np.arange(len(y)); fy = F.FORM[y]; b = np.ones_like(Q)
    for W, be in zip(st["ws"], st["bs"]): b = b * ((SF.win("eval", W) + 1e-4) / F.PG) ** be
    bits_ = -np.log2(pm * b[ix, fy] / (Q * b).sum(1)); np.savez(os.path.join(F.CD, "bits_gate9_fit30.npz" if V9 else "bits_gate8_fit30.npz"), bits=bits_, y=y, Qf=(Q * b / (Q * b).sum(1, keepdims=True)).astype(np.float16))
    F.log(f"SX8 scored on the {len(y):,} positions: {bits_.mean():.4f} bits/word (without reweight {(-np.log2(pm)).mean():.4f}; SX7 7.7280, Stack 8.1507, LM 6.026)")
