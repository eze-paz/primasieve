"""ON-DEMAND / JIT LEARNING (zero-LLM, fable-scoped a84d98c): tests the owner's efficiency thesis -- 'learn only
what the PRESENT question needs, no more.' For each query utterance, learn a lexicon from ONLY a query-RELEVANT
corpus slice (retrieved by shared char-4-grams, answer-independent), segment the query, held-out. Compare TARGETED
vs RANDOM-same-size (is targeting load-bearing?) vs FULL-corpus (amortize-everything = the LLM analog) vs a
DIFFERENT-query slice (targeting vs retrieved-text-style). Metric = F1(s) curves + crossover M* = C/s.

Anti-overclaim (I retracted 3 overclaims earlier this session): pre-registered s-grid + KILL; retrieval index cost
charged to BOTH arms (shared, reported separately); compared quantity = LEARNER WORK (chars fed to MDL) per query.
KILL: (a) targeted-random < 0.05 F1 at every s (CI includes 0); or (b) targeted needs s>=25% to reach 0.90x full
(M*<=4). TRUE claim if passed: 'a query-targeted 10% slice recovers >=90% of full-corpus F1 and beats equal-size
random; per-query learning is cheaper than amortization only when queries < C/s.' NOT 'engine beats an LLM.'"""
import os, sys, math, random, collections
sys.path.insert(0, os.path.dirname(__file__))
import seg

S_GRID = [1, 2, 5, 10, 25]          # pre-registered slice sizes (% of corpus)
NQ = 50                              # held-out queries
RAND_SEEDS = 5

def learn_lexicon(streams, iters=4, k=3):
    if not streams: return {}, (lambda w: len(w) * math.log2(27) + 6.0)
    ctx = seg.train_entropy(streams, k)
    tr_seg = [seg.segment(s, seg.fwd_entropy(s, ctx, k), 0.0) for s in streams]
    nb = lambda w: len(w) * math.log2(27) + 6.0
    for _ in range(iters):
        c = collections.Counter(t for toks in tr_seg for t in toks); N = sum(c.values()) or 1
        logp = {w: -math.log2(n / N) for w, n in c.items()}
        new = []
        for s in streams:
            pts = sorted({0, len(s)} | seg.viterbi(s, logp, nb))
            new.append([s[pts[i]:pts[i + 1]] for i in range(len(pts) - 1)])
        tr_seg = new
    c = collections.Counter(t for toks in tr_seg for t in toks); N = sum(c.values()) or 1
    return {w: -math.log2(n / N) for w, n in c.items()}, nb

def f1_on(queries_gold, logp, nb):
    pred = [seg.viterbi(s, logp, nb) for s, _ in queries_gold]
    return seg.token_f1(pred, queries_gold)

def grams(s, n=4): return set(s[i:i + n] for i in range(len(s) - n + 1))

def retrieve(qstream, corpus, budget):
    qg = grams(qstream)
    scored = sorted(corpus, key=lambda t: -len(qg & t[1]))     # t=(stream,gramset)
    out = []; tot = 0
    for stream, _ in scored:
        out.append(stream); tot += len(stream)
        if tot >= budget: break
    return out, tot

if __name__ == "__main__":
    utts = seg.load_utterances(); random.Random(2024).shuffle(utts)
    queries = utts[:NQ]; rest = utts[NQ:]
    q_gold = [seg.gold_bounds(w) for w in queries]
    q_streams = [s for s, _ in q_gold]
    # LEAKAGE guard: drop any corpus sentence sharing >=8 contiguous chars with a query, and the queries themselves
    def leaks(cs):
        for qs in q_streams:
            for i in range(len(cs) - 7):
                if cs[i:i + 8] in qs: return True
        return False
    corpus_words = [w for w in rest if not leaks("".join(w))]
    corpus = [("".join(w), grams("".join(w))) for w in corpus_words]
    C = sum(len(s) for s, _ in corpus)
    print(f"ON-DEMAND | queries {NQ}, corpus {len(corpus)} sents / {C} chars (leakage-filtered)\n")

    # FULL-corpus baseline (amortize everything)
    logp_full, nb = learn_lexicon([s for s, _ in corpus])
    f_full = f1_on(q_gold, logp_full, nb)
    print(f"  FULL-CORPUS (amortize): F1 {f_full:.3f}  (learner work per query = {C} chars, shared once)\n")

    print(f"  {'s%':>4} {'TARGETED':>9} {'RANDOM':>9} {'DIFF-Q':>9}  (chars/query)")
    curve = {}
    for s in S_GRID:
        budget = C * s // 100
        # TARGETED: per-query relevant slice
        tf = []
        for (qs, _), qg1 in zip(q_gold, q_gold):
            sl, touched = retrieve(qs, corpus, budget)
            lp, _ = learn_lexicon(sl)
            tf.append(seg.token_f1([seg.viterbi(qs, lp, nb)], [qg1]))
        # RANDOM same-size slice (avg seeds)
        rf = []
        for seed in range(RAND_SEEDS):
            rng = random.Random(seed)
            perq = []
            for qg1 in q_gold:
                sl = []; tot = 0; pool = corpus[:]; rng.shuffle(pool)
                for stream, _ in pool:
                    sl.append(stream); tot += len(stream)
                    if tot >= budget: break
                lp, _ = learn_lexicon(sl)
                perq.append(seg.token_f1([seg.viterbi(qg1[0], lp, nb)], [qg1]))
            rf.append(sum(perq) / len(perq))
        # DIFF-Q control: slice retrieved by a DIFFERENT query
        df = []
        for i, qg1 in enumerate(q_gold):
            other = q_streams[(i + 7) % NQ]
            sl, _ = retrieve(other, corpus, budget)
            lp, _ = learn_lexicon(sl)
            df.append(seg.token_f1([seg.viterbi(qg1[0], lp, nb)], [qg1]))
        t = sum(tf) / len(tf); r = sum(rf) / len(rf); d = sum(df) / len(df)
        curve[s] = (t, r, d)
        print(f"  {s:>3}% {t:>9.3f} {r:>9.3f} {d:>9.3f}  ({budget})")

    # verdict
    beats = [curve[s][0] - curve[s][1] for s in S_GRID]
    s90 = next((s for s in S_GRID if curve[s][0] >= 0.90 * f_full), None)
    Mstar = (C // (C * s90 // 100)) if s90 else None
    print(f"\n  targeting effect (targeted-random): {[f'{b:+.2f}' for b in beats]} (need >=+0.05 at some s)")
    print(f"  reaches 0.90x full ({0.90*f_full:.3f}) at s = {s90}% -> crossover M* = C/s = {Mstar} queries "
          f"(on-demand cheaper than full-corpus below M*)" if s90 else
          f"  never reaches 0.90x full within 25% -> amortization wins (KILL-b)")
    kill = (max(beats) < 0.05) or (s90 is None) or (Mstar is not None and Mstar <= 4)
    print(f"\n  RESULT: {'KILL -- targeting not load-bearing OR amortization wins at realistic query counts' if kill else 'PASS -- query-targeted slice recovers >=90% full F1 at s='+str(s90)+'%, beats random by '+f'{max(beats):+.2f}'+'; per-query cheaper below M*='+str(Mstar)+' queries'}."
          f"  (honest scope: single-utterance segmentation only; NOT 'beats an LLM'.)")