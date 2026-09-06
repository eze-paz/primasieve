"""EMERGENCE E-6 -- CLOSURE SELF-MODEL CURRICULUM (em_closure_prereg.md). ZERO LLM, pure stdlib.

E-5 nulled: learning progress had nothing to climb on a sound binary verdict. E-6 gives the policy the graded,
SOUND signal the engine already owns -- the pair-composition CLOSURE of its own library (distance 0/1/inf to each
task, by exact signature membership) -- plus permanent memory of blind failures (blind is deterministic and
library-independent). Closure maintenance and distance queries are CHARGED to energy. One loop, one solver
(em_curriculum.attempt), four selection rules. Randomness only in the presentation order; oracle untouched."""
import os, sys, json, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import em_depth as D
import em_loop as E
import em_curriculum as C
from em_curriculum import tasks_pool, attempt, lib_attempt, spearman, BUDGET, CAP, XS
from core.registry import selfcheck
from core.closure import Closure as _CoreClosure, schedule, HALT, INF   # the self-model lives in core/ now

OUT = os.path.join(HERE, "EMERGENCE.json")


def Closure():
    """core.closure.Closure bound to this thread's compose/sig (pair cache shared with em_curriculum: wall-time
    only). The first E-6 run used a local class with identical accounting; C2 requires the numbers not to move."""
    return _CoreClosure(E.compose, D.frame_sig, pair_cache=C._PAIR_SIGS)


def run(policy, seed, budget=BUDGET):
    tasks = tasks_pool(); names = list(tasks)
    rng = random.Random(seed); order = names[:]
    if policy != "ASC": rng.shuffle(order)                     # identical permutation to em_curriculum for this seed
    lib = {}; clo = Closure(); spent = 0; step = 0
    solved = set(); blind_done = set(); attempts = []; unsound = 0; halted_at = None; energy_to_20 = None
    first_solve = []
    while spent < budget:
        mode = "full"
        if policy in ("ASC", "SHUFFLED"):
            name = order[step % len(order)]
        elif policy == "BLIND-ONCE":
            name = order[step % len(order)]
            if name in blind_done: mode = "library-only"
        elif policy == "CLOSURE":
            unsolved = [n for n in order if n not in solved]
            c0 = clo.cost
            pick = schedule(clo, unsolved, lambda n: tasks[n]["sig"], blind_done)
            spent += clo.cost - c0                             # distance queries are charged
            if pick is HALT:
                halted_at = spent; break                       # self-model says nothing more can succeed
            name, mode = pick
        else:
            raise ValueError(policy)
        step += 1
        task = tasks[name]
        if mode == "library-only":
            best, cost, fr, how = lib_attempt(task, lib)
            comp = 1.0 if fr is not None else best
        else:
            comp, cost, fr, how = attempt(task, lib)
        spent += cost
        if mode in ("full", "blind-probe") and (fr is None or how == "blind"):
            blind_done.add(name)                               # blind was run on this task: permanent knowledge
        if mode == "closure" and fr is None:
            unsound += 1
        if fr is not None:
            if D.frame_sig(fr) != task["sig"]: raise AssertionError("spurious commit")
            if name not in solved:
                solved.add(name); first_solve.append(name)
                if task["kind"] == "family" and task["k"] == 20: energy_to_20 = spent
            s = D.frame_sig(fr)
            if s and not any(D.frame_sig(v) == s for v in lib.values()):
                lib[name] = fr
                c0 = clo.cost; clo.add(name, fr, lib)
                if policy == "CLOSURE": spent += clo.cost - c0  # only the arm that USES the self-model pays for it
        attempts.append({"name": name, "cost": cost, "solved": fr is not None, "kind": task["kind"], "mode": mode,
                         "blind": how == "blind" or (fr is None and mode in ("full", "blind-probe"))})
    fam = sorted(tasks[n]["k"] for n in solved if tasks[n]["kind"] == "family")
    ks_order = [tasks[n]["k"] for n in first_solve if tasks[n]["kind"] == "family"]
    return {"policy": policy, "seed": seed, "reached": fam, "max_k": max(fam) if fam else 0,
            "energy_to_20": energy_to_20, "spent": spent, "halted_at": halted_at,
            "unsolved_at_end": sorted(n for n in names if n not in solved),
            "blind_failures": sum(1 for a in attempts if a["blind"] and not a["solved"]),
            "distractor_attempts": sum(1 for a in attempts if a["kind"] == "distractor"),
            "unsound_distance1": unsound, "attempts": len(attempts),
            "waste": round(sum(a["cost"] for a in attempts if not a["solved"]) / max(1, spent), 3),
            "closure_cost": clo.cost, "rho": spearman(ks_order), "first_solve": first_solve,
            "d1_position_in_order": order.index("d1")}


def show(r):
    print(f"  {r['policy']:10s} seed {r['seed']}: reached max {r['max_k']:>2} ({len(r['reached'])}/20)  "
          f"E->20 {r['energy_to_20']}  spent {r['spent']:>6}"
          + (f"  HALTED@{r['halted_at']} unsolved={r['unsolved_at_end']}" if r["halted_at"] is not None else "  (ran to budget)")
          + f"\n{'':14s}blind failures {r['blind_failures']:>3}  distractor attempts {r['distractor_attempts']:>3}  "
          f"unsound d=1 {r['unsound_distance1']}  attempts {r['attempts']:>4}  waste {r['waste']:.2f}  "
          f"closure cost {r['closure_cost']}  d1 at position {r['d1_position_in_order']}  rho={r['rho']}", flush=True)


