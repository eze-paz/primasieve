"""Anti-unification INTERPOLATION — the upgrade from template-copy to reasoning, ZERO LLM.

The earlier analog transfer (reasoner_analog.py) required the analog to already have the fix in
almost the target's shape (a union-comprehension) — that's lookup+rename, not interpolation.
Here we INTERPOLATE across the surface gap:

  1. from the analog, extract only the RELATIONAL FRAME around its recursive result:
     e.g. get_class_members does `ret = ret + get_class_members(base)`  =>  frame `HOLE + REC`
     (the recursive result is one operand of `+`; the OTHER operand is abstracted to a HOLE).
  2. instantiate the frame in the TARGET with the target's own recursive result, and FILL the
     hole with the target's own material (its current answer expression / in-scope exprs).
     Both operand orders are tried; the TESTS disambiguate.
  3. verify.

So a plain-variable analog (`ret + recurse`) can repair a comprehension target
(`[comprehension] + rest_subsets`) — different surfaces, same relation. The analog's job is to
PRUNE synthesis to "REC is an operand of +, fill one hole"; the verifier resolves the residue.
That is reason + verify, not corpus lookup.
"""
import os, ast, copy, json
import reasoner_code as rc
from reasoner_analog import func_of, rec_result_var, comp_over

TESTS = []

# ---------- analog side: extract relational frames around the recursive result ----------
def rec_exprs(tree, fname):
    """Recursive-result expressions: calls fname(...) and vars assigned from them."""
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == fname]
    rv = rec_result_var(tree, fname)
    return calls, rv

def is_rec_operand(node, fname, rv):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == fname: return True
    if rv and isinstance(node, ast.Name) and node.id == rv: return True
    return False

def extract_frames(analog_src):
    """Return list of ('binop', op_class, side) frames: the recursive result is an operand of a
    binary op; the other operand is a HOLE. side = which side REC sits on in the analog."""
    try: t = ast.parse(analog_src)
    except Exception: return []
    f = func_of(t)
    if f is None: return []
    fname = f.name; _, rv = rec_exprs(t, fname); frames = []
    for n in ast.walk(t):
        if isinstance(n, ast.BinOp):
            if is_rec_operand(n.left, fname, rv):  frames.append(("binop", type(n.op), "left"))
            if is_rec_operand(n.right, fname, rv): frames.append(("binop", type(n.op), "right"))
    # dedupe
    return list({fr for fr in frames})

# ---------- target side: instantiate the frame, fill the hole, verify ----------
def target_answer(tree, fname):
    """The target's main (non-base-case) answer expression + its Return node."""
    rv = rec_result_var(tree, fname)
    rets = [n for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value is not None]
    # prefer the return whose value mentions the recursive result
    def mentions_rec(r):
        for x in ast.walk(r.value):
            if (rv and isinstance(x, ast.Name) and x.id == rv) or \
               (isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == fname): return True
        return False
    cand = [r for r in rets if mentions_rec(r)]
    if cand: return cand[0], rv
    # else the most complex return
    return (max(rets, key=lambda r: len(ast.dump(r.value))) if rets else None), rv

def interpolate(buggy_src, analog_src):
    """Yield (desc, candidate_tree) interpolations of the analog's frame into the target."""
    bt = ast.parse(buggy_src); bf = func_of(bt); fname = bf.name
    ret, rv = target_answer(bt, fname)
    if ret is None or rv is None: return
    frames = extract_frames(analog_src)
    E = ret.value                                   # target's current answer expr (the hole-filler)
    # hole candidates: the current answer expr, and each in-scope simple name
    holes = [("answer-expr", E)]
    for nm in sorted({n.id for n in ast.walk(bt) if isinstance(n, ast.Name)}):
        if nm != rv: holes.append((nm, ast.Name(id=nm, ctx=ast.Load())))
    for kind, opcls, side in frames:
        for hdesc, hexpr in holes:
            for order in ("REC+HOLE", "HOLE+REC"):    # tests disambiguate order
                t2 = ast.parse(buggy_src); f2 = func_of(t2)
                ret2, rv2 = target_answer(t2, f2.name)
                REC = ast.Name(id=rv2, ctx=ast.Load()); H = copy.deepcopy(hexpr)
                new = ast.BinOp(left=REC, op=opcls(), right=H) if order == "REC+HOLE" \
                      else ast.BinOp(left=H, op=opcls(), right=REC)
                ret2.value = ast.copy_location(new, ret2.value)
                yield (f"frame {opcls.__name__}[{side}] filled hole={hdesc} as {order}",
                       ast.fix_missing_locations(t2))

