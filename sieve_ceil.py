"""CE (sieve_lang_prereg.md; owner: "do the cheat"): the theme ceiling. The TC2 program's per-position bits on the eval
positions (bits_paq_sieve_tc2_offer.npy) mixed with an oracle: the word frequencies of the target's own book. Cheat =
the whole book counted, the target included; leave-one-out = the rest of the book (what perfect theme knowledge from
everything else in the book could give). Mix P = (1-lam) P_prog + lam P_book, lam chosen on the eval positions
(oracle too). Reported on all positions and on content positions (outside the 100 most frequent words).
Run: py -3.12 -W ignore sieve_ceil.py"""
import os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); z = np.load(os.path.join(HERE, "ctxw_base.npz")); s, T, b, cnt = z["s"], z["T"], z["b"], z["cnt"]
e = np.load(os.path.join(HERE, "learned", "lx", "sieve_prim_cache", "bits_paq_sieve_tc2_offer.npy")); assert len(e) == len(T), (len(e), len(T))
fn = np.zeros(len(cnt), bool); fn[np.argsort(-cnt)[:100]] = True; y = s[T]; bk = b[T]; con = (~fn[y]) & (y != 0) & (y < len(cnt) - 1)
pp = 2.0 ** -e; R = {}
for nm, loo in (("cheat", 0), ("leave-one-out", 1)):
    pb = np.zeros(len(T))
    for k in np.unique(bk):
        m = b == k; m[0] = m[0]; ws = s[m]; ws = ws[ws != 0]; c = np.bincount(ws, minlength=len(cnt)).astype(float); N = c.sum(); i = bk == k
        pb[i] = np.maximum(c[y[i]] - loo, 0) / max(N - loo, 1)
    for part, mk in (("all", np.ones(len(T), bool)), ("content", con)):
        best = min((float(-np.log2((1 - l) * pp[mk] + l * pb[mk]).mean()), l) for l in np.linspace(0, 0.9, 91))
        R[f"{nm} {part}"] = dict(program=float(e[mk].mean()), mixed=best[0], lam=float(best[1]), n=int(mk.sum()))
        print(f"CE {nm} {part}: program {e[mk].mean():.4f} bits/word; with the book's word frequencies {best[0]:.4f} (lam {best[1]:.2f}; {mk.sum():,} positions)", flush=True)
json.dump(R, open(os.path.join(HERE, "sieve_ceil.json"), "w"), indent=1)
