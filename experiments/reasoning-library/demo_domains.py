"""Two UNRELATED domains through the SAME projection_core.solve — proving the reasoner is
coding-agnostic. Domain A = Python code (AST + test oracle). Domain B = arithmetic expressions
(nested tuples + numeric oracle): no programs, no control flow, no recursion. Identical core."""
import os, ast, copy, json, textwrap, sysconfig
from projection_core import Term, solve
import reasoner_code as rc

OPMAP_AST = {"Add": ast.Add, "Sub": ast.Sub, "Mult": ast.Mult, "Div": ast.Div, "Mod": ast.Mod,
             "FloorDiv": ast.FloorDiv, "BitOr": ast.BitOr, "BitAnd": ast.BitAnd, "BitXor": ast.BitXor}
OPMAP_ARITH = {"Mult": "*", "Add": "+", "Sub": "-", "Div": "/"}

# ============================ Domain A: Python code ============================
def _func(tree): return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
def _rv(tree, fn):
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) \
           and n.value.func.id == fn and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            return n.targets[0].id
    return None
def _is_rec(node, fn, rv):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == fn) \
        or (rv and isinstance(node, ast.Name) and node.id == rv)
def _answer_ret(tree, fn, rv):
    rets = [n for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value is not None]
    def mentions(r):
        return any(_is_rec(x, fn, rv) for x in ast.walk(r.value))
    m = [r for r in rets if mentions(r)]
    return (m[0] if m else max(rets, key=lambda r: len(ast.dump(r.value)))) if rets else None

class DomainCode:
    def __init__(self, buggy_src, tests, corpus_srcs):
        self.buggy = buggy_src; self.tests = tests; self._corpus = corpus_srcs
    def corpus(self): return list(self._corpus.items())
    def to_terms(self, analog_src):
        t = ast.parse(analog_src); fn = _func(t).name; rv = _rv(t, fn); out = []
        for n in ast.walk(t):
            if isinstance(n, ast.BinOp):
                op = type(n.op).__name__
                ch = [Term(label="x", anchor=_is_rec(n.left, fn, rv)),
                      Term(label="x", anchor=_is_rec(n.right, fn, rv))]
                out.append(Term("Bin:" + op, ch))
        return out
    def build_candidates(self, op):
        if op not in OPMAP_AST: return
        t = ast.parse(self.buggy); fn = _func(t).name; rv = _rv(t, fn)
        if rv is None: return
        ret = _answer_ret(t, fn, rv)
        for order in ("REC+HOLE", "HOLE+REC"):
            t2 = ast.parse(self.buggy); fn2 = _func(t2).name; rv2 = _rv(t2, fn2)
            ret2 = _answer_ret(t2, fn2, rv2)
            REC = ast.Name(id=rv2, ctx=ast.Load()); HOLE = copy.deepcopy(ret2.value)
            new = ast.BinOp(left=REC, op=OPMAP_AST[op](), right=HOLE) if order == "REC+HOLE" \
                  else ast.BinOp(left=HOLE, op=OPMAP_AST[op](), right=REC)
            ret2.value = ast.copy_location(new, ret2.value)
            yield order, ast.fix_missing_locations(t2)
    def verify(self, tree):
        try: c = compile(tree, "<cand>", "exec")
        except Exception: return False
        name = _func(tree).name
        return all(rc.run_one(c, name, i, e)[0] for i, e in self.tests)
    def render(self, tree):
        return next(l.strip() for l in ast.unparse(tree).splitlines() if "return" in l and " + " in l or " * " in l) \
            if False else ast.unparse(tree)

# ============================ Domain B: arithmetic ============================
def arith_eval(e, env):
    if isinstance(e, tuple):
        o, a, b = e; a, b = arith_eval(a, env), arith_eval(b, env)
        return {"*": a*b, "+": a+b, "-": a-b, "/": a/b}[o]
    return env[e] if isinstance(e, str) and e in env else float(e)
