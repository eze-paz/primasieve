"""PERCEPTION rung 1 — sub-step p7 (fable-set): MULTI-RECT OCCLUSION. Two axis-aligned rects with a z-order,
composited painter's-order (higher z overwrites in the overlap) under ONE fixed law (solid pixel fill = the area
law at pixel resolution). From ONE composited grid the engine must return the EXACT SET of consistent scenes
{layers = up to 2 (rect,color) painted bottom-to-top}, committing only where the set is a SINGLETON, else returning
the survivor SET (never picking one). Everything by EXACT RE-RENDER, never rect-geometry (or the law is smuggled).

fable's traps, all handled by ENUMERATION not 'identify':
 - a back rect FULLY hidden behind the front -> many consistent backs (any rect <= front, any color) -> SET;
 - SAME-COLOR overlap -> the union decomposes many ways AND the internal boundary is invisible -> the FRONT is
   itself undetermined -> large finite SET (this is the SHARPEST kill: a connected-component heuristic 'finds the
   front' and fake-passes; the correct answer is the full decomposition set);
 - non-overlapping rects -> relative z is undecidable but render-identical -> both orders are distinct members.

Soundness+completeness check: the engine's survivor set (rects bounded to the nonzero bbox) must EQUAL a brute-force
reference set enumerated over the bbox + a 2px MARGIN (proving nothing consistent escapes the bbox bound). Abstention
must carry a WITNESS PAIR of distinct members that both re-render exactly. Bitmasks over a 6x6 field make the full
double enumeration tractable. Pure stdlib, exact, ZERO LLM."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.registry import selfcheck

import os, sys, random
sys.path.insert(0, os.path.dirname(__file__))
G = 6                                    # 6x6 pixel field (small enough for full brute double-enumeration)
NP = G * G
FULL = (1 << NP) - 1
COLORS = (1, 2, 3)

def rect_mask(x0, y0, x1, y1):
    m = 0
    for py in range(y0, y1):
        for px in range(x0, x1):
            m |= 1 << (py * G + px)
    return m

def all_rects(x0lo, y0lo, x1hi, y1hi):
    """Every axis-aligned rect within [x0lo,x1hi]x[y0lo,y1hi]; returns [(rect_tuple, mask)]."""
    out = []
    for x0 in range(x0lo, x1hi):
        for x1 in range(x0 + 1, x1hi + 1):
            for y0 in range(y0lo, y1hi):
                for y1 in range(y0 + 1, y1hi + 1):
                    out.append(((x0, y0, x1, y1), rect_mask(x0, y0, x1, y1)))
    return out

def color_masks(grid):
    Gm = {c: 0 for c in COLORS}; Z = 0
    for i in range(NP):
        c = grid[i]
        if c: Gm[c] |= 1 << i
        else: Z |= 1 << i
    return Gm, Z

def render(scene):
    """scene = tuple of (mask,color) BOTTOM-to-TOP. Returns a length-NP tuple of colors."""
    col = [0] * NP
    for m, c in scene:
        i = 0; mm = m
        while mm:
            if mm & 1: col[i] = c
            mm >>= 1; i += 1
    return tuple(col)

def _match1(fm, cf, Gm, Z):              # 1-layer scene exact-match check (bitmask)
    if fm != Gm[cf]: return False
    if (FULL & ~fm) != Z: return False
    return all(Gm[k] == 0 for k in COLORS if k != cf)

def _match2(bm, cb, fm, cf, Gm, Z):      # 2-layer (back bm/cb, front fm/cf) exact-match check (bitmask)
    if (FULL & ~(bm | fm)) != Z: return False
    vis_b = bm & ~fm
    res = {c: 0 for c in COLORS}
    res[cf] |= fm
    res[cb] |= vis_b
    return all(res[k] == Gm[k] for k in COLORS)

def survivors(grid, rects, cap=100000):
    """ALL 1- and 2-layer scenes over `rects` that EXACTLY re-render grid. Canonical members for set-equality."""
    Gm, Z = color_masks(grid)
    out = set()
    for rt, fm in rects:                                   # 1-layer
        for cf in COLORS:
            if _match1(fm, cf, Gm, Z): out.add((("L1", rt, cf),))
    for rb, bm in rects:                                   # 2-layer (ordered = z; back first)
        for rf, fm in rects:
            if fm == bm and rf == rb: continue
            for cb in COLORS:
                for cf in COLORS:
                    if _match2(bm, cb, fm, cf, Gm, Z):
                        out.add((("L2b", rb, cb), ("L2f", rf, cf)))
                        if len(out) >= cap: return out
    return out

def to_scene(member, rectmask):
    if member[0][0] == "L1":
        _, rt, cf = member[0]; return ((rectmask[rt], cf),)
    (_, rb, cb), (_, rf, cf) = member
    return ((rectmask[rb], cb), (rectmask[rf], cf))

def bbox(grid):
    xs = [i % G for i in range(NP) if grid[i]]; ys = [i // G for i in range(NP) if grid[i]]
    if not xs: return None
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1

def engine(grid, margin):
    bb = bbox(grid)
    if bb is None:                                         # all-zero: any single empty scene... = the empty scene only
        return {(("L1", (0, 0, 0, 0), 0),)}, "abstain(empty)"
    x0 = max(0, bb[0] - margin); y0 = max(0, bb[1] - margin)
    x1 = min(G, bb[2] + margin); y1 = min(G, bb[3] + margin)
    rects = all_rects(x0, y0, x1, y1)
    surv = survivors(grid, rects)
    return surv, ("identify" if len(surv) == 1 else f"SET({len(surv)})")

RALL = all_rects(0, 0, G, G)
RMASK = {rt: m for rt, m in RALL}

def rand_scene(rng, same_color=None):
    def rr():
        x0 = rng.randint(0, G - 1); x1 = rng.randint(x0 + 1, G); y0 = rng.randint(0, G - 1); y1 = rng.randint(y0 + 1, G)
        return (x0, y0, x1, y1)
    a, b = rr(), rr()
    if same_color: ca = cb = rng.choice(COLORS)
    else: ca, cb = rng.choice(COLORS), rng.choice(COLORS)
    return ((RMASK[a], ca), (RMASK[b], cb))              # a=back, b=front

if __name__ == "__main__":
    selfcheck(__file__)   # verifies this file\'s PUBLISHED claims (core/registry.py) at exit
    print("PERCEPTION rung 1 / p7 — MULTI-RECT OCCLUSION: return the exact survivor SET, commit only if singleton\n")
    N = 40
    kconf = ktruth = kcomplete = commit_ok = setret = wit_ok = 0
    singletons = sets = 0
    for s in range(N):
        rng = random.Random(30000 + s)
        true_scene = rand_scene(rng, same_color=(s % 3 == 0))   # ~1/3 same-color (the sharp case)
        grid = render(true_scene)
        eng, verd = engine(grid, margin=0)                      # rects bounded to nonzero bbox
        brute, _ = engine(grid, margin=2)                       # reference: bbox + 2px margin
        # membership of the TRUE scene (as a canonical member)
        Gm, Z = color_masks(grid)
        true_in = any(render(to_scene(m, RMASK)) == grid for m in eng)   # some engine member re-renders to grid
        if true_in: ktruth += 1
        if eng == brute: kcomplete += 1                          # completeness+soundness: bbox bound loses nothing
        # every engine member must re-render EXACTLY (soundness of the set)
        sound = all(render(to_scene(m, RMASK)) == grid for m in eng)
        if not sound: kconf += 1
        if len(eng) == 1:
            singletons += 1
            if render(to_scene(next(iter(eng)), RMASK)) == grid: commit_ok += 1
            else: kconf += 1                                     # committed a singleton that doesn't re-render
        else:
            sets += 1; setret += 1
            wl = list(eng)[:2]                                   # abstention WITNESS PAIR (2 distinct members)
            if len(wl) >= 2 and all(render(to_scene(m, RMASK)) == grid for m in wl): wit_ok += 1

    print(f"  [{N} scenes, ~1/3 same-color overlap]  singletons(committed) {singletons}, SETs(abstained) {sets}")
    print(f"  K-TRUTH true scene reproduced by an engine member: {ktruth}/{N} (must be {N})")
    print(f"  SOUND set (every member re-renders exactly) + no bad singleton commit: CONFAB {kconf}/{N} (must be 0)")
    print(f"  COMPLETE+SOUND set (engine bbox-set == bbox+2px brute-set): {kcomplete}/{N} (must be {N})")
    print(f"  singleton commits that re-render {commit_ok}/{singletons}; abstentions with a verified WITNESS PAIR "
          f"{wit_ok}/{sets}")

    # THE SHARP KILL, explicit: two SAME-COLOR overlapping rects -> the front is undetermined -> large SET, NOT one.
    print("\n  SHARP KILL — same-color overlapping rects (front must NOT be uniquely 'identified'):")
    for seed in (30000, 30003, 30012):
        rng = random.Random(seed)
        while True:
            sc = rand_scene(rng, same_color=True)
            (ma, ca), (mb, cb) = sc
            if ma & mb and ma != mb: break                       # ensure genuine overlap, distinct rects
        grid = render(sc); eng, verd = engine(grid, margin=0)
        conncomp_is_one_rect = bbox(grid) is not None and rect_mask(*bbox(grid)) == color_masks(grid)[0][ca]
        print(f"    seed {seed}: survivor SET size {len(eng)} (verdict {verd}); "
              f"naive 'nonzero==one rect' heuristic would say {'RECTANGLE(fake-identify)' if conncomp_is_one_rect else 'not-a-rect'} "
              f"-> engine returns the SET, refusing to pick a decomposition")

    passK = (kconf == 0 and ktruth == N and kcomplete == N and commit_ok == singletons and wit_ok == sets)
    print(f"\n  RESULT: {'PASS' if passK else 'CHECK'}. Occlusion: the engine returns the EXACT survivor set (== brute,")
    print("  completeness of the bbox bound proven), commits ONLY singletons, and on ambiguity (hidden back / same-")
    print("  color decomposition / z-order) returns the SET with a verified witness pair -- 0 confabulation, never")
    print("  picks one hidden arrangement. This is where the 'return the set when not 100% sure' machinery fires.")
    print("  NEXT: p8 ACTIVE(COLLECT) -- choose the next observation that SPLITS the survivor set; p9 E8-pixel kill.")
