"""PHASE 2(e) -- ACTIVE PROBING closes the integ underdetermination (the gap Phase 2 reported honestly).

Phase 2 found: the crystallised integ frame is  c' = abs(neg(c)/(e+1)).  That is EXACTLY equivalent to the true
c/(e+1) on the evidence regime (all seeds have c>0) but WRONG for c<0 (it gives +5/2 where truth is -5/2).
Root cause: the generic bootstrap tool FitTemplate cannot solve negative-coefficient seeds, so the
DISCRIMINATING TRACE DOES NOT EXIST. I labelled that an ACTIVE-PROBING gap rather than a grammar gap. This
closes it, and thereby demonstrates COLLECT at the FRAME layer (previously shown only for perception/machines).

MECHANISM (all four verbs in one loop):
  1. SLEEP returns the SURVIVOR SET of L0 frames consistent with the traces -- not the first match.
  2. If more than one survives, they AGREE on everything observed but must DISAGREE somewhere. COLLECT picks
     the input (c,e) that maximally SPLITS the survivor set (E6/p8's belief-splitting criterion).
  3. The probe is answered by the EXECUTION ORACLE, not by FitTemplate: build the single-term task at that
     (c,e), and test each survivor's predicted polynomial against the task's own tests. No new machinery, and
     FitTemplate's inability to solve negative coefficients is irrelevant -- we only need to TEST, not to SEARCH.
  4. Survivors that fail are REJECTED. Commit only on a unique survivor, else keep probing / abstain.

CONTROL: ACTIVE probe choice vs RANDOM probe choice at equal budget (E6 measured 7-12x for active).
"""
import os, sys, json, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fractions import Fraction as F
import sleep_l0 as SL
import meta_param as MP

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
SEEDS = [[(3, 2)], [(2, 3)], [(5, 4)], [(4, 2)], [(2, 5)], [(7, 3)], [(6, 5)], [(9, 2)], [(8, 3)], [(3, 4)]]
PROBE_POOL = [(c, e) for c in (-9, -7, -5, -4, -3, -2, 2, 3, 5, 7) for e in (1, 2, 3, 4, 5, 6)]


def survivors(traces, which, depth=3, cap=200000, limit=40, individuate=True):
    """SLEEP but returning the SET of consistent L0 frames (same anti-coincidence guards).

    CRITICAL: enum_trees dedupes by SIGNATURE. If the signature is computed over the OBSERVED traces only,
    every frame that agrees on the evidence collapses into ONE representative -- so the survivor set is a
    singleton BY CONSTRUCTION and the alternatives active probing needs are silently destroyed. The
    hypothesis space must be INDIVIDUATED at the resolution you intend to probe, so the dedup key here spans
    traces + the probe pool, while CONSISTENCY is still checked only on the traces."""
    inputs = [o for o, _ in traces]
    dedup_inputs = inputs + (list(PROBE_POOL) if individuate else [])
    varies = {a: len({(oc if a == "c" else oe) for (oc, oe), _ in traces}) >= 2 for a in ("c", "e")}
    out = []
    for t, _s in SL.enum_trees(dedup_inputs, depth=depth, cap=cap):
        ok = True
        for (oc, oe), new in traces:
            v = SL.ev(t, oc, oe)
            if v is None or abs(v - F(new[which]).limit_denominator(10 ** 9)) > F(1, 10 ** 6):
                ok = False; break
        if not ok: continue
        if any(not varies[a] for a in SL.refs_of(t)): continue
        out.append(t)
        if len(out) >= limit: break
    return out


def split_score(cands, ce):
    """how many DISTINCT values the surviving frames predict at this input -- the belief-splitting criterion."""
    vals = set()
    for t in cands:
        v = SL.ev(t, ce[0], ce[1])
        vals.add(None if v is None else v)
    return len(vals)


def ask_oracle(ce, transform):
    """EXECUTION ORACLE: the true single-term task at (c,e). Returns (tests, true_new_terms_for_scoring)."""
    task = MP.make_task([ce], transform)
    return task["tests"]


def passes(t_c, t_e, ce, tests):
    """does this candidate (c'-frame, e'-frame) predict a polynomial that passes the task's own tests?"""
    c, e = ce
    vc = SL.ev(t_c, c, e); ve = SL.ev(t_e, c, e)
    if vc is None or ve is None: return False
    try:
        terms = [(float(vc), int(round(float(ve))))]
        src = MP.poly_src(terms)
        ns = {}
        exec(src, ns)
        f = ns["f"]
        for inp, exp in tests:
            got = f(*inp)
            if abs(got - exp) > 1e-6: return False
        return True
    except Exception:
        return False


