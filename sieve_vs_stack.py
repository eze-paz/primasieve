"""ST1 (sieve_lang_prereg.md): Sieve vs Stack per position on the 50,114 scored positions. Stack = stack + lookup
everywhere + copy (lr_c12.py, lr_c12_bits_scored.npz); Sieve = SR's programs (sieve_fs2.py eval, bits_*.npz); LM =
RWKV-7 0.4B. Answers checked equal (Stack's unknown-word ids above the unknown id count as unknown). 95% intervals of
each mean by bootstrap over paragraphs (2,000 resamples, seed 0); means per word kind.
Run: py -3.12 -W ignore sieve_vs_stack.py"""
import os
import numpy as np
LX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned", "lx")
S = np.load(os.path.join(LX, "lr_c12_bits_scored.npz")); CD = os.path.join(LX, "sieve_fs2_cache")
ys = S["y"]; para = S["para"]; book = S["book"]
M = {"Stack (stack + lookup + copy)": S["best"], "LM (RWKV-7 0.4B)": S["llm"]}
for tag, nm in (("1", "Sieve SR selected (calibration-filtered)"), ("1_0.02_1000_0.25", "Sieve SR MDL-best"), ("sieve_fs2_st3_mdl", "Sieve ST3")):
    z = np.load(os.path.join(CD, f"bits_{tag}.npz")); y = z["y"]; unk = y.max()
    assert len(y) == len(ys) and np.all(np.minimum(y, unk) == np.minimum(ys, unk)), "positions do not align"
    M[nm] = z["bits"]
print(f"aligned: {len(ys):,} positions, answers equal")
u, inv = np.unique(para, return_inverse=True); rng = np.random.default_rng(0); B = 2000
sums = {k: np.bincount(inv, weights=v) for k, v in M.items()}; cnt = np.bincount(inv)
draws = rng.integers(0, len(u), (B, len(u)))
for k, v in M.items():
    bs = np.array([sums[k][d].sum() / cnt[d].sum() for d in draws]); lo, hi = np.quantile(bs, [0.025, 0.975])
    print(f"   {k}: mean {v.mean():.4f} bits/word, 95% interval {lo:.4f} - {hi:.4f}")
seen = np.zeros(len(ys), bool); first = {}
for i, (b, w) in enumerate(zip(book, ys)): seen[i] = (b, w) in first; first[(b, w)] = 1
kind = np.where(ys >= np.load(os.path.join(LX, "lx_tokens.npz"))["tr"].max() + 1, "unknown", np.where(seen, "repeat in book", np.where(ys <= 150, "function word", "content word")))
for kd in ("repeat in book", "function word", "content word", "unknown"):
    mk = kind == kd; print(f"   {kd:15s} {mk.sum():6,} positions: " + "; ".join(f"{k.split(' (')[0]} {v[mk].mean():.3f}" for k, v in M.items()))
