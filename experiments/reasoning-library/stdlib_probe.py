"""Is stdlib's failure a GENUINE coverage gap or a top-K / narrow-extractor artifact?
(a) attempt transfer from ALL 6794 stdlib funcs (not top-50);
(b) count the BROADER idiom: any func whose OWN recursive-call result is an operand of `+`
    (concatenate-the-recursive-result), regardless of comprehension form;
(c) time it, so we can say whether we ever 'bail'."""
import os, ast, time, json
import reasoner_code as rc, reasoner_analog as ra, stdlib_corpus as sc

def load_qb_tests(name):
    T = []
    for line in open(os.path.expanduser(f"~/quixbugs/json_testcases/{name}.json")):
        line = line.strip()
        if not line: continue
        o = json.loads(line); inp, exp = o[0], o[1]
        if not isinstance(inp, list): inp = [inp]
        T.append((inp, exp))
    return T

def verify(tree, name, tests):
    try: c = compile(ast.fix_missing_locations(tree), "<cand>", "exec")
    except Exception: return False
    return all(rc.run_one(c, name, i, e)[0] for i, e in tests)

def rec_concat(src):
    """True if the function concatenates its OWN recursive result via `+` (broad union idiom)."""
    try: t = ast.parse(src)
    except Exception: return False
    f = next((n for n in ast.walk(t) if isinstance(n, ast.FunctionDef)), None)
    if not f: return False
    fn = f.name
    recvar = None
    for n in ast.walk(t):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) \
           and isinstance(n.value.func, ast.Name) and n.value.func.id == fn \
           and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            recvar = n.targets[0].id
    def is_rec(x):
        return (isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == fn) \
            or (recvar and isinstance(x, ast.Name) and x.id == recvar)
    for n in ast.walk(t):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add) and (is_rec(n.left) or is_rec(n.right)):
            return True
    return False

if __name__ == "__main__":
    name = "powerset"; tests = load_qb_tests(name)
    buggy = open(os.path.expanduser(f"~/quixbugs/python_programs/{name}.py")).read()
    btree = ast.parse(buggy)
    t0 = time.time()
    allfuncs = list(sc.iter_funcs())
    print(f"indexed {len(allfuncs)} stdlib funcs in {time.time()-t0:.1f}s\n")

    # (a) transfer from ALL funcs
    t1 = time.time(); n_cand = 0; solved = None
    for aname, asrc in allfuncs:
        cands = list(ra.transfer_candidates(btree, asrc))
        n_cand += len(cands)
        for desc, cand in cands:
            if verify(cand, name, tests): solved = (aname, desc); break
        if solved: break
    print(f"(a) transfer attempted from ALL {len(allfuncs)} funcs in {time.time()-t1:.1f}s "
          f"(NOT a time-bail): candidates={n_cand}, solved={solved}")

    # (b) broader idiom coverage
    t2 = time.time(); hits = [a for a, s in allfuncs if rec_concat(s)]
    print(f"(b) stdlib funcs that concatenate their OWN recursive result via '+': {len(hits)}")
    for h in hits[:15]: print(f"      {h}")
    print(f"    (scanned in {time.time()-t2:.1f}s)")

    print(f"\nVERDICT: {'GENUINE coverage gap' if not solved else 'solvable'} — "
          f"{'0' if not hits else len(hits)} stdlib funcs even do the broad union idiom, "
          f"so it is NOT a top-K or time artifact.")
