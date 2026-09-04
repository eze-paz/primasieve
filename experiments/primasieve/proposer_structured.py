"""PHASE 3(c) -- is the proposer's advantage STRUCTURE-specific rather than DEPTH-specific?

Phase 3(b) refuted my regime story: on 60 RANDOM deep frames the median speedup is 1.27x. But the one big win
in Phase 3 was d2 (5.2x, and 37x on its c-component), and d2 is not a random deep frame -- it is a COMPOSITION
of a library entry (diff o diff). That left one concrete open question, which this settles.

PRE-REGISTERED, stated before the run:
  build deep frames by COMPOSING base operators (the structured set) and compare against the random deep frames
  of Phase 3(b) (median 1.27x). The advantage is STRUCTURE-specific iff the structured set's median speedup is
  >= 2.0x AND clearly exceeds the random-deep 1.27x. Otherwise Phase 3 is a null with no rescue of any kind,
  and d2's 5.2x was noise. Reported either way.
"""
import os, sys, json, time, random, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import proposer as P
import sleep_l0 as SL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))

# base operators, all of them frames the engine has actually crystallised somewhere in this project
BASE = {
    "diff":      (("*", "c", "e"), ("-", "e", 1)),
    "integ":     (("/", "c", ("+", "e", 1)), ("+", "e", 1)),
    "negate":    (("neg", "c"), "e"),
    "struct":    ("c", 2),
    "code":      (("+", "c", 1), "e"),
    "codeparam": (("+", "c", "e"), "e"),
    "double":    (("+", "c", "c"), "e"),
    "raise":     ("c", ("+", "e", 1)),
}


def subst(t, cmap, emap):
    """substitute the c/e leaves of t by whole trees (functional composition of frames)."""
    if t == "c": return cmap
    if t == "e": return emap
    if isinstance(t, (int,)): return t
    if isinstance(t, str): return t
    if t[0] in ("abs", "sign", "neg"): return (t[0], subst(t[1], cmap, emap))
    return (t[0], subst(t[1], cmap, emap), subst(t[2], cmap, emap))


def compose(fa, fb):
    """fa o fb : apply fb, then fa. Structured deep frame."""
    return (subst(fa[0], fb[0], fb[1]), subst(fa[1], fb[0], fb[1]))


if __name__ == "__main__":
    t0 = time.time()
    N_TRAIN = int(os.environ.get("N_TRAIN", "600"))
    pool = P.build_pool(3, 60000)
    print(f"PHASE 3(c) structured-vs-random -- pool {len(pool)}\n")

    # every ordered composition of base operators = the STRUCTURED deep set
    structured = []
    seen = set()
    for a in BASE:
        for b in BASE:
            fr = compose(BASE[a], BASE[b])
            s = P.sig(fr)
            tr = P.traces_of(fr)
            if s is None or tr is None or s in seen: continue
            seen.add(s)
            structured.append((f"{a} o {b}", fr, tr, s))
    print(f"structured deep frames (compositions of base operators): {len(structured)}")

    ho = {s for _, _, _, s in structured} | {P.sig(f) for f in P.HELDOUT.values() if P.sig(f)}
    data = P.sample_training_frames(pool, N_TRAIN, ho, random.Random(1))
    print(f"training pairs {len(data)} (all structured signatures EXCLUDED)")
    net, loss = P.train(data)
    sh = [(d[0], data[(i * 7 + 3) % len(data)][1]) for i, d in enumerate(data)]
    net_ko, _ = P.train(sh)
    print(f"model trained (BCE {loss:.4f})\n")

    rows = []
    print(f"{'composition':>22} {'BFS':>8} {'prior':>8} {'speedup':>8}")
    for name, fr, tr, _s in structured:
        tot_b = tot_p = tot_k = 0
        ok = True
        for which in (0, 1):
            b, _ = P.rank_of(pool, None, tr, which)
            if b is None: ok = False; break
            o = P.prior_order(net, tr, pool, which)
            p, _ = P.rank_of(pool, None, tr, which, order=o)
            o2 = P.prior_order(net_ko, tr, pool, which)
            k, _ = P.rank_of(pool, None, tr, which, order=o2)
            tot_b += b; tot_p += p; tot_k += k
        if not ok: continue
        sp = tot_b / max(1, tot_p)
        rows.append({"comp": name, "bfs": tot_b, "prior": tot_p, "ko": tot_k, "speedup": sp})
        if len(rows) <= 14:
            print(f"{name:>22} {tot_b:>8d} {tot_p:>8d} {sp:>7.2f}x")

    med = statistics.median([r["speedup"] for r in rows])
    medko = statistics.median([r["bfs"] / max(1, r["ko"]) for r in rows])
    deep = [r for r in rows if r["bfs"] > 500]
    med_deep = statistics.median([r["speedup"] for r in deep]) if deep else None
    print(f"\n  structured frames evaluated: {len(rows)}")
    print(f"  median speedup {med:.2f}x   (knockout {medko:.2f}x)")
    if deep:
        print(f"  restricted to BFS>500 ({len(deep)} frames): median {med_deep:.2f}x")
    print(f"  Phase 3(b) random deep frames: 1.27x")

    print(f"\n=== PRE-REGISTERED VERDICT ===")
    ref = med_deep if med_deep is not None else med
    if ref >= 2.0 and ref > 1.27:
        verdict = f"STRUCTURE-SPECIFIC (structured median {ref:.2f}x vs random-deep 1.27x)"
        print(f"  {verdict}")
        print(f"  The proposer helps on frames that are COMPOSITIONS of known operators, not on arbitrary deep")
        print(f"  ones. Phase 3's null stands for the general case, but amortization has a real, narrow home:")
        print(f"  predicting re-use of learned structure -- which is exactly what a recognition model should do.")
    else:
        verdict = f"NOT structure-specific (structured median {ref:.2f}x)"
        print(f"  {verdict}")
        print(f"  d2's 5.2x does not generalise to compositions in general. Phase 3 is a null with no rescue;")
        print(f"  the recognition model, as built, does not pay anywhere. Reported, not tuned.")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase3c_structured"] = {
        "n_structured": len(rows), "median_speedup": round(med, 3),
        "median_knockout": round(medko, 3),
        "n_deep": len(deep), "median_speedup_deep": round(med_deep, 3) if med_deep else None,
        "random_deep_reference": 1.27, "verdict": verdict,
        "top": sorted(rows, key=lambda r: -r["speedup"])[:6],
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
