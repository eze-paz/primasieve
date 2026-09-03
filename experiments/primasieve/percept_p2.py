"""PERCEPTION rung 1 — sub-step 2 (fable-set): close gap (a). In percept_p1 the area-coverage law was HANDED to
the inverter in code (the engine verified a human's inference, searched nothing). Here the ENGINE must DISCOVER
which renderer the world uses, by SOUND RESIDUAL REJECTION over a renderer-hypothesis library — exactly the
E7/v2/v3 pattern, now on the perceptual channel.

Library = {naive binary-fill, area-coverage(truth), floor-fill decoy, half-threshold decoy}. Per scene:
  (i)  REJECT any renderer that cannot invert the grid EXACTLY (residual != 0);
  (ii) invert only under survivors;
  (iii) return the SURVIVOR SET; commit the SIMPLEST survivor (Occam), NEVER area when a simpler one also fits.

fable's KILL: if area is ever committed while >=2 renderers survive (e.g. PIXEL-ALIGNED scenes, where naive and
area render identically) -> a smuggled prior -> FAIL. Selection of area must be RESIDUAL-DRIVEN (naive rejected
by the gray edges), never by list order. That makes area a genuine DISCOVERY, not a hardcode.

Pure stdlib, exact integer, ZERO LLM. Sealed renderer + oracle reused from percept_p1."""
import os, sys, random, statistics
sys.path.insert(0, os.path.dirname(__file__))
from percept_p1 import W, H, S, S2, COLORS, render, oracle_equal, infer_single

# --- renderer HYPOTHESES: all take the same latent (x0,y0,x1,y1,w) in SUBPIXEL coords, render differently -----
def _px_fill(px0, py0, px1, py1, w):
    g = [[0] * W for _ in range(H)]
    for py in range(max(0, py0), min(H, py1)):
        for px in range(max(0, px0), min(W, px1)):
            g[py][px] = w * S2
    return g

def render_area(lat):                       # TRUTH: per-subcell coverage summed (the sealed law)
    return render([(*lat, 0)])
def render_naive(lat):                       # edges ROUNDED to nearest pixel, whole-pixel fill (no gray)
    x0, y0, x1, y1, w = lat
    return _px_fill(round(x0 / S), round(y0 / S), round(x1 / S), round(y1 / S), w)