def verify(tree, name):
    try: c = compile(ast.fix_missing_locations(tree), "<cand>", "exec")
    except Exception: return False
    return all(rc.run_one(c, name, i, e)[0] for i, e in TESTS)

def solve(name, buggy_src, analog_src, analog_name):
    for desc, cand in interpolate(buggy_src, analog_src):
        if verify(cand, name):
            return True, desc, ast.unparse(cand)
    return False, None, None

def load_qb_tests(name):
    T = []
    for line in open(os.path.expanduser(f"~/quixbugs/json_testcases/{name}.json")):
        line = line.strip()
        if not line: continue
        o = json.loads(line); inp, exp = o[0], o[1]
        if not isinstance(inp, list): inp = [inp]
        T.append((inp, exp))
    return T

def get_stdlib_func(module, funcname):
    import sysconfig
    src = open(os.path.join(sysconfig.get_path("stdlib"), module), encoding="utf-8").read()
    t = ast.parse(src); lines = src.splitlines()
    for n in ast.walk(t):
        if isinstance(n, ast.FunctionDef) and n.name == funcname:
            import textwrap
            return textwrap.dedent("\n".join(lines[n.lineno-1:n.end_lineno]))
    return None

if __name__ == "__main__":
    print("=== ANTI-UNIFICATION INTERPOLATION (zero-LLM): can a REAL stdlib analog, of a totally")
    print("    different surface, repair powerset by frame-transfer + hole-filling? ===\n")

    TESTS = load_qb_tests("powerset")
    buggy = open(os.path.expanduser("~/quixbugs/python_programs/powerset.py")).read()

    # THE genuine test: get_class_members combines a plain VARIABLE (ret + recurse); powerset needs
    # to combine a COMPREHENSION. Different surface, same relation. No curation — real stdlib source.
    gcm = get_stdlib_func("rlcompleter.py", "get_class_members")
    print("analog = rlcompleter.get_class_members (real stdlib):")
    print("   " + "\n   ".join(gcm.strip().splitlines()) + "\n")
    print("   frames extracted:", extract_frames(gcm))
    ok, desc, fixed = solve("powerset", buggy, gcm, "get_class_members")
    print(f"\n   RESULT: {'SOLVED' if ok else 'unsolved'}   {desc or ''}")
    if ok:
        print("   fix:", [l for l in fixed.splitlines() if "return" in l and "+" in l][:1])

    print("\n--- control: does interpolation from get_class_members generalize to the strings probe? ---")
    def _ref(cs):
        if cs:
            h, *t = cs; s = _ref(t); return s + [h + x for x in s]
        return ['']
    TESTS = [([list("ab")], _ref(list("ab"))), ([list("abc")], _ref(list("abc"))), ([[]], _ref([]))]
    prefixed = ("def prefixed(chars):\n    if chars:\n        head, *tail = chars\n"
                "        sub = prefixed(tail)\n        return [head + s for s in sub]\n    else:\n        return ['']\n")
    ok2, desc2, _ = solve("prefixed", prefixed, gcm, "get_class_members")
    print(f"   prefixed: {'SOLVED' if ok2 else 'unsolved'}   {desc2 or ''}")
    print(f"\n=== interpolation from a plain-variable stdlib analog: powerset {'OK' if ok else 'X'}, "
          f"prefixed {'OK' if ok2 else 'X'} — the analog's SURFACE differs, only the RELATION transfers ===")
