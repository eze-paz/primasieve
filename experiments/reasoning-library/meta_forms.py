"""P0 — reasoning FORMS as first-class moves over a shared MetaState (METAPLAN.md).
Wraps the existing stratified engine (reasoner_code) behind one interface so an outer controller
can CHOOSE and CHAIN forms. Energy = candidate evaluations (deterministic, wall-clock-free)."""
import ast, math, time, copy
import reasoner_code as rc

class MetaState:
    def __init__(self, name, src, tests, held_back=0.0):
        # ANTI-CHEAT: the search only SEES `tests` (a subset when held_back>0); a true solve must
        # also pass the held-back assertions (checked by verify_full). Catches test-adequate cheats.
        self.name = name; self.all_tests = tests
        k = int(round(len(tests) * (1 - held_back))) if held_back else len(tests)
        self.tests = tests[:max(1, k)] if held_back else tests
        self.held = tests[max(1, k):] if held_back else []
        self.orig = ast.parse(src)
        self.tree = self.orig
        self.units = 0                       # total candidate evaluations spent
        self.best, self.susp = self._score(self.tree)
        self.stratum_seen = 0                # deepest stratum ever enumerated (for reporting)
        self.log = []                        # (form, units_before, score_before, score_after)
        self._cache = {}                     # stratum -> (tree_hash, ordered_edits, cursor)
    def _th(self):                           # content hash: exhaustion is tied to the ACTUAL tree,
        return hash(ast.dump(self.tree))     # so RESET-to-pristine keeps pristine's exhausted state
    def _score(self, tree):
        """Return (nfail, susp-belief). nfail = len(tests)+1 if it doesn't compile."""
        try: code = compile(ast.fix_missing_locations(tree), "<cand>", "exec")
        except Exception: return len(self.tests) + 1, {}
        res, covs = [], []
        for inp, exp in self.tests:
            ok, cov = rc.run_one(code, self.name, inp, exp); res.append(ok); covs.append(cov)
        nfail = sum(1 for x in res if not x)
        if nfail == 0: return 0, {}
        susp = {}; allln = set().union(*covs) if covs else set()
        for ln in allln:
            ef = sum(1 for ok, c in zip(res, covs) if not ok and ln in c)
            ep = sum(1 for ok, c in zip(res, covs) if ok and ln in c)
            susp[ln] = ef / math.sqrt(nfail * (ef + ep)) if ef else 0.0
        return nfail, susp
    def solved(self): return self.best == 0            # passes the SHOWN tests (search target)
    def verify_full(self):
        """True solve = passes ALL assertions incl. held-back (anti-cheat gate)."""
        try: code = compile(ast.fix_missing_locations(self.tree), "<cand>", "exec")
        except Exception: return False
        return all(rc.run_one(code, self.name, i, e)[0] for i, e in self.all_tests)

# ---------- forms: each is applicable()/cost()/run(state, budget) -> EvidenceDelta ----------
def _stratum_edits(tree, k, susp):
    """Edits INTRODUCED at exactly stratum k (so the controller genuinely chooses depth)."""
    edits = [e for e in rc.enumerate_edits(tree, k) if e[0] == k]
    if k >= 2: edits += rc.enumerate_stmt_moves(tree, susp)
    def key(e):
        s, ln, desc, idx, ka = e
        return (-(susp.get(ln, 0.0) if susp else 0.0), idx)
    return sorted(edits, key=key)