if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    print("EMERGENCE E-6 -- closure self-model curriculum (no authored order; blind once per task; honest halt)\n", flush=True)
    E5 = json.load(open(OUT)).get("E5_learning_progress_curriculum", {}).get("runs", [])
    e5 = {(r["policy"], r["seed"]): r for r in E5}

    results = []
    print("=== sanity: ASC and SHUFFLED must reproduce E-5 ===", flush=True)
    ok = True
    for pol, seeds in (("ASC", (0,)), ("SHUFFLED", (1, 2, 3))):
        for sd in seeds:
            r = run(pol, sd); show(r); results.append(r)
            ref = e5.get((pol, sd))
            same = ref is not None and ref["reached"] == r["reached"]
            ok = ok and same
            print(f"{'':14s}== E-5 reached set: {same}", flush=True)
    if not ok:
        print("SANITY FAILED -- harness differs from E-5; STOP."); sys.exit(1)
    print("SANITY PASSED\n", flush=True)

    for pol in ("BLIND-ONCE", "CLOSURE"):
        print(f"=== {pol} (3 seeds) ===", flush=True)
        for sd in (1, 2, 3):
            r = run(pol, sd); show(r); results.append(r)

    by = {(r["policy"], r["seed"]): r for r in results}
    asc = by[("ASC", 0)]
    print("\n=== verdicts (pre-registered) ===", flush=True)
    cl = [by[("CLOSURE", sd)] for sd in (1, 2, 3)]; bo = [by[("BLIND-ONCE", sd)] for sd in (1, 2, 3)]
    sound = all(r["unsound_distance1"] == 0 for r in cl)
    reach = all(r["reached"] == list(range(1, 21)) for r in cl)
    six = all(r["distractor_attempts"] == 6 for r in cl)
    halt = all(r["halted_at"] is not None and r["unsolved_at_end"] == sorted(f"x{k}" for k in XS) for r in cl)
    print(f"  KILL#2 self-model sound (0 unsound distance-1 calls, all seeds): {sound}", flush=True)
    print(f"  KILL#3 CLOSURE reaches k=1..20 on every seed: {reach}   (SHUFFLED: "
          f"{[len(by[('SHUFFLED', sd)]['reached']) for sd in (1, 2, 3)]}/20)", flush=True)
    print(f"  KILL#4 distractor attempts exactly 6 per run: {six}  {[r['distractor_attempts'] for r in cl]}   "
          f"(ASC {asc['distractor_attempts']}, SHUFFLED {[by[('SHUFFLED', sd)]['distractor_attempts'] for sd in (1, 2, 3)]}, "
          f"BLIND-ONCE {[r['distractor_attempts'] for r in bo]})", flush=True)
    print(f"  KILL#5 honest halt with exactly the 6 distractors unsolved, budget left unspent: {halt}  "
          f"halted at {[r['halted_at'] for r in cl]} of {BUDGET}", flush=True)
    sep = all(b["reached"] == c["reached"] and b["distractor_attempts"] == c["distractor_attempts"]
              and b["energy_to_20"] and c["energy_to_20"] and b["energy_to_20"] <= 1.5 * c["energy_to_20"]
              for b, c in zip(bo, cl))
    print(f"  KILL#6 BLIND-ONCE indistinguishable from CLOSURE (closure adds nothing over memory): {sep}   "
          f"E->20 BLIND-ONCE {[r['energy_to_20'] for r in bo]} vs CLOSURE {[r['energy_to_20'] for r in cl]}; "
          f"BLIND-ONCE halts: {[r['halted_at'] is not None for r in bo]}", flush=True)
    ratios = [(r["energy_to_20"] / asc["energy_to_20"]) if (r["energy_to_20"] and asc["energy_to_20"]) else None for r in cl]
    print(f"  #7 energy-to-20 CLOSURE/ASC per seed: {[f'{x:.2f}x' if x else 'NA' for x in ratios]}  (ASC E->20 = {asc['energy_to_20']}; "
          f"d1 positions in shuffle {[r['d1_position_in_order'] for r in cl]})  "
          f"{'>10x on a seed: self-model does not compensate for order ignorance at this budget' if any(x and x > 10 for x in ratios) else 'within 10x'}", flush=True)
    print(f"      total energy at halt CLOSURE {[r['spent'] for r in cl]} vs ASC full budget {asc['spent']} "
          f"(ASC waste {asc['waste']:.2f}; CLOSURE waste {[r['waste'] for r in cl]})", flush=True)
    print(f"  emergent ascending order rho (CLOSURE): {[r['rho'] for r in cl]}", flush=True)
    verdict = sound and reach and six and halt and not sep
    print(f"\n  PASS (all kills survived, closure adds over memory): {verdict}", flush=True)
    if verdict:
        print("  E6 CLOSURE CURRICULUM: PASS -- full reach, one probe per dead end, honest halt, no authored order", flush=True)

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E6_closure_curriculum"] = {"prereg": "em_closure_prereg.md", "runs": results, "pass": verdict,
                                  "secs": round(time.time() - t0, 1)}
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"\n({time.time()-t0:.0f}s) -> EMERGENCE.json[E6_closure_curriculum]", flush=True)
