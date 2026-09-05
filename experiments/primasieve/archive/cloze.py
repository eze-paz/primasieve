"""ON-DEMAND on a LOCALIZABLE task (zero-LLM, fable-scoped a97a493): vindicate the owner's 'learn only what the
question needs' thesis in its PROPER regime. Held-out-sentence CLOZE: mask a content word in sentence S (removed
from the corpus); predict it from a compositional left-bigram x right-bigram model fit ONLY on a query-RELEVANT
slice (retrieved answer-blind by content-word overlap). Compare TARGETED vs RANDOM-same-size vs FULL-corpus.

Localizable => a small slice should reach ~full accuracy => crossover M* LARGE (on-demand wins for many queries).
ANTI-RIG (I retracted 4 overclaims this session): the model is COMPOSITIONAL (predicts even when the exact
(left,target,right) trigram never occurred = genuine learning); we MEASURE the copy-fraction (correct hits whose
exact trigram IS in the slice) and KILL if >50% (lookup-with-extra-steps). Pre-registered KILL: k_0.9 > 10%
(M*<10), OR targeted-random < 0.10, OR copy-fraction > 50%. Pass claim (narrow): 'a targeted ~5% slice reaches
0.9x full cloze accuracy in Alice -> on-demand wins below ~20 queries'; says nothing about generality."""
import os, re, sys, math, random, collections
D = os.path.join(os.path.dirname(__file__), "_nldata")
STOP = set("the a an and or but if of to in on at for with by from as is are was were be been being it its this that "
           "these those he she they him her them his their i you we me us my your our not no so then than there here "
           "which who what when where how all any some more most very just now do does did have has had will would "
           "can could shall should may might must one two into out up down over under about".split())
K_GRID = [1, 2, 5, 10, 20]; NSITES = 300; RAND_SEEDS = 4

def sentences():
    raw = open(os.path.join(D, "alice.txt"), encoding="utf-8", errors="ignore").read()
    m = re.search(r"\*\*\* START OF.*?\*\*\*(.*?)\*\*\* END OF", raw, re.S); body = m.group(1) if m else raw
    out = []
    for s in re.split(r"[.!?]+", body):
        w = re.findall(r"[a-z]+", s.lower())
        if 4 <= len(w) <= 40: out.append(w)
    return out

def content(w): return [x for x in w if x not in STOP and len(x) > 1]

def build_counts(slice_sents):
    L = collections.defaultdict(collections.Counter); R = collections.defaultdict(collections.Counter)
    tri = set()
    for w in slice_sents:
        for i in range(1, len(w) - 1):
            L[w[i - 1]][w[i]] += 1; R[w[i + 1]][w[i]] += 1
            tri.add((w[i - 1], w[i], w[i + 1]))
    return L, R, tri

def predict(L, R, left, right):
    cands = set(L.get(left, {})) | set(R.get(right, {}))
    if not cands: return None
    def sc(v):
        lp = (L.get(left, {}).get(v, 0) + 0.1); rp = (R.get(right, {}).get(v, 0) + 0.1)
        return math.log(lp) + math.log(rp)
    return max(cands, key=sc)

if __name__ == "__main__":
    sents = sentences(); random.Random(2024).shuffle(sents)
    # draw N cloze sites: (sentence_index, position) for interior content words
    sites = []
    for si, w in enumerate(sents):
        for i in range(1, len(w) - 1):
            if w[i] not in STOP and len(w[i]) > 1: sites.append((si, i))
    random.Random(7).shuffle(sites); sites = sites[:NSITES]
    csets = [set(content(w)) for w in sents]                       # per-sentence content sets for retrieval
    C = sum(len(w) for w in sents)
    print(f"CLOZE (localizable on-demand) | sentences {len(sents)}, sites {len(sites)}, corpus {C} tokens\n")

    def eval_slice(get_slice):
        ok = copy = tot = 0
        for si, i in sites:
            w = sents[si]; left, target, right = w[i - 1], w[i], w[i + 1]
            sl = [sents[j] for j in get_slice(si, i) if j != si]   # NEVER include S (leakage)
            L, Rr, tri = build_counts(sl)
            p = predict(L, Rr, left, right)
            tot += 1
            if p == target:
                ok += 1
                if (left, target, right) in tri: copy += 1          # exact trigram present = copy, not learned
        return ok / tot, (copy / ok if ok else 0.0)

    # FULL corpus (amortize)
    all_idx = list(range(len(sents)))
    f_full, _ = eval_slice(lambda si, i: all_idx)
    print(f"  FULL-CORPUS (amortize): cloze acc {f_full:.3f}  (touches all {C} tokens, shared once)\n")

    print(f"  {'k%':>4} {'TARGETED':>9} {'RANDOM':>9}  copy-frac(targeted)")
    curve = {}
    for k in K_GRID:
        budget = C * k // 100
        def targeted(si, i, budget=budget):
            qset = csets[si] - {sents[si][i]}                      # answer-blind: drop the masked word
            order = sorted(range(len(sents)), key=lambda j: -len(qset & csets[j]))
            out = []; tot = 0
            for j in order:
                if j == si: continue
                out.append(j); tot += len(sents[j])
                if tot >= budget: break
            return out
        a_t, copyf = eval_slice(lambda si, i: targeted(si, i))
        # random equal-size
        rr = []
        for seed in range(RAND_SEEDS):
            rng = random.Random(seed)
            def randslice(si, i, rng=rng, budget=budget):
                idx = list(range(len(sents))); rng.shuffle(idx); out = []; tot = 0
                for j in idx:
                    if j == si: continue
                    out.append(j); tot += len(sents[j])
                    if tot >= budget: break
                return out
            rr.append(eval_slice(lambda si, i: randslice(si, i))[0])
        a_r = sum(rr) / len(rr)
        curve[k] = (a_t, a_r, copyf)
        print(f"  {k:>3}% {a_t:>9.3f} {a_r:>9.3f}       {copyf:.2f}")

    beats = [curve[k][0] - curve[k][1] for k in K_GRID]
    k90 = next((k for k in K_GRID if curve[k][0] >= 0.90 * f_full), None)
    Mstar = (100 // k90) if k90 else None
    maxcopy = max(curve[k][2] for k in K_GRID)
    print(f"\n  targeted-random: {[f'{b:+.2f}' for b in beats]} (need >=+0.10)")
    print(f"  reaches 0.90x full ({0.90*f_full:.3f}) at k={k90}% -> M* = 100/k = {Mstar} queries (on-demand wins below M*)"
          if k90 else "  never reaches 0.90x full within 20% (KILL-b: amortization wins)")
    print(f"  copy-fraction (must be <=0.50, else lookup-not-learning): max {maxcopy:.2f}")
    kill = (k90 is None or k90 > 10) or (max(beats) < 0.10) or (maxcopy > 0.50)
    print(f"\n  RESULT: {'KILL (on-demand not vindicated: '+('needs too-large slice' if (k90 is None or k90>10) else 'targeting weak' if max(beats)<0.10 else 'copy-not-learning')+')' if kill else 'PASS -- a targeted '+str(k90)+'% slice reaches 0.9x full cloze acc, beats random by '+f'{max(beats):+.2f}'+', learns (copy-frac '+f'{maxcopy:.2f}'+') -> on-demand wins below M*='+str(Mstar)+' queries'}."
          f"  (scope: one corpus/task/curve; NOT thesis-general.)")