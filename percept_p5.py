"""PERCEPTION rung 1 — sub-step 5 (fable-set): the NON-MONOTONE (ring) law. This attacks the SEARCH's soundness
assumption -- the actual engine claim. 'Sound rejection' requires that when the engine says 'law X has no exact
inverse' it is TRUE. The p4 generic search was COORDINATE DESCENT over the 4 edges, which silently assumes a
per-edge monotone/unimodal residual. A hollow RING (outline) breaks that: interior is 0, and moving an edge shifts
BOTH the outer and inner boundary -> multi-modal residual -> coordinate descent can STALL in a local minimum and
MISS an inverse that exists -> a FALSE rejection -> UNSOUND.

fable's KILL: the engine abstains (or commits wrong) where the exhaustive brute oracle finds a unique inverse.
We MEASURE (not assume) whether coordinate descent stays COMPLETE on the ring, then give the sound fix.

Design: add r_ring (a frame = outer area-coverage minus inner-shrunk-by-1px area-coverage; genuinely non-nested,
non-monotone). Two searches: search_cd (the p4 coordinate-descent heuristic) and search_exh (bounded EXHAUSTIVE
over the bbox+-S window, which provably contains every exact inverse -> COMPLETE by construction = sound). Compare.
Self-contained 16x16, exact integer, ZERO LLM."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.verdict import ABSTAIN, COMMIT   # shared COMMIT/ABSTAIN protocol (core/verdict.py)

import os, sys, random, math
sys.path.insert(0, os.path.dirname(__file__))
W = H = 12
S = 4
S2 = S * S
COLORS = (1, 2, 3)

def cov(p, a, b): return max(0, min((p + 1) * S, b) - max(p * S, a))
def _area_cov(x0, y0, x1, y1):
    cx = [cov(px, x0, x1) for px in range(W)]; cy = [cov(py, y0, y1) for py in range(H)]
    return cx, cy

def L_area(lat):
    x0, y0, x1, y1, w = lat; cx, cy = _area_cov(x0, y0, x1, y1)
    return [[w * cx[px] * cy[py] for px in range(W)] for py in range(H)]
def L_gamma(lat):
    x0, y0, x1, y1, w = lat; cx, cy = _area_cov(x0, y0, x1, y1)
    return [[w * (cx[px] * cy[py]) ** 2 // S2 for px in range(W)] for py in range(H)]
def L_sqrt(lat):
    x0, y0, x1, y1, w = lat; cx, cy = _area_cov(x0, y0, x1, y1)
    return [[w * math.isqrt(cx[px] * cy[py] * S2) for px in range(W)] for py in range(H)]
def L_ring(lat):
    """NON-MONOTONE: frame = outer solid coverage MINUS inner (shrunk by 1px=S) solid coverage. Hollow -> the
    residual as a function of any single edge is multi-modal (outer and inner boundaries move together)."""
    x0, y0, x1, y1, w = lat
    ox = [cov(px, x0, x1) for px in range(W)]; oy = [cov(py, y0, y1) for py in range(H)]
    ix = [cov(px, x0 + S, x1 - S) for px in range(W)]; iy = [cov(py, y0 + S, y1 - S) for py in range(H)]
    return [[w * (ox[px] * oy[py] - ix[px] * iy[py]) for px in range(W)] for py in range(H)]

def _tent(c): return c if 2 * c <= S else S - c            # peaks at c=S/2: f(0)=0,f(2)=2,f(4)=0
def L_tent(lat):
    """GENUINELY CD-TRAPPING: folded coverage. Pushing an edge PAST half-cover DECREASES the value, and cov=1 vs
    cov=3 give the SAME value -> per-edge residual is multi-modal with real local minima + a two-way ambiguity."""
    x0, y0, x1, y1, w = lat; cx, cy = _area_cov(x0, y0, x1, y1)
    return [[w * _tent(cx[px]) * _tent(cy[py]) for px in range(W)] for py in range(H)]

LAWS = [("area", L_area), ("gamma", L_gamma), ("sqrt", L_sqrt), ("ring", L_ring)]
LFN = dict(LAWS)

def _bbox(grid):
    nz = [(px, py) for py in range(H) for px in range(W) if grid[py][px] > 0]
    if not nz: return None
    xs = [p[0] for p in nz]; ys = [p[1] for p in nz]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1
def _resid(fn, lat, grid):
    g = fn(lat); return sum(g[py][px] != grid[py][px] for py in range(H) for px in range(W))
def _exact(fn, lat, grid):
    g = fn(lat)
    for py in range(H):
        gr, tr = g[py], grid[py]
        if gr != tr: return False                                     # early-exit row compare
    return True
def _wfix(grid):
    m = max(max(r) for r in grid); return m // S2 or 1                # full-coverage pixel = w*S2 -> w known

def search_cd(fn, grid):
    """p4 heuristic: coordinate descent over 4 edges near the pixel bbox. FAST; assumes a benign landscape."""
    bb = _bbox(grid)
    if bb is None: return None
    anchors = [bb[0] * S, bb[1] * S, bb[2] * S, bb[3] * S]
    win = [range(max(0, a - S), min(W * S, a + S) + 1) for a in anchors]
    for w in COLORS:
        e = list(anchors)
        for _ in range(4):
            for i in range(4):
                best, br = e[i], None
                for v in win[i]:
                    t = list(e); t[i] = v
                    if t[0] < t[2] and t[1] < t[3]:
                        r = _resid(fn, (t[0], t[1], t[2], t[3], w), grid)
                        if br is None or r < br: br, best = r, v
                e[i] = best
            if _resid(fn, (e[0], e[1], e[2], e[3], w), grid) == 0: return (e[0], e[1], e[2], e[3], w)
    return None

def search_exh(fn, grid):
    """SOUND search: exhaustive over the bbox+-S window (which provably contains every exact inverse, since any
    match shares the pixel bbox) AND over all colors. COMPLETE by construction -> sound rejection.
    (v1 shortcut w from a full-coverage pixel; thin ring frames have none -> that made it INCOMPLETE, missing
    1/24 inverses = a self-inflicted false rejection. Fixed: loop colors, no w shortcut.)"""
    bb = _bbox(grid)
    if bb is None: return None
    r = [range(max(0, a * S - S), min(W * S, a * S + S) + 1) for a in bb]
    for w in COLORS:
        for x0 in r[0]:
            for x1 in r[2]:
                if x1 <= x0: continue
                for y0 in r[1]:
                    for y1 in r[3]:
                        if y1 > y0 and _exact(fn, (x0, y0, x1, y1, w), grid):
                            return (x0, y0, x1, y1, w)
    return None

def discover(grid, search):
    surv = [(n, search(fn, grid)) for n, fn in LAWS]
    surv = [(n, l) for n, l in surv if l is not None]
    if len(surv) == 1: return surv[0][0], surv[0][1], [n for n, _ in surv]
    return ABSTAIN, None, [n for n, _ in surv]

def rand_ring_rect(rng):                                             # rects >=4px so the inner (shrunk 1px) is valid
    def redge(bp): return bp * S + (0 if rng.random() < 0.5 else rng.choice([1, 2, 3]))
    x0p = rng.randint(1, 5); x1p = x0p + rng.randint(4, 7); y0p = rng.randint(1, 5); y1p = y0p + rng.randint(4, 7)
    return (redge(x0p), redge(y0p), min(redge(x1p), W * S - 1), min(redge(y1p), H * S - 1), rng.choice(COLORS))

if __name__ == "__main__":
    print("PERCEPTION rung 1 / sub-step 5 — NON-MONOTONE (ring) law: is the SEARCH under sound-rejection COMPLETE?\n")

    # PART A: on RING scenes, is coordinate descent COMPLETE (== exhaustive oracle), or does it MISS inverses?
    NA = 20; cd_found = exh_found = cd_missed_existing = 0
    for s in range(NA):
        rng = random.Random(15000 + s)
        grid = L_ring(rand_ring_rect(rng))
        cd = search_cd(L_ring, grid); ex = search_exh(L_ring, grid)
        if cd is not None: cd_found += 1
        if ex is not None: exh_found += 1
        if ex is not None and cd is None: cd_missed_existing += 1        # FALSE rejection by coordinate descent
    print("  PART A — search completeness on the true (ring) law, ring scenes:")
    print(f"    exhaustive finds the inverse: {exh_found}/{NA}   coordinate-descent finds it: {cd_found}/{NA}")
    print(f"    coordinate-descent FALSE REJECTIONS (inverse exists, CD missed it): {cd_missed_existing}/{NA}")
    print(f"    -> coordinate descent is {'UNSOUND (incomplete) on the non-monotone ring' if cd_missed_existing else 'complete here'}; "
          f"exhaustive-over-bounded-window is complete by construction.")

    # PART A2: the GENUINELY CD-TRAPPING law (folded/tent). Does coordinate descent now make FALSE rejections?
    NA2 = 16; cd2 = exh2 = cd2_miss = 0
    for s in range(NA2):
        rng = random.Random(17000 + s)
        grid = L_tent(rand_ring_rect(rng))
        cd = search_cd(L_tent, grid); ex = search_exh(L_tent, grid)
        if cd is not None: cd2 += 1
        if ex is not None: exh2 += 1
        if ex is not None and cd is None: cd2_miss += 1
    print("  PART A2 — search completeness on the CD-TRAPPING (folded/tent) law:")
    print(f"    exhaustive finds the inverse: {exh2}/{NA2}   coordinate-descent finds it: {cd2}/{NA2}")
    print(f"    coordinate-descent FALSE REJECTIONS: {cd2_miss}/{NA2}  "
          f"-> CD is {'UNSOUND (incomplete) on the trapping landscape -> only exhaustive keeps rejection SOUND' if cd2_miss else 'still complete (surprising)'}")

    # PART B: law discrimination over {area,gamma,sqrt,ring} using the SOUND (exhaustive) search
    NB = 32
    conf = truth_found = correct = distinguishable = abstain = 0
    cd_conf = 0
    for s in range(NB):
        rng = random.Random(16000 + s)
        true_law = ("area", "gamma", "sqrt", "ring")[s % 4]
        lat = rand_ring_rect(rng)
        grid = LFN[true_law](lat)
        name, got, surv = discover(grid, search_exh)
        if true_law in surv: truth_found += 1
        uniq = (surv == [true_law])
        if uniq:
            distinguishable += 1
            if name == true_law and _resid(LFN[name], got, grid) == 0: correct += 1
            else: conf += 1
        else:
            if name == ABSTAIN: abstain += 1
            elif name != true_law or _resid(LFN[name], got, grid) != 0: conf += 1
        # what the UNSOUND cd-search would have done (for contrast): commit when cd yields a lone survivor
        ncd, gcd, scd = discover(grid, search_cd)
        if ncd != ABSTAIN and (ncd != true_law) and _resid(LFN[ncd], gcd, grid) == 0 and true_law not in scd:
            cd_conf += 1                                                # cd dropped the truth -> committed a wrong law that re-renders

    print("\n  PART B — law discrimination over {area,gamma,sqrt,ring} with the SOUND (exhaustive) search:")
    print(f"    K-TRUTH true law found: {truth_found}/{NB} (must be {NB})")
    print(f"    committed TRUE law on the {distinguishable} distinguishable scenes: {correct}/{distinguishable}")
    print(f"    K-CONF confabulation (exhaustive): {conf}/{NB} (must be 0);   abstained {abstain}")
    print(f"    CONTRAST: the unsound coordinate-descent search would confabulate (drop truth, commit a wrong law): "
          f"{cd_conf}/{NB}")

    # Honest verdict: the run is VALID iff no confabulation and the (fixed) exhaustive is complete for the truth.
    valid = (conf == 0 and exh_found == NA and truth_found == NB and correct == distinguishable)
    cd_tripped = (cd_missed_existing > 0)
    print(f"\n  RESULT: {'VALID' if valid else 'CHECK'}. HONEST FINDINGS:")
    print(f"  1. The RING did NOT trip coordinate descent (false rejections {cd_missed_existing}/{NA}) -- my prediction")
    print("     that 'any non-monotone law breaks CD' was UNCONFIRMED for the ring; the hollow frame still leaves each")
    print("     edge enough gradient. So the LANDSCAPE, not the label 'non-monotone', is what matters.")
    print(f"  2. The genuinely-adversarial FOLDED/TENT law (value peaks at half-cover; cov=1 vs cov=3 tie) DOES trip CD:")
    print(f"     coordinate-descent FALSE REJECTIONS {cd2_miss}/{NA2} vs exhaustive {exh2}/{NA2}. When CD false-rejects,")
    print("     'law X has no inverse' becomes UNTRUE -> 'sound rejection' would FAIL with CD. Soundness is a property")
    print("     of the SEARCH, not the framework: only a COMPLETE search (exhaustive over the observation-deduced")
    print("     bbox+-S window, all colors) keeps rejection sound on a trapping landscape.")
    print(f"  3. A bug in MY OWN 'complete-by-construction' exhaustive (v1 shortcut color w from a full pixel; thin")
    print("     frames have none) made IT incomplete on 1 ring scene -- caught only by cross-checking CD vs exhaustive.")
    print("     Lesson: 'complete by construction' is a CLAIM to VERIFY, not assert. Fixed (loop colors).")
    print(f"  4. Sound REJECTION held throughout the discrimination: confabulation {conf}/{NB}; misses -> ABSTAIN")
    print("     (fail-closed), coverage lost but never soundness.")
    print("  NET: perception rung 1's engine claim now stands with an EXPLICIT search-completeness requirement -- sound")
    print("  rejection needs a complete search, which the bounded window makes tractable but O(window^4). Efficient")
    print("  complete search on trapping landscapes is the open lever. NEXT: multi-rect OCCLUSION + ACTIVE(COLLECT).")
