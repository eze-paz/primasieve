"""BEAT-ZHIKOV attempt (zero-LLM): the unigram Ent-MDL pipeline in seg_zhikov.py MATCHES Zhikov 2010 (~0.741 vs
published 0.754) but does NOT beat it. The lever fable named for beating it = a BIGRAM word model (collocation
structure -- unigram MDL systematically merges frequent word pairs). seg_zhikov.bigram_viterbi_em already
implements iterated Viterbi-EM with a smoothed bigram P(w|prev) + char-model novel-word cost, seeded from
bidirectional branching entropy. This runs it on the SAME real br-phono corpus + SAME token-F metric and reports
whether bigram beats the unigram-MDL baseline. HONEST: same-corpus, same-metric head-to-head; report beat or not.
Controls carried from seg_zhikov (no-entropy/shuffle) validate the unigram arm; the bigram arm's own control is the
unigram arm itself (does adding collocation structure help?)."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import seg_zhikov as Z

if __name__ == "__main__":
    utts = Z.load_brp(); gold = Z.gold_spans(utts); streams = [s for s, _ in gold]
    print(f"br-phono: {len(utts)} utts, {sum(len(w) for w in utts)} tokens  | metric = word-token F")
    print(f"Zhikov 2010 published Ent-MDL: F=0.754 | overall record (adaptor grammars): ~0.87\n")

    # UNIGRAM baseline (the faithful Zhikov pipeline)
    t0 = time.time()
    scores = Z.entropy_abs(streams, k=4)
    low = Z.percentile([scores[u][g] for u in range(len(streams)) for g in range(1, len(streams[u]))], 35)
    pu, mu = Z.zhikov_segment(streams, k=4, kappa=1.5, rounds=8, sweeps=6, scores=scores, low_thresh=low)
    fu, Pu, Ru = Z.token_f(gold, pu)
    print(f"  UNIGRAM Ent-MDL (baseline):  token F={fu:.3f}  P={Pu:.3f} R={Ru:.3f}   [{time.time()-t0:.0f}s]")

    # BIGRAM Viterbi-EM (the beat attempt) -- sweep a couple of key knobs, pick best by DL-agnostic... no: pick by
    # token-F would be tuning-to-test. Report the DEFAULT config's F (pre-registered), plus a small honest sweep
    # shown transparently so the reader sees the spread, not a cherry-pick.
    for (iters, alpha, prem) in [(8, 0.5, 2.0), (10, 0.2, 1.5)]:
        t0 = time.time()
        pb = Z.bigram_viterbi_em(streams, iters=iters, maxlen=9, alpha=alpha, novel_premium=prem)
        fb, Pb, Rb = Z.token_f(gold, pb)
        tag = "DEFAULT" if (iters, alpha, prem) == (8, 0.5, 2.0) else "alt"
        print(f"  BIGRAM Viterbi-EM ({tag}): token F={fb:.3f}  P={Pb:.3f} R={Rb:.3f}  "
              f"(iters={iters} alpha={alpha} prem={prem}) [{time.time()-t0:.0f}s]  delta vs unigram {fb-fu:+.3f}")
    print("\n  HONEST: pre-registered claim = 'bigram collocation modeling beats unigram Ent-MDL on br-phono token-F.'")
    print("  A beat here means we EXCEED our faithful Zhikov reimplementation on the SAME corpus/metric, not the")
    print("  ~0.87 adaptor-grammar record (that needs morphology). Report the number straight.")