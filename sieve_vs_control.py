"""fair_control_prereg.md: the from-scratch network (kaggle_fair_control/fair_control.py -> fair_control_bits_<size>.npz)
against Sieve, Stack and the LM per position on the same 50,114 scored positions. Alignment: answers checked equal.
95% intervals by bootstrap over paragraphs (2,000 resamples, seed 0, the ST1 recipe); means per word kind and per
sentence position. Run: py -3.12 -W ignore sieve_vs_control.py [fair_control_bits_S.npz ...]"""
import os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); LX = os.path.join(HERE, "learned", "lx")
S = np.load(os.path.join(LX, "lr_c12_bits_scored.npz")); ys = S["y"]; para = S["para"]; book = S["book"]
Z = np.load(os.path.join(LX, "lx_tokens.npz")); UNK = Z["tr"].max() + 1
M = {"Stack": S["best"], "LM (RWKV-7 0.4B, 3T tokens)": S["llm"]}
sv = np.load(os.path.join(LX, "sieve_prim_cache", "bits_online.npy")); assert len(sv) == len(ys); M["Sieve (L4 + L7)"] = sv
te = Z["te"].astype(np.int64); b = np.nonzero(Z["tes"][1:] != Z["tes"][:-1])[0] + 1; te = np.insert(te, b, 0)
Th = np.arange(1, len(te)); Th = Th[(te[Th] != 0) & (te[Th - 1] != 0)]; assert len(Th) == len(ys)
assert np.all(np.minimum(te[Th], UNK) == np.minimum(ys, UNK)), "scored stream does not align with lr_c12 answers"
last0 = np.maximum.accumulate(np.where(te == 0, np.arange(len(te)), 0)); spos = Th - last0[Th]          # word k of the sentence (k >= 2)
for f in sys.argv[1:]:
    c = np.load(f); assert np.array_equal(c["pos"], Th), f"{f}: positions differ"; assert np.array_equal(c["y"], te[Th])
    M[f"control {os.path.basename(f)} ({int(c['params']):,} params, epoch {int(c['epoch'])}, dev {float(c['dev_bits']):.4f})"] = c["bits"]
print(f"aligned: {len(ys):,} positions, answers equal")
u, inv = np.unique(para, return_inverse=True); rng = np.random.default_rng(0); B = 2000
sums = {k: np.bincount(inv, weights=v) for k, v in M.items()}; cnt = np.bincount(inv); draws = rng.integers(0, len(u), (B, len(u)))
iv = {}
for k, v in M.items():
    bs = np.array([sums[k][d].sum() / cnt[d].sum() for d in draws]); iv[k] = np.quantile(bs, [0.025, 0.975])
    print(f"   {k}: mean {v.mean():.4f} bits/word [{v.sum():,.0f} bits], 95% interval {iv[k][0]:.4f} - {iv[k][1]:.4f}")
sk = "Sieve (L4 + L7)"
for k in M:
    if k.startswith("control"):
        a, bb = M[sk].mean(), M[k].mean(); lo_s, hi_s = iv[sk]; lo_c, hi_c = iv[k]
        verdict = "PASS (Sieve ahead; its mean outside the control's interval)" if a < bb and (a < lo_c or a > hi_c) else \
                  "KILL (control ahead; its mean outside Sieve's interval)" if bb < a and (bb < lo_s or bb > hi_s) else "PARTIAL (level)"
        print(f"   verdict vs {k.split(' (')[0]}: {verdict}")
seen = np.zeros(len(ys), bool); first = {}
for i, (bk, w) in enumerate(zip(book, ys)): seen[i] = (bk, w) in first; first[(bk, w)] = 1
kind = np.where(ys >= UNK, "unknown", np.where(seen, "repeat in book", np.where(ys <= 150, "function word", "content word")))
short = lambda k: k.split(" (")[0]
for kd in ("repeat in book", "function word", "content word", "unknown"):
    mk = kind == kd; print(f"   {kd:15s} {mk.sum():6,} positions: " + "; ".join(f"{short(k)} {v[mk].mean():.3f}" for k, v in M.items()))
for lo, hi in ((2, 2), (3, 5), (6, 10), (11, 10 ** 9)):
    mk = (spos >= lo) & (spos <= hi); print(f"   words {lo}-{min(hi, 999)} of sentence {mk.sum():6,} positions: " + "; ".join(f"{short(k)} {v[mk].mean():.3f}" for k, v in M.items()))
