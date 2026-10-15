"""R27 P5b: the Kneser-Ney counter chooses among candidate wordings (R27_prereg.md). Run: py -3.12 r27_choose_kn.py"""
import os, sys, re, json, math, random, statistics as st
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
X = np.load("r25_kn2_o5mxa_index.npz"); top = X["words"].tolist(); wid = {w: i + 1 for i, w in enumerate(top)}; RARE = 65535
NMAX = int(X["nmax"]); TOT1 = float(X["TOT1"]); C1disc = float(X["C1disc"]); MUL = np.uint64(0x9E3779B97F4A7C15); np.seterr(over="ignore")
Dn = {n: X[f"D{n}"] for n in range(1, NMAX + 1)}
c1 = np.zeros(65536); np.add.at(c1, X["wd1"].astype(np.int64), X["cnt1"])
IX = {n: (X[f"ctx{n}"], X[f"wd{n}"].astype(np.int64), X[f"cnt{n}"], X[f"hu{n}"], X[f"tot{n}"], X[f"dm{n}"]) for n in range(2, NMAX + 1)}
def hl(ids):
    h = np.uint64(0)
    for j, x in enumerate(ids): h = (h ^ np.uint64(x)) * MUL + np.uint64(j + 1)
    return h
def prob(prev, w):
    c = c1[w]; p = (max(c - Dn[1][min(int(c), 3) - 1], 0) if c else 0) / TOT1 + C1disc / TOT1 / 65536
    for n in range(2, NMAX + 1):
        if len(prev) < n - 1: break
        hc = hl(prev[-(n - 1):]); ctx, wd, cnt, hu, tot, dm = IX[n]; i = np.searchsorted(hu, hc)
        if i >= len(hu) or hu[i] != hc: break
        lo, hi = np.searchsorted(ctx, hc, "left"), np.searchsorted(ctx, hc, "right"); k = np.nonzero(wd[lo:hi] == w)[0]
        c = int(cnt[lo + k[0]]) if len(k) else 0
        p = (max(c - Dn[n][min(c, 3) - 1], 0) if c else 0) / tot[i] + dm[i] / tot[i] * p
    return p
def kn_bits(s):
    w = [x.lower() for x in re.findall(r"[A-Za-z]+", s)]; ids = [wid.get(x, RARE) for x in w]; prev = [0]; b = 0.0
    for x in ids: b -= math.log2(max(prob(prev, x), 1e-12)); prev.append(x)
    return b / max(1, len(ids))
from r27_choose import candidates
if __name__ == "__main__":
    from r27_fluency import judge_bits
    rows = [r for r in json.load(open("r27_p1c_sentences.json", encoding="utf-8")) if r["s"] and r["story"]]
    random.Random(0).shuffle(rows); rows = rows[:300]; chosen = []
    for r in rows:
        base = kn_bits(r["s"]); best = min(candidates(r["s"], r["a"]), key=kn_bits); chosen.append(best if kn_bits(best) < base - 0.5 else r["s"])
    changed = sum(1 for r, c in zip(rows, chosen) if c != r["s"])
    j1 = st.mean(judge_bits(r["s"]) for r in rows); j2 = st.mean(judge_bits(c) for c in chosen)
    print(f"P5b changed {changed} of {len(rows)}; judge P1c {j1:.3f} -> counter's choice {j2:.3f}", flush=True)
    for r, c in list(zip(rows, chosen))[:60]:
        if c != r["s"]: print("  ", r["s"], "=>", c)
