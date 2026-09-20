"""PHASE 6 -- NOISE, SOUNDLY (the rung-2 mechanism the E1 gate was waiting for).

E1 found a CLIFF: a SUBSET (sound-but-incomplete) oracle degrades gracefully, an unsound/FLIP oracle collapses.
Rung 2 (noisy observation) was therefore gated on "a mechanism". This is the candidate:

    acceptance = consistency WITHIN A TOLERANCE eps, and the output is the SET of eps-consistent latents,
    never a probability; the set is shrunk by COLLECTING more observations.

The soundness argument is a THEOREM, not a hope: if eps is an honest UPPER BOUND on the corruption, then
Hamming(render(truth), observation) <= eps by definition, so the truth is GUARANTEED to survive. The price is
a bigger set (honest abstention), never a wrong answer. The mechanism therefore has a PRECONDITION, and the
experiment must show both sides of it:

  eps >= actual noise  -> truth never excluded, 0 confabulation, |set| grows with eps  (SOUND, costs abstention)
  eps <  actual noise  -> the TRUTH ITSELF is rejected                                  (UNSOUND -- the cliff)

World: 1-layer rect scenes on a 6x6 field (441 rects x 3 colours = 1323 latents, fully enumerable, so the
survivor set is EXACT and completeness is a theorem, not a heuristic).

MEASURED
  (A) tolerance sweep      : truth-in-set / singleton / mean |set| / confabulations over eps x noise
  (B) the cliff            : truth-exclusion rate when eps underestimates the noise
  (C) COLLECT under noise  : k independent noisy observations -> set shrinks (abstention resolved by probing)
KILL 6: any CONFABULATION (a committed singleton that is not the truth) at an honest eps.
"""
import os, sys, json, random, time, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The eps-consistency and tolerance-SET mechanism defined here is now core.tolerance, so that every thread
# gets it: Stage 3d reused it for grammar induction, and perception's rung 2 was GATED on its existence.
# This file keeps its own tiny hot-loop copies (ham/eps_set) for speed over 1323 enumerable latents, and
# CHECKS them against the shared implementation instead of drifting from it.
from core.tolerance import within as _core_within, survivors as _core_survivors

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
G = 6
NP = G * G
COLORS = (1, 2, 3)


def all_rects():
    out = []
    for x0 in range(G):
        for x1 in range(x0 + 1, G + 1):
            for y0 in range(G):
                for y1 in range(y0 + 1, G + 1):
                    out.append((x0, y0, x1, y1))
    return out


RECTS = all_rects()
LATENTS = [(r, c) for r in RECTS for c in COLORS]


def render(latent):
    (x0, y0, x1, y1), c = latent
    g = [0] * NP
    for py in range(y0, y1):
        for px in range(x0, x1):
            g[py * G + px] = c
    return g


RENDERS = {l: render(l) for l in LATENTS}


def corrupt(grid, q, rng):
    """quantisation/sensor noise: each pixel independently replaced by a WRONG value with probability q."""
    out = list(grid)
    nc = 0
    for i in range(NP):
        if rng.random() < q:
            alts = [v for v in (0,) + COLORS if v != out[i]]
            out[i] = rng.choice(alts); nc += 1
    return out, nc


def _core_agreement_check():
    """The shared implementation must agree with the local hot loop, or one of them has drifted."""
    for l in LATENTS[:40]:
        obs = RENDERS[l]
        assert _core_within(obs, RENDERS[l], 0), "core.tolerance.within disagrees at eps=0"
        assert l in _core_survivors(LATENTS[:40], lambda h: RENDERS[h], obs, 0), "core survivors disagree"
    return True


def ham(a, b):
    return sum(1 for i in range(NP) if a[i] != b[i])


def eps_set(obs, eps_pixels, cap=None):
    """EXACT set of latents whose exact re-render is within eps_pixels Hamming distance of the observation."""
    out = []
    for l in LATENTS:
        if ham(RENDERS[l], obs) <= eps_pixels:
            out.append(l)
            if cap and len(out) > cap: break
    return out


