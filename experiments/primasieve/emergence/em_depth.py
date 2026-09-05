"""EMERGENCE E-2b -- a curriculum whose EXTENSION provably deepens, and the compounding test.

E-2a (em_loop.py) was VOID as a depth test and is reported as such. Its tiers counted transforms APPLIED, and
its base set nearly closes under composition (negate is an involution, double/raise are commuting shifts), so a
syntactically deep tier-6 frame is often EXTENSIONALLY equal to a shallow one on the sample inputs -- and blind
depth-3 search correctly finds the simpler equivalent. Occam working, not a library failure. Measured: tier-6
c-trees average syntactic depth 4.75, yet blind reached tier 6. Same extensional-vs-syntactic trap as the
Phase 2(e) signature-dedup bug.

FIX: repeated DIFFERENTIATION. d^k has c' = c*e*(e-1)*...*(e-k+1) (a falling factorial) and e' = e-k. That
extension genuinely deepens with k and cannot collapse to a shallower one. The blind L0 pool is depth 3, so
blind must wall around k=3-4; the library should go far past it because d_a o d_b = d_(a+b), i.e. two tier-k
entries compose to tier-2k -- reachable depth should grow EXPONENTIALLY in cycles.

ARMS (identical curriculum, identical verifier)
  LIBRARY  crystallises every solved frame, including COMPOSED ones, and carries them across cycles
  BLIND    L0 depth-3 search only
MEASURED: max k reached per cycle, and WHICH k each arm can reach at all.
KILL: if the library's reachable k plateaus where blind does, compounding is bounded -- report, do not tune.
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # read-only imports from ../
sys.path.insert(0, HERE)
from fractions import Fraction as F
import sleep_l0 as SL
import em_loop as E                                 # compose/subst/pool helpers (same directory)

OUT = os.path.join(HERE, "EMERGENCE.json")
INPUTS = [(3, 30), (2, 28), (5, 26), (4, 25), (7, 24), (2, 23), (6, 22), (9, 21)]
DIFF = (("*", "c", "e"), ("-", "e", 1))


def dk_frame(k):
    """d^k as an L0 frame, by composing DIFF with itself k times."""
    fr = DIFF
    for _ in range(k - 1):
        fr = E.compose(DIFF, fr)
    return fr


def dk_truth(k, c, e):
    """ground truth: c * e*(e-1)*...*(e-k+1),  e-k."""
    m = F(c)
    for i in range(k):
        m *= (e - i)
    return (m, e - k)


def traces_k(k):
    return [((c, e), dk_truth(k, c, e)) for (c, e) in INPUTS]


def sig_k(k):
    return tuple((str(a), str(b)) for _, (a, b) in traces_k(k))


def frame_sig(fr):
    out = []
    for (c, e) in INPUTS:
        r = E.apply_frame(fr, c, e)
        if r is None: return None
        out.append((str(r[0]), str(r[1])))
    return tuple(out)


def solve_blind(k, depth=3, cap=60000):
    """find (c-tree, e-tree) in the depth-3 L0 pool matching d^k's extension."""
    tr = traces_k(k)
    got = [None, None]; ev = 0
    for which in (0, 1):
        found = None
        for t, _s in E.pool(INPUTS, depth, cap):
            ev += 1
            ok = True
            for (oc, oe), new in tr:
                v = SL.ev(t, oc, oe)
                if v is None or v != F(new[which]): ok = False; break
            if ok: found = t; break
        if found is None: return None, ev
        got[which] = found
    return (got[0], got[1]), ev


def solve_by_library(k, lib):
    """entry alone, then every ordered PAIR."""
    target = sig_k(k); ev = 0
    for n, fr in lib.items():
        ev += 1
        if frame_sig(fr) == target: return fr, n, ev
    names = list(lib)
    for a in names:
        for b in names:
            ev += 1
            fr = E.compose(lib[a], lib[b])
            if frame_sig(fr) == target: return fr, f"({a} o {b})", ev
    return None, None, ev


def run(use_library, ks, cycles):
    lib = {}; hist = []
    for cyc in range(1, cycles + 1):
        reached = []; cost = 0; how = {}
        for k in ks:
            fr = None; tag = None
            if use_library and lib:
                fr, tag, ev = solve_by_library(k, lib); cost += ev
            if fr is None:
                fr, ev = solve_blind(k); cost += ev
                tag = "blind" if fr else None
            if fr is not None:
                reached.append(k); how[k] = tag
                if use_library:
                    s = frame_sig(fr)
                    if s and not any(frame_sig(v) == s for v in lib.values()):
                        lib[f"d{k}"] = fr
        hist.append({"cycle": cyc, "reached": reached, "max_k": max(reached) if reached else 0,
                     "library": len(lib), "cost": cost, "how": {str(a): b for a, b in how.items()}})
        print(f"  cycle {cyc}  reached k={reached}  max {max(reached) if reached else 0:>2}  "
              f"library {len(lib):>2}  cost {cost}")
    return hist, lib


if __name__ == "__main__":
    t0 = time.time()
    KS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16]
    CYCLES = int(os.environ.get("EM_CYCLES", "4"))
    print("EMERGENCE E-2b -- repeated differentiation (extension provably deepens)\n")
    print(f"tasks: d^k for k in {KS};  L0 pool depth 3\n")
    print("BLIND arm (L0 depth-3 search only):")
    hb, _ = run(False, KS, CYCLES)
    print("\nLIBRARY arm (crystallises composed frames, carries across cycles):")
    hl, lib = run(True, KS, CYCLES)

    mb = max(h["max_k"] for h in hb); ml = max(h["max_k"] for h in hl)
    blind_ks = sorted({k for h in hb for k in h["reached"]})
    lib_ks = sorted({k for h in hl for k in h["reached"]})
    print(f"\n  BLIND   reaches k = {blind_ks}   (max {mb})")
    print(f"  LIBRARY reaches k = {lib_ks}   (max {ml})")
    print(f"  library-only k    = {sorted(set(lib_ks) - set(blind_ks))}")
    print(f"  final library entries: {sorted(lib)}")
    print(f"  how the last cycle solved each k: {hl[-1]['how']}")
    print(f"\n=== VERDICT ===")
    if ml > mb:
        print(f"  COMPOUNDING: the library reaches depths blind search cannot (max k {ml} vs {mb}).")
        print(f"  Composed frames are crystallised, so two tier-k entries give tier-2k -- reachable depth")
        print(f"  grows by composition, not by searching harder.")
    else:
        print(f"  NO COMPOUNDING: library max k {ml} == blind {mb}. Report, do not tune.")
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E2b_depth_curriculum"] = {
        "ks": KS, "blind": hb, "library": hl, "blind_max_k": mb, "library_max_k": ml,
        "blind_reaches": blind_ks, "library_reaches": lib_ks,
        "library_only": sorted(set(lib_ks) - set(blind_ks)), "entries": sorted(lib),
        "verdict": "COMPOUNDING" if ml > mb else "no compounding",
    }
    d["E2a_void_note"] = ("em_loop.py's tier curriculum was VOID as a depth test: tiers counted transforms "
                          "APPLIED and the base set nearly closes under composition, so deep tier-6 frames were "
                          "extensionally equal to shallow ones and blind depth-3 search correctly found the "
                          "simpler equivalent. Its 11.3x cost figure is NOT an emergence result.")
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  ({time.time()-t0:.0f}s) -> {os.path.basename(OUT)}")