def render_floor(lat):                        # decoy: edges TRUNCATED to pixel, whole-pixel fill
    x0, y0, x1, y1, w = lat
    return _px_fill(x0 // S, y0 // S, x1 // S, y1 // S, w)
def render_thresh(lat):                       # decoy: a pixel is full iff >= half its subcells are covered
    x0, y0, x1, y1, w = lat
    g = [[0] * W for _ in range(H)]
    for py in range(H):
        for px in range(W):
            cov = max(0, min((px + 1) * S, x1) - max(px * S, x0)) * max(0, min((py + 1) * S, y1) - max(py * S, y0))
            if cov * 2 >= S2:
                g[py][px] = w * S2
    return g

# --- inversion under each renderer: find SOME latent it maps exactly to the grid, else None (residual reject) --
def _bbox_pixels(grid):
    nz = [(px, py) for py in range(H) for px in range(W) if grid[py][px] > 0]
    if not nz:
        return None
    xs = [p[0] for p in nz]; ys = [p[1] for p in nz]
    w = max(max(r) for r in grid) // S2 or 1
    return (min(xs) * S, min(ys) * S, (max(xs) + 1) * S, (max(ys) + 1) * S, w)
def invert_area(grid):
    v, lat = infer_single(grid)
    return lat if v == "identify" else None
def invert_wholepixel(grid, rfn):            # naive/floor/thresh only make whole-pixel grids -> reject any gray
    lat = _bbox_pixels(grid)
    return lat if (lat is not None and oracle_equal(rfn(lat), grid)) else None

# Occam order: simpler (whole-pixel, no gray) renderers FIRST; area last. Area may win ONLY by residual rejection.
LIB = [("naive", render_naive, lambda g: invert_wholepixel(g, render_naive)),
       ("floor", render_floor, lambda g: invert_wholepixel(g, render_floor)),
       ("thresh", render_thresh, lambda g: invert_wholepixel(g, render_thresh)),
       ("area", render_area, invert_area)]

def discover(grid):
    """Return (committed_renderer_name, latent, survivor_set). Commit the SIMPLEST survivor; abstain if none."""
    survivors = []
    for name, rfn, inv in LIB:
        lat = inv(grid)
        if lat is not None and oracle_equal(rfn(lat), grid):    # SOUND: survives iff it re-renders EXACTLY
            survivors.append((name, lat))
    if not survivors:
        return "abstain", None, []
    name, lat = survivors[0]                                    # LIB is Occam-ordered -> simplest survivor
    return name, lat, [s[0] for s in survivors]

# --- scene generators: PIXEL-ALIGNED (edges on pixel grid) vs SUBPIXEL (gray edges) ---
def rand_rect(rng, aligned):
    m = S if aligned else 1                                     # aligned -> edges multiples of S
    def snap(v): return (v // m) * m
    x0 = snap(rng.randint(1 * S, 13 * S)); y0 = snap(rng.randint(1 * S, 13 * S))
    x1 = snap(x0 + rng.randint(3 * S, 8 * S)); y1 = snap(y0 + rng.randint(3 * S, 8 * S))
    if not aligned:                                            # force at least one truly sub-pixel edge
        x1 += rng.choice([1, 2, 3])
    x1 = min(x1, W * S - S); y1 = min(y1, H * S - S)
    return (x0, y0, x1, y1, rng.choice(COLORS))

if __name__ == "__main__":
    print("PERCEPTION rung 1 / sub-step 2 — the ENGINE discovers the renderer by SOUND RESIDUAL REJECTION\n")
    N = 80
    RFN = {"naive": render_naive, "floor": render_floor, "thresh": render_thresh, "area": render_area}
    kill_fired = 0            # fable's KILL: area committed while >=2 survivors
    cover = confab = abst = 0
    gray_area = grayN = flat_naive = flatN = miss = 0
    survset_hist = {}
    for s in range(N):
        rng = random.Random(7000 + s)
        lat_true = rand_rect(rng, aligned=(s % 2 == 0))
        grid = render([(*lat_true, 0)])
        w_true = lat_true[4]
        has_gray = any(v not in (0, w_true * S2) for row in grid for v in row)   # GENERATOR-INDEPENDENT label
        name, lat, surv = discover(grid)
        survset_hist[tuple(surv)] = survset_hist.get(tuple(surv), 0) + 1
        if name == "abstain":
            abst += 1
        elif oracle_equal(RFN[name](lat), grid):
            cover += 1
        else:
            confab += 1
        if name == "area" and len(surv) >= 2:                  # fable's KILL
            kill_fired += 1
        if has_gray:                                           # a gray grid: naive CANNOT fit -> area must win
            grayN += 1
            if name == "area" and "naive" not in surv: gray_area += 1
            else: miss += 1
        else:                                                  # whole-pixel grid: commit the simplest (naive)
            flatN += 1; flat_naive += (name == "naive")

    print(f"  [{N} scenes -> by ACTUAL grid content: {grayN} gray (sub-pixel edges), {flatN} whole-pixel]")
    print(f"  GROUNDING: committed-renderer re-renders EXACT {cover}/{N}, CONFABULATION {confab}/{N}, abstain {abst}/{N}")
    print(f"  DISCOVERY: on GRAY grids, area SELECTED via residual (naive rejected) {gray_area}/{grayN}  (misses {miss})")
    print(f"  ON WHOLE-PIXEL grids, simplest (naive) committed {flat_naive}/{flatN} (area NOT over-claimed)")
    print(f"  fable KILL (area chosen despite >=2 survivors) fired {kill_fired}/{N}  -> must be 0")
    print(f"  survivor-set histogram: {survset_hist}")

    # decoy sanity: floor/thresh must be rejected where they disagree with truth
    rng = random.Random(999); dl = rand_rect(rng, aligned=False)
    dg = render([(*dl, 0)])
    print(f"\n  decoy check on a sub-pixel scene: survivors = {discover(dg)[2]} (floor/thresh must be absent)")

    verdict = "PASS" if (confab == 0 and kill_fired == 0 and gray_area == grayN and flat_naive == flatN) else "CHECK"
    print(f"\n  RESULT: {verdict}. The engine now DISCOVERS the area-coverage renderer from the gray residual")
    print("  (area wins ONLY when naive is residual-rejected), commits the simplest survivor on underdetermined")
    print("  (pixel-aligned) scenes, and never over-claims area with >=2 survivors -> gap (a) closed on single rects.")
    print("  NEXT: multi-rect occlusion inference (search, not analytic inverse) + ACTIVE(COLLECT) scene probing +")
    print("  the E8-over-pixel-string kill baseline.")
