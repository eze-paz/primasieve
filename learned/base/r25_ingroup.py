"""R25-cn: context-conditioned word choice inside the group. The network B gives P(group); the word then gets its
unigram share inside the group. Here the share is replaced by
  q(w | g, prev) = (c(prev, w) + a * share(w)) / (c_g(prev) + a),   c = c_train + m * c_book
where c_train counts word pairs in the training paragraphs (across sentences inside a paragraph, as the network
reads), c_book counts pairs in the held-out text already read, and c_g(prev) sums c(prev, .) over the group.
Words predicted through the unknown group keep their charge. (a, m) chosen on paragraphs 0-499; reported on 500-999.
Run: py -3.12 r25_ingroup.py r25_ch_probs.npz"""
import os, sys, math, time, collections, itertools
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--threads", "2", "--groups-file", "r25_classes_wnx.json"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
g, encode, gw, _uni, _cnt, UNKG = (R[k] for k in "g encode gw _uni _cnt UNKG".split())
import numpy as np
t0 = time.time(); Bz = np.load(ARGV[1]); PB, PA = Bz["p"], Bz["para"]
pair = collections.Counter(); pg = collections.Counter()
for p in g["trp"]:
    ws = [x for s in p for x in s]
    for a, b in zip(ws, ws[1:]): pair[(a, b)] += 1
for (a, b), c in pair.items(): pg[(a, gw(b))] += c
print(f"R25-cn {len(pair):,} training pairs ({time.time() - t0:.0f} s)", flush=True)
items = []                                                                                          # (para, prev, word, group, share, B prob)
j = 0
for pi, p in enumerate(g["tep"][:1000]):
    a_, mask = encode(p); ws = [x for s in p for x in s]
    for k in range(1, len(a_)):
        if not mask[k]: continue
        gid = gw(ws[k]); items.append((pi, ws[k - 1], ws[k], gid, (_uni[ws[k]] + 0.5) / _cnt[gid] if gid != UNKG else None, PB[j])); j += 1
assert j == len(PB) and (np.array([it[0] for it in items]) == PA).all()
def run(a, m):
    bp = collections.Counter(); bg = collections.Counter(); out = np.empty(len(items)); last = -1
    for i, (pi, pv, w, gid, sh, pb) in enumerate(items):
        if sh is None: out[i] = pb
        else:
            num = pair[(pv, w)] + m * bp[(pv, w)] + a * sh; den = pg[(pv, gid)] + m * bg[(pv, gid)] + a
            out[i] = pb / sh * num / den
        bp[(pv, w)] += 1; bg[(pv, gid)] += 1
    return out
res = {}
for a, m in itertools.product((1, 3, 10, 30, 100), (0, 3, 10, 30)):
    P = run(a, m); res[(a, m)] = P; b = -np.log2(P)
    print(f"  a {a} m {m}: 0-499 {b[PA < 500].mean():.4f}, 500-999 {b[PA >= 500].mean():.4f}", flush=True)
for mm in (0, None):                                                                                # training-only best, and overall best
    cand = [k for k in res if mm is None or k[1] == mm]; best = min(cand, key=lambda k: -np.log2(res[k][PA < 500]).mean())
    P = res[best]; tag = "train" if mm == 0 else "book"; np.savez(f"r25_ingroup_{tag}_probs.npz", p=P, para=PA)
    print(f"R25-cn {tag} chosen {best}: 500-999 {-np.log2(P[PA >= 500]).mean():.4f} (B alone {-np.log2(PB[PA >= 500]).mean():.4f})", flush=True)
