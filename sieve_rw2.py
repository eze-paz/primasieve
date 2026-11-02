"""SV1 (sieve_lang_prereg.md): stacked reweight stage on SU1's chain. b(f) = prod_i ((Pwin_i(f) + 1e-4) / Pglob(f))^beta_i,
P'(y) = P(y) b(form(y)) / sum_f Q[f] b(f). Windows: past 50 / 200 / 1,000 / 5,000 tokens, or the whole book so far.
MDL on the 9,000 fit positions; the chosen stage scored once. Run: py -3.12 -W ignore sieve_rw2.py"""
import os, sys, json, math, itertools
import numpy as np
import sieve_fs2 as F
WS = (50, 200, 1000, 5000, "book")
def win(cx, W):
    if W != "book": return F.windows(cx, W)
    f = os.path.join(F.CD, f"{cx}_winbook.npy")
    if not os.path.exists(f):
        s, T, book = F.ctx(cx); out = np.zeros((len(T), F.NF), np.float32); cur = None
        for i, t in enumerate(T):
            if book[t] != cur:                                                  # positions are in reading order: restart at each book
                cur = book[t]; st = t
                while st > F.NT and book[st - 1] == cur: st -= 1
                cnt = np.zeros(F.NF); last = st
            cnt += np.bincount(F.FORM[s[last:t]], minlength=F.NF); last = t; out[i] = cnt / max(cnt.sum(), 1)
        np.save(f, out)
    return np.load(f)
if __name__ == "__main__":                                                                  # importable (sieve_free.py uses win)
    P = json.load(open(os.path.join(F.HERE, "sieve_fs2_su1_mdl.json"))); names = [n for n, _ in P["chain"]]; ch = [(k, None if cb is None else tuple(cb)) for k, (_, cb) in enumerate(P["chain"])]
    RQ = {}
    def bits(cx, stage, e):
        if cx not in RQ: C = {k: F.load(cx, n, True) for k, n in enumerate(names)}; RQ[cx] = F.run_q(ch, C)
        m, p, Q = RQ[cx]; s, T, _ = F.ctx(cx); y = s[T]; fy = F.FORM[y]; ix = np.arange(len(y))
        b = np.ones((len(y), F.NF))
        for W, beta in stage: b = b * ((win(cx, W) + 1e-4) / F.PG) ** beta
        pe = np.where(m, (1 - e) * p + e / F.Vt, 1 / F.Vt); Zn = np.where(m, (1 - e) * (Q * b).sum(1) + e * (F.U * b).sum(1), (F.U * b).sum(1))
        return -np.log2(pe * b[ix, fy] / Zn)
    stages = [()] + [((W, b),) for W in WS for b in (0.25, 0.5, 1.0)] + [((W1, b1), (W2, b2)) for W1, W2 in itertools.combinations(WS, 2) for b1 in (0.25, 0.5) for b2 in (0.25, 0.5)]
    rows = []
    for st in stages:
        bb = bits("fit9", st, P["escape"]).sum(); dlr = 1 + len(st) * (1 + math.log2(5) + math.log2(3)); rows.append((bb + dlr, bb, st))
    rows.sort(key=lambda r: (round(r[0], 9), repr(r[2])))
    for r in rows[:6]: print(f"   {r[2] or 'no reweight'}: fit {r[1] / 9000:.4f} bits/word, total {r[0]:.1f}")
    best = rows[0][2]; e = P["escape"]
    for st in ((), ((1000, 0.25),), best):
        print(f"   scored {st or 'no reweight'}: {bits('eval', st, e).mean():.4f} bits/word")
    F.log(f"SV1: MDL chose {best}")
