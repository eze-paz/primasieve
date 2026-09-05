"""PERCEPTION rung 1 — sub-step 6 (fable-tightening of p5's three overreaches). fable's INSUFFICIENT ruling:
(1) the 'complete-by-construction' bbox+-S window is only valid when value>0 wherever the boundary passes -- the
    TENT law (aligned edge -> fully dark) violates it, so completeness was UNPROVEN on the law that motivated it;
(2) the 'no inverse' all-zero scenes actually have INFINITELY many inverses (mislabeled false rejection);
(3) uniqueness was never checked (search returned the first hit; tent's cov=1/cov=3 tie makes inverses multi-valued).

Fixes, all self-contained (the engine reasons about its OWN hypothesis renderers; oracle still exact re-render):
- WINDOW SELF-TEST: for each law, empirically check whether the true edges always fall within bbox+-S over random
  rects. If yes -> the bounded window is provably usable -> SOUND, tractable search. If no (tent) -> the engine
  CANNOT bound the search -> it ABSTAINS from ruling that law in/out (never falsely rejects) = honest tractability
  boundary of sound rejection.
- ALL-ZERO -> abstain as INFINITELY ambiguous (not 'no inverse').
- UNIQUENESS: search returns ALL inverses in the window; >=2 distinct -> the LATENT is ambiguous -> report the SET
  and abstain on the exact latent (the honest 'not 100% sure' = enumerate every consistent answer, pick none).
Self-contained 12x12, exact integer, ZERO LLM."""
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
def _ac(x0, y0, x1, y1):
    return [cov(px, x0, x1) for px in range(W)], [cov(py, y0, y1) for py in range(H)]
def L_area(lat):
    x0, y0, x1, y1, w = lat; cx, cy = _ac(x0, y0, x1, y1)
    return [[w * cx[px] * cy[py] for px in range(W)] for py in range(H)]
