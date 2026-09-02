"""P0 — reasoning FORMS as first-class moves over a shared MetaState (METAPLAN.md).
Wraps the existing stratified engine (reasoner_code) behind one interface so an outer controller
can CHOOSE and CHAIN forms. Energy = candidate evaluations (deterministic, wall-clock-free)."""
import ast, math, time
import reasoner_code as rc

class MetaState:
    def __init__(self, name, src, tests):
        self.name = name; self.tests = tests
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
    def solved(self): return self.best == 0

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
    def __init__(self, k): self.k = k; self.name = f"ENUMERATE({k})"
    def applicable(self, st):
        return not st.solved() and not self._exhausted(st)
    def _edits(self, st):
        th = st._th(); c = st._cache.get(self.k)
        if c is None or c[0] != th:
            edits = [(ln, idx, ka) for (s, ln, desc, idx, ka) in _stratum_edits(st.tree, self.k, st.susp)
                     if not (st.susp and st.susp.get(ln, 0.0) == 0.0)]
            st._cache[self.k] = [th, edits, 0]
        return st._cache[self.k]
    def _exhausted(self, st):
        c = st._cache.get(self.k)
        return c is not None and c[0] == st._th() and c[2] >= len(c[1])
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
    """Return to the pristine program (undo a stranding partial improvement)."""
    name = "RESET"
    def applicable(self, st): return not st.solved()
    def applicable(self, st):
        # only useful to UNDO a partial improvement (return to pristine); not when already pristine
        return not st.solved() and st.tree is not st.orig
    def run(self, st, budget):
        before = st.best
        st.tree = st.orig; st.best, st.susp = st._score(st.orig)
        st.log.append((self.name, before, st.best))
        return {"form": self.name, "tried": 0, "before": before, "after": st.best,
                "improved": False, "solved": st.best == 0, "exhausted": False, "fix": None}

def default_forms():
    return [Enumerate(0), Enumerate(1), Enumerate(2), Reset()]
