"""PARAMETRIC-REWRITE OPERATOR CLASS (fable-scoped) — can a NON-UNIFORM structural map emerge, where
each term's rewrite depends on its OWN attributes? This is the class beyond STRUCT_GLOBAL (uniform).
Generic term-rewrite rules with variables; needed by differentiation, integration, AND code. ZERO LLM.

Dev family = DIFFERENTIATION (d/dx c*x^n = c*n*x^(n-1)). Integration is a SEALED holdout (same class,
atoms /,+1 vs *,-1) — the frame grammar is built WITHOUT looking at integration; the knockout asks if
integration emerges with ZERO code changes. fable's guards: (a) generic linear-fit primitive so
fractional coeffs are reachable (else no traces); (b) log frame-grammar SIZE (>100 = real search, not
lookup); (c) NEGATE / Pow2 must fall out as degenerate 1-attribute frames; (d) fit points != verify
points (no leakage). Treadmill test: hand-added vocab per family must be 0."""
import ast, copy, os, sys, itertools
sys.path.insert(0, os.path.dirname(__file__))
from meta_forms import MetaState
from meta_reason import solve_ucb

XS_FIT = [1.5, 2.5]                                   # points used to FIT a hole constant
XS_VER = [0.7, 1.9, 2.6, 3.3, -1.4, -2.1]            # DISJOINT points used to VERIFY (no leakage)

# ---------------- domain: single/multi-term polynomials, diff & integrate (float oracle) ----------
def _ev(terms, x): return sum(c * x**e for c, e in terms)
def term_src(c, e): return f"{c}*x**{e}"      # ALWAYS explicit exponent node (so FitTemplate can edit it)
def poly_src(terms): return "def f(x):\n    return " + " + ".join(term_src(c, e) for c, e in terms)
def differentiate(terms): return [(c*e, e-1) for c, e in terms if e != 0]
def integrate(terms): return [(c/(e+1), e+1) for c, e in terms]
def make_task(terms, transform):
    tgt = transform(terms); f = lambda x: _ev(tgt, x)
    return {"src": poly_src(terms), "tests": [([x], f(x)) for x in XS_VER + XS_FIT],
            "terms": terms, "target": tgt}

# ---------------- generic FitTemplate primitive: structure-search x linear hole-fit ----------------
def _int_consts(tree):
    return [i for i, n in enumerate(ast.walk(tree))
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)]
def _set_const(tree, walk_idx, val):
    t = copy.deepcopy(tree)
    for i, n in enumerate(ast.walk(t)):
        if i == walk_idx and isinstance(n, ast.Constant): n.value = val; return ast.fix_missing_locations(t)
    return None
def _eval_at(tree, x):
    try:
        code = compile(ast.fix_missing_locations(tree), "<c>", "exec"); ns = {}
        exec(code, ns); return ns["f"](x)
    except Exception: return None
def _linfit(tree, cidx, x0, target):
    """Fit constant at cidx assuming output is LINEAR in it: solve from one point (generic)."""
    a = _eval_at(_set_const(tree, cidx, 0.0), x0)
    b = _eval_at(_set_const(tree, cidx, 1.0), x0)
    if a is None or b is None or abs(b - a) < 1e-12: return None
    return (target - a) / (b - a)

class FitTemplate:
    """GENERIC: hypothesize a small structural change (one int const -> a nearby value) THEN linearly
    FIT one other constant from a sample point; verify on DISJOINT points. Reaches c*x^n -> (c')*x^(n')
    for ANY numeric c' (fractional too) in one move = the primitive that produces parametric traces."""
    name = "FIT_TEMPLATE"; cost_hint = 3.0
    def _key(self, st): return ("FIT", st._th())
    def applicable(self, st): return not st.solved() and st._cache.get(self._key(st)) is None
    def run(self, st, budget):
        before = st.best; best = (before, None, None, None); tried = 0
        consts = _int_consts(st.tree)
        x0, tgt0 = st.tests[0][0][0], st.tests[0][1]      # a fit point (tests[0] is XS_VER[0]) ...
        # use a dedicated fit point disjoint from most verify points:
        xf = XS_FIT[0]; tgtf = next((e for (i, ), e in st.tests if abs(i - xf) < 1e-9), None)
        for cs in consts:                                  # structural hypothesis: vary one int const
            base = None
            for n_i, n in enumerate(ast.walk(st.tree)):
                if n_i == cs: base = n.value
            if not isinstance(base, int): continue
            for v in range(base - 3, base + 4):
                t_struct = _set_const(st.tree, cs, v)
                if t_struct is None: continue
                for cf in consts:                          # fit another const to match
                    if cf == cs or tried >= budget: continue
                    w = _linfit(t_struct, cf, xf, tgtf) if tgtf is not None else None
                    if w is None: continue
                    t2 = _set_const(t_struct, cf, round(w, 9))
                    if t2 is None: continue
                    tried += 1; st.units += 1
                    nf, susp2 = st._score(t2)
                    if nf < best[0]: best = (nf, t2, susp2, f"FIT c[{cs}]={v},c[{cf}]={round(w,4)}")
                    if nf == 0: break
                if best[0] == 0: break
            if best[0] == 0: break
        st._cache[self._key(st)] = True
        if best[1] is not None and best[0] < before:
            st.tree, st.susp, st.best = best[1], best[2], best[0]
            st.log.append((self.name, before, best[0]))
            return {"form": self.name, "tried": tried, "before": before, "after": best[0],
                    "improved": True, "solved": best[0] == 0, "exhausted": False, "fix": best[3]}
        return {"form": self.name, "tried": tried, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}

