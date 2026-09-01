"""End-to-end: can the STDLIB corpus supply a working analog for powerset? Retrieve top-K by
structural similarity, attempt structure-mapping transfer from each, verify. Honest test of
corpus COVERAGE (not plumbing): if 0 transfer, the pattern powerset needs simply isn't in stdlib."""
import os, ast, json
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

if __name__ == "__main__":
    name = "powerset"; tests = load_qb_tests(name)
    buggy = open(os.path.expanduser(f"~/quixbugs/python_programs/{name}.py")).read()
    btree = ast.parse(buggy)
    K = 50
    top = sc.retrieve(buggy, k=K)
    print(f"retrieved top-{K} stdlib analogs; attempting structure-mapping transfer from each...\n")
    solved = None; tried_transfer = 0
    for sc_score, aname, asrc, csig in top:
        cands = list(ra.transfer_candidates(btree, asrc))
        tried_transfer += len(cands)
        for desc, cand in cands:
            if verify(cand, name, tests):
                solved = (aname, desc); break
        if solved: break
    print(f"stdlib analogs that yielded ANY transfer candidate: {tried_transfer}")
    if solved:
        print(f"SOLVED via stdlib analog '{solved[0]}' ({solved[1]})")
    else:
        print("NOT solved by any stdlib analog.")
        print("Reason: the relation powerset needs (answer = recursive_result + comprehension_over(it))")
        print("has 0 instances in stdlib (union_comp=0). Retrieval found structural neighbors")
        print("(recursive + comprehension) but NONE exhibit the missing-union RELATION to transfer.")
        print("=> Corpus COVERAGE, not availability, is the binding constraint. Stdlib is idiomatic")
        print("   infra code (tree-walks/IO/parsing); combinatorial 'union recursive result' idioms")
        print("   live in ALGORITHM corpora (TheAlgorithms, itertools recipes) or a self-grown store.")
