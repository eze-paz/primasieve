"""P0 — Forms refactor: wrap the existing engines in a uniform Form API. ZERO LLM.

Every reasoning form implements:
    applicable(st) -> bool          cheap gate
    cost(st)       -> float         estimated energy units (candidate-evaluations)
    run(st, budget)-> EvidenceDelta bounded execution; returns what changed

st is a shared mutable state dict:
    name, src, tests, tree (current AST), stratum, best (abandon threshold),
    deadline, tried, solved, susp (Ochiai map), log (episode records)

EvidenceDelta: dict(candidates, score_before, score_after, solved, notes)
Regression gate (metaplan P0): the hand-coded escalation order replayed THROUGH the
Form API must still solve 25/26 at the same cost +/-10%.
"""
import os, sys, json, copy, ast, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reasoner_code import (enumerate_edits, enumerate_stmt_moves, apply_edit,
                           run_one, load_tests, QB, BUDGET, TIME_CAP)

# ---------- shared task state ----------
class TaskState:
    def __init__(self, name, src, tests, deadline=None):
        self.name=name; self.src=src; self.tests=tests
        self.tree=ast.parse(src)
        self.best=len(tests)+1
        self.deadline=deadline if deadline is not None else time.time()+TIME_CAP
        self.stratum=0; self.tried=0; self.solved=False
        self.susp={}; self.nfail=len(tests)
        self.episode=[]                      # (form, candidates, score_before, score_after)

    def compile_tree(self, tree):
        try: return compile(ast.fix_missing_locations(tree),"<cand>","exec")
        except Exception: return None

    def simulate_diff(self, tree):
        """Exact execution + Ochiai diff. Returns (score, susp) — score 0 = solved."""
        code=self.compile_tree(tree)
        if code is None: return (len(self.tests)+1, None)
        res=[]; covs=[]; fails=0
        for inp,exp in self.tests:
            ok,cov=run_one(code,self.name,inp,exp)
            res.append(ok); covs.append(cov)
            if not ok:
                fails+=1
                if fails>=self.best: return (len(self.tests)+1, None)
        nfail=sum(1 for x in res if not x)
        self.best=min(self.best,nfail)
        if nfail==0: return (0,None)
        susp={}; totfail=nfail
        allln=set().union(*covs) if covs else set()
        for ln in allln:
            ef=sum(1 for ok,c in zip(res,covs) if not ok and ln in c)
            ep=sum(1 for ok,c in zip(res,covs) if ok and ln in c)
            susp[ln]= ef/math.sqrt(totfail*(ef+ep)) if ef else 0.0
        return (nfail,susp)

# ---------- Form API ----------
class Form:
    name="FORM"
    def applicable(self,st): return True
    def cost(self,st): return 0.0
    def run(self,st,budget): raise NotImplementedError

class ENUMERATE(Form):
    """Stratum-k enumeration: evaluate every edit at this stratum, accept best improvement.
    Faithful re-implementation of CodeDomain.moves+reason's solve-first steepest scan."""
    def __init__(self,k): self.k=k; self.name=f"ENUMERATE({k})"
    def applicable(self,st): return st.stratum>=self.k and not st.solved
    def cost(self,st):
        try:
            n=len(enumerate_edits(st.tree,self.k))
            if self.k>=2: n+=len(enumerate_stmt_moves(st.tree,st.susp))
            return float(n)
        except Exception: return 1e9
    def run(self,st,budget):
        before=st.nfail; cands=0
        edits=enumerate_edits(st.tree,self.k)
        if self.k>=2: edits+=enumerate_stmt_moves(st.tree,st.susp)
        def key(e):
            s,ln,desc,idx,ka=e
            b=st.susp.get(ln,0.0) if st.susp else 0.0
            return (s,-b,idx)
        best=(st.nfail,None,None,None)
        for s,ln,desc,idx,ka in sorted(edits,key=key):
            if st.tried>=budget or time.time()>st.deadline: break
            if st.susp and st.susp.get(ln,0.0)==0.0: continue
            t2=apply_edit(st.tree,idx,ka)
            if t2 is None: continue
            st.tried+=1; cands+=1
            sc,susp=st.simulate_diff(t2)
            if sc<best[0]: best=(sc,desc,t2,susp)
            if sc==0: break
        if best[1] is not None:
            st.tree=best[2]; st.nfail=best[0]; st.susp=best[3] or {}
            st.solved = best[0]==0
        st.episode.append((self.name,cands,before,st.nfail))
        return dict(candidates=cands,score_before=before,score_after=st.nfail,
                    solved=st.solved,notes=best[1] or "no improving edit")

