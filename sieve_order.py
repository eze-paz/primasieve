"""S3 (sieve_lang_prereg.md): Sieve on word order. The same held-out sentences as NC2 (learned/lx/lr_unscr.py). The
oracle is attestation in the library (358 training + 400 extra books): numpy builds the attested n-gram sets for the
words that occur in these sentences; the engine side is stdlib. GENERATE every order of the bag whose adjacent pairs,
first word (sentence start) and last word (sentence end) are attested; COLLECT trigram then 4-gram lookups in
best-split order (core.collect.best_split), rejecting survivors that contain an unattested one; COMMIT a single
survivor, else ABSTAIN (core.verdict.score_two_mode). When more than 200 orders survive, every probe is looked up at once
(best-split order is kept below that). Run: py -3.12 sieve_order.py [scored|dev]"""
import os, sys, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from core.collect import best_split
from core.verdict import score_two_mode, line
import numpy as np, pickle, warnings
warnings.filterwarnings("ignore")
LX = os.path.join(HERE, "learned", "lx"); t0 = time.time(); CAP = 20000
MAXK = int(sys.argv[sys.argv.index("--maxk") + 1]) if "--maxk" in sys.argv else 4      # descriptive (post hoc): stop the channel at pairs / trigrams
def log(*a): print(*a, f"({time.time() - t0:.0f} s)", flush=True)
Z = np.load(os.path.join(LX, "lx_tokens.npz")); D = np.load(os.path.join(LX, "lx_docs.npz")); X = np.load(os.path.join(LX, "lx_library.npz"))
B = np.load(os.path.join(LX, "lr_base.npz")); UNK = int(B["gid"].shape[0]) - 1; cut = int(B["dvcut"])
# ---- the same sentences as NC2 ----
folds = []
for name, tok, sid in (("scored", Z["te"].astype(np.int64), Z["tes"]), ("dev", D["dv"][:cut].astype(np.int64), D["dvs"][:cut])):
    rng = np.random.default_rng(3); us, start, cnt = np.unique(sid, return_index=True, return_counts=True)
    ok = [(a, c) for a, c in zip(start, cnt) if 5 <= c <= 8 and (tok[a:a + c] < UNK).all()]
    pick = [ok[i] for i in rng.choice(len(ok), min(2000, len(ok)), replace=False)]
    folds.append((name, [tuple(int(w) for w in tok[a:a + c]) for a, c in pick]))
# ---- the oracle: attested n-grams in the library ----
L = np.r_[Z["tr"].astype(np.int64), X["lib"].astype(np.int64)]; LS = np.r_[Z["trs"].astype(np.int64), X["libs"].astype(np.int64) + int(Z["trs"].max()) + 1]
P = np.int64(1_000_003)
def hashes(a, k):
    h = np.zeros(len(a) - k + 1, np.int64)
    for j in range(k): h = h * P + a[j:len(a) - k + 1 + j]
    return h
first = np.r_[True, LS[1:] != LS[:-1]]; last = np.r_[LS[1:] != LS[:-1], True]
STARTS = set(np.unique(L[first]).tolist()); ENDS = set(np.unique(L[last]).tolist())
ATT = {}; cache = os.path.join(LX, "sieve_order_oracle.pkl")
if os.path.exists(cache): ATT, STARTS, ENDS = pickle.load(open(cache, "rb"))
for k in ((2, 3, 4) if not ATT else ()):
    want = set()
    for _, ss in folds:
        for s in ss:
            w = sorted(set(s))
            if k == 2: want |= {a * P + b for a in w for b in w}
            else:
                import itertools
                for t in itertools.permutations(s, k):
                    h = 0
                    for x in t: h = h * P + x
                    want.add(h)
    want = np.array(sorted(want), np.int64); h = hashes(L, k); same = LS[k - 1:] == LS[:len(LS) - k + 1]
    ATT[k] = set(np.intersect1d(h[same], want).tolist()); log(f"oracle: {len(ATT[k]):,} of {len(want):,} candidate {k}-grams attested")
if not os.path.exists(cache): pickle.dump((ATT, STARTS, ENDS), open(cache, "wb"))
def att(t):
    h = 0
    for x in t: h = h * P + x
    return h in ATT[len(t)]
# ---- Sieve ----
def generate(bag):
    """every distinct order whose adjacent pairs, first and last word are attested (REJECT inside GENERATE)"""
    out = set(); n = len(bag)
    def dfs(seq, used):
        if len(out) > CAP: return
        if len(seq) == n:
            if seq[-1] in ENDS: out.add(tuple(seq))
            return
        tried = set()
        for i in range(n):
            if used >> i & 1 or bag[i] in tried: continue
            tried.add(bag[i])
            if (not seq and bag[i] in STARTS) or (seq and att((seq[-1], bag[i]))): dfs(seq + [bag[i]], used | 1 << i)
    dfs([], 0); return list(out)
def grams(h, k): return {h[i:i + k] for i in range(len(h) - k + 1)}
stats = collections.Counter()
def sieve(bag):
    S = generate(bag); stats["generated"] += len(S)
    if len(S) > CAP: stats["over cap"] += 1; return None
    for k in [k for k in (3, 4) if k <= MAXK]:
        if len(S) <= 1: break
        G = {h: grams(h, k) for h in S}; checked = set()
        if len(S) > 200:                                                              # bulk: look up every probe once (lookups counted)
            probes = {q for h in S for q in G[h]}; bad = {q for q in probes if not att(q)}; stats["lookups"] += len(probes); checked |= probes
            S = [h for h in S if not (G[h] & bad)]
        while len(S) > 1:
            probes = {q for h in S for q in G[h]} - checked
            q = best_split(S, probes, lambda h, q: q in G[h])
            if q is None: break
            checked.add(q); stats["lookups"] += 1
            if not att(q): S = [h for h in S if q not in G[h]]
    stats["survivors 1"] += len(S) == 1; stats["survivors 0"] += len(S) == 0; stats["survivors >1"] += len(S) > 1
    return S[0] if len(S) == 1 else None
for name, ss in [f for f in folds if not {"scored", "dev"} & set(sys.argv) or f[0] in sys.argv]:
    stats.clear()
    def truth_alive(s): return s[0] in STARTS and s[-1] in ENDS and all(att(s[i:i + 2]) for i in range(len(s) - 1))
    alive = sum(truth_alive(s) for s in ss)
    r = score_two_mode(lambda s: sieve(tuple(sorted(s))), [(s, s) for s in ss])
    log(f"{name}: {len(ss)} sentences; true order survives the pair channel in {alive}"); print(line(f"Sieve, n-grams <= {MAXK}", r))
    print(f"   singleton {stats['survivors 1']}, empty {stats['survivors 0']}, several left {stats['survivors >1']}, over the {CAP:,} cap {stats['over cap']}; "
          f"orders generated {stats['generated']:,}; lookups {stats['lookups']:,}")
