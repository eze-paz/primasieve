"""NON-UNIFORM CROSS-DOMAIN test (owner's follow-up): a real CODE bug whose per-site fix depends on
that site's OWN attribute — the integration-shaped claim, but in code. Weighted sum:

    buggy:   def f(a): return a[0]*w0 + a[1]*w1 + a[2]*w2 + ...
    correct: the weight at index i should be (w_i + i)  ->  NON-uniform (site 0:+0, site 1:+1, ...)

Two cross-referenced attributes per site: weight w and index i; fix new_w = w + i. The SAME math
frame grammar (meta_param.frame_grammar / discover_relation) must discover it with ZERO changes
(mapping w->coeff slot, i->exp slot). Bootstrap uses a generic linear hole-fit primitive (same class
as FitTemplate — a tool, not a frame edit). Multi-site is FLAT (fixing one weight can't pass while
others are wrong) so primitives WALL; the discovered parametric op rewrites every site by its own i.
ZERO LLM."""
import ast, copy, os, sys, random
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("META_GLOBAL", "8000")
from meta_forms import MetaState
from meta_reason import solve_ucb
import meta_param as MP

AVECS = [[1.3, 0.7, 2.1, 1.9, 0.4, 2.6, 1.1, 0.9],      # verify vectors (disjoint from the fit vector)
         [2.2, 1.1, 0.5, 3.0, 1.7, 0.8, 2.3, 1.4],
         [0.6, 2.4, 1.8, 0.9, 2.7, 1.2, 0.3, 2.0],
         [1.9, 0.5, 2.9, 1.1, 0.8, 2.2, 1.6, 0.7]]
AVEC_FIT = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]     # a distinct vector used only for hole-fitting

def gen_weight_bug(rng, k):
    ws = [rng.randint(2, 9) for _ in range(k)]
    body = lambda W: " + ".join(f"a[{i}]*{w}" for i, w in enumerate(W))
    src = f"def f(a):\n    return {body(ws)}"
    corr = [w + i for i, w in enumerate(ws)]
    ns = {}; exec(f"def g(a):\n    return {body(corr)}", ns)
    tests = [([v], ns["g"](v)) for v in AVECS + [AVEC_FIT]]
    return {"src": src, "tests": tests, "ws": ws, "k": k}

def parse_sites(tree):
    """Each addend a[i]*w -> (weight w, index i, walk-index of the weight Constant)."""
    ret = next(n for n in ast.walk(tree) if isinstance(n, ast.Return)).value
    def addends(n):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add): return addends(n.left) + addends(n.right)
        return [n]
    idx_of = {id(n): wi for wi, n in enumerate(ast.walk(tree))}
    out = []
    for a in addends(ret):
        if isinstance(a, ast.BinOp) and isinstance(a.op, ast.Mult):
            sub = a.left if isinstance(a.left, ast.Subscript) else (a.right if isinstance(a.right, ast.Subscript) else None)
            wc = a.right if isinstance(a.right, ast.Constant) else (a.left if isinstance(a.left, ast.Constant) else None)
            if sub is not None and wc is not None and isinstance(sub.slice, ast.Constant):
                out.append((wc.value, sub.slice.value, idx_of[id(wc)]))
    return out

def _eval_code(tree, avec):
    try:
        code = compile(ast.fix_missing_locations(tree), "<c>", "exec"); ns = {}
        exec(code, ns); return ns["f"](avec)
    except Exception: return None

class CodeFitWeight:
    """GENERIC linear hole-fit (same class as FitTemplate): fit ONE weight constant from a sample
    vector, verify on disjoint vectors. Solves single-site; can't jointly fit non-uniform multi-site."""
    name = "CODE_FIT_W"; cost_hint = 3.0
    def _key(self, st): return ("CFITW", st._th())
    def applicable(self, st): return not st.solved() and st._cache.get(self._key(st)) is None
    def run(self, st, budget):
        before = st.best; best = (before, None, None, None); tried = 0
        tgtf = next((e for (v,), e in st.tests if v == AVEC_FIT), None)
        for (w, i, cidx) in parse_sites(st.tree):
            if tried >= budget or tgtf is None: break
            t0 = MP._set_const(st.tree, cidx, 0.0); t1 = MP._set_const(st.tree, cidx, 1.0)
            a0, b0 = _eval_code(t0, AVEC_FIT), _eval_code(t1, AVEC_FIT)
            if a0 is None or b0 is None or abs(b0 - a0) < 1e-12: continue
            wv = (tgtf - a0) / (b0 - a0)
            t2 = MP._set_const(st.tree, cidx, wv)
            if t2 is None: continue
            tried += 1; st.units += 1; nf, susp2 = st._score(t2)
            if nf < best[0]: best = (nf, t2, susp2, f"FITW[{i}]={wv}")
            if nf == 0: break
        st._cache[self._key(st)] = True
        if best[1] is not None and best[0] < before:
            st.tree, st.susp, st.best = best[1], best[2], best[0]; st.log.append((self.name, before, best[0]))
            return {"form": self.name, "tried": tried, "before": before, "after": best[0],
                    "improved": True, "solved": best[0] == 0, "exhausted": False, "fix": best[3]}
        return {"form": self.name, "tried": tried, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}