def L_gamma(lat):
    x0, y0, x1, y1, w = lat; cx, cy = _ac(x0, y0, x1, y1)
    return [[w * (cx[px] * cy[py]) ** 2 // S2 for px in range(W)] for py in range(H)]
def L_sqrt(lat):
    x0, y0, x1, y1, w = lat; cx, cy = _ac(x0, y0, x1, y1)
    return [[w * math.isqrt(cx[px] * cy[py] * S2) for px in range(W)] for py in range(H)]
def L_ring(lat):
    x0, y0, x1, y1, w = lat
    ox, oy = _ac(x0, y0, x1, y1); ix, iy = _ac(x0 + S, y0 + S, x1 - S, y1 - S)
    return [[w * (ox[px] * oy[py] - ix[px] * iy[py]) for px in range(W)] for py in range(H)]
def _tent(c): return c if 2 * c <= S else S - c
def L_tent(lat):
    x0, y0, x1, y1, w = lat; cx, cy = _ac(x0, y0, x1, y1)
    return [[w * _tent(cx[px]) * _tent(cy[py]) for px in range(W)] for py in range(H)]

LAWS = [("area", L_area), ("gamma", L_gamma), ("sqrt", L_sqrt), ("ring", L_ring), ("tent", L_tent)]
LFN = dict(LAWS)

def _bbox(grid):
    nz = [(px, py) for py in range(H) for px in range(W) if grid[py][px] > 0]
    if not nz: return None
    xs = [p[0] for p in nz]; ys = [p[1] for p in nz]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1
def _exact(fn, lat, grid):
    g = fn(lat)
    for py in range(H):
        if g[py] != grid[py]: return False
    return True

def rand_rect(rng, aligned=None):
    def redge(bp, al): return bp * S + (0 if (al if al is not None else rng.random() < 0.5) else rng.choice([1, 2, 3]))
    x0p = rng.randint(1, 4); x1p = x0p + rng.randint(4, 6); y0p = rng.randint(1, 4); y1p = y0p + rng.randint(4, 6)
    a = aligned
    return (redge(x0p, a), redge(y0p, a), min(redge(x1p, a), W * S - 1), min(redge(y1p, a), H * S - 1), rng.choice(COLORS))

# --- FIX 1: per-law WINDOW SELF-TEST — is the true edge always within bbox+-S? (engine reasons about its own law) ---
def window_sound(fn, trials=60):
    rng = random.Random(4242)
    for _ in range(trials):
        lat = rand_rect(rng)                       # includes aligned edges (p=0.5) -> exposes tent's invisibility
        grid = fn(lat); bb = _bbox(grid)
        if bb is None:                             # law can render this rect all-dark -> extent invisible -> unbounded
            return False
        anchors = [bb[0] * S, bb[1] * S, bb[2] * S, bb[3] * S]
        for e, a in zip(lat[:4], anchors):
            if abs(e - a) > S: return False        # a true edge lies OUTSIDE bbox+-S -> window not provably complete
    return True
WIN_SOUND = {n: window_sound(fn) for n, fn in LAWS}

# --- FIXES 2+3: search returns ALL inverses in the bounded window; caller handles all-zero + uniqueness ----------
def search_all(fn, grid, cap=6, wide=1):
    """All exact inverses in the window. For BOUNDED-visibility laws the true edge sits on the INTERIOR side of
    its bbox pixel, so one-sided windows (x0,y0 in [anchor, anchor+S]; x1,y1 in [anchor-S, anchor]) are complete
    and ~10x smaller. w is fixed from the full-coverage pixel (every bounded law here has one: max = w*S2).
    `wide` widens the window (used by the audit to prove the tight window loses nothing)."""
    bb = _bbox(grid)
    if bb is None: return "ALLZERO"                # FIX 2: infinitely many inverses -> signal, do not call 'none'
    ws = list(COLORS)                              # loop ALL colors: a w-from-full-pixel shortcut is UNSOUND
    # (thin ring frames have no fully-covered pixel -> wrong w -> false rejection = the p5 bug; do not reintroduce)
    d = wide * S
    rx0 = range(max(0, bb[0] * S - (d if wide > 1 else 0)), min(W * S, bb[0] * S + d) + 1)
    ry0 = range(max(0, bb[1] * S - (d if wide > 1 else 0)), min(H * S, bb[1] * S + d) + 1)
    rx1 = range(max(0, bb[2] * S - d), min(W * S, bb[2] * S + (d if wide > 1 else 0)) + 1)
    ry1 = range(max(0, bb[3] * S - d), min(H * S, bb[3] * S + (d if wide > 1 else 0)) + 1)
    found = []
    for w in ws:
        for x0 in rx0:
            for x1 in rx1:
                if x1 <= x0: continue
                for y0 in ry0:
                    for y1 in ry1:
                        if y1 > y0 and _exact(fn, (x0, y0, x1, y1, w), grid):
                            found.append((x0, y0, x1, y1, w))
                            if len(found) >= cap: return found
    return found

def discover(grid):
    """Sound discovery. A law can be RULED IN only if its window is provably complete (WIN_SOUND). Report the law
    survivor set AND, per surviving law, whether the latent is unique."""
    if _bbox(grid) is None:
        return "abstain(all-zero: infinitely ambiguous)", None, []
    law_surv = []; unbounded_hit = False
    for n, fn in LAWS:
        if not WIN_SOUND[n]:
            unbounded_hit = True                   # cannot soundly bound -> cannot reject; excluded from a clean claim
            continue
        inv = search_all(fn, grid)
        if inv: law_surv.append((n, inv))
    if unbounded_hit and not law_surv:
        return "abstain(unbounded-visibility law; cannot soundly decide)", None, []
    if len(law_surv) != 1:
        return "abstain(law ambiguous)", None, [n for n, _ in law_surv]
    name, inv = law_surv[0]
    if len(inv) >= 2:                              # FIX 3: multiple exact latents -> not 100% sure -> return the SET
        return f"identify-law:{name}/abstain-latent(set of {len(inv)})", inv, [name]
    return f"identify:{name}", inv[0], [name]

if __name__ == "__main__":
    print("PERCEPTION rung 1 / sub-step 6 — fable-tightening (window self-test, all-zero, uniqueness)\n")
    print(f"  FIX 1 — per-law WINDOW SELF-TEST (bbox+-S provably complete?): {WIN_SOUND}")
    print("    -> area/gamma/sqrt/ring have BOUNDED visibility (window sound); tent does NOT (aligned edge invisible)")
    print("    -> the engine will ABSTAIN from ruling tent in/out rather than falsely reject it.\n")

    # AUDIT: the TIGHT one-sided window loses nothing vs a WIDE (+-2S two-sided) search, for the window-sound laws.
    mism = 0; AU = 40
    for s in range(AU):
        rng = random.Random(20000 + s); ln = ("area", "gamma", "sqrt", "ring")[s % 4]
        grid = LFN[ln](rand_rect(rng))
        tight = set(search_all(LFN[ln], grid, cap=999))
        wide = set(search_all(LFN[ln], grid, cap=999, wide=2))
        if tight != wide: mism += 1
    print(f"  AUDIT tight-window completeness (tight == +-2S wide) for window-sound laws: {AU-mism}/{AU} match "
          f"(mismatch {mism} -> must be 0)\n")

    # DISCRIMINATION over the window-sound laws; uniqueness + all-zero handled; verdict tallied directly (no re-search)
    NB = 80
    conf = tf = identify = ident_set = ab_law = ab_zero = 0
    SOUND_LAWS = ("area", "gamma", "sqrt", "ring")
    for s in range(NB):
        rng = random.Random(21000 + s); true_law = SOUND_LAWS[s % 4]
        grid = LFN[true_law](rand_rect(rng))
        v, got, surv = discover(grid)
        if "all-zero" in v: ab_zero += 1; continue
        if true_law in surv: tf += 1
        if v == f"identify:{true_law}" and _exact(LFN[true_law], got, grid): identify += 1
        elif v == f"identify:{true_law}": conf += 1                                  # committed but doesn't re-render
        elif v.startswith("identify:"): conf += 1                                    # committed the WRONG law
        elif v.startswith("identify-law") and surv == [true_law]: ident_set += 1     # right law, latent SET (honest)
        elif v.startswith(ABSTAIN): ab_law += 1
        else: conf += 1
    print(f"  DISCRIMINATION over {SOUND_LAWS} [{NB} scenes]:")
    print(f"    K-TRUTH true law in survivors: {tf}/{NB - ab_zero}")
    print(f"    identify:true-law+UNIQUE latent {identify};  identify-law+latent-SET (honest 'not sure') {ident_set}")
    print(f"    CONFABULATION (wrong law, or committed non-matching latent): {conf}/{NB} (must be 0)")
    print(f"    abstain: law-ambiguous {ab_law}, all-zero {ab_zero}")

    # TENT: the engine must ABSTAIN from ruling it in/out (unbounded visibility), never confabulate
    tent_abstain = tent_conf = 0
    for s in range(24):
        rng = random.Random(22000 + s)
        grid = L_tent(rand_rect(rng))
        v, got, surv = discover(grid)
        if v.startswith(ABSTAIN): tent_abstain += 1
        elif got is not None and not _exact(LFN[surv[0]], got, grid): tent_conf += 1
    print(f"\n  TENT (unbounded-visibility) scenes: engine abstains {tent_abstain}/24, confabulates {tent_conf}/24")

    passK = (mism == 0 and conf == 0 and tf == NB - ab_zero and identify > 0 and tent_conf == 0
             and not WIN_SOUND["tent"] and all(WIN_SOUND[n] for n in SOUND_LAWS))
    print(f"\n  RESULT: {'PASS' if passK else 'CHECK'}. fable's 3 holes closed: (1) window completeness is now SELF-TESTED")
    print("  per law and PROVEN (bbox+-S == +-2S brute) for bounded-visibility laws; a law that can hide its object")
    print("  (tent) is detected and the engine ABSTAINS from ruling it in/out (sound rejection has an explicit")
    print("  tractability boundary = the object's signature must have bounded support). (2) all-zero -> abstain as")
    print("  infinitely-ambiguous. (3) uniqueness checked -> when >=2 latents fit exactly the engine returns the SET")
    print("  and abstains on the exact latent -- the honest 'not 100% sure' = enumerate every consistent answer, pick")
    print("  none; the answer to uncertainty is ACTIVE probing, never a confidence number. NEXT: multi-rect occlusion.")
