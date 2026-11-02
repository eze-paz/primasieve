"""SX6 (sieve_lang_prereg.md): trust-gated weights. Weight of component c at position i = w_c (n_i / (n_i + T_i))^g_c
(n = matched count, T = distinct followers; the uniform token has gate 1). Starting from SX4's mixture (35 components),
g_c is added component by component in gradient order, fitted jointly with the log-weights by gradient, kept while it
saves more than (1/2) log2 n + log2(35) bits. Then the reweight stage (as sieve_free.py) and the score.
Run: py -3.12 -W ignore sieve_gate.py gate | rw | eval   (each resumable, under five minutes)"""
import os, sys, json, math, time
import numpy as np
import sieve_fs2 as F, sieve_free as SF
T0 = time.time(); CX = "fit30"; PROG = json.load(open(os.path.join(F.HERE, "sieve_free_fit30_sx4.json"))); SEL = PROG["sel"]
CK = os.path.join(F.HERE, "sieve_gate_fit30.json")
def arrays(cx):
    C = [F.load(cx, n) for n in SEL]; n = len(C[0][0])
    P = np.vstack([np.full(n, 1 / F.Vt)] + [c[1] for c in C]); M = np.vstack([np.ones(n, bool)] + [c[0] for c in C])
    LG = np.vstack([np.zeros(n)] + [np.where(c[0], np.log(np.maximum(c[2], 1) / (np.maximum(c[2], 1) + np.maximum(c[3], 1))), 0) for c in C]); return P, M, LG
def bits(th, ga, P, M, LG):
    lw = th[:, None] + ga[:, None] * LG; w = np.exp(lw - lw.max(0)) * M; num = (w * P).sum(0); den = w.sum(0)
    b = -(np.log2(num) - np.log2(den)).sum(); d = (w * P / num - w / den) / math.log(2); return b, -d.sum(1), -(d * LG).sum(1)
def fit(th, ga, act, P, M, LG, iters=150):
    b, gt, gg = bits(th, ga, P, M, LG); lr = 1.0; n = P.shape[1]
    for _ in range(iters):
        while lr > 1e-9:
            t2 = th - lr * gt / n; g2 = ga - lr * gg * act / n; b2, gt2, gg2 = bits(t2, g2, P, M, LG)
            if b2 < b - 1e-9: th, ga, b, gt, gg = t2, g2, b2, gt2, gg2; lr *= 1.5; break
            lr *= 0.5
        else: break
    return th, ga, b
def weights_q(cx, th, ga):
    P, M, LG = arrays(cx); lw = th[:, None] + ga[:, None] * LG; w = np.exp(lw - lw.max(0)) * M; den = w.sum(0); pm = (w * P).sum(0) / den
    Q = w[0][:, None] * F.U[None, :]
    for k, nme in enumerate(SEL): Q += w[k + 1][:, None] * F.load(cx, nme, True)[4]
    return pm, Q / den[:, None]
mode = sys.argv[1] if len(sys.argv) > 1 else "gate"
if mode == "gate":
    P, M, LG = arrays(CX); n = P.shape[1]; half = 0.5 * math.log2(n); pick = math.log2(len(SEL))
    st = json.load(open(CK)) if os.path.exists(CK) else dict(th=PROG["th"], ga=[0.0] * (len(SEL) + 1), act=[], rejected=[])
    th, ga = np.array(st["th"]), np.array(st["ga"]); act = np.zeros(len(SEL) + 1); act[st["act"]] = 1; cur = bits(th, ga, P, M, LG)[0]
    F.log(f"SX6: {len(SEL)} components, {len(st['act'])} gates so far; fit {cur / n:.4f} bits/word")
    while True:
        _, _, gg = bits(th, ga, P, M, LG); added = False
        for k in sorted(range(1, len(SEL) + 1), key=lambda k: -abs(gg[k])):
            if act[k] or k in st["rejected"] or abs(gg[k]) < 1e-9: continue
            if time.time() - T0 > 240: st.update(th=th.tolist(), ga=ga.tolist()); json.dump(st, open(CK, "w")); F.log("   time budget: checkpoint saved"); sys.exit(0)
            a2 = act.copy(); a2[k] = 1; t2, g2, b2 = fit(th, ga, a2, P, M, LG)
            if cur - b2 > half + pick:
                th, ga, act, cur = t2, g2, a2, b2; st["act"].append(int(k)); st["rejected"] = []; added = True
                F.log(f"   + gate on {F.desc(SEL[k - 1])}: g = {ga[k]:.3f}, fit {cur / n:.4f} bits/word"); st.update(th=th.tolist(), ga=ga.tolist()); json.dump(st, open(CK, "w")); break
            st["rejected"].append(int(k))
        if not added: break
    st.update(th=th.tolist(), ga=ga.tolist(), done=True, fit=cur / n); json.dump(st, open(CK, "w")); F.log(f"SX6 gates: {len(st['act'])}; fit {cur / n:.4f} bits/word")
elif mode == "rw":
    st = json.load(open(CK)); s, T, _ = F.ctx(CX); y = s[T]; n = len(T); half = 0.5 * math.log2(n)
    MC = os.path.join(F.CD, "gate_fit30_model.npz")
    if not os.path.exists(MC): pm, Q = weights_q(CX, np.array(st["th"]), np.array(st["ga"])); np.savez(MC, pm=pm, Q=Q.astype(np.float32)); F.log("   gated mixture outputs cached, rerun"); sys.exit(0)
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
    st.update(ws=ws, bs=bs, rwcur=cur, tried={}, rwdone=True); json.dump(st, open(CK, "w")); F.log(f"SX6 reweight: {ws} {np.round(bs, 3).tolist()}; fit {cur / n:.4f} bits/word")
else:
    st = json.load(open(CK)); pm, Q = weights_q("eval", np.array(st["th"]), np.array(st["ga"])); y = F.ev_s[F.Te]; ix = np.arange(len(y)); fy = F.FORM[y]
    b = np.ones_like(Q)
    for W, be in zip(st["ws"], st["bs"]): b = b * ((SF.win("eval", W) + 1e-4) / F.PG) ** be
    bits_ = -np.log2(pm * b[ix, fy] / (Q * b).sum(1)); np.savez(os.path.join(F.CD, "bits_gate_fit30.npz"), bits=bits_, y=y, Qf=(Q * b / (Q * b).sum(1, keepdims=True)).astype(np.float16))
    F.log(f"SX6 scored on the {len(y):,} positions: {bits_.mean():.4f} bits/word (without reweight {(-np.log2(pm)).mean():.4f}; SX4 7.8430, Stack 8.1507, LM 6.026)")
