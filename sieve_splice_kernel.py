"""SPLICE (sieve_lang_prereg.md): how coverage of real continuations grows with training words, to predict whether more
PG-19 text is worth downloading. Training stream = BIG's books stream (MT 27M training words, then the four PG-19
half-shards, 191M). Held-out = MT books eval text (unchanged). For each held-out position t (true word not UNK, not a
boundary target excluded) and each context length k, "covered at N" = the (k+1)-gram ending at t occurs in the first N
training words. The generator's key is 4 words, so unseen 5-gram share = where it cannot continue a real source with the
true word = splice pressure. One hash pass per n: first training occurrence of every query n-gram, then any prefix N is
a comparison. Smoke: SP_SMOKE=1 SP_DATA=.. SP_OUT=.. (MT only)"""
import glob, os, time, json, numpy as np
SMOKE = bool(os.environ.get("SP_SMOKE")); T0 = time.time(); M64 = np.uint64(0x9E3779B97F4A7C15); V = 60000; UNK = V + 1
NQ = 20_000 if SMOKE else 200_000; NS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 13)          # n-gram orders = context k + 1
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("SP_OUT", ".")
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
z = np.load([x for x in find("*_data.npz", "SP_DATA") if os.path.basename(x).startswith("books")][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"])
ev = S[ntr:]; tr = [S[:ntr]]; marks = [ntr // 4, ntr // 2, ntr]
if not SMOKE:
    for p in ("0_0", "0_1", "1_0", "1_1"):
        a = np.load(glob.glob(f"/kaggle/input/**/tok_books_{p}.npz", recursive=True)[0])["S"].astype(np.int64); tr.append(a); marks.append(marks[-1] + len(a))
tr = np.concatenate(tr); del S; NT = len(tr); log(f"training {NT:,} words, prefixes {marks}")
g = np.random.default_rng(0); cand = np.arange(max(NS), len(ev)); cand = cand[(ev[cand] != UNK) & (ev[cand] != 0)]; q = np.sort(g.choice(cand, NQ, replace=False))
unk_tr = [float((tr[:m] == UNK).mean()) for m in marks]; unk_ctx = float(np.mean([(ev[t - 4:t] == UNK).any() for t in q]))
def hashes(x, n, ends):
    h = np.zeros(len(ends), np.uint64)
    with np.errstate(over="ignore"):
        for i in range(n - 1, -1, -1): h = h * M64 + (x[ends - i].astype(np.uint64) + np.uint64(1))
    return h
first = {}
for n in NS:
    hq = hashes(ev, n, q); o = np.argsort(hq); hs = hq[o]; f = np.full(NQ, np.iinfo(np.int64).max)
    for c0 in range(n - 1, NT, 50_000_000):                                                   # chunks keep memory bounded
        ends = np.arange(c0, min(c0 + 50_000_000, NT)); ht = hashes(tr, n, ends); i = np.minimum(np.searchsorted(hs, ht), NQ - 1); hit = np.nonzero(hs[i] == ht)[0]
        if len(hit):
            u, fi = np.unique(i[hit], return_index=True); pos = ends[hit[fi]]; cur = f[o[u]]; f[o[u]] = np.minimum(cur, pos)
        # equal hashes among queries (same n-gram twice) share one slot in hs: copy below
    srt = hs; grp = np.r_[0, np.cumsum(srt[1:] != srt[:-1])]; fo = f[o]; best = np.full(grp[-1] + 1, np.iinfo(np.int64).max); np.minimum.at(best, grp, fo); f[o] = best[grp]
    first[n] = f; log(f"n {n}: covered at 191M {float((f < NT).mean()):.4f}")
R = dict(marks=marks, unk_train=unk_tr, unk_in_query_context=unk_ctx, nq=NQ, by_prefix={})
for m in marks:
    cov = {n: float((first[n] < m).mean()) for n in NS}; L = np.zeros(NQ)
    for n in NS: L = np.where(first[n] < m, n - 1, L)                                          # longest covered context (on the measured grid)
    R["by_prefix"][str(m)] = dict(covered=cov, unseen5=1 - cov[5], mean_context=float(L.mean())); log(f"N {m:,}: unseen 5-gram {1 - cov[5]:.4f}, covered {cov}, mean context {L.mean():.3f}")
# fits on the PG-19-era prefixes (>= 27M) and on all; predictions at 0.5B, 1B, 1.9B (full PG-19 train)
# (a) Wyner-Ziv: longest match grows linearly in log2 N (slope = 1 / entropy rate in bits per word): mean_context = a + b log2 N
# (b) coverage of (k+1)-grams grows as a power law while small: covered = a N^b
x2 = np.log2(np.array(marks, float)); R["fit"] = {}; PN = (191e6, 5e8, 1e9, 1.9e9)
for nm, sel in (("ge27M", np.array(marks) >= marks[2]), ("all", np.ones(len(marks), bool))):
    y = np.array([R["by_prefix"][str(m)]["mean_context"] for m in marks]); b, a = np.polyfit(x2[sel], y[sel], 1)
    R["fit"][f"{nm}_meanctx"] = dict(words_per_doubling=float(b), pred={str(N): float(a + b * np.log2(N)) for N in PN}); log(f"fit {nm} mean context: {b:.4f} words per doubling, predicted {R['fit'][f'{nm}_meanctx']['pred']}")
    for n in (4, 5, 6):
        y = np.log2(np.array([R["by_prefix"][str(m)]["covered"][n] for m in marks])); b, a = np.polyfit(x2[sel], y[sel], 1)
        R["fit"][f"{nm}_cov{n}"] = dict(exponent=float(b), pred={str(N): float(min(1.0, 2 ** (a + b * np.log2(N)))) for N in PN})
        log(f"fit {nm} coverage n{n}: exponent {b:.4f}, predicted covered {R['fit'][f'{nm}_cov{n}']['pred']}")
json.dump(R, open(os.path.join(OUTD, "splice.json"), "w"), indent=1); log("saved")
