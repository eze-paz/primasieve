"""PHASE 3(b) -- REGIME TEST: does the proposer pay ONLY where blind search is expensive?

Phase 3 fired its kill (median 0.8x) and I explained it as: the shallow targets already sit at BFS ranks 2-52,
so there is no headroom, and only deep frames have room. That explanation rested on n=2 in the expensive
regime, and those two CONTRADICTED each other (integ 0.6x, d2 5.2x). So it was a story, not a result.

This tests it properly on many held-out DEEP frames.

PRE-REGISTERED, stated before the run:
  bucket targets by their BLIND BFS rank. In the EXPENSIVE bucket (BFS rank > 500) the median speedup must be
  >= 2.0x for the regime explanation to stand. If it is not, the explanation is REFUTED and Phase 3's null is
  simply a null, with no regime that rescues it. Reported either way; no tuning after seeing the buckets.

Held-out frames are sampled from L0 and their signatures are EXCLUDED from the proposer's training set.
"""
import os, sys, json, time, random, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import proposer as P
import sleep_l0 as SL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))

if __name__ == "__main__":
    t0 = time.time()
    N_TRAIN = int(os.environ.get("N_TRAIN", "600"))
    N_EVAL = int(os.environ.get("N_EVAL", "60"))
    DEPTH, CAP = 3, 60000
    pool = P.build_pool(DEPTH, CAP)
    print(f"PHASE 3(b) regime test -- pool {len(pool)}, eval on {N_EVAL} held-out frames\n")

    rng = random.Random(5)
    trees = [t for t, _ in pool]
    # sample held-out EVAL frames first, so they can be excluded from training
    evals = []
    seen = set()
    while len(evals) < N_EVAL and len(seen) < N_EVAL * 200:
        fr = (rng.choice(trees), rng.choice(trees))
        s = P.sig(fr)
        if s is None or s in seen: continue
        seen.add(s)
        tr = P.traces_of(fr)
        if tr is None: continue
        evals.append((fr, tr, s))
    ho = {s for _, _, s in evals} | {P.sig(f) for f in P.HELDOUT.values() if P.sig(f)}
    data = P.sample_training_frames(pool, N_TRAIN, ho, random.Random(1))
    print(f"training pairs {len(data)} (all {len(evals)} eval signatures EXCLUDED)")
    net, loss = P.train(data)
    sh = [(d[0], data[(i * 7 + 3) % len(data)][1]) for i, d in enumerate(data)]
    net_ko, _ = P.train(sh)
    print(f"model trained (BCE {loss:.4f}); knockout trained\n")

    rows = []
    for fr, tr, _s in evals:
        rec = {"frame": [SL.lab(fr[0]), SL.lab(fr[1])]}
        tot_b = tot_p = tot_k = 0
        ok = True
        for which in (0, 1):
            b, _ = P.rank_of(pool, None, tr, which)
            if b is None: ok = False; break
            o = P.prior_order(net, tr, pool, which)
            p, _ = P.rank_of(pool, None, tr, which, order=o)
            ok2 = P.prior_order(net_ko, tr, pool, which)
            k, _ = P.rank_of(pool, None, tr, which, order=ok2)
            tot_b += b; tot_p += p; tot_k += k
        if not ok: continue
        rec.update({"bfs": tot_b, "prior": tot_p, "ko": tot_k, "speedup": tot_b / max(1, tot_p)})
        rows.append(rec)
    print(f"evaluated {len(rows)} frames")

    def bucket(r):
        if r["bfs"] <= 100: return "cheap (<=100)"
        if r["bfs"] <= 500: return "mid (101-500)"
        return "EXPENSIVE (>500)"

    print(f"\n{'bucket':>18} {'n':>4} {'median BFS':>11} {'median prior':>13} {'median speedup':>15} "
          f"{'ko speedup':>11}")
    summary = {}
    for bname in ("cheap (<=100)", "mid (101-500)", "EXPENSIVE (>500)"):
        sub = [r for r in rows if bucket(r) == bname]
        if not sub:
            print(f"{bname:>18} {0:>4}"); continue
        msp = statistics.median([r["speedup"] for r in sub])
        mko = statistics.median([r["bfs"] / max(1, r["ko"]) for r in sub])
        summary[bname] = {"n": len(sub), "median_bfs": statistics.median([r["bfs"] for r in sub]),
                          "median_prior": statistics.median([r["prior"] for r in sub]),
                          "median_speedup": round(msp, 3), "median_ko_speedup": round(mko, 3)}
        print(f"{bname:>18} {len(sub):>4} {statistics.median([r['bfs'] for r in sub]):>11.0f} "
              f"{statistics.median([r['prior'] for r in sub]):>13.0f} {msp:>15.2f}x {mko:>10.2f}x")

    exp = summary.get("EXPENSIVE (>500)")
    print(f"\n=== PRE-REGISTERED VERDICT ===")
    if not exp or exp["n"] < 5:
        verdict = "INCONCLUSIVE (too few expensive-bucket frames)"
        print(f"  {verdict}")
    elif exp["median_speedup"] >= 2.0:
        verdict = f"REGIME CONFIRMED (expensive-bucket median {exp['median_speedup']:.2f}x >= 2x)"
        print(f"  {verdict}")
        print(f"  Phase 3's null is a REGIME limitation: amortization pays exactly where blind search is")
        print(f"  costly, and the task set was dominated by frames Occam already finds in <60 candidates.")
    else:
        verdict = f"EXPLANATION REFUTED (expensive-bucket median {exp['median_speedup']:.2f}x < 2x)"
        print(f"  {verdict}")
        print(f"  My 'no headroom' story does NOT hold: even where blind search is expensive the proposer")
        print(f"  fails to deliver 2x. Phase 3 is simply a null, with no regime that rescues it.")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase3b_regime_test"] = {
        "n_eval": len(rows), "n_train": len(data), "buckets": summary, "verdict": verdict,
        "prereg": "expensive bucket (BFS rank > 500) median speedup must be >= 2.0x for the regime "
                  "explanation to stand; reported either way, no tuning after seeing buckets",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
