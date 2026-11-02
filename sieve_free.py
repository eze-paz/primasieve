"""SW (sieve_lang_prereg.md): a search without tuning buttons. Model: P(y) = sum_{c present} w_c p_c(y) / sum_{c
present} w_c over the selected components + the uniform token (always present), then an optional reweight stage by
recent form shares, P'(y) = P(y) b(form y) / sum_f Q[f] b(f), b = prod_i ((Pwin_i + 1e-4) / Pglob)^beta_i. Every
continuous parameter (log-weights, betas) is fitted by gradient and charged (1/2) log2(n) bits (n = fit positions);
every discrete choice log2 of its options. Selection: at each step every unused component's gradient at weight 0 is
computed; candidates are fitted in gradient order and the first whose fit saves more than its bits is added; stop when
none does. Then reweight windows are added the same way. Run: py -3.12 -W ignore sieve_free.py fit9 ; sieve_free.py rw fit9 ; sieve_free.py eval fit9"""
import os, sys, json, math, time
import numpy as np
import sieve_fs2 as F
from sieve_rw2 import win
MODE = sys.argv[1] if len(sys.argv) > 1 else "fit9"; CX = sys.argv[2] if MODE in ("rw", "eval") and len(sys.argv) > 2 else (MODE if MODE not in ("rw", "eval") else "fit9"); T0 = time.time()
NAMES = F.names_of("count") + F.names_of("book") + F.names_of("recency") + [f"graded_id_{w}" for w in F.GW] + F.names_of("long")
if os.path.exists(os.path.join(F.CD, f"{sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] in ('rw', 'eval') else (sys.argv[1] if len(sys.argv) > 1 else 'fit9')}_trig_10_100.npz")):
    NAMES += [f"trig_{W}_{thr}" for W in (10, 50) for thr in (100, 1000)]                                # SX1: trigger components
    if os.path.exists(os.path.join(F.CD, f"{sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] in ('rw', 'eval') else (sys.argv[1] if len(sys.argv) > 1 else 'fit9')}_btrig_10_100.npz")):
        NAMES += [f"btrig_{W}_{thr}" for W in (10, 50) for thr in (100, 1000, "any")]                    # SX2: book triggers
        if os.path.exists(os.path.join(F.CD, f"{sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] in ('rw', 'eval') else (sys.argv[1] if len(sys.argv) > 1 else 'fit9')}_fact_0_0.npz")):
            import sieve_factor as SFa; NAMES += [f"fact_{a}_{b}" for a in range(len(SFa.AS)) for b in range(len(SFa.BS))]   # SX3/SX4: factor combinator
WS = (50, 200, 1000, 5000, "book")
def mix_bits(th, P, M):
    """bits and gradient wrt log-weights; row 0 = uniform"""
    w = np.exp(th)[:, None] * M; num = (w * P).sum(0); den = w.sum(0); b = -(np.log2(num) - np.log2(den)).sum()
    g = -((w * P / num).sum(1) - (w / den).sum(1)) / math.log(2); return b, g
def fit_w(P, M, th):
    b, g = mix_bits(th, P, M); lr = 1.0
    for _ in range(300):
        while lr > 1e-9:
            t2 = th - lr * g / P.shape[1]; b2, g2 = mix_bits(t2, P, M)
            if b2 < b - 1e-9: th, b, g = t2, b2, g2; lr *= 1.5; break
            lr *= 0.5
        else: break
    return th, b