class CodeStructParam:
    """DISCOVERED non-uniform parametric op: rewrite EVERY site's weight by frame(w,i) using that site's
    OWN index i. The genuine cross-domain analog of STRUCT_PARAM (integration)."""
    cost_hint = 1.0
    def __init__(self, fn, label): self.fn = fn; self.name = f"CODE_STRUCT_PARAM[w'={label}]"
    def _key(self, st): return ("CSPARAM", st._th())
    def applicable(self, st): return not st.solved() and st._cache.get(self._key(st)) is None
    def run(self, st, budget):
        before = st.best; t = copy.deepcopy(st.tree); sites = parse_sites(t); hits = 0
        # re-parse on the copy to get its own constant nodes
        for (w, i, cidx) in parse_sites(t):
            for wi, n in enumerate(ast.walk(t)):
                if wi == cidx and isinstance(n, ast.Constant):
                    n.value = self.fn(w, i); hits += 1
        st._cache[self._key(st)] = True
        if hits:
            t = ast.fix_missing_locations(t); st.units += 1; nf, susp2 = st._score(t)
            if nf == 0:
                st.tree, st.susp, st.best = t, susp2, nf; st.log.append((self.name, before, nf))
                return {"form": self.name, "tried": 1, "before": before, "after": nf,
                        "improved": True, "solved": True, "exhausted": False, "fix": self.name}
        return {"form": self.name, "tried": 1, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}

def discover(seed_rng):
    """WAKE: CodeFitWeight solves single-site -> (w,i)->(new_w,i) traces. SLEEP: SAME math grammar
    (w->coeff slot, i->exp slot) discovers new_w = w + i with ZERO changes."""
    traces = []
    for _ in range(6):
        w = seed_rng.randint(2, 9); i = seed_rng.randint(1, 6)     # i>=1 so the fix is non-trivial
        src = f"def f(a):\n    return a[{i}]*{w}"
        ns = {}; exec(f"def g(a):\n    return a[{i}]*{w + i}", ns)
        tests = [([v], ns["g"](v)) for v in AVECS + [AVEC_FIT]]
        st = MetaState("f", src, tests); d = CodeFitWeight().run(st, 50)
        if d["solved"]:
            s = parse_sites(st.tree)
            if s: traces.append(((w, i), (round(s[0][0]), i)))     # (w,i)->(new_w,i); map w->coeff,i->exp
    rel = MP.discover_relation(traces, 0)                          # SAME grammar as math
    op = CodeStructParam(rel[2], rel[0]) if rel else None
    return op, (rel[0] if rel else None), traces

if __name__ == "__main__":
    print("=== NON-UNIFORM CODE FAMILY: a[i]*w -> a[i]*(w+i), per-site index-dependent ===")
    op, label, traces = discover(random.Random(7))
    print(f"  single-site traces (w,i)->(w',i): {traces}")
    print(f"  discovered weight rule (SAME math grammar, 0 changes): w' = {label}  -> "
          f"{'CRYSTALLIZED' if op else 'FAILED'}\n")
    rng = random.Random(555)
    print(f"  {'k':>2s}  {'primitives':>10s}  {'+discovered':>11s}   (per-site fix differs by index = NON-uniform)")
    for k in (2, 3, 4, 6, 8):
        t = gen_weight_bug(rng, k)
        okP, enP, _ = solve_ucb("f", t["src"], t["tests"], [], extra_forms=(CodeFitWeight(),))
        okD, enD, _ = solve_ucb("f", t["src"], t["tests"], [], extra_forms=((op,) if op else ()) + (CodeFitWeight(),))
        print(f"  {k:>2d}  {('Y' if okP else 'n')+f'({enP})':>10s}  {('Y' if okD else 'n')+f'({enD})':>11s}")
    print("\n(single-site solvable by generic linear fit; NON-uniform multi-site walls for primitives;"
          "\n the discovered op applies each site's OWN index = the parametric class holds in a real code bug.)")
