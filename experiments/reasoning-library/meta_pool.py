"""P2/#1 — EXPERIENCE ENGINE: generate a large, difficulty-diverse pool of synthetic bugs by
mutating CORRECT programs (each mutation = a bug with a known a-priori class). Breaks the
data-starvation that refuted S2. Held-out = the REAL QuixBugs bugs (different distribution).
ZERO LLM. Leakage-safe: synthetic bugs come from correct sources; the a-priori signature never
sees the fix."""
import os, ast, random, json
import reasoner_code as rc

QB = os.path.expanduser("~/quixbugs")

def load_tests(name):
    T = []
    for line in open(f"{QB}/json_testcases/{name}.json"):
        line = line.strip()
        if not line: continue
        o = json.loads(line); inp, exp = o[0], o[1]
        if not isinstance(inp, list): inp = [inp]
        T.append((inp, exp))
    return T

def _nfail(src, name, tests):
    try: code = compile(ast.fix_missing_locations(ast.parse(src)) if isinstance(src, str) else src, "<c>", "exec")
    except Exception: return None
    nf = 0
    for inp, exp in tests:
        ok, _ = rc.run_one(code, name, inp, exp)
        if not ok: nf += 1
    return nf

def mutate(tree, k, rng):
    """Apply ONE random edit introduced at stratum k. Returns new tree or None."""
    edits = [e for e in rc.enumerate_edits(tree, k) if e[0] == k]
    rng.shuffle(edits)
    for s, ln, desc, idx, ka in edits:
        t2 = rc.apply_edit(tree, idx, ka)
        if t2 is not None: return t2, ka[0]
    return None, None

def _clean(src):
    """Drop module-level docstrings/string-literal statements (QuixBugs files trail example code
    in a triple-quoted string; round-tripping them mangles the module). Keep real code only."""
    t = ast.parse(src)
    t.body = [n for n in t.body
              if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                      and isinstance(n.value.value, str))]
    return t

def synth_bugs(name, correct_src, tests, rng, per_program=9):
    """Difficulty spectrum: single stratum-0 (easy), single stratum-1 (medium), double (compose)."""
    base = _clean(correct_src); bugs = []
    plan = [(0, "s0"), (0, "s0"), (0, "s0"), (1, "s1"), (1, "s1"),
            (1, "s1"), ("dd", "compose"), ("dd", "compose"), ("dd", "compose")]
    for i, (kind, tag) in enumerate(plan[:per_program]):
        if kind == "dd":
            t1, k1 = mutate(base, 0, rng)
            if t1 is None: continue
            t2, k2 = mutate(t1, rng.choice([0, 1]), rng)
            mut = t2; cls = "compose"
        else:
            t2, cls = mutate(base, kind, rng); mut = t2
        if mut is None: continue
        try: src2 = ast.unparse(ast.fix_missing_locations(mut))
        except Exception: continue
        nf = _nfail(src2, name, tests)
        if nf is None or nf == 0 or nf == len(tests):   # must break SOME (not none, not all)
            continue
        bugs.append({"id": f"{name}#{tag}{i}", "src": src2, "tests": tests,
                     "class": tag, "mut_kind": cls, "nfail0": nf})
    return bugs

def build_pool(rng, per_program=9):
    names = sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))
    train, holdout = [], []
    for name in names:
        tests = load_tests(name)
        csrc = open(f"{QB}/correct_python_programs/{name}.py").read()
        try: ccode = compile(csrc, "<c>", "exec")
        except Exception: continue
        if not all(rc.run_one(ccode, name, i, e)[0] for i, e in tests): continue
        # TRAIN = synthetic bugs from the correct source
        train += synth_bugs(name, csrc, tests, rng, per_program)
        # HOLDOUT = the REAL seeded QuixBugs bug (different distribution, never used for training)
        bsrc = open(f"{QB}/python_programs/{name}.py").read()
        holdout.append({"id": name, "src": bsrc, "tests": tests, "class": "real", "mut_kind": "real"})
    return train, holdout

if __name__ == "__main__":
    rng = random.Random(0)
    train, holdout = build_pool(rng)
    from collections import Counter
    print(f"TRAIN synthetic bugs: {len(train)}   HOLDOUT real bugs: {len(holdout)}")
    print("train by class:", dict(Counter(b['class'] for b in train)))
    print("train by baseline nfail:", dict(Counter(min(b['nfail0'],5) for b in train)))
    json.dump({"n_train": len(train), "n_holdout": len(holdout),
               "by_class": dict(Counter(b['class'] for b in train))},
              open("meta_pool_stats.json", "w"), indent=1)
