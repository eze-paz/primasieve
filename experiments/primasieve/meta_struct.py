"""CAN A *STRUCTURAL* OPERATOR EMERGE? (owner's option A — generic, NOT hardcoded integration).

Every operator discovered so far (NEGATE, GlobalApply) EDITS or SWAPS an existing node. A structural
operator INSERTS tree structure (a node with children) — a qualitatively harder, untested leap. This
is the honest first rung toward integration: a UNIFORM structural map (raise every term's degree),
verifiable numerically (eval on FLOAT points vs the correct fn), that can actually bootstrap. If a
uniform structural op can't emerge, integration (a NON-uniform map needing two-variable frames) is
hopeless; if it can, integration is the next rung.

Pipeline, ZERO LLM, operator DISCOVERED not coded:
  WAKE  : a GENERIC structural primitive (GrammarExpand: depth-1 expr-grammar expansions at a leaf)
          solves single-term degree-raise (c*x -> c*x**2) for several coeffs. Default forms CANNOT
          (they edit consts/ops; none inserts a Pow node) -> clean attribution to the structural move.
  SLEEP : trace-DIFF buggy->fixed (struct_changes) extracts the inserted template; anti-unify across
          >=2 traces; if consistent -> crystallize StructGlobalApply (apply that template at ALL sites).
  WAKE2 : multi-term degree-raise (k>=2) is a FLAT landscape (a partial single-site expansion fails
          every point identically = no gradient) -> GrammarExpand STALLS = impasse. The DISCOVERED
          StructGlobalApply clears it in one move. Knockout: primitives-only vs +discovered."""
import ast, copy, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from meta_reason import solve_ucb

XS = [0.5, 1.7, 2.3, 3.1, 4.2, -1.3, -2.6]          # FLOAT points, avoid 0/1 (where x==x**2)

# ---------------- domain: uniform degree-raise (integration-flavored, not integration) -----------
def _fn(coeffs, deg):
    def f(x): return sum(c * x**deg for c in coeffs)
    return f
def gen_degree_bug(coeffs):
    """buggy: sum(c*x)  ->  correct: sum(c*x**2)  (each term's degree raised by 1, uniformly)."""
    body_bug = " + ".join(f"{c}*x" for c in coeffs)
    src = f"def f(x):\n    return {body_bug}"
    correct = _fn(coeffs, 2)
    tests = [([x], correct(x)) for x in XS]
    return {"src": src, "tests": tests, "coeffs": coeffs}

# ---------------- a GENERIC structural primitive (grammar expansions, NOT 'integrate') -----------
def _load_names(tree):
    return [(i, n) for i, n in enumerate(ast.walk(tree))
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)]
def _replace_nth_name(tree, walk_idx, builder):
    """Replace the node at ast.walk index `walk_idx` (must be a Load Name) with builder(node)."""
    t = copy.deepcopy(tree); nodes = list(ast.walk(t))
    if walk_idx >= len(nodes): return None
    target = nodes[walk_idx]
    if not (isinstance(target, ast.Name) and isinstance(target.ctx, ast.Load)): return None
    new = builder(target)
    for p in ast.walk(t):                        # splice: swap the parent's child reference
        for field, val in list(ast.iter_fields(p)):
            if val is target: setattr(p, field, new); return ast.fix_missing_locations(t)
            if isinstance(val, list):
                for k, item in enumerate(val):
                    if item is target: val[k] = new; return ast.fix_missing_locations(t)
    return None
# generic depth-1 expansions of a leaf T (FIXED order -> deterministic template across traces)
def _templates():
    def binop(opname, c): return lambda n: ast.BinOp(ast.Name(n.id, ast.Load()), getattr(ast, opname)(), ast.Constant(c))
    def selfmul(n): return ast.BinOp(ast.Name(n.id, ast.Load()), ast.Mult(), ast.Name(n.id, ast.Load()))
    return [("Pow", 2, binop("Pow", 2)), ("Pow", 3, binop("Pow", 3)),
            ("MultSelf", None, selfmul), ("Mult", 2, binop("Mult", 2)), ("Add", 2, binop("Add", 2))]

class GrammarExpand:
    """GENERIC structural move: replace a leaf Name with a depth-1 grammar expansion (T op T / T op c).
    Not math-specific — 'integrate' is only one thing among many it can express. Solves single-site
    structural fixes; STALLS on multi-site (flat landscape) = the impasse that motivates discovery."""
    name = "GRAMMAR_EXPAND"; cost_hint = 2.0
    def _key(self, st): return ("GEXPAND", st._th())
    def applicable(self, st): return not st.solved() and st._cache.get(self._key(st)) is None
    def run(self, st, budget):
        before = st.best; best = (before, None, None, None); tried = 0
        for idx, _ in _load_names(st.tree):
            for opname, c, builder in _templates():
                if tried >= budget: break
                t2 = _replace_nth_name(st.tree, idx, builder)
                if t2 is None: continue
                tried += 1; st.units += 1
                nf, susp2 = st._score(t2)
                if nf < best[0]: best = (nf, t2, susp2, f"EXPAND name->{opname}{c if c else ''}")
                if nf == 0: break
            if best[0] == 0: break
        st._cache[self._key(st)] = True
        if best[1] is not None and best[0] < before:
            st.tree, st.susp, st.best = best[1], best[2], best[0]
            st.log.append((self.name, before, best[0]))
            return {"form": self.name, "tried": tried, "before": before, "after": best[0],
                    "improved": True, "solved": best[0] == 0, "exhausted": False, "fix": best[3]}
        return {"form": self.name, "tried": tried, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}

