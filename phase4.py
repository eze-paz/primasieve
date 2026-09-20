"""PHASE 4 -- COMPRESSION AS THE UNIVERSAL *REJECTION* ORACLE (GENERAL_REASONER_PLAN.md).

Earned in the segmentation work: DL-minimum ANTI-correlates with truth (Zhikov's good answer is a greedy
LOCAL optimum, not the compression minimum). So the plan's rule is an ASYMMETRY:
    compression is a sound REJECTOR   -- a hypothesis that fails to compress is wrong
    compression is an UNSOUND ACCEPTOR -- the best compressor need not be true
This phase MEASURES both halves on br-phono, the one domain here with gold truth.

The rejector claim is WEAKER than "gold is the DL minimum": gold need only beat a NULL model. That distinction
is the whole point, and it is what is tested.

  (A) GLOBAL   : DL(gold) vs DL(null) for three nulls -- gold must beat all of them, else compression would
                 reject the truth outright and is not even a sound rejector.
  (B) BOUNDARY : for every TRUE boundary, dDL of removing it. Removal that IMPROVES DL = a true boundary the
                 compression filter would REJECT = FALSE-REJECTION. Pre-registered bound: <5%.
  (C) ACCEPTOR : for every gold NON-boundary gap, dDL of adding it. Improvement = a FALSE boundary compression
                 would ACCEPT. This is expected to be LARGE -- it is the unsound-acceptor half, and quantifies
                 exactly why compression must never decide.

KILL 4: false-rejection (B) above the 5% bound -> compression is not a sound rejector in this domain either,
and the domain is reported out of scope. (C) being large is NOT a kill -- it is the predicted result.
"""
import os, sys, json, time, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seg_zhikov as SZ

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
BOUND = 0.05                                    # pre-registered false-rejection bound


def build(streams, seg, kappa=1.5):
    """MDLZ state for a given segmentation (seg = per-utterance sorted internal boundary list)."""
    m = SZ.MDLZ(streams, kappa)
    for s, bl in zip(streams, seg):
        pts = [0] + list(bl) + [len(s)]
        for i in range(len(pts) - 1):
            m.change(s[pts[i]:pts[i + 1]], +1)
    return m


