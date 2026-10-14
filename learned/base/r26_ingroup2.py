"""R26 T08: in-group word choice by the two previous words, backing off to the previous word (R25-cn / R25-co).
Run: py -3.12 r26_ingroup2.py r25_dyn_probs.npz"""
import os, sys, math, time, collections, itertools
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--threads", "2", "--groups-file", "r25_classes_wnx.json"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
g, encode, gw, _uni, _cnt, UNKG = (R[k] for k in "g encode gw _uni _cnt UNKG".split())
import numpy as np
t0 = time.time(); Bz = np.load(ARGV[1]); PB, PA = Bz["p"], Bz["para"]
pair = collections.Counter(); pg = collections.Counter(); tri = collections.Counter(); tg = collections.Counter()
for p in g["trp"]:
    ws = [x for s in p for x in s]
    for a, b in zip(ws, ws[1:]): pair[(a, b)] += 1
    for a, b, c in zip(ws, ws[1:], ws[2:]): tri[(a, b, c)] += 1
for (a, b), c in pair.items(): pg[(a, gw(b))] += c
for (a, b, c_), c in tri.items(): tg[(a, b, gw(c_))] += c
print(f"T08 {len(pair):,} pairs, {len(tri):,} triples ({time.time() - t0:.0f} s)", flush=True)
items = []; j = 0
for pi, p in enumerate(g["tep"][:1000]):
    a_, mask = encode(p); ws = [x for s in p for x in s]
    for k in range(1, len(a_)):
        if not mask[k]: continue
        gid = gw(ws[k]); items.append((pi, ws[k - 2] if k >= 2 else None, ws[k - 1], ws[k], gid, (_uni[ws[k]] + 0.5) / _cnt[gid] if gid != UNKG else None, PB[j])); j += 1
assert j == len(PB)
BD = float(ARGV[ARGV.index("--bookdecay") + 1]) if "--bookdecay" in ARGV else None
def run(a3, m3, a=10, m=100, d=1.0):
    bp = collections.Counter(); bg = collections.Counter(); bt = collections.Counter(); btg = collections.Counter(); out = np.empty(len(items)); sc = 1.0
    for i, (pi, p2, pv, w, gid, sh, pb) in enumerate(items):
        if d < 1.0:
            sc /= d
            if sc > 1e100:
                for C_ in (bp, bg, bt, btg):
                    for k_ in C_: C_[k_] /= sc
                sc = 1.0
        m_, m3_ = m / sc, m3 / sc
        if sh is None: out[i] = pb
        else:
            q2 = (pair[(pv, w)] + m_ * bp[(pv, w)] + a * sh) / (pg[(pv, gid)] + m_ * bg[(pv, gid)] + a)
            if p2 is not None: q2 = (tri[(p2, pv, w)] + m3_ * bt[(p2, pv, w)] + a3 * q2) / (tg[(p2, pv, gid)] + m3_ * btg[(p2, pv, gid)] + a3)
            out[i] = pb / sh * q2
        bp[(pv, w)] += sc; bg[(pv, gid)] += sc
        if p2 is not None: bt[(p2, pv, w)] += sc; btg[(p2, pv, gid)] += sc
    return out
res = {}
GRID_ = [(30, 100, d) for d in (1.0, 0.9995, 0.998)] if BD is not None else [(a3, m3, 1.0) for a3, m3 in itertools.product((3, 10, 30), (0, 30, 100))]
for a3, m3, d in GRID_:
    P = run(a3, m3, d=d); res[(a3, m3, d)] = P; b = -np.log2(P)
    print(f"  a3 {a3} m3 {m3} d {d}: 0-499 {b[PA < 500].mean():.4f}, 500-999 {b[PA >= 500].mean():.4f}", flush=True)
best = min(res, key=lambda k: -np.log2(res[k][PA < 500]).mean()); P = res[best]
np.savez(ARGV[2] if len(ARGV) > 2 else "r26_ingroup2_probs.npz", p=P, para=PA)
print(f"T08 chosen {best}: 500-999 {-np.log2(P[PA >= 500]).mean():.4f} (R25-co B 7.5306; network alone {-np.log2(PB[PA >= 500]).mean():.4f})", flush=True)
