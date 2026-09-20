"""EMERGENCE E-1/E-2 -- persistent library + many wake/sleep cycles + a DEPTH-FORCING curriculum.

WHY THIS AND NOT SOMETHING ELSE (from the Phase 0-6 measurements, all in ../BASELINE.json):
  * L0 discovery costs only 1.59x the hand-authored 450-relation menu -> the BASE LANGUAGE is not the cap.
  * Reuse by composition was 373x cheaper than rediscovery, and deleting the entry caused total failure.
  * The learned proposer paid ONLY on compositions of known operators (2.52x) and not on random deep frames
    (1.27x) -- i.e. even the amortization win is a COMPOSITION win.
Every positive signal is about composition depth; every negative is about better search. Yet the library has
always been FLAT (depth <= 2), tiny (~6 entries), single-pass, and DISCARDED at the end of each run.

THE MECHANIC UNDER TEST: crystallise the COMPOSED frame too. Then two tier-k entries compose to tier-2k, so
reachable depth should grow EXPONENTIALLY in cycles rather than linearly. That is the testable form of
"massively increase emergence".

CURRICULUM: a tier-k task applies k base transforms in sequence to a polynomial. Blind L0 at depth 3 can reach
tier 1-2 (the d2 frame was found at 2687 candidates) but tier 3+ frames lie OUTSIDE depth 3 -- so tier 3+ is
blind-UNREACHABLE and only a library can get there. That is the compounding boundary, chosen from a measured
number rather than guessed.

ARMS
  LIBRARY  persistent library, crystallises solved frames (incl. composed ones), carries across cycles
  BLIND    same curriculum, library disabled -> must wall at the depth-3 boundary
KILL: if reachable tier plateaus at 2 with the library, compounding is bounded -- report it, do not tune.
"""
import os, sys, json, time, random, itertools
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # read-only imports from ../ (never edited)
sys.path.insert(0, HERE)
from fractions import Fraction as F
import sleep_l0 as SL                               # ../sleep_l0.py  (read-only)

OUT = os.path.join(HERE, "EMERGENCE.json")
LIBFILE = os.path.join(HERE, "library.json")

# ---- ground-truth base transforms; used ONLY to GENERATE tasks, never shown to the engine ----
BASE = {
    "diff":   (("*", "c", "e"), ("-", "e", 1)),
    "negate": (("neg", "c"), "e"),
    "double": (("+", "c", "c"), "e"),
    "raise":  ("c", ("+", "e", 1)),
}
TERM_INPUTS = [(3, 11), (2, 13), (5, 12), (4, 15), (7, 14), (2, 16), (6, 12), (9, 13)]


def subst(t, cmap, emap):
    if t == "c": return cmap
    if t == "e": return emap
    if isinstance(t, int) or isinstance(t, str): return t
    if t[0] in ("abs", "sign", "neg"): return (t[0], subst(t[1], cmap, emap))
    return (t[0], subst(t[1], cmap, emap), subst(t[2], cmap, emap))


def compose(fa, fb):
    """fa o fb : apply fb first, then fa."""
    return (subst(fa[0], fb[0], fb[1]), subst(fa[1], fb[0], fb[1]))


def apply_frame(fr, c, e):
    a = SL.ev(fr[0], c, e); b = SL.ev(fr[1], c, e)
    if a is None or b is None: return None
    return (a, b)


def traces_of(fr, inputs=TERM_INPUTS):
    out = []
    for (c, e) in inputs:
        r = apply_frame(fr, c, e)
        if r is None: return None
        out.append(((c, e), r))
    return out


def sig(fr, inputs=TERM_INPUTS):
    tr = traces_of(fr, inputs)
    return None if tr is None else tuple((str(a), str(b)) for _, (a, b) in tr)


def make_tier(k, rng):
    """a tier-k task = k base transforms applied in sequence (the engine sees only the traces)."""
    names = [rng.choice(list(BASE)) for _ in range(k)]
    fr = BASE[names[0]]
    for n in names[1:]:
        fr = compose(BASE[n], fr)
    return names, fr


# ---------------- the engine ----------------
def solve_by_library(target_sig, lib, inputs=TERM_INPUTS):
    """try each entry ALONE, then every ordered PAIR. Returns (frame, name, evals) or (None,None,evals)."""
    ev = 0
    for n, fr in lib.items():
        ev += 1
        if sig(fr, inputs) == target_sig: return fr, n, ev
    names = list(lib)
    for a in names:
        for b in names:
            ev += 1
            fr = compose(lib[a], lib[b])
            if sig(fr, inputs) == target_sig: return fr, f"({a} o {b})", ev
    return None, None, ev


