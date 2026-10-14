"""R25-cj: count the text as you read it (dynamic n-gram cache on top of the best static counter, o5mxa).
Reading the 1,000 held-out paragraphs in order (across sentences and paragraphs), phrase counts of the text read so
far (1-5 words) are kept; for each prediction, starting from the static Kneser-Ney probability p, for context lengths
1..4 that occurred before: p <- (count(context, w) + beta * p) / (count(context) + beta) -- the text's own phrases
pull the prediction toward what this book actually says. Only past text is used. beta from {0.5, 1, 2, 4, 8, 16} chosen
on paragraphs 0-499; reported on 500-999. Saved with the static match depth as r25_kndyn_probs.npz (usable as K).
Run: py -3.12 r25_kndyn.py"""
import os, sys, math, time, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
ARGV0 = list(sys.argv); sys.argv = ["r25_kn2.py", "--order", "5", "--mkn", "--cross", "--all-text"]
src = open("r25_kn2.py", encoding="utf-8").read(); src = src[:src.index("P, A, Dp = [], [], []")]
K = {"__name__": "r25_kn2_defs", "__file__": os.path.join(HERE, "r25_kn2.py")}; exec(compile(src, "r25_kn2.py", "exec"), K)
prob, wid, RARE, rare_share, NMAX, tep = K["prob"], K["wid"], K["RARE"], K["rare_share"], K["NMAX"], K["g"]["tep"][:1000]
t0 = time.time(); seq, rows = [], []                                                              # seq: the whole held-out stream; rows: (position, paragraph, static p, depth)
for pi, pg in enumerate(tep):
    seq.append(0)
    for s in pg:
        ids = [wid.get(x, RARE) for x in s]
        for i, w in enumerate(ids):
            if i >= 1:
                q, d = prob(seq[-NMAX:], w)
                if w == RARE: q *= rare_share(s[i])
                rows.append((len(seq), pi, q, d, rare_share(s[i]) if w == RARE else 1.0))
            seq.append(w)
print(f"R25-cj static probabilities for {len(rows)} predictions ({time.time() - t0:.0f} s)", flush=True)
BML = []
def run(beta):
    cnt = collections.Counter(); ctx = collections.Counter(); out = []; j = 0; BML.clear()
    for t in range(len(seq)):
        while j < len(rows) and rows[j][0] == t:                                                  # predict seq[t] before counting it
            _, _, q, _, rs = rows[j]; w = seq[t]; p = q; m = 0
            for L in range(1, NMAX):
                if t - L < 0: break
                h = tuple(seq[t - L:t]); n = ctx[h]
                if n == 0: break
                m = L
                bL = beta[L - 1] if isinstance(beta, tuple) else beta
                p = (cnt[h + (w,)] * rs + bL * p) / (n + bL)
            out.append(p); BML.append(m); j += 1
        for L in range(1, NMAX):                                                                  # then count the phrases ending at t
            if t - L < 0: break
            h = tuple(seq[t - L:t]); ctx[h] += 1; cnt[h + (seq[t],)] += 1
    return np.array(out)
para = np.array([r[1] for r in rows]); tr, te = para < 500, para >= 500; best = None
BETAS = [tuple(b1 / f ** (L - 1) for L in range(1, NMAX)) for b1 in (64, 256, 1024, 4096) for f in (2, 4, 8, 16)] if "--perlen" in ARGV0 else ((16, 32, 64, 128, 256, 512) if "--wide" in ARGV0 else (0.5, 1, 2, 4, 8, 16))   # R25-cl: one strength per context length
for beta in BETAS:
    P = run(beta); b = -np.log2(P[tr]).mean(); print(f"  beta {beta}: paragraphs 0-499 {b:.4f}", flush=True)
    if best is None or b < best[0]: best = (b, beta, P)
_, beta, P = best; stat = np.array([r[2] for r in rows])
np.savez("r25_kndyn_perlen_probs.npz" if "--perlen" in ARGV0 else "r25_kndyn_wide_probs.npz" if "--wide" in ARGV0 else "r25_kndyn_probs.npz", p=P, para=para, deep=np.array([r[3] for r in rows]), bml=np.array(BML))
print(f"R25-cj live phrase counting (beta {beta}): paragraphs 500-999 {-np.log2(P[te]).mean():.4f} bits/word (static o5mxa {-np.log2(stat[te]).mean():.4f}) ({time.time() - t0:.0f} s)", flush=True)
