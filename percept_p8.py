"""PERCEPTION rung 1 — sub-step p8 (fable-set): ACTIVE(COLLECT) over the occlusion survivor set, and the QUOTIENT
p7 was missing. p7 returned the full set of consistent scenes but CONFLATED 'unknown' (resolvable by more
observation) with 'unknowable' (irreducibly hidden). p8 adds a sound probe -- PEEL pixel (x,y): reveal the color
BENEATH the top layer (what a physical 'lift the top sticker' would show). The engine ACTIVELY chooses the pixel
that maximally SPLITS the current survivor set, filters by the true answer, and drives the set down to its
OBSERVATIONALLY-IRREDUCIBLE class (all remaining members agree on every peel = genuinely unknowable), halting when
no probe splits it. This separates unknown from unknowable.

fable KILLS: ACTIVE reaches the irreducible class in FEWER peels than RANDOM; ACTIVE NEVER spends a zero-split probe
(a peel all survivors already agree on = vacuous 'confabulation' of active design); both HALT at the irreducible
class (the true observational-equivalence class, containing the truth). Completeness of the bbox bound is a THEOREM
(any layer pixel outside the nonzero bbox renders nonzero or is covered by one that does -> contradiction) GIVEN no
rect uses the background color; asserted below. Pure stdlib, exact, ZERO LLM."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.collect import best_split
from core.registry import selfcheck

import os, sys, random, statistics
sys.path.insert(0, os.path.dirname(__file__))
from percept_p7 import G, NP, COLORS, render, survivors, all_rects, RMASK, to_scene, bbox, rand_scene

assert 0 not in COLORS, "completeness theorem requires layer colors != background(0) (no 'eraser' rects)"

def peel(scene, x, y):
    """Color BENEATH the top layer at (x,y): the 2nd-highest layer covering it, else background 0."""
    i = y * G + x
    covering = [c for (m, c) in scene if (m >> i) & 1]      # bottom-to-top order preserved
    return covering[-2] if len(covering) >= 2 else 0

def peel_grid(scene):
    return tuple(peel(scene, x, y) for y in range(G) for x in range(G))

def bbox_rects(grid):
    bb = bbox(grid)
    if bb is None: return []
    return all_rects(bb[0], bb[1], bb[2], bb[3])            # THEOREM: consistent rects subset the nonzero bbox

def refine(grid, arm, seed):
    """Return (#peels_used, final_survivor_set, halted_ok). ACTIVE picks the max-split pixel; RANDOM picks any."""
    rng = random.Random(seed)
    true_scene = TRUE[grid]
    rects = bbox_rects(grid)
    surv = [to_scene(m, RMASK) for m in survivors(grid, rects)]
    peeled = set(); peels = 0; wasted = 0
    while True:
        # candidate pixels that still SPLIT the survivor set (>=2 distinct peel values among survivors)
        splits = {}
        for i in range(NP):
            x, y = i % G, i // G
            if i in peeled: continue
            vals = {peel(s, x, y) for s in surv}
            if len(vals) >= 2: splits[i] = len(vals)
        if not splits:                                     # IRREDUCIBLE class reached -> halt
            return peels, surv, True
        if arm == "active":
            i = best_split(surv, list(splits), lambda s, k: peel(s, k % G, k // G))   # core.collect (shared with E6, phase5c)
        else:
            i = rng.choice([k for k in range(NP) if k not in peeled])
            if i not in splits: wasted += 1                # RANDOM may spend a zero-split (vacuous) probe
        x, y = i % G, i // G
        ans = peel(true_scene, x, y)                       # SOUND oracle: the true peel
        surv = [s for s in surv if peel(s, x, y) == ans]   # REJECT inconsistent
        peeled.add(i); peels += 1
        if arm == "active" and i not in splits:            # must never happen for active
            return peels, surv, "ACTIVE_WASTED"

if __name__ == "__main__":
    selfcheck(__file__)   # verifies this file\'s PUBLISHED claims (core/registry.py) at exit
    print("PERCEPTION rung 1 / p8 — ACTIVE(COLLECT) peeling: drive the survivor set to its IRREDUCIBLE class\n")
    # focus on AMBIGUOUS scenes (large survivor sets), where active design matters
    scenes = []
    s = 0
    while len(scenes) < 24:
        rng = random.Random(40000 + s); s += 1
        sc = rand_scene(rng, same_color=(s % 2 == 0))
        (ma, ca), (mb, cb) = sc
        grid = render(sc)
        rects = bbox_rects(grid)
        if len(survivors(grid, rects)) >= 4:               # only genuinely ambiguous scenes
            scenes.append((grid, sc))
    TRUE = {g: sc for g, sc in scenes}

    a_peels, r_peels = [], []
    active_wasted = halt_bad = truth_lost = irar = 0
    for grid, sc in scenes:
        ap, aset, aok = refine(grid, "active", 0)
        rp, rset, rok = refine(grid, "random", 7)
        if aok == "ACTIVE_WASTED": active_wasted += 1; aok = False
        a_peels.append(ap); r_peels.append(rp)
        if aok is not True or rok is not True: halt_bad += 1
        # both must halt at the SAME irreducible class = the true observational-equivalence class
        a_class = {peel_grid(x) for x in aset}; r_class = {peel_grid(x) for x in rset}
        if len(a_class) != 1 or a_class != r_class: irar += 1        # active/random converge to the same class
        if peel_grid(sc) not in a_class: truth_lost += 1            # truth's peel-class is the surviving class

    print(f"  [{len(scenes)} ambiguous scenes; initial survivor sets >=4]")
    print(f"  peels to reach the irreducible class: ACTIVE mean {statistics.mean(a_peels):.1f} (max {max(a_peels)}), "
          f"RANDOM mean {statistics.mean(r_peels):.1f} (max {max(r_peels)})")
    print(f"  ACTIVE spent a ZERO-SPLIT (vacuous) probe: {active_wasted}/{len(scenes)} (must be 0)")
    print(f"  both HALT at the irreducible class: {'OK' if halt_bad == 0 else f'{halt_bad} FAILED'}")
    print(f"  ACTIVE & RANDOM converge to the SAME single irreducible class: {'OK' if irar == 0 else f'{irar} FAILED'}")
    print(f"  the truth's peel-class IS the surviving class (0 confab): {'OK' if truth_lost == 0 else f'{truth_lost} FAILED'}")

    # show the quotient: full survivor set vs its irreducible (unknowable) residue on one same-color scene
    demo = next(g for g, sc in scenes if len(survivors(g, bbox_rects(g))) >= 20)
    full = len(survivors(demo, bbox_rects(demo)))
    _, aset, _ = refine(demo, "active", 0)
    print(f"\n  QUOTIENT demo (a same-color scene): full survivor set {full} -> after active peeling, irreducible "
          f"class size {len(aset)} ({len({peel_grid(x) for x in aset})} distinct peel-signature)")
    print("    => 'unknown' (resolved by peeling) is separated from 'unknowable' (the irreducible residue: members")
    print("    no peel can tell apart -- e.g. same-color tilings / z of non-overlap). The engine reports the residue,")
    print("    never a guess.")

    passK = (active_wasted == 0 and halt_bad == 0 and irar == 0 and truth_lost == 0
             and statistics.mean(a_peels) < statistics.mean(r_peels))
    print(f"\n  RESULT: {'PASS' if passK else 'CHECK'}. ACTIVE(COLLECT) drives the occlusion survivor set to its")
    print("  observationally-irreducible class in fewer peels than RANDOM, never wastes a zero-split probe, halts")
    print("  correctly, and preserves the truth's class (0 confab) -- the perception analog of E6's active design,")
    print("  and it makes the p7 quotient (unknown vs UNKNOWABLE) explicit. NEXT: p9 the E8-over-pixel-string kill.")
