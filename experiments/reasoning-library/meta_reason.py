"""P1 — meta-controller v0: UCB over reasoning FORMS, energy-accounted, with episode logging.
KNOCKOUT: does a learned form-selection policy match the HAND-CODED escalation (strata 0->1->2
+ reset) at EQUAL energy on QuixBugs? (METAPLAN.md S1 / P1). Zero LLM."""
import os, json, math, time, ast, random
import reasoner_code as rc
from meta_forms import MetaState, Enumerate, Reset, default_forms

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
def solve_ucb(name, src, tests, ep_log, warm=None, held_back=0.0):
    st = MetaState(name, src, tests, held_back=held_back)
    forms = default_forms()
    # warm = {form_name: prior_pseudo_reward}; seeds q with n=1 so a mined strategy biases early picks
    n = {f.name: (1 if warm and f.name in warm else 0) for f in forms}
    q = {f.name: (warm[f.name] if warm and f.name in warm else 0.0) for f in forms}
    total = sum(n.values())
    while not st.solved() and st.units < GLOBAL:
        avail = [f for f in forms if f.applicable(st)]
        if not avail: break                    # all strata exhausted, nothing left to try
        def ucb(f):                            # COST-AWARE UCB: Occam prior in the exploration term
            ch = getattr(f, "cost_hint", 1.0)
            if n[f.name] == 0: return 100.0 / ch          # try CHEAP forms first (not blind 1e9)
            return q[f.name] + 1.5 * math.sqrt(math.log(total + 1) / n[f.name]) / ch
        f = max(avail, key=ucb)
        before = st.best; u0 = st.units
        d = f.run(st, SLICE)
        spent = max(1, st.units - u0)
        gain = (before - st.best) / (len(tests) + 1)     # normalized score improvement
        r = gain / (spent / SLICE) + (5.0 if d["solved"] else 0.0)
        n[f.name] += 1; total += 1; q[f.name] += (r - q[f.name]) / n[f.name]
        ep_log.append({"form": f.name, "before": before, "after": st.best, "spent": spent,
                       "reward": round(r, 4), "solved": d["solved"], "improved": d["improved"]})
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