class LOCALIZE(Form):
    """Refresh the Ochiai suspiciousness map on the CURRENT tree (evidence refresh)."""
    def __init__(self): self.name="LOCALIZE"
    def cost(self,st): return float(len(st.tests))
    def run(self,st,budget):
        before=st.nfail
        sc,susp=st.simulate_diff(st.tree)
        if susp is not None: st.susp=susp
        st.nfail=sc; st.solved = sc==0
        st.episode.append((self.name,len(st.tests),before,st.nfail))
        return dict(candidates=len(st.tests),score_before=before,score_after=st.nfail,
                    solved=st.solved,notes="susp refreshed")

class RESET(Form):
    """Reset to pristine + drop one stratum of memory (used on escalation)."""
    def __init__(self): self.name="RESET"
    def cost(self,st): return 0.0
    def run(self,st,budget):
        st.tree=ast.parse(st.src); st.best=len(st.tests)+1
        # recompute evidence on the pristine tree (baseline acquire() re-diffs the
        # reset state; a stale susp map filters away the right line otherwise)
        sc,susp=st.simulate_diff(st.tree)
        st.nfail=sc; st.susp=susp or {}; st.solved = sc==0
        st.episode.append((self.name,0,st.nfail,st.nfail))
        return dict(candidates=0,score_before=st.nfail,score_after=st.nfail,
                    solved=st.solved,notes="reset to pristine + re-localize")

class DEEPEN(Form):
    """Epistemic move: raise the grammar stratum (acquire)."""
    def __init__(self): self.name="DEEPEN"
    def applicable(self,st): return st.stratum<2
    def cost(self,st): return 0.0
    def run(self,st,budget):
        st.stratum+=1
        st.episode.append((self.name,0,st.nfail,st.nfail))
        return dict(candidates=0,score_before=st.nfail,score_after=st.nfail,
                    solved=st.solved,notes=f"stratum -> {st.stratum}")

# ---------- hand-coded escalation order, replayed THROUGH the Form API ----------
def solve_task(name, budget=BUDGET, verbose=False):
    tests=load_tests(name)
    src=open(f"{QB}/python_programs/{name}.py").read()
    st=TaskState(name,src,tests)
    forms=[ENUMERATE(0),ENUMERATE(1),ENUMERATE(2),LOCALIZE(),RESET(),DEEPEN()]
    while not st.solved and st.tried<budget and time.time()<st.deadline:
        # faithful replay of the hand-coded escalation: scan the CURRENT stratum
        # (enumerate_edits returns all edits s<=stratum, cheapest first); if it yields
        # no improving edit, spend the epistemic move (deepen + reset) — exactly
        # CodeDomain.acquire. Stratum is capped at 2; exhausted => stop.
        f=forms[min(st.stratum,2)]
        delta=f.run(st,budget)
        if verbose: print(f"  [{st.tried}] {f.name}: {delta['score_before']}->{delta['score_after']} {delta['notes']}",flush=True)
        if st.solved: break
        if delta["score_after"]<delta["score_before"]:
            continue                          # improved: rescan the same stratum
        if st.stratum<2:
            DEEPEN().run(st,budget)           # stratum += 1
            RESET().run(st,budget)            # reset-to-pristine on escalation
        else:
            break                             # grammar exhausted at max stratum
    return st

if __name__=="__main__":
    SLICE=os.environ.get("FORM_SLICE")
    names=sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))
    if SLICE: names=[n for n in names if n in SLICE.split(",")]
    t0=time.time(); solved=[]; failed=[]; skipped=[]
    for name in names:
        tests=load_tests(name)
        csrc=open(f"{QB}/correct_python_programs/{name}.py").read()
        try: ccode=compile(csrc,"<cand>","exec")
        except Exception: skipped.append(name); continue
        if not all(run_one(ccode,name,i,e)[0] for i,e in tests):
            skipped.append(name); continue
        st=solve_task(name)
        (solved if st.solved else failed).append(name)
        print(f"{name:26s} {'SOLVED' if st.solved else 'no':6s} stratum={st.stratum} mutants={st.tried:6d} {time.time()-t0:6.1f}s",flush=True)
    print(f"\n=== P0 Form-API replay on QuixBugs: {len(solved)}/{len(solved)+len(failed)} solved ({len(skipped)} excluded) in {time.time()-t0:.0f}s ===")
    print("solved:",solved); print("unsolved:",failed)