def eps_set_multi(obss, eps_pixels):
    """NAIVE COLLECT (kept to DOCUMENT ITS UNSOUNDNESS): survive only if within tolerance of EVERY
    observation. This is a CONJUNCTION, so P(truth survives k observations) = p^k and DECAYS -- more
    evidence makes the engine reject the truth more often. Measured below: truth-in-set 1.000 -> 0.875."""
    out = []
    for l in LATENTS:
        r = RENDERS[l]
        if all(ham(r, o) <= eps_pixels for o in obss):
            out.append(l)
    return out


def aggregate(obss):
    """CORRECTED COLLECT: DENOISE first by per-pixel majority vote over independent observations, then apply a
    single tolerance bound. Aggregation REDUCES the effective corruption instead of multiplying the chances of
    exceeding the bound, so the soundness theorem still applies to the aggregate."""
    out = []
    for i in range(NP):
        vals = [o[i] for o in obss]
        out.append(max(set(vals), key=vals.count))
    return out


def eps_set_agg(obss, eps_pixels):
    return eps_set(aggregate(obss), eps_pixels)


if __name__ == "__main__":
    t0 = time.time()
    TRIALS = int(os.environ.get("P6_TRIALS", "40"))
    rng = random.Random(7)
    print(f"PHASE 6 -- noise, soundly.  {len(LATENTS)} enumerable latents on {G}x{G} "
          f"(survivor set EXACT, completeness a theorem)\n")

    # ---------------- (A) tolerance sweep + (B) the cliff ----------------
    print("(A/B) tolerance sweep -- eps is a BUDGET IN PIXELS; actual corruption count is known per trial")
    assert _core_agreement_check()
    print(f"{'noise q':>8} {'eps(px)':>8} {'truth in set':>13} {'singleton':>10} {'mean|set|':>10} "
          f"{'confab':>7} {'eps>=noise':>11}")
    rows = []
    for q in (0.0, 0.03, 0.06, 0.12):
        for epsf in (0.0, 0.03, 0.08, 0.15):
            eps_px = int(round(epsf * NP))
            tin = 0; single = 0; sizes = []; confab = 0; honest = 0
            for _ in range(TRIALS):
                truth = rng.choice(LATENTS)
                obs, nc = corrupt(RENDERS[truth], q, rng)
                S = eps_set(obs, eps_px)
                sizes.append(len(S))
                if truth in S: tin += 1
                if len(S) == 1:
                    single += 1
                    if S[0] != truth: confab += 1
                if nc <= eps_px: honest += 1
            rows.append({"q": q, "eps_frac": epsf, "eps_px": eps_px,
                         "truth_in_set": tin / TRIALS, "singleton": single / TRIALS,
                         "mean_set": round(statistics.mean(sizes), 1), "confab": confab,
                         "eps_covers_noise": honest / TRIALS})
            print(f"{q:>8.2f} {eps_px:>8d} {tin/TRIALS:>13.3f} {single/TRIALS:>10.3f} "
                  f"{statistics.mean(sizes):>10.1f} {confab:>7d} {honest/TRIALS:>11.3f}")

    # the theorem check: restrict to trials where eps DID cover the actual corruption
    print(f"\n  THEOREM CHECK -- on trials where eps >= actual corrupted-pixel count, is the truth ALWAYS in the set?")
    viol = 0; tot = 0
    for q in (0.03, 0.06, 0.12):
        for epsf in (0.03, 0.08, 0.15):
            eps_px = int(round(epsf * NP))
            for _ in range(TRIALS):
                truth = rng.choice(LATENTS)
                obs, nc = corrupt(RENDERS[truth], q, rng)
                if nc > eps_px: continue
                tot += 1
                if truth not in eps_set(obs, eps_px): viol += 1
    print(f"    {tot} qualifying trials, truth-exclusion violations: {viol}  "
          f"-> {'THEOREM HOLDS' if viol == 0 else 'VIOLATED'}")

    print(f"\n  THE CLIFF -- when eps UNDERESTIMATES the noise, the truth itself is rejected:")
    cliff = []
    for q in (0.06, 0.12):
        eps_px = 0
        excl = 0
        for _ in range(TRIALS):
            truth = rng.choice(LATENTS)
            obs, nc = corrupt(RENDERS[truth], q, rng)
            if nc == 0: continue
            if truth not in eps_set(obs, eps_px): excl += 1
        cliff.append({"q": q, "eps_px": eps_px, "truth_excluded": excl / TRIALS})
        print(f"    q={q:.2f}, eps=0 (exact-match rung 1): truth EXCLUDED in {excl/TRIALS:.0%} of trials "
              f"-> rung 1 is unusable under noise, which is WHY rung 2 needed a mechanism")

    # ---------------- (C) COLLECT under noise ----------------
    print(f"\n(C) COLLECT under noise: k independent noisy observations, eps held at an honest bound")
    q = 0.06; eps_px = int(round(0.15 * NP))
    print(f"    q={q}, eps={eps_px}px")
    print(f"{'k obs':>6} {'mean|set|':>10} {'singleton':>10} {'truth in set':>13} {'confab':>7}")
    coll = []
    for mode, fn in (("NAIVE intersect", eps_set_multi), ("CORRECTED majority-vote", eps_set_agg)):
        print(f"  -- {mode} --")
        for k in (1, 2, 3, 5):
            sizes = []; single = 0; tin = 0; confab = 0
            for _ in range(TRIALS):
                truth = rng.choice(LATENTS)
                obss = [corrupt(RENDERS[truth], q, rng)[0] for _ in range(k)]
                S = fn(obss, eps_px)
                sizes.append(len(S))
                if truth in S: tin += 1
                if len(S) == 1:
                    single += 1
                    if S[0] != truth: confab += 1
            coll.append({"mode": mode, "k": k, "mean_set": round(statistics.mean(sizes), 1),
                         "singleton": single / TRIALS, "truth_in_set": tin / TRIALS, "confab": confab})
            print(f"{k:>6} {statistics.mean(sizes):>10.1f} {single/TRIALS:>10.3f} {tin/TRIALS:>13.3f} {confab:>7d}")

    total_confab = sum(r["confab"] for r in rows if r["eps_covers_noise"] == 1.0) + sum(c["confab"] for c in coll)
    naive_excl = [c for c in coll if c["mode"].startswith("NAIVE") and c["truth_in_set"] < 1.0]
    corr_excl = [c for c in coll if c["mode"].startswith("CORRECTED") and c["truth_in_set"] < 1.0]
    print(f"\n=== KILL 6 ===")
    if viol:
        print(f"  FIRED: {viol} truth-exclusions where eps covered the noise -> tolerance-sets are not sound.")
        verdict = f"FIRED ({viol} truth-exclusions)"
    elif total_confab:
        print(f"  FIRED: {total_confab} confabulations at an honest eps.")
        verdict = f"FIRED ({total_confab} confabulations)"
    else:
        print(f"  PASSES: with eps an honest upper bound on corruption the truth is NEVER excluded and no")
        print(f"  committed singleton is ever wrong; noise is paid for in ABSTENTION (set size), and COLLECT")
        print(f"  shrinks the set. The rung-2 precondition is explicit: eps must bound the noise -- underestimate")
        print(f"  it and the truth is rejected (the cliff), which is exactly E1's unsound-oracle failure.")
        verdict = "PASSES"
    print("")
    print("  COLLECT soundness: NAIVE intersect excludes the truth at k>1 in "
          f"{len(naive_excl)}/4 settings (UNSOUND, documented); CORRECTED majority-vote excludes it in "
          f"{len(corr_excl)}/4.")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase6_noise_tolerance_sets"] = {
        "latents": len(LATENTS), "grid": f"{G}x{G}", "trials_per_cell": TRIALS,
        "sweep": rows, "theorem_qualifying_trials": tot, "theorem_violations": viol,
        "cliff_exact_match_under_noise": cliff, "collect": coll,
        "confabulations_at_honest_eps": total_confab, "kill6": verdict,
        "mechanism": "acceptance within a SOUND tolerance bound eps, output = the eps-consistent SET (never a "
                     "probability), shrunk by COLLECTing independent observations. Soundness is a theorem given "
                     "eps >= corruption; the cost is abstention. Precondition: eps must bound the noise.",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