class Enumerate:
    """Try edits at a fixed stratum, RESUMING across calls via a per-stratum cursor. Accepts the
    first STRICT improvement in this slice (steepest scan continues next call). 'exhausted' means
    the whole stratum was scanned with no improvement (only then is the form truly done)."""
    def __init__(self, k):
        self.k = k; self.name = f"ENUMERATE({k})"
        self.cost_hint = (1.0, 2.5, 8.0)[k] if k < 3 else 12.0   # Occam prior: deeper = pricier
    def applicable(self, st):
        return not st.solved() and not self._exhausted(st)
    def _edits(self, st):
        # cursor keyed by (tree-content, stratum): committing a partial (new tree) does NOT overwrite
        # the pristine stratum cursor, so RESET-to-pristine resumes where it left off (fixes sqrt).
        key = (st._th(), self.k); c = st._cache.get(key)
        if c is None:
            edits = [(ln, idx, ka) for (s, ln, desc, idx, ka) in _stratum_edits(st.tree, self.k, st.susp)
                     if not (st.susp and st.susp.get(ln, 0.0) == 0.0)]
            st._cache[key] = [st._th(), edits, 0]
        return st._cache[key]
    def _exhausted(self, st):
        c = st._cache.get((st._th(), self.k))
        return c is not None and c[2] >= len(c[1])
    def run(self, st, budget):
        # SOLVE-FIRST STEEPEST within this slice: evaluate up to `budget` candidates, take the BEST
        # (first-improvement strands the true fix behind a cheaper partial one).
        before = st.best; tried = 0
        cache = self._edits(st); _, edits, cur = cache
        st.stratum_seen = max(st.stratum_seen, self.k)
        best = (before, None, None, None)     # (nf, tree, susp, fixdesc)
        while cur < len(edits) and tried < budget:
            ln, idx, ka = edits[cur]; cur += 1
            t2 = rc.apply_edit(st.tree, idx, ka)
            if t2 is None: continue
            tried += 1; st.units += 1
            nf, susp2 = st._score(t2)
            if nf < best[0]: best = (nf, t2, susp2, desc_of(ka, ln))
            if nf == 0: break
        cache[2] = cur
        if best[1] is not None:               # accept the best strict improvement in the slice
            st.tree, st.susp, st.best = best[1], best[2], best[0]
            st.log.append((self.name, before, best[0]))
            return {"form": self.name, "tried": tried, "before": before, "after": best[0],
                    "improved": True, "solved": best[0] == 0, "exhausted": False, "fix": best[3]}
        return {"form": self.name, "tried": tried, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": cur >= len(edits), "fix": None}

def desc_of(ka, ln): return f"L{ln}:{ka[0]}"

class Reset:
    """Return to the pristine program (undo a stranding partial). Fires early (cost 0.5) to escape a
    DEAD-END partial (e.g. pascal); MOMENTUM (re-run a just-improved form) protects PRODUCTIVE
    partials (e.g. sqrt's 2-edit compose) from being discarded, so early RESET is safe now."""
    name = "RESET"; cost_hint = 0.5
    def applicable(self, st):
        # only useful to UNDO a partial improvement (return to pristine); not when already pristine
        return not st.solved() and st.tree is not st.orig
    def run(self, st, budget):
        before = st.best
        st.tree = st.orig; st.best, st.susp = st._score(st.orig)
        st.log.append((self.name, before, st.best))
        return {"form": self.name, "tried": 0, "before": before, "after": st.best,
                "improved": False, "solved": st.best == 0, "exhausted": False, "fix": None}

class Interpolate:
    """Structure-mapping form: fetch an analog, extract its relational frame, project onto the
    current tree (fills the frame's hole with the target's own material). Solves the powerset-class
    'missing relation' bugs no single edit reaches. One-shot per state (analogs tried once)."""
    name = "INTERPOLATE"; cost_hint = 6.0
    def __init__(self):
        import reasoner_interp as ri
        self.ri = ri
        self.analogs = [("get_class_members", ri.get_stdlib_func("rlcompleter.py", "get_class_members"))]
    def _key(self, st): return ("INTERP", st._th())
    def applicable(self, st):
        return not st.solved() and st._cache.get(self._key(st)) is None
    def run(self, st, budget):
        import ast as _ast
        before = st.best; src = _ast.unparse(st.tree)
        for aname, asrc in self.analogs:
            try: cands = list(self.ri.interpolate(src, asrc))
            except Exception: cands = []
            for desc, cand in cands:
                st.units += 1
                nf, susp2 = st._score(cand)
                if nf < before:
                    st.tree, st.susp, st.best = cand, susp2, nf
                    st.log.append((self.name, before, nf))
                    st._cache[self._key(st)] = True   # (new tree -> new key; old marked below too)
                    return {"form": self.name, "tried": 1, "before": before, "after": nf,
                            "improved": True, "solved": nf == 0, "exhausted": False,
                            "fix": f"interp[{aname}]:{desc[:24]}"}
        st._cache[self._key(st)] = True               # exhausted on this tree
        return {"form": self.name, "tried": 1, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}

class GlobalApply:
    """3rd-order LEARNED operator wired live: 'if fixing one site helps, fix ALL matching sites in
    ONE move'. Reshapes the landscape for multi-site bugs (no per-site local optima) that primitive
    single-site search stalls on. Parameter-free / generic over edit kind (cmp & binop swaps)."""
    # cheap probe (~a few dozen evals) that SUBSUMES single-site operator swaps and solves multi-site
    # operator bugs in one move -> tried first; on non-operator bugs it no-ops fast and cedes to edits.
    name = "GLOBAL_APPLY"; cost_hint = 1.0
    def _key(self, st): return ("GLOBAL", st._th())
    def applicable(self, st):
        return not st.solved() and st._cache.get(self._key(st)) is None
    def run(self, st, budget):
        before = st.best; best = (before, None, None, None); seen = set(); tried = 0
        for node in ast.walk(st.tree):
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                cur = type(node.ops[0]).__name__; kind = "cmp"; opts = rc.CMP_OPS
            elif isinstance(node, ast.BinOp):
                cur = type(node.op).__name__; kind = "binop"; opts = rc.BIN_OPS
            else:
                continue
            for op in opts:
                # swap all nodes whose op == cur (the SOURCE) to op (the TARGET) -> leaves other ops
                # untouched (e.g. Add->Sub must NOT also turn Mult into Sub). Keyed by (kind,cur,tgt).
                if op.__name__ == cur or (kind, cur, op.__name__) in seen or tried >= budget: continue
                seen.add((kind, cur, op.__name__))
                t2 = _apply_global(st.tree, kind, cur, op)
                if t2 is None: continue
                tried += 1; st.units += 1
                nf, susp2 = st._score(t2)
                if nf < best[0]: best = (nf, t2, susp2, f"GLOBAL {kind} {cur}->{op.__name__}")
                if nf == 0: break
        st._cache[self._key(st)] = True
        # accept ONLY a full solve: a uniform global swap that merely PARTIALLY improves is almost
        # always a wrong strand (right for some sites, wrong for others) -> would strand the search.
        if best[1] is not None and best[0] == 0:
            st.tree, st.susp, st.best = best[1], best[2], best[0]
            st.log.append((self.name, before, best[0]))
            return {"form": self.name, "tried": tried, "before": before, "after": best[0],
                    "improved": True, "solved": True, "exhausted": False, "fix": best[3]}
        return {"form": self.name, "tried": tried, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}

def _apply_global(tree, kind, source, op):
    """Swap all nodes whose current op == `source` to `op` (leaves other op kinds untouched)."""
    t = copy.deepcopy(tree); changed = False
    for node in ast.walk(t):
        if kind == "cmp" and isinstance(node, ast.Compare) and len(node.ops) == 1 \
           and type(node.ops[0]).__name__ == source:
            node.ops = [op()]; changed = True
        elif kind == "binop" and isinstance(node, ast.BinOp) and type(node.op).__name__ == source:
            node.op = op(); changed = True
    return ast.fix_missing_locations(t) if changed else None

def default_forms():
    return [GlobalApply(), Enumerate(0), Enumerate(1), Enumerate(2), Interpolate(), Reset()]
