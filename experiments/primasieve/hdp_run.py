"""Full-corpus HDP headline run: bigram-HDP vs unigram-DP, 1 seed, long sampling. Pre-registered config
(hdp_prereg.md): a0=100 a1=3000 p#=0.2 bigram / a0=20 p#=0.5 unigram; anneal 10->1; select by trajectory not peak.
Prints trajectory + the emergence signature (mean token length vs gold ~2.9) + final. NO verdict word until the full
multi-seed suite + word-shuffle knockout run (hdp_seg.py). This is the convergence/mechanism probe on real data."""
import sys, os, random, time
sys.path.insert(0, os.path.dirname(__file__))
import hdp_seg as H, seg_zhikov as Z

SWEEPS = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--sweeps=")), 400))
utts = Z.load_brp(); random.Random(2024).shuffle(utts)
gold = Z.gold_spans(utts); streams = [s for s, _ in gold]
gml = sum(len(w) for u in utts for w in u) / sum(len(u) for u in utts)
print(f"FULL br-phono: {len(utts)} utts, {sum(len(w) for w in utts)} tokens | gold mean len {gml:.2f} | sweeps={SWEEPS}")
gold_bounds = [set(a for (a, b) in gb if a > 0) for _, gb in gold]   # spans -> boundary positions
print(f"scorer-drift: gold-vs-gold={Z.token_f(gold, gold_bounds)[0]:.3f} (must=1.000) | Zhikov=0.741\n")
for bg, tag in [(True, "BIGRAM-HDP"), (False, "UNIGRAM-DP")]:
    t0 = time.time()
    print(f"{tag} (a0={'100' if bg else '20'} a1={'3000' if bg else '-'} p#={'0.2' if bg else '0.5'}):")
    H.run(streams, gold, bigram=bg, sweeps=SWEEPS, init="entropy", seed=0, tag=tag[:6], report_every=25)
    print(f"  [{time.time()-t0:.0f}s]\n")