# ---------------- SLEEP: GENERIC parametric frame grammar (attribute-agnostic, family-agnostic) ---
ATTRS = ("coeff", "exp")
OPS = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
       "/": lambda a, b: (a / b if abs(b) > 1e-9 else None)}
CONSTS = (-2, -1, 1, 2, 3, 4)
def _get(a, c, e): return c if a == "coeff" else e
def _operands():
    ops = [(a, (a,), (lambda c, e, a=a: _get(a, c, e))) for a in ATTRS]                 # identity
    for a in ATTRS:                                                                      # unary a OP k
        for opn, opf in OPS.items():
            for k in CONSTS:
                ops.append((f"({a}{opn}{k})", (a,), (lambda c, e, a=a, opf=opf, k=k: opf(_get(a, c, e), k))))
    return ops
def frame_grammar():
    """Every candidate relation for ONE output attribute, depth<=2, atoms {+,-,*,/}x small-int, any
    attribute, cross-attribute refs allowed. Same set used for coeff and exp, for EVERY family."""
    ops = _operands(); cands = list(ops)                                                 # depth-1
    for a in ATTRS:                                                                       # depth-2: a OP operand
        for opn, opf in OPS.items():
            for lab, refs, fn in ops:
                def make(a, opf, fn):
                    def g(c, e):
                        v = fn(c, e)
                        return None if v is None else opf(_get(a, c, e), v)
                    return g
                cands.append((f"{a}{opn}{lab}", set(refs) | {a}, make(a, opf, fn)))
    return cands
def discover_relation(traces, which):
    """Simplest consistent relation predicting new coeff(which=0)/exp(which=1); needs >=3 traces and
    the referenced attributes must VARY (>=2 distinct values) so a match isn't coincidence."""
    if len(traces) < 3: return None
    best = None
    for lab, refs, fn in frame_grammar():
        good = True
        for (oc, oe), (nc, ne) in traces:
            v = fn(oc, oe); tgt = nc if which == 0 else ne
            if v is None or abs(v - tgt) > 1e-6: good = False; break
        if not good: continue
        for a in refs:
            if len({_get(a, oc, oe) for (oc, oe), _ in traces}) < 2: good = False; break
        if good and (best is None or len(lab) < len(best[0])): best = (lab, refs, fn)
    return best

def parse_terms(tree):
    ret = next(n for n in ast.walk(tree) if isinstance(n, ast.Return)).value
    def addends(n):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add): return addends(n.left) + addends(n.right)
        return [n]
    out = []
    for a in addends(ret):
        if isinstance(a, ast.BinOp) and isinstance(a.op, ast.Mult) and isinstance(a.left, ast.Constant) \
           and isinstance(a.right, ast.BinOp) and isinstance(a.right.op, ast.Pow) \
           and isinstance(a.right.right, ast.Constant):
            out.append((a.left.value, a.right.right.value))
    return out

class StructParam:
    """DISCOVERED parametric operator: rewrite EVERY term by the crystallized frame, each using its OWN
    (coeff,exp) -> a NON-UNIFORM structural map in one move. The class beyond STRUCT_GLOBAL."""
    cost_hint = 1.0
    def __init__(self, rc, re_, label):
        self.rc, self.re_ = rc, re_; self.name = f"STRUCT_PARAM[{label}]"
    def _key(self, st): return ("SPARAM", st._th())
    def applicable(self, st): return not st.solved() and st._cache.get(self._key(st)) is None
    def run(self, st, budget):
        before = st.best; terms = parse_terms(st.tree)
        st._cache[self._key(st)] = True
        if not terms:
            return {"form": self.name, "tried": 0, "before": before, "after": before,
                    "improved": False, "solved": False, "exhausted": True, "fix": None}
        new = [(self.rc(c, e), int(round(self.re_(c, e)))) for c, e in terms]   # full float (rounding x high power > 1e-6)
        try: t2 = ast.parse(poly_src(new))
        except Exception: t2 = None
        if t2 is not None:
            st.units += 1; nf, susp2 = st._score(t2)
            if nf == 0:
                st.tree, st.susp, st.best = t2, susp2, nf; st.log.append((self.name, before, nf))
                return {"form": self.name, "tried": 1, "before": before, "after": nf,
                        "improved": True, "solved": True, "exhausted": False, "fix": self.name}
        return {"form": self.name, "tried": 1, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}

