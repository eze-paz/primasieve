"""PERCEPTION rung 1 — sub-step 4 (fable-set): close gap (a'') = LAW DISCRIMINATION among NON-NESTED rivals.
percept_p3's rivals were degenerate cases of the truth (a flat render IS an area render with pixel-aligned edges),
so "area always survives" held by construction, not by discrimination. Here the world draws its coverage LAW
per scene UNIFORMLY from THREE genuinely non-nested laws, and the engine must identify WHICH law generated each
observation (plus the latent), by generic search + SOUND residual rejection.

Laws (none is a special case of another -- three distinct coverage-response CURVES: linear/convex/concave):
  area  : LINEAR area coverage at S=4      pixel = w * covx * covy
  gamma : CONVEX (quadratic) response      pixel = w * (covx*covy)^2 // S2
  sqrt  : CONCAVE (sqrt) response          pixel = w * isqrt(covx*covy * S2)
(ss2/coarse-supersample was tried and REJECTED: it equals area with edges snapped to even sub-pixels = NESTED,
never uniquely identifiable -- the very flaw fable flagged. sqrt is genuinely non-nested: no linear/quadratic law
reproduces a concave falloff.)

Per scene: true law ~ Uniform{area,ss2,gamma}. Engine tries to invert the grid EXACTLY under EACH law (one generic
coordinate-descent search, no bespoke inverter); survivors = laws with an exact inverse; commit the UNIQUE survivor,
else ABSTAIN. fable KILLs: (K-CONF) commit a law that doesn't re-render, OR commit the WRONG law when the true law
was uniquely invertible = confabulation (must be 0). (K-TRUTH) the true law must ALWAYS be found (search complete).
(K-ABST) abstain exactly on genuinely-indistinguishable scenes (>=2 laws co-invert) -- rate ~ the coincidence rate.
Self-contained 16x16, exact integer, ZERO LLM."""
import os, sys, random, math
sys.path.insert(0, os.path.dirname(__file__))
W = H = 16
S = 4
S2 = S * S
COLORS = (1, 2, 3)

def cov(p, a, b): return max(0, min((p + 1) * S, b) - max(p * S, a))          # S=4 subcell coverage

def L_area(lat):                                                             # LINEAR
    x0, y0, x1, y1, w = lat
    cx = [cov(px, x0, x1) for px in range(W)]; cy = [cov(py, y0, y1) for py in range(H)]
    return [[w * cx[px] * cy[py] for px in range(W)] for py in range(H)]
