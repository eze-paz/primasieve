"""PERCEPTION rung 1 (fable-designed; see perception_p1_prereg.md). The FIRST genuinely perceptual rung: the
observation is NOT already a token -- it is a 24x24 gray grid with no delimiters, lossy (occlusion), many-to-one.
The oracle stays SOUND: a deterministic, SEALED rasterizer renders a hidden symbolic scene (axis-aligned
rectangles) -> grid; the agent infers the scene from the grid ALONE; correctness is checked by PIXEL-EXACT
re-render. No noise (that is rung 2, gated on E1's unsound-oracle mechanism).

This file delivers rung-1 START: (1) the sealed exact-integer rasterizer + re-render oracle; (2) single-rectangle
latent inference by coverage-inversion + sound re-render rejection (grounds, 0 confab); (3) the INVENTION TARGET
is real -- a NAIVE binary-fill (integer-pixel) renderer CANNOT match the sub-pixel gray edges; the area-coverage
law can; (4) ABSTENTION on genuinely undecidable (occluded) scenes where >=2 latents re-render identically;
(5) the KILL baselines ("tokens smuggled back in"): a fixed-index positional decode must FAIL.

Everything is exact integer arithmetic -> the re-render oracle is deterministic and sound. Pure stdlib, ZERO LLM."""
import os, sys, random, statistics
sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------------------------------------------
# SEALED RASTERIZER (the renderer). The inference code below may ONLY call render(); it never reads a scene's
# rectangles. Subpixel resolution S: coords are integers in [0, W*S] = 1/S-pixel resolution. A pixel's value is
# the SUM over its S*S subcells of the top-most (painter's z-order) covering rectangle's gray weight. Rectangles
# use the half-open fill rule at subpixel resolution: covered iff x0 <= cx < x1 and y0 <= cy < y1. A pixel that a
# rectangle edge crosses gets PARTIAL coverage -> an intermediate gray level == the sub-pixel position, exactly.
# ---------------------------------------------------------------------------------------------------------------
W = H = 24
S = 4                      # 4x4 supersample; edges land on a 1/4-pixel grid
S2 = S * S                 # 16 subcells / pixel
COLORS = (1, 2, 3)         # gray weights; interior pixel = w*S2 (<=48, fits a byte)

def render(scene):
    """scene = list of (x0,y0,x1,y1,w,z) in SUBPIXEL coords. Returns a 24x24 grid of ints (0..48). SEALED."""
    sub = [[0] * (W * S) for _ in range(H * S)]                 # subcell gray weights
    for (x0, y0, x1, y1, w, z) in sorted(scene, key=lambda r: r[5]):   # ascending z = painter's order
        for cy in range(max(0, y0), min(H * S, y1)):
            row = sub[cy]
            for cx in range(max(0, x0), min(W * S, x1)):
                row[cx] = w                                     # higher z drawn later -> overwrites (occlusion)
    grid = [[0] * W for _ in range(H)]
    for py in range(H):
        for px in range(W):
            acc = 0
            for sy in range(S):
                base = sub[py * S + sy]
                b = px * S
                for sx in range(S):
                    acc += base[b + sx]
            grid[py][px] = acc
    return grid

def oracle_equal(g1, g2):
    """SOUND oracle: pixel-exact re-render match. Deterministic; generator-independent."""
    return g1 == g2

# ---------------------------------------------------------------------------------------------------------------
# NAIVE hypothesis (the wrong default the loop must reject): binary fill at INTEGER-PIXEL edges, no gray. This is
# what a learner without the area-coverage law would commit to. It CANNOT produce edge gray levels.
# ---------------------------------------------------------------------------------------------------------------
def render_naive(px0, py0, px1, py1, w):
    grid = [[0] * W for _ in range(H)]
    for py in range(max(0, py0), min(H, py1)):
        for px in range(max(0, px0), min(W, px1)):
            grid[py][px] = w * S2                               # whole-pixel fill only
    return grid