if __name__ == "__main__":
    t0 = time.time()
    utts = SZ.load_brp(); gold = SZ.gold_spans(utts)
    streams = [s for s, _ in gold]
    gold_b = [sorted(x[0] for x in gs if x[0] > 0) for _, gs in gold]
    ngaps = sum(len(s) - 1 for s in streams)
    ntrue = sum(len(b) for b in gold_b)
    print(f"br-phono: {len(streams)} utts, {ngaps} internal gaps, {ntrue} TRUE boundaries "
          f"({ntrue/ngaps:.1%} density)\n")

    # ---------------- (A) GLOBAL: does the truth beat the nulls? ----------------
    m_gold = build(streams, gold_b)
    dl_gold = m_gold.dl()
    nulls = {}
    nulls["merged (1 token/utterance)"] = build(streams, [[] for _ in streams]).dl()
    nulls["all-chars (every gap)"] = build(streams, [list(range(1, len(s))) for s in streams]).dl()
    rng = random.Random(0); dens = ntrue / ngaps
    nulls["random @gold density"] = build(
        streams, [sorted(g for g in range(1, len(s)) if rng.random() < dens) for s in streams]).dl()
    print("(A) GLOBAL two-part DL (lower = compresses better)")
    print(f"  GOLD segmentation            {dl_gold:12.0f}")
    beats_all = True
    for k, v in nulls.items():
        ok = dl_gold < v
        beats_all &= ok
        print(f"  {k:28s} {v:12.0f}   gold {'BEATS' if ok else 'LOSES TO'} it "
              f"({(v-dl_gold)/v:+.1%})")
    print(f"  -> gold beats every null: {beats_all}")

    # ---------------- (B) FALSE-REJECTION: true boundaries compression would remove ----------------
    m = build(streams, gold_b)
    reject = 0; deltas = []
    for u, s in enumerate(streams):
        bl = gold_b[u]
        for j, g in enumerate(bl):
            lo = bl[j - 1] if j - 1 >= 0 else 0
            hi = bl[j + 1] if j + 1 < len(bl) else len(s)
            left, right, merged = s[lo:g], s[g:hi], s[lo:hi]
            before = m.dl()
            m.change(left, -1); m.change(right, -1); m.change(merged, +1)
            after = m.dl()
            m.change(merged, -1); m.change(left, +1); m.change(right, +1)   # restore
            d = after - before
            deltas.append(d)
            if d < 0: reject += 1        # removing the TRUE boundary IMPROVES DL -> filter rejects truth
    fr = reject / max(1, ntrue)
    print(f"\n(B) FALSE-REJECTION of TRUE boundaries (dDL<0 when removed)")
    print(f"  {reject}/{ntrue} = {fr:.2%}   (pre-registered bound {BOUND:.0%})")
    print(f"  mean dDL of removing a true boundary {sum(deltas)/len(deltas):+.2f} bits "
          f"(positive = compression defends the truth)")

    # ---------------- (C) UNSOUND ACCEPTOR: false boundaries compression would add ----------------
    m = build(streams, gold_b)
    accept = 0; tot = 0
    for u, s in enumerate(streams):
        bset = set(gold_b[u]); bl = gold_b[u]
        import bisect
        for g in range(1, len(s)):
            if g in bset: continue
            tot += 1
            idx = bisect.bisect_left(bl, g)
            lo = bl[idx - 1] if idx - 1 >= 0 else 0
            hi = bl[idx] if idx < len(bl) else len(s)
            whole, a, b = s[lo:hi], s[lo:g], s[g:hi]
            before = m.dl()
            m.change(whole, -1); m.change(a, +1); m.change(b, +1)
            after = m.dl()
            m.change(a, -1); m.change(b, -1); m.change(whole, +1)
            if after < before: accept += 1
    fa = accept / max(1, tot)
    print(f"\n(C) FALSE-ACCEPTANCE of NON-boundaries (dDL<0 when added)")
    print(f"  {accept}/{tot} = {fa:.2%}   <- the UNSOUND-ACCEPTOR half (large is EXPECTED, not a kill)")

    print(f"\n=== KILL 4 ===")
    if not beats_all:
        print(f"  FIRED: gold does not beat every null -> compression rejects the truth outright.")
        verdict = "FIRED (gold loses to a null)"
    elif fr > BOUND:
        print(f"  FIRED: false-rejection {fr:.2%} > {BOUND:.0%} -> compression is NOT a sound rejector here;")
        print(f"  the domain is reported OUT OF SCOPE for compression-as-filter.")
        verdict = f"FIRED (false-rejection {fr:.2%})"
    else:
        print(f"  PASSES: false-rejection {fr:.2%} <= {BOUND:.0%} and gold beats every null.")
        print(f"  => compression is a SOUND REJECTOR (safe as a filter) and a DEMONSTRABLY UNSOUND ACCEPTOR")
        print(f"     ({fa:.1%} of non-boundaries would be accepted). The asymmetry the plan assumed is MEASURED.")
        verdict = "PASSES"
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase4_compression_oracle"] = {
        "corpus": "br-phono", "gaps": ngaps, "true_boundaries": ntrue,
        "dl_gold": round(dl_gold), "dl_nulls": {k: round(v) for k, v in nulls.items()},
        "gold_beats_all_nulls": beats_all,
        "false_rejection_rate": round(fr, 4), "false_rejection_bound": BOUND,
        "mean_delta_removing_true_boundary": round(sum(deltas)/len(deltas), 3),
        "false_acceptance_rate": round(fa, 4),
        "kill4": verdict,
        "reading": "compression is safe as a REJECTOR (filter) but must never DECIDE; the acceptor half is "
                   "quantified and large, which is why grounding/active probing keeps acceptance.",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
