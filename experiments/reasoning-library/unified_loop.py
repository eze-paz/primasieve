"""ONE loop, two task-types — bug-fix AND feature-add through the SAME control flow, ZERO LLM.

  parse -> LOCATE entity in codebase
        -> FOUND  (bug):     spec = code-minus-bug (tests); analogue = a nearby pattern;
                             PROJECT the analogue's relation onto the existing code; VERIFY.
        -> MISS   (feature): no spec in code -> CONFIRM spec with the human (examples);
                             analogue = the closest existing function elsewhere;
                             PROJECT its skeleton + SYNTHESIZE the holes from the spec; VERIFY.

The only differences are (a) where the analogue comes from and (b) the feature branch pauses to
confirm the spec (the verifier a new feature otherwise lacks). Same states, same code path.
'parse' is the tiny slot-filler's job (stubbed here — we are the translator).
"""
import ast, operator
import reasoner_interp as ri

OPS = {"+": operator.add, "-": operator.sub, "*": operator.mul}

# ---------------- a tiny "codebase" ----------------
BUGGY_POWERSET = open(__import__("os").path.expanduser("~/quixbugs/python_programs/powerset.py")).read()
SUM_LIST = "def sum_list(xs):\n    acc = 0\n    for x in xs:\n        acc = acc + x\n    return acc\n"
GET_CLASS_MEMBERS = ri.get_stdlib_func("rlcompleter.py", "get_class_members")
CODEBASE = {"powerset": BUGGY_POWERSET, "sum_list": SUM_LIST, "get_class_members": GET_CLASS_MEMBERS}

# ---------------- shared FSM primitives ----------------
def locate(codebase, entity):
    return codebase.get(entity)

def retrieve_analogue(codebase, exclude, want):
    """Closest existing function by crude structural fit to what we need."""
    best = None
    for name, src in codebase.items():
        if name == exclude: continue
        t = ast.parse(src)
        recursive = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
                        for n in ast.walk(t))
        has_reduce = any(isinstance(n, ast.For) for n in ast.walk(t))
        score = (recursive == want.get("recursive", False)) + (has_reduce == want.get("reduce", False))
        if best is None or score > best[0]: best = (score, name, src)
    return best[1], best[2]

# ---------------- feature projection: analogue skeleton + hole synthesis ----------------
def feature_skeleton(analogue_src):
    """Confirm the analogue is a reduce (init const + `acc = acc <op> x` in a loop + return acc)."""
    t = ast.parse(analogue_src); f = next(n for n in ast.walk(t) if isinstance(n, ast.FunctionDef))
    init = next((n for n in f.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)), None)
    loop = next((n for n in f.body if isinstance(n, ast.For)), None)
    if not init or not loop: return None
    upd = next((n for n in loop.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.BinOp)), None)
    if not upd: return None
    return {"acc": init.targets[0].id, "iter": loop.target.id, "seq": loop.iter.id}

def project_feature(analogue_src, new_name, spec_examples):
    """Fill the skeleton's holes (identity + operator) by synthesizing from the confirmed spec."""
    sk = feature_skeleton(analogue_src)
    if sk is None: return None, None
    for idv in (0, 1, 2, -1):
        for sym, op in OPS.items():
            def cand(xs, idv=idv, op=op):
                acc = idv
                for x in xs: acc = op(acc, x)
                return acc
            if all(cand(inp) == exp for inp, exp in spec_examples):
                src = (f"def {new_name}({sk['seq']}):\n    {sk['acc']} = {idv}\n"
                       f"    for {sk['iter']} in {sk['seq']}:\n        {sk['acc']} = {sk['acc']} {sym} {sk['iter']}\n"
                       f"    return {sk['acc']}\n")
                return src, (idv, sym)
    return None, None

def verify_feature(src, name, spec_examples):
    ns = {};
    try: exec(src, ns)
    except Exception: return False
    f = ns[name]
    return all(f(inp) == exp for inp, exp in spec_examples)

# ---------------- the ONE loop ----------------
def solve(request, codebase, trace):
    ent = request["entity"]
    trace.append(f"PARSE     -> entity='{ent}'")
    loc = locate(codebase, ent)
    if loc is not None:
        # ---- BUG branch ----
        trace.append(f"LOCATE    -> FOUND '{ent}' (exists but misbehaves) => BUG")
        ri.TESTS = request["tests"]
        trace.append("SPEC      <- code-minus-bug (behavioral tests)")
        aname, asrc = retrieve_analogue(codebase, ent, {"recursive": True, "reduce": False})
        trace.append(f"RETRIEVE  -> analogue '{aname}' (nearby, same relational shape)")
        ok, desc, fixed = ri.solve(ent, loc, asrc, aname)
        trace.append(f"PROJECT   -> {desc if ok else 'no frame projected'}")
        trace.append(f"VERIFY    -> {'PASS' if ok else 'FAIL'}")
        return ("bug", ok, fixed)
    else:
        # ---- FEATURE branch ----
        trace.append(f"LOCATE    -> MISS (no '{ent}' in codebase) => FEATURE")
        spec = request["confirm_examples"]           # the human-confirmed spec (query-user branch)
        trace.append(f"CONFIRM   <- human ratifies spec via examples e.g. {ent}{spec[0][0]}=={spec[0][1]}")
        aname, asrc = retrieve_analogue(codebase, ent, {"recursive": False, "reduce": True})
        trace.append(f"RETRIEVE  -> analogue '{aname}' (closest existing, same list->scalar shape)")
        draft, holes = project_feature(asrc, ent, spec)
        trace.append(f"PROJECT   -> skeleton of '{aname}' + synthesized holes {holes}")
        ok = draft is not None and verify_feature(draft, ent, spec)
        trace.append(f"VERIFY    -> {'PASS' if ok else 'FAIL'}")
        return ("feature", ok, draft)

if __name__ == "__main__":
    print("=== ONE loop: bug-fix AND feature-add, same FSM, zero LLM ===\n")

    # TASK 1 — BUG: powerset exists but drops half its subsets
    ptests = ri.load_qb_tests("powerset")
    print("TASK 1  request: 'powerset doesn't return all subsets'")
    tr = []
    kind, ok, out = solve({"entity": "powerset", "tests": ptests}, CODEBASE, tr)
    for s in tr: print("   " + s)
    print("   =>", "SOLVED" if ok else "unsolved", "|",
          [l.strip() for l in (out or "").splitlines() if "return" in l and "+" in l][:1], "\n")

    # TASK 2 — FEATURE: product_list does NOT exist; drafted from sum_list by analogy+synthesis
    print("TASK 2  request: 'add product_list, like sum_list but multiplies'")
    spec = [([2, 3, 4], 24), ([], 1), ([5], 5), ([2, 2, 2], 8)]
    tr = []
    kind, ok, out = solve({"entity": "product_list", "confirm_examples": spec}, CODEBASE, tr)
    for s in tr: print("   " + s)
    print("   => drafted feature:", (out or "").replace("\n", "  "))
    print(f"   => {'VERIFIED' if ok else 'FAILED'}")

    print("\n=== same locate->(miss?)->retrieve->project->verify path; only the analogue source and")
    print("    the feature's human-confirmed spec differ. Widen the analogue source = new capability. ===")