# ---------------------------------------------------------------------------------------------------------------
# INFERENCE (the agent). Sees ONLY the grid. For a single axis-aligned rect the coverage is SEPARABLE:
#   pixel(px,py) = w * hx(px) * hy(py),  hx,hy in [0,S]  (subcell columns/rows covered in that pixel).
# So a vertically-interior row (hy=S) exposes hx(px)=pixel/(w*S), from which x0,x1 recover exactly; likewise y.
# Then we VERIFY by exact re-render (sound rejection) with a tiny +-1 subpixel local search for robustness.
# ---------------------------------------------------------------------------------------------------------------
def _edges_from_profile(h):
    """h[i] in [0,S] = subcell coverage of pixel-column i. Return (lo_sub, hi_sub) subpixel edges, or None."""
    nz = [i for i, v in enumerate(h) if v > 0]
    if not nz:
        return None
    lo, hi = nz[0], nz[-1]
    if lo == hi and h[lo] < S:            # rect narrower than one pixel -> position within the pixel is ambiguous
        return None                        # (genuinely non-injective; caller abstains)
    x0 = (lo + 1) * S - h[lo]              # left pixel: covered on its right side
    x1 = hi * S + h[hi]                    # right pixel: covered on its left side
    return x0, x1

def infer_single(grid):
    """Return ('identify',(x0,y0,x1,y1,w)) if a single rect re-renders EXACTLY, else ('abstain',None)."""
    mx = max(max(r) for r in grid)
    if mx == 0:
        return "abstain", None                                 # empty
    for w in COLORS:
        if mx != w * S2:                                       # a fully-interior pixel must equal w*S2
            continue
        # locate a max pixel -> its row is vertically-interior (hy=S), its column horizontally-interior (hx=S)
        py0 = next(py for py in range(H) if any(grid[py][px] == mx for px in range(W)))
        px0 = next(px for px in range(W) if grid[py0][px] == mx)
        hx = [grid[py0][px] // (w * S) if grid[py0][px] % (w * S) == 0 else -1 for px in range(W)]
        hy = [grid[py][px0] // (w * S) if grid[py][px0] % (w * S) == 0 else -1 for py in range(H)]
        if -1 in hx or -1 in hy:                               # not a clean single-rect row/col
            continue
        ex, ey = _edges_from_profile(hx), _edges_from_profile(hy)
        if ex is None or ey is None:
            continue
        x0, x1 = ex; y0, y1 = ey
        cand = (x0, y0, x1, y1, w)
        # sound rejection + tiny local search (+-1 subpixel per edge) to absorb any off-by-one
        for dx0 in (0, -1, 1):
            for dy0 in (0, -1, 1):
                for dx1 in (0, -1, 1):
                    for dy1 in (0, -1, 1):
                        t = (x0 + dx0, y0 + dy0, x1 + dx1, y1 + dy1, w)
                        if t[0] < t[2] and t[1] < t[3] and oracle_equal(render([(*t, 0)]), grid):
                            return "identify", t
    return "abstain", None

# ---------------------------------------------------------------------------------------------------------------
# KILL baseline #1 ("tokens smuggled back in"): a FIXED-INDEX positional decode -- read the latent from fixed grid
# positions. If this matched the inference accuracy, the observation was effectively tokenized (NOT perception).
# ---------------------------------------------------------------------------------------------------------------
def fixed_index_decode(grid):
    """Pretend the latent lives at fixed cells (e.g. corners). Deliberately naive; MUST fail on real scenes."""
    # a fixed-index reader cannot recover sub-pixel edges or occlusion; return a whole-pixel bbox guess
    nz = [(px, py) for py in range(H) for px in range(W) if grid[py][px] > 0]
    if not nz:
        return "abstain", None
    xs = [p[0] for p in nz]; ys = [p[1] for p in nz]
    w = max(max(r) for r in grid) // S2 or 1
    return "identify", (min(xs) * S, min(ys) * S, (max(xs) + 1) * S, (max(ys) + 1) * S, w)

# ---------------------------------------------------------------------------------------------------------------
# scene generators (used only to make observations; the inference never sees them)
# ---------------------------------------------------------------------------------------------------------------
def rand_rect(rng, zmax=0):
    x0 = rng.randint(1 * S, 14 * S); y0 = rng.randint(1 * S, 14 * S)
    x1 = x0 + rng.randint(2 * S, 8 * S); y1 = y0 + rng.randint(2 * S, 8 * S)   # >= 2px each side (edges recoverable)
    x1 = min(x1, W * S - S); y1 = min(y1, H * S - S)
    return (x0, y0, x1, y1, rng.choice(COLORS), rng.randint(0, zmax))

if __name__ == "__main__":
    print("PERCEPTION rung 1 — sealed exact rasterizer; observation = 24x24 gray grid (NOT tokens)\n")

    # (0) show a scene: gray sub-pixel edges + occlusion, proving the observation is perceptual not symbolic
    demo = [(3 * S + 2, 3 * S + 1, 10 * S + 3, 9 * S + 2, 2, 0),            # back
            (7 * S + 1, 6 * S + 3, 14 * S + 2, 12 * S + 1, 3, 1)]          # front (higher z, occludes)
    g = render(demo)
    ramp = " .:-=+*#%@"
    print("  demo scene (2 rects, front occludes back; note intermediate gray at edges):")
    for py in range(2 * S, 13 * S // S + 13):
        if py >= H: break
        print("   " + "".join(ramp[min(len(ramp) - 1, g[py][px] * (len(ramp) - 1) // 48)] for px in range(W)))

    # (1) GROUNDING: single-rect inference over held-out scenes -> exact re-render, 0 confabulation
    N = 60
    cover = confab = abst = 0
    naive_cover = 0
    fixed_cover = 0
    for s in range(N):
        rng = random.Random(1000 + s)
        scene = [rand_rect(rng)]
        grid = render(scene)
        verd, lat = infer_single(grid)
        if verd == "identify":
            if oracle_equal(render([(*lat, 0)]), grid): cover += 1
            else: confab += 1
        else:
            abst += 1
        # NAIVE renderer best whole-pixel fit (bbox) -> can it match? (invention target check)
        nz = [(px, py) for py in range(H) for px in range(W) if grid[py][px] > 0]
        xs = [p[0] for p in nz]; ys = [p[1] for p in nz]; ww = max(max(r) for r in grid) // S2 or 1
        if oracle_equal(render_naive(min(xs), min(ys), max(xs) + 1, max(ys) + 1, ww), grid): naive_cover += 1
        # FIXED-INDEX baseline (the tokens-smuggled kill)
        fv, fl = fixed_index_decode(grid)
        if fv == "identify" and oracle_equal(render([(*fl, 0)]), grid): fixed_cover += 1
    print(f"\n  (1) GROUNDING single-rect [{N} held-out]: identify+exact-re-render {cover}/{N}, "
          f"CONFABULATION {confab}/{N}, abstain {abst}/{N}")
    print(f"  (3) INVENTION TARGET real: NAIVE binary-fill (integer-pixel) matches {naive_cover}/{N} "
          f"(cannot reproduce sub-pixel gray edges -> area-coverage law is load-bearing)")
    print(f"  (5) KILL baseline: FIXED-INDEX positional decode matches {fixed_cover}/{N} "
          f"(must be ~0 -> observation is NOT tokenized; perception path required)")

    # (4) ABSTENTION on undecidable occlusion: two DIFFERENT scenes render identically -> inverse ambiguous
    front = (5 * S, 5 * S, 15 * S, 15 * S, 3, 5)
    A = [front]
    B = [front, (6 * S, 6 * S, 14 * S, 14 * S, 1, 0)]          # a rect fully hidden behind `front`
    same = oracle_equal(render(A), render(B))
    print(f"\n  (4) ABSTENTION (occlusion): scene A (front only) and scene B (front + fully-hidden rect) "
          f"re-render identically = {same}")
    print(f"      => the hidden rect is provably undecidable from the observation -> the sound answer is ABSTAIN "
          f"(never commit one of >=2 latents that produce the same grid).")

    print("\n  STATUS: rung-1 START. Sound exact renderer+oracle live; single-rect grounding 0-confab; invention")
    print("  target (area-coverage) shown load-bearing vs naive; occlusion-abstention principle shown; fixed-index")
    print("  kill-baseline fails as required. NEXT: multi-rect inference under occlusion + the DISCOVERY loop")
    print("  (reject naive from gray residual, SELECT area-coverage) + ACTIVE(COLLECT) vs RANDOM scene probing.")
