"""P1 — meta-controller v0: UCB over reasoning FORMS, energy-accounted, with episode logging.
KNOCKOUT: does a learned form-selection policy match the HAND-CODED escalation (strata 0->1->2
+ reset) at EQUAL energy on QuixBugs? (METAPLAN.md S1 / P1). Zero LLM."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.select import cost_aware_ucb as _core_ucb   # the shared selector this file's UCB is extracted into

import os, json, math, time, ast, random
import reasoner_code as rc
from meta_forms import MetaState, Enumerate, Reset, Interpolate, default_forms

QB = os.path.expanduser("~/quixbugs")
SLICE = int(os.environ.get("META_SLICE", "250"))       # candidate-eval budget per form call
GLOBAL = int(os.environ.get("META_GLOBAL", "12000"))   # candidate-eval budget per program
EPISODES = os.path.join(os.path.dirname(__file__), "episodes"); os.makedirs(EPISODES, exist_ok=True)

def load_tests(name):
    T = []
    for line in open(f"{QB}/json_testcases/{name}.json"):
        line = line.strip()
        if not line: continue
        o = json.loads(line); inp, exp = o[0], o[1]
        if not isinstance(inp, list): inp = [inp]
        T.append((inp, exp))
    return T

# ---------------- controller A: hand-coded escalation (the current reasoner_code policy) --------
def solve_handcoded(name, src, tests):
    st = MetaState(name, src, tests)
    reset = Reset()
    for k in (0, 1, 2):                    # fixed escalation; reset-to-pristine before deepening
        f = Enumerate(k)
        if k > 0 and st.tree is not st.orig: reset.run(st, 0)
        while st.units < GLOBAL and not f._exhausted(st):
            d = f.run(st, SLICE)
            if d["solved"]: return True, st.units, st.stratum_seen
    return st.solved(), st.units, st.stratum_seen

# ---------------- controller B: UCB bandit over forms (learned selection) ----------------------
def solve_ucb(name, src, tests, ep_log, warm=None, held_back=0.0, feat_log=None, qfn=None, extra_forms=(), return_state=False):
    st = MetaState(name, src, tests, held_back=held_back)
    forms = list(extra_forms) + default_forms()   # discovered operators (extra_forms) get first pick
    warm = warm or {}                      # {form_name: pseudo_reward in ~[0,2]}
    tried_forms = set()
    err0 = None
    if feat_log is not None or qfn is not None:
        import meta_features as mf
        err0 = mf.baseline_error(st)       # cache baseline error class once (used by features)
    n = {f.name: 0 for f in forms}; q = {f.name: 0.0 for f in forms}; total = 0; momentum = None
    st.stuck = False; best_ever = st.best; units_at_best = 0; seen_fp = set()   # STUCK detector state
    while not st.solved() and st.units < GLOBAL:
        avail = [f for f in forms if f.applicable(st)]
        if not avail: break                    # all strata exhausted, nothing left to try
        # MOMENTUM: if a form just improved, give it another turn before UCB (composes multi-edit
        # fixes like sqrt's ENUM1 6->1->0 immediately, so RESET never discards the partial).
        def bonus(fn):                         # learned Q overrides warm prior when provided
            if qfn is not None:
                import meta_features as mf
                return qfn(st, fn, tried_forms, err0)
            return warm.get(fn, 0.0)
        # the selector itself is now core.select.cost_aware_ucb, shared -- see that module for the three
        # load-bearing details (cost-awareness, momentum, and lift-normalization of the prior)
        def ucb(f):                            # COST-AWARE UCB + (warm|learned) prior on exploration
            ch = getattr(f, "cost_hint", 1.0)
            if n[f.name] == 0:                 # unexplored: cheap-first (Occam) biased by the prior
                return 100.0 / ch + 55.0 * bonus(f.name)
            return q[f.name] + 1.5 * math.sqrt(math.log(total + 1) / n[f.name]) / ch
        mom = next((f for f in avail if f.name == momentum), None) if momentum else None
        f = mom if mom is not None else max(avail, key=ucb)
        row_before = None
        if feat_log is not None:
            import meta_features as mf
            row_before = mf.feature_row(st, f.name, tried_forms, err0)   # features at DECISION time
        before = st.best; u0 = st.units
        d = f.run(st, SLICE)
        spent = max(1, st.units - u0)
        if feat_log is not None:
            feat_log.append((row_before, 1 if (d["improved"] or d["solved"]) else 0))
        tried_forms.add(f.name)
        gain = (before - st.best) / (len(tests) + 1)     # normalized score improvement
        r = gain / (spent / SLICE) + (5.0 if d["solved"] else 0.0)
        n[f.name] += 1; total += 1; q[f.name] += (r - q[f.name]) / n[f.name]
        momentum = f.name if (d["improved"] and not d["solved"]) else None   # re-run a winning form
        # STUCK detector (fable): progress clears it; else a re-seen plateau after RESET or 25% of
        # remaining budget spent since the last verified new-best -> unlock escalation rungs (REPEAT).
        fp = getattr(st, "last_fail", None)
        if st.best < best_ever:
            best_ever = st.best; units_at_best = st.units; st.stuck = False
        else:
            reset_cycle = (f.name == "RESET" and fp in seen_fp)
            budget_stall = (st.units - units_at_best) > 0.25 * max(1, GLOBAL - units_at_best)
            if reset_cycle or budget_stall: st.stuck = True
        if fp is not None: seen_fp.add(fp)
        ep_log.append({"form": f.name, "before": before, "after": st.best, "spent": spent,
                       "reward": round(r, 4), "solved": d["solved"], "improved": d["improved"]})
    true_solve = st.verify_full() if st.held else st.solved()
    if return_state: return true_solve, st.units, st.stratum_seen, st   # for honest trace-diffing
    return true_solve, st.units, st.stratum_seen

def solve_iterdeep(name, src, tests, held_back=0.0, b0=40):
    """ITERATIVE-DEEPENING over the fixed cheap->deep ladder (fable-subagent's direction): try each
    form up to cap b, escalate; after a full pass with no solve, reset to pristine and DOUBLE b.
    Captures deep-fix headroom (reach ENUMERATE(2) after ~3b, not after exhausting cheap forms) with
    ZERO transfer / zero mis-steer: still cheap-first, worst case a constant-factor overhead."""
    st = MetaState(name, src, tests, held_back=held_back)
    ladder = [Enumerate(0), Enumerate(1), Enumerate(2), Interpolate()]; reset = Reset()
    b = b0
    while not st.solved() and st.units < GLOBAL:
        progressed = False
        for f in ladder:
            spent = 0
            while spent < b and f.applicable(st) and st.units < GLOBAL:
                u0 = st.units; d = f.run(st, min(SLICE, b - spent)); spent += st.units - u0
                if d["solved"]:
                    true_solve = st.verify_full() if st.held else st.solved()
                    return true_solve, st.units, st.stratum_seen
                if d["improved"]: progressed = True
                if not d["improved"] and d.get("exhausted"): break
        if all(not f.applicable(st) for f in ladder): break     # everything exhausted
        if not progressed and st.tree is not st.orig: reset.run(st, 0)
        b *= 2
    true_solve = st.verify_full() if st.held else st.solved()
    return true_solve, st.units, st.stratum_seen

if __name__ == "__main__":
    names = sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))
    sl = os.environ.get("META_NAMES")
    if sl: names = [n for n in names if n in sl.split(",")]
    t0 = time.time()
    A = {"solved": 0, "energy": 0}; B = {"solved": 0, "energy": 0}
    episodes = []
    for name in names:
        tests = load_tests(name)
        csrc = open(f"{QB}/correct_python_programs/{name}.py").read()
        try: ccode = compile(csrc, "<c>", "exec")
        except Exception: continue
        if not all(rc.run_one(ccode, name, i, e)[0] for i, e in tests): continue  # fair-scoring guard
        bsrc = open(f"{QB}/python_programs/{name}.py").read()
        aok, aen, ast_ = solve_handcoded(name, bsrc, tests)
        ep = []
        bok, ben, bst = solve_ucb(name, bsrc, tests, ep)
        episodes.append({"name": name, "handcoded": {"solved": aok, "energy": aen},
                         "ucb": {"solved": bok, "energy": ben}, "trace": ep})
        A["solved"] += aok; A["energy"] += aen; B["solved"] += bok; B["energy"] += ben
        print(f"{name:26s} hand {'Y' if aok else 'n'}({aen:5d})  ucb {'Y' if bok else 'n'}({ben:5d})",
              flush=True)
    json.dump(episodes, open(os.path.join(EPISODES, "p1_knockout.json"), "w"), indent=1)
    N = len(episodes)
    print(f"\n=== META-CONTROLLER KNOCKOUT ({N} programs) — equal-energy, ZERO LLM ===")
    print(f"HAND-CODED escalation : {A['solved']}/{N} solved, total energy {A['energy']}")
    print(f"UCB over forms        : {B['solved']}/{N} solved, total energy {B['energy']}")
    print(f"energy ratio ucb/hand : {B['energy']/max(1,A['energy']):.2f}x  "
          f"(<=1.0 = learned policy matches-or-beats hand-coded at equal solves)")
    print(f"total {time.time()-t0:.0f}s")
