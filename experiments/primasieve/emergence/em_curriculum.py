"""EMERGENCE E-5 -- LEARNING-PROGRESS CURRICULUM (em_curriculum_prereg.md). ZERO LLM, pure stdlib.

Can a learning-progress bandit recover a usable curriculum from an UNORDERED task pool with dead ends, at
matched energy, or does the rejection-first engine's binary verdict leave it nothing to climb? World = E-2b's
d^k family (k=1..20) + 6 deceptive distractors; solver = em_depth's library-then-blind, one code path for every
arm; selection = core.select.cost_aware_ucb (constant cost = plain UCB; realized cost = the project's form).
Randomness lives ONLY in task selection. The oracle (exact trace match) is untouched."""
import os, sys, json, time, random, collections, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # read-only imports from ../ (core/, sleep_l0)
sys.path.insert(0, HERE)
from fractions import Fraction as F
import sleep_l0 as SL
import em_loop as E
import em_depth as D
from core.select import cost_aware_ucb

OUT = os.path.join(HERE, "EMERGENCE.json")
INPUTS = D.INPUTS
CAP = 8000                     # pinned (prereg): d1@51, d2@1733 reachable; d3+ unreachable even at 60000
BUDGET = 320000                # pinned: 40 blind failures
KS = list(range(1, 21))
XS = (3, 5, 7, 9, 11, 13)


# ---------------------------------------------------------------- the world
def tasks_pool():
    T = collections.OrderedDict()
    for k in KS:
        T[f"d{k}"] = {"sig": D.sig_k(k), "traces": D.traces_k(k), "kind": "family", "k": k}
    for k in XS:
        def truth(c, e, k=k):
            m = F(c)
            for i in range(k):
                m *= (e - i)
            return (m + k * e, e - k)
        tr = [((c, e), truth(c, e)) for c, e in INPUTS]
        T[f"x{k}"] = {"sig": tuple((str(a), str(b)) for _, (a, b) in tr), "traces": tr, "kind": "distractor", "k": k}
    return T


def comp_frac(s, target):
    return (all(x[0] == y[0] for x, y in zip(s, target)) + all(x[1] == y[1] for x, y in zip(s, target))) / 2


_SIG = {}      # wall-time caches only: library entries are immutable once named, so (name) and (a,b) signatures
_PAIR = {}     # never change. Energy is still counted as 1 per check, exactly as em_depth.solve_by_library does.
_PAIR_SIGS = _PAIR   # shared with em_closure's core.closure.Closure(pair_cache=...) -- same (frame, sig) shape


def _entry_sig(n, fr):
    if n not in _SIG: _SIG[n] = D.frame_sig(fr)
    return _SIG[n]


def _pair(a, b, lib):
    key = (a, b)
    if key not in _PAIR:
        fr = E.compose(lib[a], lib[b]); _PAIR[key] = (fr, D.frame_sig(fr))
    return _PAIR[key]


def lib_attempt(task, lib):
    """entries, then ordered pairs; -> (best partial competence, cost, frame|None, how)."""
    target = task["sig"]; best = 0.0; cost = 0
    for n, fr in list(lib.items()):
        cost += 1; s = _entry_sig(n, fr)
        if s == target: return 1.0, cost, fr, f"library:{n}"
        if s: best = max(best, comp_frac(s, target))
    names = list(lib)
    for a in names:
        for b in names:
            cost += 1; fr, s = _pair(a, b, lib)
            if s == target: return 1.0, cost, fr, f"library:({a} o {b})"
            if s: best = max(best, comp_frac(s, target))
    return best, cost, None, None


def blind_attempt(task):
    """em_depth.solve_blind semantics at CAP: c-component first, return on its failure; graded competence."""
    tr = task["traces"]; got = [None, None]; cost = 0
    for which in (0, 1):
        found = None
        for t, _s in E.pool(INPUTS, 3, CAP):
            cost += 1; ok = True
            for (oc, oe), new in tr:
                v = SL.ev(t, oc, oe)
                if v is None or v != F(new[which]): ok = False; break
            if ok: found = t; break
        if found is None:
            return (0.0 if which == 0 else 0.5), cost, None
        got[which] = found
    return 1.0, cost, (got[0], got[1])


def attempt(task, lib, use_library=True):
    cost = 0; best = 0.0
    if use_library and lib:
        best, c, fr, how = lib_attempt(task, lib); cost += c
        if fr is not None: return 1.0, cost, fr, how
    comp, c, fr = blind_attempt(task); cost += c
    if fr is not None: return 1.0, cost, fr, "blind"
    return max(best, comp), cost, None, None