def arith_str(e):
    return f"({arith_str(e[1])} {e[0]} {arith_str(e[2])})" if isinstance(e, tuple) else str(e)

class DomainArith:
    def __init__(self, buggy, anchor, oracle, corpus):
        self.buggy = buggy; self.anchor = anchor; self.oracle = oracle; self._corpus = corpus
    def corpus(self): return list(self._corpus.items())
    def _to_term(self, e, anchorvar):
        if isinstance(e, tuple):
            lbl = {"*": "Mult", "+": "Add", "-": "Sub", "/": "Div"}[e[0]]
            return Term("Bin:" + lbl, [self._to_term(e[1], anchorvar), self._to_term(e[2], anchorvar)])
        return Term(label="leaf", anchor=(e == anchorvar))
    def to_terms(self, analog):
        expr, anchorvar = analog
        return [self._to_term(expr, anchorvar)]
    def build_candidates(self, op):
        if op not in OPMAP_ARITH: return
        o = OPMAP_ARITH[op]
        for cand in ((o, self.anchor, self.buggy), (o, self.buggy, self.anchor)):
            yield ("REC" + o + "HOLE"), cand
    def verify(self, cand):
        for env, expected in self.oracle:
            try:
                if abs(arith_eval(cand, env) - expected) > 1e-9: return False
            except Exception: return False
        return True
    def render(self, cand): return arith_str(cand)

# ============================ demos ============================
def load_qb_tests(name):
    T = []
    for line in open(os.path.expanduser(f"~/quixbugs/json_testcases/{name}.json")):
        line = line.strip()
        if not line: continue
        o = json.loads(line); inp, exp = o[0], o[1]
        if not isinstance(inp, list): inp = [inp]
        T.append((inp, exp))
    return T
def stdlib_func(module, funcname):
    src = open(os.path.join(sysconfig.get_path("stdlib"), module), encoding="utf-8").read()
    t = ast.parse(src); lines = src.splitlines()
    for n in ast.walk(t):
        if isinstance(n, ast.FunctionDef) and n.name == funcname:
            return textwrap.dedent("\n".join(lines[n.lineno-1:n.end_lineno]))

if __name__ == "__main__":
    print("=== SAME projection_core.solve over two UNRELATED domains ===\n")

    print("DOMAIN A — Python code: repair powerset")
    tests = load_qb_tests("powerset")
    buggy = open(os.path.expanduser("~/quixbugs/python_programs/powerset.py")).read()
    domA = DomainCode(buggy, tests, {"rlcompleter.get_class_members": stdlib_func("rlcompleter.py", "get_class_members")})
    outA, metaA = solve(domA)
    print("  fix:", [l.strip() for l in (outA or "").splitlines() if "rest_subsets +" in l or "+ rest_subsets" in l][:1], "\n")

    print("DOMAIN B — arithmetic (no programs/control-flow/recursion): repair area = pi*r  ->  pi*r*r")
    # buggy formula pi*r ; anchor variable 'r' ; oracle = area of circle pi*r^2 at sample radii
    import math
    buggy_expr = ("*", "pi", "r")
    oracle = [({"pi": math.pi, "r": r}, math.pi * r * r) for r in (1.0, 2.0, 3.5)]
    # analog: kinetic energy k*x*x (anchor x) — totally different quantity, same 'scale by the var' relation
    corpus = {"kinetic_energy k*x*x": (("*", ("*", "k", "x"), "x"), "x"),
              "decoy linear a*x": (("*", "a", "x"), "x")}
    domB = DomainArith(buggy_expr, "r", oracle, corpus)
    outB, metaB = solve(domB)
    print(f"  fix: area = {outB}")

    print(f"\n=== one core, two domains: code {'OK' if outA else 'X'} | arithmetic {'OK' if outB else 'X'} "
          f"— the reasoner never mentions 'code' ===")