def fit_beta(pm, Q, m, ws, y, cx, betas, only_last=False):
    """bits of the reweight stage with windows ws; betas fitted by coordinate golden search"""
    fy = F.FORM[y]; ix = np.arange(len(y))
    if only_last:                                                                                       # fixed windows folded once: one power per evaluation (time)
        fix = np.ones_like(Q)
        for W, be in zip(ws[:-1], betas[:-1]): fix *= ((win(cx, W) + 1e-4) / F.PG) ** be
        QF = Q * fix; fy_fix = fix[ix, fy]; Bn = np.log((win(cx, ws[-1]) + 1e-4) / F.PG); By = Bn[ix, fy]
        def b1(be): return -(np.log2(pm * fy_fix) + be * By / math.log(2) - np.log2((QF * np.exp(be * Bn)).sum(1))).sum()
        lo, hi = -0.5, 2.0; g = (math.sqrt(5) - 1) / 2
        for _ in range(18):
            a, c = hi - g * (hi - lo), lo + g * (hi - lo)
            if b1(a) < b1(c): hi = c
            else: lo = a
        be = (lo + hi) / 2; return list(betas[:-1]) + [be], b1(be)
    bs, b = list(betas), None                                                                          # joint refit: coordinate descent, each coordinate folded as above
    for _ in range(2):
        for k in range(len(bs)):
            o = [i for i in range(len(bs)) if i != k] + [k]; nb, b = fit_beta(pm, Q, m, [ws[i] for i in o], y, cx, [bs[i] for i in o], only_last=True); bs[k] = nb[-1]
    return bs, b
    B = [((win(cx, W) + 1e-4) / F.PG) for W in ws]
    def bits(bs):
        b = np.ones_like(Q)
        for Bi, be in zip(B, bs): b = b * Bi ** be
        return -np.log2(pm * b[ix, fy] / (Q * b).sum(1)).sum()
    bs = list(betas)
    for _ in range(1 if only_last or len(bs) == 1 else 2):
        for k in ([len(bs) - 1] if only_last else range(len(bs))):
            lo, hi = -0.5, 2.0; g = (math.sqrt(5) - 1) / 2
            for _ in range(18):
                a, c = hi - g * (hi - lo), lo + g * (hi - lo); fa = bits(bs[:k] + [a] + bs[k + 1:]); fc = bits(bs[:k] + [c] + bs[k + 1:])
                if fa < fc: hi = c
                else: lo = a
            bs[k] = (lo + hi) / 2
    return bs, bits(bs)
def model(cx, sel, th, ws, bs):
    s, T, _ = F.ctx(cx); y = s[T]; C = [F.load(cx, n, True) for n in sel]; n = len(T)
    P = np.vstack([np.full(n, 1 / F.Vt)] + [c[1] for c in C]); M = np.vstack([np.ones(n, bool)] + [c[0] for c in C])
    w = np.exp(th)[:, None] * M; den = w.sum(0); pm = (w * P).sum(0) / den
    Q = w[0][:, None] * F.U[None, :]                                                                    # accumulated one component at a time (memory)
    for k, c in enumerate(C): Q += w[k + 1][:, None] * c[4]
    Q /= den[:, None]
    if not ws: return -np.log2(pm), Q
    b = np.ones_like(Q)
    for W, be in zip(ws, bs): b = b * ((win(cx, W) + 1e-4) / F.PG) ** be
    return -np.log2(pm * b[np.arange(n), F.FORM[y]] / (Q * b).sum(1)), Q * b / (Q * b).sum(1, keepdims=True)
if __name__ == "__main__" and MODE not in ("rw", "eval"):
    s, T, _ = F.ctx(CX); y = s[T]; n = len(T); half = 0.5 * math.log2(n); pick = math.log2(len(NAMES))
    C = {nm: F.load(CX, nm) for nm in NAMES}; sel = []; th = np.zeros(1); CK = os.path.join(F.HERE, f"sieve_free_{CX}_ckpt.json")
    P = np.full((1, n), 1 / F.Vt); M = np.ones((1, n), bool); cur = n * math.log2(F.Vt); F.log(f"SW on {CX}: {len(NAMES)} components, {n:,} positions; uniform {cur / n:.4f} bits/word")
    rejected = set()                                                                                    # tried and not paying at the current selection
    if os.path.exists(CK):                                                                              # SW2: resume the selection across runs
        ck = json.load(open(CK)); sel, th, cur = ck["sel"], np.array(ck["th"]), ck["cur"]; rejected = set(ck.get("rejected", []))
        P = np.vstack([P] + [C[nm][1] for nm in sel]); M = np.vstack([M] + [C[nm][0] for nm in sel]); F.log(f"   resumed with {len(sel)} components, fit {cur / n:.4f}")
    while True:
        if time.time() - T0 > 240: F.log("   time budget: checkpoint saved, rerun to resume"); sys.exit(0)
        w = np.exp(th)[:, None] * M; num = (w * P).sum(0); den = w.sum(0)
        grad = {nm: (C[nm][0] * (C[nm][1] / num - 1 / den)).sum() for nm in NAMES if nm not in sel and C[nm][0].any()}   # d bits / d w at w = 0 (sign flipped)
        added = False
        for nm in sorted(grad, key=lambda k: (-grad[k], k)):
            if grad[nm] <= 0: break
            if nm in rejected: continue
            if time.time() - T0 > 250: json.dump(dict(sel=sel, th=th.tolist(), cur=float(cur), rejected=sorted(rejected)), open(CK, "w")); F.log(f"   time budget: checkpoint ({len(rejected)} rejected), rerun to resume"); sys.exit(0)
            P2 = np.vstack([P, C[nm][1]]); M2 = np.vstack([M, C[nm][0]]); t2, b2 = fit_w(P2, M2, np.r_[th, math.log(1e-3) + th.max()])
            if cur - b2 > pick + half:
                sel.append(nm); P, M, th, cur = P2, M2, t2, b2; added = True; rejected = set(); F.log(f"   + {F.desc(nm)}: fit {cur / n:.4f} bits/word ({len(sel)} components)")
                json.dump(dict(sel=sel, th=th.tolist(), cur=float(cur), rejected=[]), open(CK, "w")); break
            rejected.add(nm)
        if not added: break
    json.dump(dict(sel=sel, th=th.tolist(), ws=[], bs=[], fit=cur / n, cx=CX), open(os.path.join(F.HERE, f"sieve_free_{CX}.json"), "w"))
    F.log(f"SW selected {len(sel)} components; fit {cur / n:.4f} bits/word, description {len(sel) * (pick + half):.1f} bits")