# ---------------------------------------------------------------- the arms
def run(policy, seed, budget=BUDGET, use_library=True, verbose=False):
    tasks = tasks_pool(); names = list(tasks)
    rng = random.Random(seed)
    order = names[:]
    if policy != "ASC": rng.shuffle(order)                 # SHUFFLED / LP list order; RANDOM ignores it
    lib = {}; spent = 0; step = 0
    comp_prev = {n: 0.0 for n in names}
    tried = collections.Counter(); reward = collections.defaultdict(float); costsum = collections.Counter()
    solved = set(); first_solve = []; attempts = []; spurious = 0
    while spent < budget:
        if policy in ("ASC", "SHUFFLED"): name = order[step % len(order)]
        elif policy == "RANDOM": name = rng.choice(names)
        elif policy in ("LP-UCB", "SUCCESS-UCB"):
            name = cost_aware_ucb(order, tried, reward, cost=lambda m: 1.0)
        elif policy == "LP-COST":
            name = cost_aware_ucb(order, tried, reward, cost=lambda m: (costsum[m] / tried[m]) if tried[m] else 1.0)
        else: raise ValueError(policy)
        step += 1
        comp, cost, fr, how = attempt(tasks[name], lib, use_library)
        spent += cost
        prog = max(0.0, comp - comp_prev[name])
        r = comp if policy == "SUCCESS-UCB" else prog
        tried[name] += 1; reward[name] += r; costsum[name] += cost
        comp_prev[name] = max(comp_prev[name], comp)
        already = name in solved
        if fr is not None:
            if D.frame_sig(fr) != tasks[name]["sig"]: spurious += 1          # cannot happen with an exact oracle; counted
            if not already: solved.add(name); first_solve.append((name, spent))
            if use_library:
                s = D.frame_sig(fr)
                if s and not any(D.frame_sig(v) == s for v in lib.values()): lib[name] = fr
        attempts.append({"name": name, "comp": comp, "cost": cost, "solved": fr is not None, "mastered_re": already,
                         "kind": tasks[name]["kind"]})
    fam = sorted(tasks[n]["k"] for n in solved if tasks[n]["kind"] == "family")
    waste = sum(a["cost"] for a in attempts if not a["solved"]) / max(1, spent)
    dis_att = sum(1 for a in attempts if a["kind"] == "distractor")
    dis_re = sum(1 for a in attempts if a["kind"] == "distractor") - len({a["name"] for a in attempts if a["kind"] == "distractor"})
    unsolved_fam = [n for n in names if tasks[n]["kind"] == "family" and n not in solved]
    unsolved_fam_att = sum(tried[n] for n in unsolved_fam)
    per_dis = dis_att / len(XS)
    per_unsolved = (unsolved_fam_att / len(unsolved_fam)) if unsolved_fam else 0.0
    ks_order = [tasks[n]["k"] for n, _ in first_solve if tasks[n]["kind"] == "family"]
    rho = spearman(ks_order)
    return {"policy": policy, "seed": seed, "reached": fam, "max_k": max(fam) if fam else 0, "waste": round(waste, 3),
            "spent": spent, "attempts": len(attempts), "mastered_re": sum(1 for a in attempts if a["mastered_re"]),
            "distractor_attempts": dis_att, "distractor_reattempts": dis_re, "per_distractor": round(per_dis, 2),
            "per_unsolved_family": round(per_unsolved, 2), "first_solve_ks": ks_order, "rho": rho,
            "distractors_solved": sorted(n for n in solved if tasks[n]["kind"] == "distractor"), "spurious": spurious,
            "library": len(lib)}


def spearman(seq):
    """rank correlation between position in seq and the value; None if < 3 items."""
    n = len(seq)
    if n < 3: return None
    rank_val = {v: i for i, v in enumerate(sorted(seq))}
    d2 = sum((i - rank_val[v]) ** 2 for i, v in enumerate(seq))
    return round(1 - 6 * d2 / (n * (n * n - 1)), 3)


def show(r):
    print(f"  {r['policy']:11s} seed {r['seed']}: reached k={r['reached']} max {r['max_k']:>2}  waste {r['waste']:.2f}  "
          f"attempts {r['attempts']:>4} (mastered re {r['mastered_re']:>4}, distractor {r['distractor_attempts']:>3}; "
          f"per-distractor {r['per_distractor']:.1f} vs per-unsolved-family {r['per_unsolved_family']:.1f})  rho={r['rho']}"
          + (f"  DISTRACTOR SOLVED {r['distractors_solved']}" if r["distractors_solved"] else ""), flush=True)


