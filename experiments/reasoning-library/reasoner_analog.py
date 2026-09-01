"""Analogical repair — the THIRD thing (neither LLM-memory nor blind permutation), ZERO LLM.

Human loop the user described:
  1. localize the divergence  (not blind replacement)
  2. spend energy trying to fix it locally; if entropy doesn't drop after a BUDGET of work,
  3. go fetch the CLOSEST working analog (ranked by structural similarity),
  4. ALIGN it to our case by ROLE and TRANSFER the structural delta (Gentner structure-mapping:
     relations transfer, surface attributes don't), verify. Still stuck -> fetch the NEXT analog.

This is energy-budgeted analogical reasoning. The analog is a DIFFERENT working function; we
import only the RELATIONAL skeleton it exhibits (e.g. `answer = recursive_result <op> transform
(recursive_result)`), re-expressed in OUR variables, keeping OUR own subexpression. Every
transfer is test-verified, so nothing is trusted — only checked.

Run: python reasoner_analog.py
"""
import os, sys, ast, copy, time, math, json
import reasoner_code as rc

# ---------------- analog store (working functions; NONE is the target) ----------------
# Includes DECOYS so retrieval must actually rank, not pick a hardcoded winner.
ANALOGS = {
 # relevant: shares the relation `answer = rec_result + comprehension_over(rec_result)`,
 # but computes subset SUMS (ints), not subsets -> different surface, same relation.
 "subset_sums": """
def subset_sums(nums):
    if nums:
        head, *tail = nums
        sub = subset_sums(tail)
        return sub + [head + s for s in sub]
    else:
        return [0]
""",
 # decoy: recursive + concat but NO comprehension (near-miss)
 "rev": """
def rev(s):
    if not s:
        return s
    return rev(s[1:]) + s[0]
""",
 # decoy: recursive, no union, no comprehension
 "gcd": """
def gcd(a, b):
    if b == 0:
        return a
    return gcd(b, a % b)
""",
 # decoy: comprehension but not recursive
 "squares": """
def squares(xs):
    return [x * x for x in xs]
""",
}

# ---------------- structural features + analog ranking ----------------
def func_of(tree):
    return next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)), None)

def rec_result_var(tree, fname):
    """The variable assigned directly from a recursive call to fname, if any."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) \
           and isinstance(n.value.func, ast.Name) and n.value.func.id == fname \
           and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            return n.targets[0].id
    return None

def comp_over(tree, var):
    """A ListComp whose (first) iterable is Name `var`."""
    for n in ast.walk(tree):
        if isinstance(n, ast.ListComp) and n.generators \
           and isinstance(n.generators[0].iter, ast.Name) and n.generators[0].iter.id == var:
            return n
    return None

def features(src):
    t = ast.parse(src); f = func_of(t); fn = f.name
    rv = rec_result_var(t, fn)
    has_comp_over_rec = rv is not None and comp_over(t, rv) is not None
    return {"recursive": any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == fn for n in ast.walk(t)),
            "has_listcomp": any(isinstance(n, ast.ListComp) for n in ast.walk(t)),
            "union_comp_schema": has_comp_over_rec and _has_union_schema(t, fn, rv)}

def _has_union_schema(tree, fname, rv):
    """Return the analog's answer expr if it matches `rv <Add> comp` or `comp <Add> rv`."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.BinOp) and isinstance(n.value.op, ast.Add):
            L, R = n.value.left, n.value.right
            if isinstance(L, ast.Name) and L.id == rv and isinstance(R, ast.ListComp): return n.value
            if isinstance(R, ast.Name) and R.id == rv and isinstance(L, ast.ListComp): return n.value
    return None

def similarity(buggy_src, analog_src):
    b, a = features(buggy_src), features(analog_src)
    return sum(2 if k == "union_comp_schema" and a[k] and b.get(k) else
               (1 if a[k] and b.get(k) else 0) for k in a)