def solve_blind(traces, depth=3, cap=60000):
    """L0 blind discovery of the frame from traces (the no-library route)."""
    box_c, box_e = [], []
    rc = SL.discover_relation_l0(traces, 0, depth=depth, cap=cap, verify=[], energy_box=box_c)
    re_ = SL.discover_relation_l0(traces, 1, depth=depth, cap=cap, verify=[], energy_box=box_e)
    ev = (box_c[-1] if box_c else cap) + (box_e[-1] if box_e else cap)
    if not (rc and re_): return None, ev
    return None, ev            # label only; the tree itself is rebuilt below by re-search


_POOL = {}


def pool(inputs, depth=3, cap=60000):
    """the L0 candidate pool, built ONCE per input set (rebuilding it per call was the bottleneck)."""
    key = (tuple(inputs), depth, cap)
    if key not in _POOL:
        _POOL[key] = SL.enum_trees(list(inputs), depth=depth, cap=cap)
    return _POOL[key]


def solve_blind_frame(traces, depth=3, cap=60000):
    """same, but returns the actual (c-tree, e-tree) so it can be crystallised."""
    inputs = [o for o, _ in traces]
    got = [None, None]; ev = 0
    for which in (0, 1):
        found = None
        for i, (t, _s) in enumerate(pool(inputs, depth, cap)):
            ev += 1
            ok = True
            for (oc, oe), new in traces:
                v = SL.ev(t, oc, oe)
                if v is None or abs(v - F(new[which]).limit_denominator(10 ** 12)) > F(1, 10 ** 9):
                    ok = False; break
            if ok: found = t; break
        if found is None: return None, ev
        got[which] = found
    return (got[0], got[1]), ev


def run(use_library, cycles, tiers, rng_seed=5, verbose=True):
    lib = {}
    rng = random.Random(rng_seed)
    hist = []
    for cyc in range(1, cycles + 1):
        solved_tiers = []
        cost = 0
        for k in tiers:
            names, fr = make_tier(k, rng)
            tr = traces_of(fr)
            if tr is None: continue
            tsig = sig(fr)
            frame = None; how = None
            if use_library and lib:
                frame, how, ev = solve_by_library(tsig, lib)
                cost += ev
            if frame is None:
                frame, ev = solve_blind_frame(tr)
                cost += ev
                how = "blind" if frame else None
            if frame is not None:
                solved_tiers.append(k)
                if use_library:
                    s = sig(frame)
                    if s is not None and not any(sig(v) == s for v in lib.values()):
                        lib[f"T{k}#{len(lib)}"] = frame          # CRYSTALLISE (incl. composed frames)
        mx = max(solved_tiers) if solved_tiers else 0
        hist.append({"cycle": cyc, "max_tier": mx, "solved": sorted(set(solved_tiers)),
                     "library": len(lib), "cost": cost})
        if verbose:
            print(f"  cycle {cyc:>2}  max tier {mx:>2}  solved {sorted(set(solved_tiers))}  "
                  f"library {len(lib):>2}  cost {cost}")
    return hist, lib


if __name__ == "__main__":
    t0 = time.time()
    CYCLES = int(os.environ.get("EM_CYCLES", "6"))
    print("EMERGENCE E-2 -- persistent library, many cycles, depth-forcing curriculum\n")
    print(f"curriculum: tier k = k base transforms composed; blind L0 depth 3 should wall at tier ~3\n")

    # each cycle sees tiers 1..cyc (graded: you cannot meet tier k before cycle k)
    print("LIBRARY arm (crystallises composed frames, carries across cycles):")
    hl, lib = run(True, CYCLES, tiers=None or [1, 2, 3, 4, 5, 6])
    print("\nBLIND arm (no library; L0 depth-3 search only):")
    hb, _ = run(False, CYCLES, tiers=[1, 2, 3, 4, 5, 6])

    ml = max(h["max_tier"] for h in hl); mb = max(h["max_tier"] for h in hb)
    cl = sum(h["cost"] for h in hl); cb = sum(h["cost"] for h in hb)
    print(f"\n  LIBRARY max tier {ml}  total cost {cl}   library size {len(lib)}")
    print(f"  BLIND   max tier {mb}  total cost {cb}")
    print(f"  depth gain {ml - mb} tiers; cost ratio {cb/max(1,cl):.1f}x")

    json.dump({"library": {k: str(v) for k, v in lib.items()}}, open(LIBFILE, "w"), indent=1)
    d = {"library_arm": hl, "blind_arm": hb, "max_tier_library": ml, "max_tier_blind": mb,
         "cost_library": cl, "cost_blind": cb, "library_size": len(lib),
         "secs": round(time.time() - t0, 1)}
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  ({time.time()-t0:.0f}s) -> {os.path.basename(OUT)}")
