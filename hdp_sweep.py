"""ALPHA-1 SENSITIVITY with GOLD-BLIND selection. The committed a1=3000 over-merges (bigram backs off to unigram
-> F=0.548 < Zhikov). a1 is mis-specified for this corpus. DISCIPLINED fix (NOT tuning-to-F): sweep a1, select by
the MODEL's own corpus log-likelihood (gold-blind, legitimate Bayesian model selection), and report token-F AT the
LL-selected a1. If the LL-selected bigram beats unigram and approaches ~0.72, the mechanism works and I mis-committed
a1; if not, the null stands. Also reports unigram-DP as the a1->inf reference. Full corpus, 1 seed, 130 sweeps."""
import sys, os, random, time
sys.path.insert(0, os.path.dirname(__file__))
import hdp_seg as H, seg_zhikov as Z

SW = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--sweeps=")), 130))
utts = Z.load_brp(); random.Random(2024).shuffle(utts)
gold = Z.gold_spans(utts); streams = [s for s, _ in gold]
gml = sum(len(w) for u in utts for w in u) / sum(len(u) for u in utts)
print(f"FULL br-phono {len(utts)} utts / {sum(len(w) for w in utts)} tokens | gold mlen {gml:.2f} | sweeps={SW}")
print(f"Zhikov (same scorer) = 0.741 | committed a1=3000 over-merged to 0.548\n")

def fit(bigram, a0, a1, tag):
    logP0 = H.make_P0(streams, p_hash=0.2 if bigram else 0.5)
    dp = H.DP(logP0, bigram, a0, a1)
    B = H.init_boundaries(streams, "entropy", 0); H.build_state(dp, streams, B)
    rng = random.Random(1)
    for it in range(1, SW + 1):
        H.gibbs_sweep(dp, streams, B, H.anneal_temp(it, SW), rng)
    f, P, R = Z.token_f(gold, [set(c) for c in B])
    ll = dp.corpus_ll(streams, B); ty, ml, one = H.degeneracy(streams, B)
    print(f"  {tag:18s} F={f:.3f} P={P:.3f} R={R:.3f} | LL={ll:11.0f} | types={ty} mlen={ml:.2f} one={one:.2f}")
    return dict(tag=tag, a1=a1, f=f, ll=ll, bigram=bigram)

t0 = time.time()
res = []
print("BIGRAM-HDP, a1 sweep (a0=100, p#=0.2):")
for a1 in [30, 100, 300, 1000, 3000]:
    res.append(fit(True, 100.0, float(a1), f"bigram a1={a1}"))
print("\nUNIGRAM-DP reference (a0=20, p#=0.5):")
uni = fit(False, 20.0, 0.0, "unigram")
print(f"\n[{time.time()-t0:.0f}s]")

big = [r for r in res if r["bigram"]]
best_ll = max(big, key=lambda r: r["ll"])         # SELECT BY LIKELIHOOD, not F
best_f = max(big, key=lambda r: r["f"])            # shown only for transparency (NOT the selection)
print(f"\nLL-SELECTED bigram: a1={best_ll['a1']:.0f} -> token F={best_ll['f']:.3f}  (selection was gold-blind, by LL)")
print(f"  (for transparency, best-F bigram was a1={best_f['a1']:.0f} F={best_f['f']:.3f} — NOT used for selection)")
print(f"  unigram-DP: F={uni['f']:.3f}")
print(f"  bigram(LL-sel) - unigram = {best_ll['f']-uni['f']:+.3f}   vs Zhikov 0.741 = {best_ll['f']-0.741:+.3f}")
print("\nHONEST: 130 sweeps = PARTIAL convergence; a1 committed value was mis-specified; selection is by model LL not F.")
print("No verdict word until this is confirmed across seeds + the word-shuffle knockout.")