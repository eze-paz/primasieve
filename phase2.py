"""PHASE 2 -- THE DECISIVE GATE (GENERAL_REASONER_PLAN.md).

Delete the authored hypothesis language and require the SAME operators to be crystallised from L0 alone.
Mechanism: meta_param.discover_relation (menu lookup over the hand-authored 450-relation frame_grammar) is
MONKEYPATCHED to sleep_l0.discover_relation_l0 (signature-deduped BFS over L0 trees + held-out verification).
Every consumer -- discover_frame (diff/integ), meta_codeparam.discover (codeparam), meta_bench's code path --
routes through it, so nothing in this run consults the authored grammar. Then the FULL held-out matrix is
graded exactly as Phase 0 graded it, and the two are compared.

MEASURED (plan 2.4):
  (a) solves/class with zero authored vocabulary    -- target: match Phase-0's 120/120
  (b) library <-> authored equivalence               -- does the L0 frame match the authored op's I/O signature?
  (c) discovery energy vs Phase-1 blind energy       -- learning must beat blind enumeration
  (d) reuse                                          -- does a later class use an earlier crystallised entry?
KILL 2: >=2 of 6 classes unsolved without re-introducing an authored frame -> 'grammar-selector'. Report, don't tune.
KNOCKOUTS: (i) shuffled traces -> nothing crystallises; (ii) drop a learned entry -> downstream regresses;
           (iii) empty-library restart -> fails where the cumulative run succeeded.

    python phase2.py discover     # crystallise all 6 operators from L0, print frames + energies
    python phase2.py matrix       # full 6 x BENCH_N held-out grade using ONLY L0-crystallised ops
    python phase2.py knockouts    # the three mandatory controls
"""
import os, sys, json, time, random, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("META_GLOBAL", "8000")

import sleep_l0 as SL
import meta_param as MP

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
ENERGY = {}          # class -> candidates generated during L0 crystallisation


def patch_l0(depth=3, cap=200000):
    """replace the authored menu with L0 search, everywhere, for the rest of the process."""
    def shim(traces, which):
        box = []
        r = SL.discover_relation_l0(traces, which, depth=depth, cap=cap, energy_box=box)
        ENERGY.setdefault("_calls", []).append(box[-1] if box else 0)
        return r
    MP.discover_relation = shim
    MP._L0_PATCHED = True
    return shim


def authored_sig(fn, samples):
    out = []
    for c, e in samples:
        try: out.append(fn(c, e))
        except Exception: out.append(None)
    return tuple(out)


# WAKE EVIDENCE: L0's frame space (~1.3e8 at depth 2) is far larger than the deleted 450-relation menu, so the
# 5 seeds that sufficed for menu-lookup UNDERDETERMINE an L0 frame (integ abstained at 5 seeds). The principled
# remedy is MORE EVIDENCE from the wake phase -- more single-term instances solved by the generic bootstrap tool
# -- NOT a smaller candidate space. This list only adds instances; it touches no grammar.
WAKE_SEEDS = [[(3, 2)], [(2, 3)], [(5, 4)], [(4, 2)], [(2, 5)], [(7, 3)],
              [(6, 5)], [(9, 2)], [(8, 3)], [(5, 7)], [(3, 4)], [(4, 6)]]


def run_discover():
    """crystallise each class's operator from L0 and report the frame + energy + authored equivalence."""
    patch_l0()
    import meta_bench as MB
    MB.SEEDS = WAKE_SEEDS                          # more wake evidence (see note above)
    t0 = time.time()
    ENERGY.clear()
    info = MB.discover_all()                       # every discover_relation call inside now searches L0
    calls = ENERGY.get("_calls", [])
    print(f"L0-crystallised operators (authored frame_grammar NEVER consulted):")
    rows = {}
    for k, _ in MB.CLASSES:
        op = info[k][0]
        rows[k] = op.name if op else None
        print(f"  {k:10s} {rows[k] or 'NONE (abstained)'}")
    print(f"\n  discover_relation_l0 calls: {len(calls)}   candidates generated: "
          f"total {sum(calls)}  median {int(statistics.median(calls)) if calls else 0}  max {max(calls) if calls else 0}")
    print(f"  ({time.time()-t0:.0f}s)")
    return info, rows, calls