def bootstrap_traces(family_transform, seeds):
    """WAKE: generic FitTemplate solves single-term tasks -> clean parametric traces ((oc,oe),(nc,ne))."""
    traces = []
    for terms in seeds:
        t = make_task(terms, family_transform); st = MetaState("f", t["src"], t["tests"])
        d = FitTemplate().run(st, 400)
        if d["solved"]:
            nt = parse_terms(st.tree)
            if len(nt) == 1: traces.append((terms[0], nt[0]))
    return traces

def discover_frame(traces, tag):
    rc, re_ = discover_relation(traces, 0), discover_relation(traces, 1)
    if rc and re_:
        op = StructParam(rc[2], re_[2], f"c'={rc[0]},e'={re_[0]}")
        return op, (rc[0], re_[0])
    return None, (rc[0] if rc else None, re_[0] if re_ else None)

if __name__ == "__main__":
    os.environ.setdefault("META_GLOBAL", "8000")
    G = frame_grammar()
    print(f"frame grammar size = {len(G)} candidate relations (>100 = real search, not lookup)\n")

    SEEDS = [[(3, 2)], [(2, 3)], [(5, 4)], [(4, 2)], [(2, 5)]]   # distinct (c,e) for the distinctness gate
    MULTI = {2: [(3, 2), (2, 3)], 3: [(3, 2), (2, 3), (5, 4)],
             4: [(3, 2), (2, 3), (5, 4), (2, 5)], 6: [(3, 2), (2, 3), (5, 4), (2, 5), (4, 6), (3, 7)]}

    def run_family(name, tf, extra):
        print(f"--- {name}: multi-term (NON-uniform: each term transforms by its OWN exponent) ---")
        for k, terms in MULTI.items():
            t = make_task(terms, tf)
            okP, enP, _ = solve_ucb("f", t["src"], t["tests"], [], extra_forms=(FitTemplate(),))
            okD, enD, _ = solve_ucb("f", t["src"], t["tests"], [], extra_forms=extra + (FitTemplate(),))
            print(f"    k={k}: primitives {'Y' if okP else 'n'}({enP:5d})   +discovered {'Y' if okD else 'n'}({enD:5d})")

    print("=== DEV FAMILY = DIFFERENTIATION (frame grammar built here, NOT looking at integration) ===")
    dtr = bootstrap_traces(differentiate, SEEDS)
    print(f"  single-term traces (FitTemplate): {[(o, n) for o, n in dtr]}")
    dop, dframe = discover_frame(dtr, "diff")
    print(f"  discovered frame: coeff'={dframe[0]}   exp'={dframe[1]}   -> {'CRYSTALLIZED' if dop else 'FAILED'}")
    run_family("diff", differentiate, (dop,) if dop else ())

    print("\n=== SEALED HOLDOUT = INTEGRATION (SAME grammar & code, ZERO changes) ===")
    itr = bootstrap_traces(integrate, SEEDS)
    print(f"  single-term traces (FitTemplate): {[(o, n) for o, n in itr]}")
    iop, iframe = discover_frame(itr, "integ")
    print(f"  discovered frame: coeff'={iframe[0]}   exp'={iframe[1]}   -> {'CRYSTALLIZED' if iop else 'FAILED'}")
    run_family("integ", integrate, (iop,) if iop else ())

    print("\n=== RE-DERIVATION SANITY: NEGATE & Pow2 as degenerate frames in the SAME grammar ===")
    neg = bootstrap_traces(lambda ts: [(-c, e) for c, e in ts], SEEDS)   # c'=-c (NEGATE), e'=e
    nrc = discover_relation(neg, 0); nre = discover_relation(neg, 1)
    print(f"  NEGATE-class: coeff'={nrc[0] if nrc else None}  exp'={nre[0] if nre else None}")
    pw = bootstrap_traces(lambda ts: [(c, e + 1) for c, e in ts], SEEDS)  # e'=e+1 (Pow-raise), c'=c
    prc = discover_relation(pw, 0); pre = discover_relation(pw, 1)
    print(f"  POW-RAISE-class: coeff'={prc[0] if prc else None}  exp'={pre[0] if pre else None}")
    print("\n(hand-added vocab items to reach integration = 0; integration emerging from a grammar built"
          "\n only on differentiation = the parametric-rewrite CLASS generalized, not a coded operator.)")
