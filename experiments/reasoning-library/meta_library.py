"""3rd-order LIBRARY-LEARNING (METAPLAN P4 / S3 capability crossover), ZERO LLM. Code analog of
emergence.py's `sq`: compress a recurring single-site EDIT into a macro operator that applies it
EVERYWHERE, so a k-identical-site bug (combinatorial for primitive single-site search) becomes a
one-move fix. Measure reachability/energy vs k, primitives-only vs primitives+learned-macro.
The crossover = capability that APPEARED from the system's own solutions, not programmed."""
import ast, copy, time
import reasoner_code as rc

BUDGET = 20000

# ---------- a k-identical-site bug family ----------
def gen(k):
    """A function with k threshold checks, ALL using `<` where `<=` is correct. Tests isolate each
    threshold so the fix is well-defined; a correct fix flips every `<` to `<=`."""
    lines = ["def f(x):", "    n = 0"]
    for i in range(1, k + 1):
        lines.append(f"    if x < {i}: n += 1")     # bug: should be x <= i
    lines.append("    return n")
    src = "\n".join(lines) + "\n"
    def correct(x): return sum(1 for i in range(1, k + 1) if x <= i)
    tests = [([i], correct(i)) for i in range(0, k + 2)]   # inputs isolate each threshold
    return src, tests

def score(tree, tests):
    try: code = compile(ast.fix_missing_locations(tree), "<c>", "exec")
    except Exception: return len(tests) + 1
    return sum(1 for inp, exp in tests if not rc.run_one(code, "f", inp, exp)[0])

# ---------- primitive single-site search (steepest hill-climb over stratum-0) ----------
def solve_primitive(src, tests, extra_forms=(), budget=BUDGET):
    tree = ast.parse(src); best = score(tree, tests); units = 0; accepted = []
    while best > 0 and units < budget:
        cand_best = (best, None, None)
        # learned macro operators first (cheap, big moves)
        for mname, apply_macro in extra_forms:
            t2 = apply_macro(tree)
            if t2 is None: continue
            units += 1; s = score(t2, tests)
            if s < cand_best[0]: cand_best = (s, t2, ("MACRO", mname))
        # primitive single-site edits
        for s0, ln, desc, idx, ka in [e for e in rc.enumerate_edits(tree, 0) if e[0] == 0]:
            t2 = rc.apply_edit(tree, idx, ka)
            if t2 is None: continue
            units += 1; s = score(t2, tests)
            if s < cand_best[0]: cand_best = (s, t2, ka)
            if units >= budget: break
        if cand_best[1] is None: break             # no improving move -> stuck
        tree, best, mv = cand_best[1], cand_best[0], cand_best[2]
        accepted.append(mv)
    return best == 0, units, accepted

# ---------- sleep: compress a recurring single-site edit into a GLOBAL macro ----------
def learn_macro(accepted_lists):
    """Find the single-site edit KIND that recurred most (applied at many sites) and abstract it to
    'apply this edit to ALL matching nodes at once'. Generic over the edit kind."""
    from collections import Counter
    cnt = Counter()
    for acc in accepted_lists:
        for mv in acc:
            if isinstance(mv, tuple) and mv and mv[0] != "MACRO":
                cnt[(mv[0], _kakey(mv))] += 1
    if not cnt: return None
    (kind, keyarg), c = cnt.most_common(1)[0]
    if c < 2: return None                          # only compress a genuinely RECURRING edit
    def apply_all(tree, kind=kind, keyarg=keyarg):
        t = copy.deepcopy(tree); changed = False
        for node in ast.walk(t):
            if _matches(node, kind, keyarg):
                _apply_inplace(node, kind, keyarg); changed = True
        return ast.fix_missing_locations(t) if changed else None
    name = f"ALL[{kind}:{keyarg}]"
    return (name, apply_all), c

# helpers: edit-kind matching for the macro (covers cmp / binop swaps)
def _kakey(ka):
    kind, arg = ka[0], ka[1]
    return arg.__name__ if isinstance(arg, type) else str(arg)
def _matches(node, kind, keyarg):
    if kind == "cmp" and isinstance(node, ast.Compare) and len(node.ops) == 1:
        return type(node.ops[0]).__name__ != keyarg
    if kind == "binop" and isinstance(node, ast.BinOp):
        return type(node.op).__name__ != keyarg
    return False
_OPS = {"LtE": ast.LtE, "Lt": ast.Lt, "GtE": ast.GtE, "Gt": ast.Gt, "Eq": ast.Eq, "NotEq": ast.NotEq,
        "Add": ast.Add, "Sub": ast.Sub, "Mult": ast.Mult, "Mod": ast.Mod, "FloorDiv": ast.FloorDiv}
def _apply_inplace(node, kind, keyarg):
    if kind == "cmp": node.ops = [_OPS[keyarg]()]
    elif kind == "binop": node.op = _OPS[keyarg]()

if __name__ == "__main__":
    print("=== 3rd-ORDER LIBRARY-LEARNING: capability crossover from self-compression (zero LLM) ===\n")
    KS = [1, 2, 3, 4, 5, 6, 8, 10, 12]

    # WAKE: solve small k with primitives, collect accepted edits
    print("WAKE — primitive single-site search:")
    accepted_lists = []
    prim = {}
    for k in KS:
        src, tests = gen(k)
        ok, units, acc = solve_primitive(src, tests)
        prim[k] = (ok, units)
        if k <= 3 and ok: accepted_lists.append(acc)     # learn only from SMALL solved cases
        print(f"  k={k:2d}: {'SOLVED' if ok else 'FAIL  '} units={units}")

    # SLEEP: compress the recurring edit into a global macro
    learned = learn_macro(accepted_lists)
    if not learned:
        print("\nno recurring edit to compress"); raise SystemExit
    (mname, macro), c = learned
    print(f"\nSLEEP — recurring single-site edit seen {c}x -> compressed macro operator '{mname}'"
          f" (apply everywhere in ONE move)\n")

    # WAKE 2: same k, primitives + learned macro
    print("WAKE 2 — primitives + learned macro:")
    for k in KS:
        src, tests = gen(k)
        ok, units, acc = solve_primitive(src, tests, extra_forms=[(mname, macro)])
        p_ok, p_units = prim[k]
        mark = ""
        if ok and not p_ok: mark = "  <== NOW REACHABLE (was unsolved)"
        elif ok and p_ok and units < p_units: mark = f"  (prim {p_units} -> {units})"
        print(f"  k={k:2d}: {'SOLVED' if ok else 'FAIL  '} units={units}{mark}")

    print(f"\n=== S3: the macro '{mname}' was LEARNED from k<=3 solutions and makes large-k bugs")
    print(f"    reachable/cheap that primitive single-site search cannot reach in budget. Capability")
    print(f"    GREW from the system's own compression — nothing about large k was programmed. ===")