if __name__ == "__main__":
    t0 = time.time()
    print("EMERGENCE E-5 -- learning-progress curriculum vs authored / shuffled / random sweeps\n", flush=True)
    print(f"world: d^k k=1..20 + 6 distractors x_k; blind cap {CAP}; budget {BUDGET} evals per run\n", flush=True)

    # ---- dead-end verification + sanity ----
    T = tasks_pool()
    dead = {}
    for k in XS:
        comp, cost, fr = blind_attempt(T[f"x{k}"])
        dead[f"x{k}"] = fr is None
    print(f"distractors blind-unreachable at cap: {dead}", flush=True)
    san = run("ASC", 0, budget=60000, use_library=False)
    print(f"SANITY no-library ASC: reached k={san['reached']}  (must be a subset of [1, 2])", flush=True)
    if not set(san["reached"]) <= {1, 2}:
        print("SANITY FAILED -- world broken; STOP."); sys.exit(1)
    print("SANITY PASSED\n", flush=True)

    results = []
    print("=== ASC (authored order; deterministic) ===", flush=True)
    r = run("ASC", 0); show(r); results.append(r)
    for pol in ("SHUFFLED", "RANDOM", "LP-UCB", "LP-COST"):
        print(f"=== {pol} (3 seeds) ===", flush=True)
        for sd in (1, 2, 3):
            r = run(pol, sd); show(r); results.append(r)
    print("=== SUCCESS-UCB knockout (reward = competence, not progress) ===", flush=True)
    r = run("SUCCESS-UCB", 1); show(r); results.append(r)

    # ---- verdicts ----
    print("\n=== verdicts (pre-registered) ===", flush=True)
    by = collections.defaultdict(dict)
    for r in results: by[r["policy"]][r["seed"]] = r
    asc = by["ASC"][0]
    for lp in ("LP-UCB", "LP-COST"):
        win = True; notes = []
        for sd in (1, 2, 3):
            L = by[lp][sd]; S = by["SHUFFLED"][sd]; R = by["RANDOM"][sd]
            sup = set(L["reached"]) >= set(S["reached"]) and set(L["reached"]) >= set(R["reached"])
            w = L["waste"] <= 0.5 * S["waste"] and L["waste"] <= 0.5 * R["waste"]
            notes.append(f"seed{sd}: reached>=controls {sup}, waste<=half {w} ({L['waste']:.2f} vs S {S['waste']:.2f} R {R['waste']:.2f})")
            win = win and sup and w
        print(f"  {lp}: {'WIN over controls' if win else 'null: does not beat a fixed sweep'}   " + "; ".join(notes), flush=True)
        worst_max = min(by[lp][sd]["max_k"] for sd in (1, 2, 3))
        print(f"      vs ASC: ASC max k {asc['max_k']} waste {asc['waste']:.2f}; {lp} worst-seed max k {worst_max}, "
              f"waste {max(by[lp][sd]['waste'] for sd in (1, 2, 3)):.2f}", flush=True)
    ko = by["SUCCESS-UCB"][1]; lpu = by["LP-UCB"][1]
    print(f"  knockout SUCCESS-UCB (seed 1): mastered re-attempts {ko['mastered_re']} vs LP-UCB {lpu['mastered_re']} "
          f"(>=3x? {ko['mastered_re'] >= 3 * max(1, lpu['mastered_re'])}); max k {ko['max_k']} vs {lpu['max_k']} "
          f"(<=? {ko['max_k'] <= lpu['max_k']})", flush=True)
    for lp in ("LP-UCB", "LP-COST"):
        misled = [sd for sd in (1, 2, 3) if by[lp][sd]["per_distractor"] > by[lp][sd]["per_unsolved_family"] and by[lp][sd]["per_unsolved_family"] > 0]
        print(f"  deception check {lp}: distractors drew more attempts per task than unsolved family tasks on seeds {misled or 'none'}", flush=True)
    rhos = {f"{r['policy']}/{r['seed']}": r["rho"] for r in results}
    all_high = all(v is not None and v > 0.8 for v in rhos.values())
    print(f"  emergent ascending order: rho>0.8 in ALL arms = {all_high}  {rhos}", flush=True)
    print(f"  spurious commits (frame not matching its task): {sum(r['spurious'] for r in results)}", flush=True)

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E5_learning_progress_curriculum"] = {"prereg": "em_curriculum_prereg.md", "cap": CAP, "budget": BUDGET,
                                            "dead_ends": dead, "runs": results, "secs": round(time.time() - t0, 1)}
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"\n({time.time()-t0:.0f}s) -> EMERGENCE.json[E5_learning_progress_curriculum]. Read the verdict lines as-is.", flush=True)