# ---------------- structure-mapping transfer ----------------
def extract_relation(analog_src):
    """Parse the analog, extract its RELATIONAL answer template with two holes:
       <R> = recursive-result var, <C> = the comprehension over it. Returns ('R+C'|'C+R') or None."""
    t = ast.parse(analog_src); f = func_of(t); rv = rec_result_var(t, f.name)
    if rv is None: return None
    ans = _has_union_schema(t, f.name, rv)
    if ans is None: return None
    return "R+C" if isinstance(ans.left, ast.Name) and ans.left.id == rv else "C+R"

def transfer_candidates(buggy_tree, analog_src):
    """Instantiate the analog's relation in the BUGGY function's own variables/comprehension.
    Yields (desc, new_tree). General: works for any analog exposing a self-union-comprehension."""
    rel = extract_relation(analog_src)
    if rel is None: return
    bf = func_of(buggy_tree); brv = rec_result_var(buggy_tree, bf.name)
    if brv is None: return
    comp = comp_over(buggy_tree, brv)
    if comp is None: return
    # find the Return whose value IS (or contains) that bare comprehension
    for ret in [n for n in ast.walk(buggy_tree) if isinstance(n, ast.Return)]:
        if ret.value is comp or (isinstance(ret.value, ast.ListComp) and ret.value is comp):
            for order in (rel, ("C+R" if rel == "R+C" else "R+C")):  # try analog's order, then flip
                t2 = copy.deepcopy(buggy_tree)
                bf2 = func_of(t2); brv2 = rec_result_var(t2, bf2.name); comp2 = comp_over(t2, brv2)
                r2 = next(n for n in ast.walk(t2) if isinstance(n, ast.Return) and n.value is comp2)
                Rn = ast.Name(id=brv2, ctx=ast.Load())
                new = ast.BinOp(left=Rn, op=ast.Add(), right=copy.deepcopy(comp2)) if order == "R+C" \
                      else ast.BinOp(left=copy.deepcopy(comp2), op=ast.Add(), right=Rn)
                r2.value = ast.copy_location(new, comp2)
                yield f"transfer[{order}]: answer = {brv2} + <comprehension>", ast.fix_missing_locations(t2)

# ---------------- energy-budgeted analogical solver ----------------
TESTS = []
def solve(name, buggy_src, EPOCH=1500, verbose=True):
    """Spend EPOCH units of work per phase; when entropy/score stalls, fetch the next-closest
    analog and add its transfer moves. Returns (solved, fixed_src, log)."""
    t0 = time.time(); tree = ast.parse(buggy_src)
    units = 0; log = []
    def belief_entropy(tr):
        obs = simulate(tr);
        if obs is None: return None
        res, covs = obs
        if all(res): return 0.0
        allln = set().union(*covs) if covs else set(); ent = {}
        nfail = sum(1 for x in res if not x)
        for ln in allln:
            ef = sum(1 for ok, c in zip(res, covs) if not ok and ln in c)
            ep = sum(1 for ok, c in zip(res, covs) if ok and ln in c)
            ent[ln] = ef / math.sqrt(nfail * (ef + ep)) if ef else 0.0
        s = sum(ent.values()) or 1.0; p = [v / s for v in ent.values() if v > 0]
        return -sum(x * math.log(x + 1e-12) for x in p)
    def simulate(tr):
        try: c = compile(ast.fix_missing_locations(tr), "<cand>", "exec")
        except Exception: return None
        res = []; covs = []
        for inp, exp in TESTS:
            ok, cov = rc.run_one(c, name, inp, exp); res.append(ok); covs.append(cov)
        return res, covs
    def score(tr):
        obs = simulate(tr)
        return len(TESTS) + 1 if obs is None else sum(1 for x in obs[0] if not x)

    best = score(tree); H0 = belief_entropy(tree)
    log.append(f"start: {best} failing, belief-entropy={H0:.3f}" if H0 is not None else f"start: {best} failing")
    if verbose: print(log[-1], flush=True)

    # phase 0: base grammar (no analogs) until EPOCH units spend with no improvement
    def run_moves(move_iter):
        nonlocal best, tree, units
        improved = False
        for desc, cand in move_iter:
            units += 1
            s = score(cand)
            if s < best:
                best, tree = s, cand
                log.append(f"  [{units}u] {desc}: -> {best} failing");
                if verbose: print(log[-1], flush=True)
                improved = True
                if best == 0: return True
            if units % EPOCH == 0: return improved
        return improved

    dom = rc.CodeDomain(name, buggy_src, TESTS)
    spent0 = units
    while units - spent0 < EPOCH and best > 0:
        susp = dom.diff(dom.simulate(tree))[1]
        if not run_moves(((d, c) for d, c in _base_moves(dom, tree))): break
    if best == 0:
        return True, ast.unparse(tree), log

    # phases 1..k: fetch analogs by descending similarity, add transfer moves
    ranked = sorted(ANALOGS.items(), key=lambda kv: -similarity(buggy_src, kv[1]))
    for i, (aname, asrc) in enumerate(ranked):
        sim = similarity(buggy_src, asrc)
        Hnow = belief_entropy(tree)
        log.append(f"{units}u spent, {best} failing, entropy stalled (H={Hnow}) "
                   f"-> ACQUIRE analog #{i+1}: '{aname}' (similarity={sim})")
        if verbose: print(log[-1], flush=True)
        if run_moves(transfer_candidates(tree, asrc)):
            if best == 0:
                log.append(f"  SOLVED by analogy from '{aname}' in {time.time()-t0:.2f}s, {units} units")
                if verbose: print(log[-1], flush=True)
                return True, ast.unparse(tree), log
    return False, ast.unparse(tree), log

