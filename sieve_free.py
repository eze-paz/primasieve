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
def fit_beta(pm, Q, m, ws, y, cx, betas):
    """bits of the reweight stage with windows ws; betas fitted by coordinate golden search"""
    fy = F.FORM[y]; ix = np.arange(len(y)); B = [((win(cx, W) + 1e-4) / F.PG) for W in ws]
    def bits(bs):
        b = np.ones_like(Q)
        for Bi, be in zip(B, bs): b = b * Bi ** be
        return -np.log2(pm * b[ix, fy] / (Q * b).sum(1)).sum()
    bs = list(betas)
    for _ in range(2 if len(bs) > 1 else 1):
        for k in range(len(bs)):
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
    Qs = np.stack([np.broadcast_to(F.U, (n, F.NF))] + [c[4] for c in C]); w = np.exp(th)[:, None] * M; den = w.sum(0)
    pm = (w * P).sum(0) / den; Q = np.einsum("kn,knf->nf", w, Qs) / den[:, None]
    if not ws: return -np.log2(pm), Q
    b = np.ones_like(Q)
    for W, be in zip(ws, bs): b = b * ((win(cx, W) + 1e-4) / F.PG) ** be
    return -np.log2(pm * b[np.arange(n), F.FORM[y]] / (Q * b).sum(1)), Q * b / (Q * b).sum(1, keepdims=True)
if __name__ == "__main__" and MODE not in ("rw", "eval"):
    s, T, _ = F.ctx(CX); y = s[T]; n = len(T); half = 0.5 * math.log2(n); pick = math.log2(len(NAMES))
    C = {nm: F.load(CX, nm) for nm in NAMES}; sel = []; th = np.zeros(1); CK = os.path.join(F.HERE, f"sieve_free_{CX}_ckpt.json")
    P = np.full((1, n), 1 / F.Vt); M = np.ones((1, n), bool); cur = n * math.log2(F.Vt); F.log(f"SW on {CX}: {len(NAMES)} components, {n:,} positions; uniform {cur / n:.4f} bits/word")
    if os.path.exists(CK):                                                                              # SW2: resume the selection across runs
        ck = json.load(open(CK)); sel, th, cur = ck["sel"], np.array(ck["th"]), ck["cur"]
        P = np.vstack([P] + [C[nm][1] for nm in sel]); M = np.vstack([M] + [C[nm][0] for nm in sel]); F.log(f"   resumed with {len(sel)} components, fit {cur / n:.4f}")
    while True:
        if time.time() - T0 > 240: F.log("   time budget: checkpoint saved, rerun to resume"); sys.exit(0)
        w = np.exp(th)[:, None] * M; num = (w * P).sum(0); den = w.sum(0)
        grad = {nm: (C[nm][0] * (C[nm][1] / num - 1 / den)).sum() for nm in NAMES if nm not in sel and C[nm][0].any()}   # d bits / d w at w = 0 (sign flipped)
        added = False
        for nm in sorted(grad, key=lambda k: (-grad[k], k)):
            if grad[nm] <= 0: break
            P2 = np.vstack([P, C[nm][1]]); M2 = np.vstack([M, C[nm][0]]); t2, b2 = fit_w(P2, M2, np.r_[th, math.log(1e-3) + th.max()])
            if cur - b2 > pick + half:
                sel.append(nm); P, M, th, cur = P2, M2, t2, b2; added = True; F.log(f"   + {F.desc(nm)}: fit {cur / n:.4f} bits/word ({len(sel)} components)")
                json.dump(dict(sel=sel, th=th.tolist(), cur=float(cur)), open(CK, "w")); break
        if not added: break
    json.dump(dict(sel=sel, th=th.tolist(), ws=[], bs=[], fit=cur / n, cx=CX), open(os.path.join(F.HERE, f"sieve_free_{CX}.json"), "w"))
    F.log(f"SW selected {len(sel)} components; fit {cur / n:.4f} bits/word, description {len(sel) * (pick + half):.1f} bits")
elif __name__ == "__main__" and MODE == "rw":                                                       # the reweight stage, a separate run (five-minute cap)
    prog = json.load(open(os.path.join(F.HERE, f"sieve_free_{CX}.json"))); sel, th = prog["sel"], np.array(prog["th"]); s, T, _ = F.ctx(CX); y = s[T]; n = len(T); half = 0.5 * math.log2(n)
    ws, bs = [], []; pm_bits, Q = model(CX, sel, th, [], []); cur = pm_bits.sum()
    pm = 2.0 ** -pm_bits
    while True:
        best = None
        for W in WS:
            if W in ws: continue
            b2s, b2 = fit_beta(pm, Q, None, ws + [W], y, CX, bs + [0.25])
            if best is None or b2 < best[1]: best = (W, b2, b2s)
        if best is None or cur - best[1] <= math.log2(len(WS)) + half: break
        ws.append(best[0]); bs = best[2]; cur = best[1]; F.log(f"   + reweight by form shares of {best[0]}: betas {np.round(bs, 3).tolist()}, fit {cur / n:.4f} bits/word")
    prog.update(ws=ws, bs=bs, fit=cur / n); json.dump(prog, open(os.path.join(F.HERE, f"sieve_free_{CX}.json"), "w"))
    F.log(f"SW reweight stage: {len(ws)} windows {ws}, betas {np.round(bs, 3).tolist()}; fit {cur / n:.4f} bits/word")
elif __name__ == "__main__":
    prog = json.load(open(os.path.join(F.HERE, f"sieve_free_{CX}.json")))
    bits, Q = model("eval", prog["sel"], np.array(prog["th"]), prog["ws"], prog["bs"]); b0, _ = model("eval", prog["sel"], np.array(prog["th"]), [], [])
    np.savez(os.path.join(F.CD, f"bits_free_{prog['cx']}.npz"), bits=bits, y=F.ev_s[F.Te], Qf=Q.astype(np.float16))
    F.log(f"SW scored on the {len(bits):,} positions: {bits.mean():.4f} bits/word (without reweight {b0.mean():.4f}; SU1 chain 7.9517, Stack 8.1507, LM 6.026)")
