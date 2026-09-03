"""PERCEPTION rung 1 — sub-step 3 (fable-set): close gap (a') + (i). percept_p2 had ONE gray renderer (area=truth)
vs whole-pixel strawmen -> area won gray scenes by default (1 bit), inverter bespoke-analytic. Here:
  (alpha) TWO genuine gray RIVALS that are observationally EQUIVALENT to area on a real fraction of gray scenes:
          xflat = whole-pixel in X, sub-pixel in Y ; yflat = whole-pixel in Y, sub-pixel in X.
          So area is uniquely identified ONLY when BOTH an x-edge AND a y-edge are sub-pixel (residual rejects both
          flats); when only one axis is sub-pixel, a flat co-survives and the engine must NOT claim area.
  (beta)  ONE generic latent SEARCH (coordinate descent over the 4 sub-pixel edges near the pixel bbox, all colors,
          accept only EXACT re-render) inverts under EVERY renderer -- no bespoke inverter.

Per-edge alignment is independent (p=0.5) so each flat is a NON-strawman rival (co-survives >=~25% of gray scenes).
fable KILLs: K1 area committed while a gray flat also survives -> smuggled prior (must be 0). K2 area always survives
(search complete for the truth). K3 each gray flat survives on >=10% of GRAY scenes (else strawman -> void). K4 the
survivor set varies (>=2 distinct sets). Self-contained 16x16, exact integer, ZERO LLM."""
import os, sys, random
sys.path.insert(0, os.path.dirname(__file__))
W = H = 16
S = 4
S2 = S * S
COLORS = (1, 2, 3)

def cov(p, a, b): return max(0, min((p + 1) * S, b) - max(p * S, a))     # subcell coverage of pixel p by [a,b)

# --- renderers: same latent (x0,y0,x1,y1,w), different coverage laws ------------------------------------------
def r_area(lat):                              # TRUTH: sub-pixel in BOTH axes
    x0, y0, x1, y1, w = lat
    cx = [cov(px, x0, x1) for px in range(W)]; cy = [cov(py, y0, y1) for py in range(H)]
    return [[w * cx[px] * cy[py] for px in range(W)] for py in range(H)]
def r_naive(lat):                             # whole-pixel BOTH axes (no gray)
    x0, y0, x1, y1, w = lat
    px0, py0, px1, py1 = round(x0 / S), round(y0 / S), round(x1 / S), round(y1 / S)
    cx = [S if px0 <= px < px1 else 0 for px in range(W)]; cy = [S if py0 <= py < py1 else 0 for py in range(H)]
    return [[w * cx[px] * cy[py] for px in range(W)] for py in range(H)]
def r_xflat(lat):                             # GRAY rival: whole-pixel X, sub-pixel Y
    x0, y0, x1, y1, w = lat
    px0, px1 = round(x0 / S), round(x1 / S)
    cx = [S if px0 <= px < px1 else 0 for px in range(W)]; cy = [cov(py, y0, y1) for py in range(H)]
    return [[w * cx[px] * cy[py] for px in range(W)] for py in range(H)]
def r_yflat(lat):                             # GRAY rival: whole-pixel Y, sub-pixel X
    x0, y0, x1, y1, w = lat
    py0, py1 = round(y0 / S), round(y1 / S)
    cx = [cov(px, x0, x1) for px in range(W)]; cy = [S if py0 <= py < py1 else 0 for py in range(H)]
    return [[w * cx[px] * cy[py] for px in range(W)] for py in range(H)]

LIB = [("naive", r_naive), ("xflat", r_xflat), ("yflat", r_yflat), ("area", r_area)]   # Occam: area LAST
GRAY_RIVALS = {"xflat", "yflat"}

# --- ONE generic latent search shared by all renderers (beta) --------------------------------------------------
def _bbox(grid):
    nz = [(px, py) for py in range(H) for px in range(W) if grid[py][px] > 0]
    if not nz: return None
    xs = [p[0] for p in nz]; ys = [p[1] for p in nz]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1
def _resid(rfn, lat, grid):
    g = rfn(lat); return sum(g[py][px] != grid[py][px] for py in range(H) for px in range(W))