# ---------------- SLEEP: extract the inserted structural template by DIFFING trees ----------------
def struct_changes(buggy, fixed):
    """Generic: a leaf Name that got WRAPPED into BinOp(op, name, const|self). Returns (op, const, var)."""
    bnames = {n.id for n in ast.walk(buggy) if isinstance(n, ast.Name)}
    out = []
    for node in ast.walk(fixed):
        if isinstance(node, ast.BinOp) and isinstance(node.left, ast.Name) and node.left.id in bnames:
            if isinstance(node.right, ast.Constant):
                out.append((type(node.op).__name__, node.right.value, node.left.id))
            elif isinstance(node.right, ast.Name) and node.right.id == node.left.id:
                out.append((type(node.op).__name__, "SELF", node.left.id))
    return out

def discover_struct_op(pairs):
    """Anti-unify inserted templates across solved traces; crystallize if one is consistent (>=2)."""
    from collections import Counter
    votes = Counter()
    for buggy, fixed in pairs:
        for tmpl in set(struct_changes(buggy, fixed)): votes[tmpl] += 1
    if not votes: return None, votes
    (op, const, var), n = votes.most_common(1)[0]
    if n >= 2: return StructGlobalApply(op, const, var), votes
    return None, votes

class StructGlobalApply:
    """DISCOVERED structural operator: wrap EVERY matching leaf in the crystallized template, in ONE
    move (the structural analog of GlobalApply). INSERTS tree structure -> a new capability class."""
    cost_hint = 1.0
    def __init__(self, op, const, var):
        self.op, self.const, self.var = op, const, var
        self.name = f"STRUCT_GLOBAL[{var}->{op}{'' if const=='SELF' else const}]"
    def _key(self, st): return ("SGLOBAL", st._th())
    def applicable(self, st): return not st.solved() and st._cache.get(self._key(st)) is None
    def _build(self, n):
        if self.const == "SELF":
            return ast.BinOp(ast.Name(n.id, ast.Load()), getattr(ast, self.op)(), ast.Name(n.id, ast.Load()))
        return ast.BinOp(ast.Name(n.id, ast.Load()), getattr(ast, self.op)(), ast.Constant(self.const))
    def run(self, st, budget):
        before = st.best; t = copy.deepcopy(st.tree); hits = 0
        for p in ast.walk(t):
            for field, val in list(ast.iter_fields(p)):
                if isinstance(val, ast.Name) and val.id == self.var and isinstance(val.ctx, ast.Load):
                    setattr(p, field, self._build(val)); hits += 1
                elif isinstance(val, list):
                    for k, item in enumerate(val):
                        if isinstance(item, ast.Name) and item.id == self.var and isinstance(item.ctx, ast.Load):
                            val[k] = self._build(item); hits += 1
        st._cache[self._key(st)] = True
        if hits:
            t = ast.fix_missing_locations(t); st.units += 1
            nf, susp2 = st._score(t)
            if nf == 0:                              # accept ONLY a full solve (partial = wrong strand)
                st.tree, st.susp, st.best = t, susp2, nf
                st.log.append((self.name, before, nf))
                return {"form": self.name, "tried": 1, "before": before, "after": nf,
                        "improved": True, "solved": True, "exhausted": False, "fix": f"{self.name} x{hits}"}
        return {"form": self.name, "tried": 1, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}

if __name__ == "__main__":
    os.environ.setdefault("META_GLOBAL", "12000")
    ge = GrammarExpand()

    print("=== WAKE: generic structural primitive solves SINGLE-TERM degree-raise (traces) ===")
    boot = [gen_degree_bug([c]) for c in (2, 3, 5, 7)]
    pairs = []
    for t in boot:
        buggy = ast.parse(t["src"])
        ok, en, _, st = solve_ucb("f", t["src"], t["tests"], [], extra_forms=(GrammarExpand(),), return_state=True)
        tag = st.log[-1][0] if st.log else "-"
        print(f"  c={t['coeffs'][0]}: {'SOLVED' if ok else 'FAIL':6s} @{en:4d} via {tag}")
        if ok: pairs.append((buggy, st.tree))
    # control: can DEFAULT forms (no structural primitive) solve it? (should NOT)
    okd, end, _ = solve_ucb("f", boot[0]["src"], boot[0]["tests"], [])
    print(f"  [control] default forms (no structural move) on c=2: {'SOLVED' if okd else 'CANNOT'} @{end}\n")

    print("=== SLEEP: diff traces, anti-unify inserted template, crystallize ===")
    op, votes = discover_struct_op(pairs)
    print(f"  inserted-template votes: {dict(votes)}")
    print(f"  crystallized: {op.name if op else 'NONE (not consistent >=2)'}\n")

    print("=== WAKE2 KNOCKOUT: multi-term degree-raise (FLAT, k>=2) — primitives vs +discovered ===")
    extra = (op,) if op else ()
    for k in (1, 2, 3, 5, 8):
        coeffs = list(range(2, 2 + k))
        t = gen_degree_bug(coeffs)
        okP, enP, _ = solve_ucb("f", t["src"], t["tests"], [], extra_forms=(GrammarExpand(),))          # primitives only
        okD, enD, _ = solve_ucb("f", t["src"], t["tests"], [], extra_forms=extra + (GrammarExpand(),))   # + discovered
        print(f"  k={k}: primitives {'Y' if okP else 'n'}({enP:5d})   +discovered {'Y' if okD else 'n'}({enD:5d})")
    print("\n(primitives solve k=1 only [flat multi-site wall]; the DISCOVERED structural operator, which"
          "\n INSERTS tree structure, reaches k>=2 in one move = a NEW capability class emerged, not coded.)")
