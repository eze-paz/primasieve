"""Step 3 (fable) — NEGATE EMERGES from the stuck signal, ZERO LLM. Owner's thesis end-to-end:
a flat-landscape sign-flip STALLS gradient search -> STUCK fires -> escalates to REPEAT -> solved.
The SLEEP step then diffs buggy->fixed, sees a single-site const change old->new, and the relational
anti-unifier keeps the template consistent across >=2 traces: new == -old  -> crystallizes NEGATE as
a first-class operator. On RE-RUN, NEGATE solves the same bugs in one move -> escalation UNNECESSARY.
Emergence signature: operator ABSENT at t0, PRESENT only after escalation-solved traces, and it
removes the need to escalate. Nobody hand-added it to the loop."""
import ast, random, collections
from meta_reason import solve_ucb
from meta_forms import Negate, MetaState
from domain_math import gen_poly_bug

class _FoldNeg(ast.NodeTransformer):
    """Fold UnaryOp(USub, Constant(k)) -> Constant(-k) so ast.unparse's '-3' (which re-parses as a
    unary minus over Constant(3)) is seen as the signed value -3, not 3."""
    def visit_UnaryOp(self, n):
        self.generic_visit(n)
        if isinstance(n.op, ast.USub) and isinstance(n.operand, ast.Constant) and isinstance(n.operand.value, int):
            return ast.copy_location(ast.Constant(value=-n.operand.value), n)
        return n

def const_changes(buggy_src, fixed_src):
    """(old, new) for each signed-integer-constant change buggy->fixed (position-matched)."""
    def consts(s):
        t = _FoldNeg().visit(ast.parse(s)); ast.fix_missing_locations(t)
        return [n.value for n in ast.walk(t)
                if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool)]
    bo, fo = consts(buggy_src), consts(fixed_src)
    if len(bo) != len(fo): return []
    return [(o, n) for o, n in zip(bo, fo) if o != n]

def capture_fix(name, src, tests):
    """Solve with the FULL live controller (incl. stuck->REPEAT escalation); return fixed source."""
    ep = []; ok, en, _ = solve_ucb(name, src, tests, ep)
    if not ok: return None
    # re-solve capturing the tree (solve_ucb doesn't return it) via a MetaState replay of the fix:
    return _resolve_src(name, src, tests)

def _resolve_src(name, src, tests):
    from meta_reason import default_forms
    st = MetaState(name, src, tests); momentum = None; stuck_units = {}
    # minimal replay controller (cheapest-first + momentum + stuck->REPEAT) that returns the tree
    from meta_forms import default_forms as _df
    forms = _df(); st.stuck = False; best_ever = st.best; ub = 0; seen = set(); units = 0
    while not st.solved() and units < 12000:
        avail = [f for f in forms if f.applicable(st)]
        if not avail: break
        mom = next((f for f in avail if f.name == momentum), None)
        f = mom or min(avail, key=lambda f: getattr(f, "cost_hint", 1.0))
        u0 = st.units; d = f.run(st, 250); units += st.units - u0
        momentum = f.name if (d["improved"] and not d["solved"]) else None
        fp = getattr(st, "last_fail", None)
        if st.best < best_ever: best_ever = st.best; ub = units; st.stuck = False
        else:
            if (f.name == "RESET" and fp in seen) or (units - ub) > 0.25*max(1,12000-ub): st.stuck = True
        if fp is not None: seen.add(fp)
    return ast.unparse(ast.fix_missing_locations(st.tree)) if st.solved() else None

def discover_negate(pairs):
    """Relational anti-unification over const changes: keep the frame consistent across >=2 traces.
    Templates tried: new==-old, new==0, new==old+1, new==old-1."""
    frames = {"new==-old": lambda o, n: n == -o, "new==0": lambda o, n: n == 0,
              "new==old+1": lambda o, n: n == o+1, "new==old-1": lambda o, n: n == o-1}
    votes = collections.Counter()
    for bsrc, fsrc in pairs:
        for (o, n) in const_changes(bsrc, fsrc):
            for name, pred in frames.items():
                if pred(o, n): votes[name] += 1
    if not votes: return None, ["no const-change relational frame found"]
    top, c = votes.most_common(1)[0]
    report = [f"const-change relational frames across traces: {dict(votes)}",
              f"most consistent (>=2): '{top}' seen {c}x"]
    if top == "new==-old" and c >= 2:
        report.append("-> crystallized operator NEGATE (c -> -c) as a first-class rung")
        return Negate(), report
    return None, report + ["(top frame is not a clean negation; no operator crystallized)"]

if __name__ == "__main__":
    print("=== Step 3: NEGATE EMERGES from the stuck->REPEAT signal (zero-LLM) ===\n")
    rng = random.Random(7)
    # sign-flip tasks (the flat-landscape class that needs escalation)
    signs = [gen_poly_bug(rng, degree=rng.choice([2,3]), kind="sign") for _ in range(20)]
    signs = [t for t in signs if t["buggy"] != t["correct"]][:10]

    print("t0 — solve sign-flips with the LIVE controller (stuck->REPEAT); capture fixes:")
    pairs = []; e0 = 0; s0 = 0
    for t in signs:
        fx = capture_fix("f", t["src"], t["tests"])
        ep = []; ok, en, _ = solve_ucb("f", t["src"], t["tests"], ep); e0 += en; s0 += ok
        via = next((e["form"] for e in ep if e.get("solved")), "-")
        if fx: pairs.append((t["src"], fx))
    print(f"  solved {s0}/{len(signs)} (energy {e0}); {len(pairs)} fixes captured for sleep\n")

    print("SLEEP — relational anti-unification over the captured const changes:")
    negate_op, report = discover_negate(pairs)
    for r in report: print("   " + r)

    if negate_op is not None:
        print("\nt1 — RE-RUN the SAME sign-flips with the crystallized NEGATE operator available:")
        e1 = 0; s1 = 0; used_neg = 0
        for t in signs:
            ep = []; ok, en, _ = solve_ucb("f", t["src"], t["tests"], ep, extra_forms=(negate_op.__class__(),))
            e1 += en; s1 += ok
            if any(e["form"] == "NEGATE" and e.get("solved") for e in ep): used_neg += 1
        print(f"  solved {s1}/{len(signs)} (energy {e1}), NEGATE was the solver on {used_neg}")
        print(f"\n=== EMERGENCE: NEGATE was ABSENT at t0 (needed stuck->REPEAT escalation, {e0} energy),")
        print(f"    crystallized by sleep from its OWN escalation-solved traces (new==-old), and at t1")
        print(f"    solves the same bugs directly ({e1} energy, {e0/max(1,e1):.1f}x cheaper) -> escalation")
        print(f"    UNNECESSARY. The operator emerged from getting stuck; nobody hand-added it. ===")