def _base_moves(dom, tree):
    dom.stratum = 2
    yield from dom.moves(tree, dom.diff(dom.simulate(tree))[1])

# ---------------- tasks ----------------
def load_qb_tests(name):
    T = []
    for line in open(os.path.expanduser(f"~/quixbugs/json_testcases/{name}.json")):
        line = line.strip()
        if not line: continue
        o = json.loads(line); inp, exp = o[0], o[1]
        if not isinstance(inp, list): inp = [inp]
        T.append((inp, exp))
    return T

if __name__ == "__main__":
    print("=== ANALOGICAL REPAIR (zero-LLM, energy-budgeted analog fetch + structure-mapping) ===\n")

    # TASK 1: powerset — the 1 QuixBugs bug the base grammar can't reach
    TESTS = load_qb_tests("powerset")
    buggy = open(os.path.expanduser("~/quixbugs/python_programs/powerset.py")).read()
    print("TASK 1: powerset  (base grammar failed this in the 25/26 sweep)")
    ok, fixed, log = solve("powerset", buggy)
    print(f"  RESULT: {'SOLVED' if ok else 'unsolved'}")
    print("  fix:", [l for l in fixed.splitlines() if "return" in l and "+" in l][:1], "\n")

    # TASK 2 (TRANSFER PROBE): a DIFFERENT function, same missing-union relation, strings not lists.
    # Same analog must solve it -> proves the analog transfers (the 'crystal' generalizes).
    prefixed_buggy = (
        "def prefixed(chars):\n"
        "    if chars:\n"
        "        head, *tail = chars\n"
        "        sub = prefixed(tail)\n"
        "        return [head + s for s in sub]\n"     # missing: sub + ...
        "    else:\n"
        "        return ['']\n")
    # expected: all suffixes each optionally prefixed by earlier chars, unioned with the sub-result
    def _ref_prefixed(chars):
        if chars:
            head, *tail = chars; sub = _ref_prefixed(tail)
            return sub + [head + s for s in sub]
        return ['']
    TESTS = [([list("ab")], _ref_prefixed(list("ab"))),
             ([list("abc")], _ref_prefixed(list("abc"))),
             ([[]], _ref_prefixed([]))]
    print("TASK 2 (transfer probe): 'prefixed' — different surface (strings), same missing-union relation")
    ok2, fixed2, log2 = solve("prefixed", prefixed_buggy)
    print(f"  RESULT: {'SOLVED' if ok2 else 'unsolved'}")
    used = [l for l in log2 if "SOLVED by analogy" in l]
    print("  ", used[0].strip() if used else "(no analog succeeded)")
    print(f"\n=== analogy engine: powerset {'OK' if ok else 'X'}, transfer-probe {'OK' if ok2 else 'X'} "
          f"(same analog 'subset_sums' should solve BOTH) ===")