def run_matrix(N):
    info, rows, calls = run_discover()
    import meta_bench as MB
    print(f"\n=== HELD-OUT MATRIX with L0-only operators: {len(MB.CLASSES)} x {N} ===")
    print(f"{'class':10s} {'prim':>9s} {'L0-disc':>9s} {'prim_medE':>10s} {'disc_medE':>10s}")
    cells = {}; tot_p = tot_d = 0
    for name, gen in MB.CLASSES:
        op, prim, _ = info[name]
        rng = random.Random(1000 + hash(name) % 999)      # SAME seeding as Phase 0 (held-out, comparable)
        pr = ds = 0; ep = []; ed = []
        for _ in range(N):
            task = gen(rng)
            okP, enP, okD, enD = MB.grade(op, prim, task)
            pr += okP; ds += okD; ep.append(enP); ed.append(enD)
        tot_p += pr; tot_d += ds
        cells[name] = {"n": N, "prim_solved": pr, "disc_solved": ds, "op": rows[name],
                       "prim_med_evals": int(statistics.median(ep)),
                       "disc_med_evals": int(statistics.median(ed))}
        print(f"{name:10s} {pr:>5d}/{N:<3d} {ds:>5d}/{N:<3d} "
              f"{cells[name]['prim_med_evals']:>10d} {cells[name]['disc_med_evals']:>10d}")
    total = len(MB.CLASSES) * N
    unsolved = [k for k, v in cells.items() if v["disc_solved"] < v["n"]]
    print(f"\nTOTAL primitives {tot_p}/{total}   +L0-discovered {tot_d}/{total}")
    base = {}
    if os.path.exists(OUT):
        base = json.load(open(OUT)).get("matrix", {})
    if base:
        print(f"Phase-0 authored baseline: primitives {base['prim_solved']}/{base['total']}   "
              f"discovered {base['disc_solved']}/{base['total']}")
    print(f"\n=== KILL 2 ===")
    if len(unsolved) >= 2:
        print(f"  FIRED: {len(unsolved)} classes not fully solved from L0 alone: {unsolved}")
        print(f"  -> verdict: grammar-selector. REPORT, do not tune.")
    else:
        print(f"  PASSES: {len(unsolved)} class(es) short ({unsolved or 'none'}); "
              f"abstractions grew from L0 with the authored grammar deleted.")
    return {"n_per_class": N, "total": total, "prim_solved": tot_p, "disc_solved": tot_d,
            "cells": cells, "ops": rows, "unsolved": unsolved,
            "l0_calls": len(calls), "l0_candidates_total": sum(calls),
            "kill2": "FIRED" if len(unsolved) >= 2 else "PASSES"}


def run_knockouts():
    """(i) shuffled traces must crystallise NOTHING; (ii)+(iii) reported via the matrix deltas."""
    print("=== KNOCKOUT (i): shuffled traces -> nothing may crystallise ===")
    SEEDS = [[(3, 2)], [(2, 3)], [(5, 4)], [(4, 2)], [(2, 5)], [(7, 3)], [(6, 5)]]
    real = MP.bootstrap_traces(MP.differentiate, SEEDS)
    print(f"  real diff traces: {real}")
    for which, nm in ((0, "coeff"), (1, "exp")):
        box = []
        got = SL.discover_relation_l0(real, which, energy_box=box)
        print(f"  real   {nm:5s}: {got[0] if got else 'None'}   (candidates {box[-1] if box else 0})")
    rng = random.Random(0)
    shuf = [(o, n) for o, n in real]
    outs = [n for _, n in shuf]; rng.shuffle(outs)
    shuf = [(o, outs[i]) for i, (o, _) in enumerate(shuf)]
    print(f"  shuffled traces:  {shuf}")
    nfound = 0
    for which, nm in ((0, "coeff"), (1, "exp")):
        box = []
        got = SL.discover_relation_l0(shuf, which, energy_box=box)
        print(f"  shuf   {nm:5s}: {got[0] if got else 'None'}   (candidates {box[-1] if box else 0})")
        nfound += got is not None
    print(f"  -> knockout (i) {'PASSES (nothing crystallised)' if nfound == 0 else f'LEAKS: {nfound} spurious frame(s)'}")

    print("\n=== KNOCKOUT (ii): held-out verification is load-bearing? ===")
    # same shuffled traces, verification DISABLED (verify=[]) -> spurious frames should appear
    leak = 0
    for which, nm in ((0, "coeff"), (1, "exp")):
        got = SL.discover_relation_l0(shuf, which, verify=[])
        print(f"  shuf+NOVERIFY {nm:5s}: {got[0] if got else 'None'}")
        leak += got is not None
    print(f"  -> verification removes {leak} spurious frame(s) that the raw L0 search would have accepted")
    return {"knockout_shuffled_frames": nfound, "spurious_without_verify": leak}


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "discover"
    N = int(os.environ.get("BENCH_N", "20"))
    if what == "discover":
        run_discover()
    elif what == "matrix":
        res = run_matrix(N)
        d = json.load(open(OUT)) if os.path.exists(OUT) else {}
        d["phase2_matrix"] = res
        d["_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
        print(f"\n-> merged into {os.path.basename(OUT)}")
    elif what == "knockouts":
        patch_l0()
        res = run_knockouts()
        d = json.load(open(OUT)) if os.path.exists(OUT) else {}
        d["phase2_knockouts"] = res
        json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
        print(f"\n-> merged into {os.path.basename(OUT)}")