def search(rfn, grid):
    bb = _bbox(grid)
    if bb is None: return None
    anchors = [bb[0] * S, bb[1] * S, bb[2] * S, bb[3] * S]
    windows = [range(max(0, a - S), min(W * S, a + S) + 1) for a in anchors]
    for w in COLORS:
        edges = list(anchors)
        for _ in range(3):                    # coordinate-descent passes
            for i in range(4):
                best, bestr = edges[i], None
                for v in windows[i]:
                    e = list(edges); e[i] = v
                    if e[0] < e[2] and e[1] < e[3]:
                        r = _resid(rfn, (e[0], e[1], e[2], e[3], w), grid)
                        if bestr is None or r < bestr: bestr, best = r, v
                edges[i] = best
            lat = (edges[0], edges[1], edges[2], edges[3], w)
            if _resid(rfn, lat, grid) == 0: return lat      # accept EXACT only (sound)
    return None

def discover(grid):
    surv = [(n, search(rfn, grid)) for n, rfn in LIB]
    surv = [(n, l) for n, l in surv if l is not None]
    if not surv: return "abstain", None, []
    return surv[0][0], surv[0][1], [n for n, _ in surv]     # simplest survivor (Occam)

def rand_rect(rng):
    def redge(base_px): return base_px * S + (0 if rng.random() < 0.5 else rng.choice([1, 2, 3]))
    x0p = rng.randint(1, 6); x1p = x0p + rng.randint(3, 6); y0p = rng.randint(1, 6); y1p = y0p + rng.randint(3, 6)
    x0, x1 = redge(x0p), min(redge(x1p), W * S - 1); y0, y1 = redge(y0p), min(redge(y1p), H * S - 1)
    return (x0, y0, x1, y1, rng.choice(COLORS))

if __name__ == "__main__":
    print("PERCEPTION rung 1 / sub-step 3 — generic SEARCH + genuine RIVAL gray renderers (fable K1-K4)\n")
    RFN = dict(LIB)
    N = 100
    confab = abst = area_survive = area_sole = grayN = area_with_rival = 0
    rival_gray = {d: 0 for d in GRAY_RIVALS}
    sets = {}
    for s in range(N):
        rng = random.Random(11000 + s)
        lat_true = rand_rect(rng)
        grid = r_area(lat_true)               # WORLD is always area (truth)
        w = lat_true[4]
        has_gray = any(v not in (0, w * S2) for row in grid for v in row)
        name, lat, surv = discover(grid)
        sets[tuple(surv)] = sets.get(tuple(surv), 0) + 1
        if name == "abstain": abst += 1
        elif _resid(RFN[name], lat, grid) != 0: confab += 1
        if "area" in surv: area_survive += 1
        if name == "area" and any(d in surv for d in GRAY_RIVALS): area_with_rival += 1
        if has_gray:
            grayN += 1
            if surv == ["area"]: area_sole += 1
            for d in GRAY_RIVALS:
                if d in surv: rival_gray[d] += 1

    print(f"  [{N} scenes; {grayN} gray-edge grids]")
    print(f"  SOUND: CONFABULATION {confab}/{N}, abstain {abst}")
    print(f"  K2 area-always-survives (search complete for truth): {area_survive}/{N} (must be {N})")
    print(f"  DISCOVERY: area is SOLE survivor on {area_sole}/{grayN} gray scenes (BOTH axes sub-pixel -> both flats rejected)")
    print(f"  K1 area committed while a gray rival also survives: {area_with_rival}/{N} (must be 0)")
    print(f"  K3 gray-rival co-survival on GRAY scenes (>=10% each): "
          f"{ {d: f'{rival_gray[d]}/{grayN} ({100*rival_gray[d]//max(1,grayN)}%)' for d in GRAY_RIVALS} }")
    print(f"  K4 distinct survivor-sets: {len(sets)} (must be >=2)")
    for k, v in sorted(sets.items(), key=lambda kv: -kv[1]): print(f"       {v:3d}  {k}")

    okK3 = all(rival_gray[d] >= 0.10 * grayN for d in GRAY_RIVALS)
    passK = (confab == 0 and area_survive == N and area_with_rival == 0 and len(sets) >= 2 and okK3)
    print(f"\n  RESULT: {'PASS' if passK else 'CHECK'}. Area is selected AGAINST genuine gray rivals by residual — it")
    print("  wins ONLY when both flats are residual-rejected (both axes sub-pixel); when a flat co-survives the engine")
    print("  commits the simpler flat and does NOT over-claim area (K1=0). Generic search shared by all renderers.")
    print("  -> gap (a')+(i) closed on single rects. NEXT: multi-rect OCCLUSION (combinatorial, non-analytic search)")
    print("  + ACTIVE(COLLECT) scene selection + E8-over-pixel-string kill baseline.")