def run(mode, S0, transform, e_frame, budget=6, rng=None):
    """iteratively probe until the c-frame survivor set is a singleton (or budget exhausted).
    S0 is the survivor set computed ONCE (enumerating the L0 pool per call was the bottleneck)."""
    cands = list(S0)
    used = []
    while len(cands) > 1 and len(used) < budget:
        pool = [p for p in PROBE_POOL if p not in used]
        if not pool: break
        if mode == "active":
            probe = max(pool, key=lambda p: split_score(cands, p))
            if split_score(cands, probe) < 2: break        # no probe can split -> genuinely unknowable
        else:
            probe = rng.choice(pool)
        used.append(probe)
        tests = ask_oracle(probe, transform)
        cands = [t for t in cands if passes(t, e_frame, probe, tests)]
    return cands, used


if __name__ == "__main__":
    t0 = time.time()
    print("PHASE 2(e) -- ACTIVE PROBING closes the integ underdetermination\n")
    traces = MP.bootstrap_traces(MP.integrate, SEEDS)
    print(f"wake traces (FitTemplate, positive c only -- it cannot solve c<0): {len(traces)}")
    print(f"  {traces[:4]} ...")

    e_frame = ("+", "e", 1)                     # the exponent frame (already unique from the traces)
    S0 = survivors(traces, 0)
    print(f"\nSLEEP survivor SET for the c-frame (not just the first match): {len(S0)} frames")
    for t in S0[:6]:
        v_neg = SL.ev(t, -5, 1)
        print(f"  {SL.lab(t):34s} predicts c=-5,e=1 -> {v_neg}   (truth {F(-5,2)})")
    correct = [t for t in S0 if all(SL.ev(t, c, e) == F(c, e + 1) for c in (-9, -5, 2, 7) for e in (1, 3))]
    print(f"  of these, {len(correct)} are correct in general; the rest agree only on c>0 "
          f"=> UNDERDETERMINED by the available evidence, exactly as Phase 2 reported")

    print(f"\n=== ACTIVE probing (COLLECT: maximise survivor-set split) ===")
    ca, ua = run("active", S0, MP.integrate, e_frame)
    print(f"  probes used {len(ua)}: {ua}")
    print(f"  survivors -> {len(ca)}: {[SL.lab(t) for t in ca[:3]]}")
    ok_active = len(ca) == 1 and all(SL.ev(ca[0], c, e) == F(c, e + 1) for c in (-9, -5, 2, 7) for e in (1, 3, 5))
    print(f"  committed frame is CORRECT IN GENERAL (incl. c<0): {ok_active}")

    print(f"\n=== CONTROL: RANDOM probing at equal budget (20 seeds) ===")
    solved = 0; tot_pr = 0; sizes = []
    for s in range(20):
        cr, ur = run("random", S0, MP.integrate, e_frame, rng=random.Random(s))
        tot_pr += len(ur); sizes.append(len(cr))
        if len(cr) == 1 and all(SL.ev(cr[0], c, e) == F(c, e + 1) for c in (-9, -5, 2, 7) for e in (1, 3, 5)):
            solved += 1
    print(f"  random: {solved}/20 reached the correct unique frame; mean probes {tot_pr/20:.1f}; "
          f"mean survivors left {sum(sizes)/len(sizes):.1f}")
    print(f"  active: {'1/1' if ok_active else '0/1'} with {len(ua)} probe(s)")

    print(f"\n=== VERDICT ===")
    if ok_active:
        print(f"  GAP CLOSED: the engine ITSELF detects that its survivor set is underdetermined, CHOOSES the")
        print(f"  discriminating input, asks the execution oracle, and commits the generally-correct frame")
        print(f"  c/(e+1) in {len(ua)} probe(s). FitTemplate's c<0 blindness is bypassed because a probe only")
        print(f"  needs TESTING, not searching. COLLECT now demonstrated at the FRAME layer, not just perception.")
    else:
        print(f"  NOT closed: active probing left {len(ca)} survivors -- report, do not tune.")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase2e_active_probing"] = {
        "wake_traces": len(traces), "survivor_set_before": len(S0),
        "correct_in_general_before": len(correct),
        "active_probes": ua, "active_survivors": len(ca),
        "active_frame": SL.lab(ca[0]) if ca else None, "active_correct_general": bool(ok_active),
        "random_control": {"solved": solved, "n": 20, "mean_probes": tot_pr / 20,
                           "mean_survivors_left": sum(sizes) / len(sizes)},
        "verdict": "GAP CLOSED" if ok_active else "not closed",
        "reading": "the underdetermination Phase 2 reported was an ACTIVE-PROBING gap, not a grammar gap, and "
                   "the engine closes it itself: detect a non-singleton survivor set, choose the maximally "
                   "splitting input, answer it with the execution oracle, reject the losers. COLLECT at the "
                   "frame layer. A probe requires only TESTING, so FitTemplate's inability to SEARCH c<0 "
                   "never blocks it.",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