elif __name__ == "__main__" and MODE == "rw":                                                       # the reweight stage, a separate run (five-minute cap)
    prog = json.load(open(os.path.join(F.HERE, f"sieve_free_{CX}.json"))); sel, th = prog["sel"], np.array(prog["th"]); s, T, _ = F.ctx(CX); y = s[T]; n = len(T); half = 0.5 * math.log2(n)
    RC = os.path.join(F.HERE, f"sieve_free_{CX}_rwckpt.json"); rc = json.load(open(RC)) if os.path.exists(RC) else dict(ws=[], bs=[], tried={})   # resumable
    MC = os.path.join(F.CD, f"free_{CX}_model.npz")                                                      # the mixture's outputs, computed once (time)
    if not os.path.exists(MC): pm_bits, Q = model(CX, sel, th, [], []); np.savez(MC, pm_bits=pm_bits, Q=Q.astype(np.float32)); F.log("   mixture outputs cached, rerun"); sys.exit(0)
    z = np.load(MC); pm_bits, Q = z["pm_bits"], z["Q"].astype(np.float64)
    ws, bs = rc["ws"], rc["bs"]; cur = pm_bits.sum() if not ws else rc["cur"]
    pm = 2.0 ** -pm_bits
    while True:
        for W in WS:
            if W in ws or str(W) in rc["tried"]: continue
            if time.time() - T0 > 230: json.dump(rc, open(RC, "w")); F.log("   time budget: reweight checkpoint saved, rerun to resume"); sys.exit(0)
            b2s, b2 = fit_beta(pm, Q, None, ws + [W], y, CX, bs + [0.25], only_last=len(ws) > 0); rc["tried"][str(W)] = [b2, b2s]   # screening: the new beta alone
        best = min(((W, *rc["tried"][str(W)]) for W in WS if str(W) in rc["tried"]), key=lambda r: r[1], default=None)
        if best is None or cur - best[1] <= math.log2(len(WS)) + half: break
        W = best[0] if best[0] == "book" else int(best[0]); ws.append(W); bs, cur = fit_beta(pm, Q, None, ws, y, CX, best[2]) if len(ws) > 1 else (best[2], best[1]); rc.update(ws=ws, bs=bs, cur=cur, tried={}); json.dump(rc, open(RC, "w"))
        F.log(f"   + reweight by form shares of {W}: betas {np.round(bs, 3).tolist()}, fit {cur / n:.4f} bits/word")
    prog.update(ws=ws, bs=bs, fit=cur / n); json.dump(prog, open(os.path.join(F.HERE, f"sieve_free_{CX}.json"), "w"))
    F.log(f"SW reweight stage: {len(ws)} windows {ws}, betas {np.round(bs, 3).tolist()}; fit {cur / n:.4f} bits/word")
elif __name__ == "__main__":
    prog = json.load(open(os.path.join(F.HERE, f"sieve_free_{CX}.json")))
    bits, Q = model("eval", prog["sel"], np.array(prog["th"]), prog["ws"], prog["bs"]); b0, _ = model("eval", prog["sel"], np.array(prog["th"]), [], [])
    np.savez(os.path.join(F.CD, f"bits_free_{prog['cx']}.npz"), bits=bits, y=F.ev_s[F.Te], Qf=Q.astype(np.float16))
    F.log(f"SW scored on the {len(bits):,} positions: {bits.mean():.4f} bits/word (without reweight {b0.mean():.4f}; SU1 chain 7.9517, Stack 8.1507, LM 6.026)")