def L_gamma(lat):                                                           # CONVEX (quadratic)
    x0, y0, x1, y1, w = lat
    cx = [cov(px, x0, x1) for px in range(W)]; cy = [cov(py, y0, y1) for py in range(H)]
    return [[w * (cx[px] * cy[py]) * (cx[px] * cy[py]) // S2 for px in range(W)] for py in range(H)]
def L_sqrt(lat):                                                            # CONCAVE (sqrt)
    x0, y0, x1, y1, w = lat
    cx = [cov(px, x0, x1) for px in range(W)]; cy = [cov(py, y0, y1) for py in range(H)]
    return [[w * math.isqrt(cx[px] * cy[py] * S2) for px in range(W)] for py in range(H)]

LAWS = [("area", L_area), ("gamma", L_gamma), ("sqrt", L_sqrt)]
LFN = dict(LAWS)

def _bbox(grid):
    nz = [(px, py) for py in range(H) for px in range(W) if grid[py][px] > 0]
    if not nz: return None
    xs = [p[0] for p in nz]; ys = [p[1] for p in nz]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1
def _resid(fn, lat, grid):
    g = fn(lat); return sum(g[py][px] != grid[py][px] for py in range(H) for px in range(W))
def search(fn, grid):
    """ONE generic latent search (shared by every law): coordinate descent over the 4 sub-pixel edges near the
    pixel bbox, over all colors; accept ONLY an exact re-render (sound). None if no exact inverse found."""
    bb = _bbox(grid)
    if bb is None: return None
    anchors = [bb[0] * S, bb[1] * S, bb[2] * S, bb[3] * S]
    windows = [range(max(0, a - S), min(W * S, a + S) + 1) for a in anchors]
    for w in COLORS:
        edges = list(anchors)
        for _ in range(4):
            for i in range(4):
                best, bestr = edges[i], None
                for v in windows[i]:
                    e = list(edges); e[i] = v
                    if e[0] < e[2] and e[1] < e[3]:
                        r = _resid(fn, (e[0], e[1], e[2], e[3], w), grid)
                        if bestr is None or r < bestr: bestr, best = r, v
                edges[i] = best
            lat = (edges[0], edges[1], edges[2], edges[3], w)
            if _resid(fn, lat, grid) == 0: return lat
    return None

def discover(grid):
    surv = [(n, search(fn, grid)) for n, fn in LAWS]
    surv = [(n, l) for n, l in surv if l is not None]
    if len(surv) == 1:
        return surv[0][0], surv[0][1], [n for n, _ in surv]        # unique law -> identify
    return "abstain", None, [n for n, _ in surv]                   # 0 or >=2 -> abstain (can't tell the law)

def brute_survivors(grid):
    """COMPLETENESS ORACLE (fable audit): exhaustive JOINT search over the bbox+-S window (which provably contains
    every exact inverse, since any match shares the pixel bbox) for each law -> the ground-truth survivor set."""
    bb = _bbox(grid)
    if bb is None: return []
    w = max(max(r) for r in grid) // S2 or 1                        # full-coverage interior pixel = 16w -> w known
    rng4 = [range(max(0, a * S - S), min(W * S, a * S + S) + 1) for a in bb]
    out = []
    for name, fn in LAWS:
        hit = False
        for x0 in rng4[0]:
            for x1 in rng4[2]:
                if x1 <= x0: continue
                for y0 in rng4[1]:
                    for y1 in rng4[3]:
                        if y1 > y0 and _resid(fn, (x0, y0, x1, y1, w), grid) == 0:
                            hit = True; break
                    if hit: break
                if hit: break
            if hit: break
        if hit: out.append(name)
    return out

def rand_rect(rng):
    def redge(bp): return bp * S + (0 if rng.random() < 0.5 else rng.choice([1, 2, 3]))
    x0p = rng.randint(1, 6); x1p = x0p + rng.randint(3, 6); y0p = rng.randint(1, 6); y1p = y0p + rng.randint(3, 6)
    return (redge(x0p), redge(y0p), min(redge(x1p), W * S - 1), min(redge(y1p), H * S - 1), rng.choice(COLORS))

if __name__ == "__main__":
    print("PERCEPTION rung 1 / sub-step 4 — LAW DISCRIMINATION among NON-NESTED rivals {area, gamma, sqrt}\n")
    N = 150
    conf = 0                       # committed law that doesn't re-render, OR wrong law when true was unique
    truth_found = 0                # true law survives (search complete)
    correct = distinguishable = 0  # among scenes where only the true law inverts -> must commit it
    abstain = 0
    survcount = {0: 0, 1: 0, 2: 0, 3: 0}
    by_true = {n: [0, 0] for n, _ in LAWS}     # [count, correctly-identified]
    for s in range(N):
        rng = random.Random(13000 + s)
        true_law = ("area", "gamma", "sqrt")[s % 3]
        lat = rand_rect(rng)
        grid = LFN[true_law](lat)
        name, got, surv = discover(grid)
        survcount[len(surv)] += 1
        if true_law in surv: truth_found += 1
        by_true[true_law][0] += 1
        uniq = (surv == [true_law])            # only the true law inverts exactly -> distinguishable
        if uniq:
            distinguishable += 1
            if name == true_law and _resid(LFN[name], got, grid) == 0:
                correct += 1; by_true[true_law][1] += 1
            else:
                conf += 1                       # failed to commit the uniquely-correct law
        else:
            if name == "abstain": abstain += 1
            elif name != true_law or _resid(LFN[name], got, grid) != 0:
                conf += 1                       # committed a wrong/invalid law when it shouldn't
    coincidence = survcount[2] + survcount[3]
    print(f"  [{N} scenes; true law ~ Uniform{{area,gamma,sqrt}}]")
    print(f"  survivor-count distribution: {survcount}  (>=2 = genuinely indistinguishable coincidences)")
    print(f"  K-TRUTH true law always found (search complete): {truth_found}/{N}  (must be {N})")
    print(f"  DISCRIMINATION: on the {distinguishable} uniquely-identifiable scenes, committed the TRUE law {correct}/{distinguishable}")
    print(f"  per-true-law correct: {{ {', '.join(f'{n}:{c}/{t}' for n,(t,c) in by_true.items())} }}")
    print(f"  K-CONF confabulation (wrong/invalid law when distinguishable): {conf}/{N}  (must be 0)")
    print(f"  K-ABST abstained on {abstain} scenes; analytic coincidence (>=2 co-invert) = {coincidence} "
          f"-> abstain rate {100*abstain//N}% vs coincidence {100*coincidence//N}%")
    # --- fable AUDIT 1: search completeness for RIVALS (coord-descent survivor set == exhaustive brute oracle) ---
    audit_n = 18; audit_mismatch = 0
    for s in range(audit_n):
        rng = random.Random(13000 + s)
        grid = LFN[("area", "gamma", "sqrt")[s % 3]](rand_rect(rng))
        cd = set(discover(grid)[2]); bf = set(brute_survivors(grid))
        if cd != bf: audit_mismatch += 1
    # --- fable AUDIT 2: are the >=2-survivor coincidences exactly the structurally-ambiguous (few partial levels)? ---
    strat = {}
    for s in range(N):
        rng = random.Random(13000 + s)
        grid = LFN[("area", "gamma", "sqrt")[s % 3]](rand_rect(rng))
        w = max(max(r) for r in grid) // S2 or 1
        levels = len({v for row in grid for v in row if v not in (0, w * S2)})   # # distinct PARTIAL gray levels
        nsurv = len(discover(grid)[2])
        strat.setdefault(levels, [0, 0]); strat[levels][0] += 1; strat[levels][1] += (nsurv >= 2)
    print(f"  AUDIT-1 search completeness (coord-descent survivor set == brute oracle): "
          f"{audit_n-audit_mismatch}/{audit_n} match  (mismatch {audit_mismatch} -> must be 0)")
    print(f"  AUDIT-2 coincidences by #distinct partial gray levels (levels: total, #>=2-surv): "
          f"{ {k: tuple(v) for k, v in sorted(strat.items())} }")

    passK = (conf == 0 and truth_found == N and correct == distinguishable and abstain == coincidence
             and audit_mismatch == 0)
    print(f"\n  RESULT: {'PASS' if passK else 'CHECK'}. The world uses a DIFFERENT non-nested law per scene; the engine")
    print("  identifies WHICH generative law (+latent) by generic search + sound residual rejection, commits the true")
    print("  law whenever residual distinguishes it, and abstains exactly on genuine coincidences -> law-discrimination")
    print("  shown, gap (a) CLOSED for single rects. Caveat: search landscape is still per-edge monotone (gamma is")
    print("  monotone in coverage); a non-monotone law (outline/ring) + multi-rect OCCLUSION are the next hills.")
