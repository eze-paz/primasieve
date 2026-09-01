"""P1 — Meta-controller v0: UCB bandit over reasoning FORMS, energy accounting in
candidate-evaluations, JSONL episode logs. ZERO LLM.

Middle loop (metaplan 2): state=(task, evidence, budget-left); actions=Forms;
selection=UCB1 warm-started by nothing (v0); reward = verifier-gradient movement
per unit energy. Knockout (P1): meta-controller vs the HAND-CODED escalation order
(meta_forms.solve_task) on the same pool at equal energy — must be >= hand-coded -10%.

Reward design (metaplan 2.2 + anti-cheat 4.1): reward = (score_before - score_after)
/ max(candidates,1); entropy bonus NOT included in v0 (one-shot entropy farming is
the #1 expected hack — deferred until there is a use for it).
"""
import os, sys, json, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meta_forms import TaskState, ENUMERATE, LOCALIZE, RESET, DEEPEN, load_tests, run_one, QB, BUDGET, TIME_CAP

class Episode:
    def __init__(self, name, controller):
        self.name=name; self.controller=controller; self.records=[]
    def add(self, rec): self.records.append(rec)
    def dump(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path,"a") as f: f.write(json.dumps({"task":self.name,"controller":self.controller,"records":self.records})+"\n")

def ucb_select(forms, stats, total_picks, c=1.2):
    """UCB1 over applicable forms. stats[form_name]=(pulls, mean_reward)."""
    best=None; bestv=-1e18
    for f in forms:
        if not f.applicable(st_holder[0]): continue
        pulls,mean=stats.get(f.name,(0,0.0))
        if pulls==0: return f                      # play each arm once first
        v=mean + c*math.sqrt(math.log(max(total_picks,1))/pulls)
        if v>bestv: bestv=v; best=f
    return best

st_holder=[None]   # ucb_select needs applicability of the live state (v0 simplification)

def solve_task_meta(name, budget=BUDGET, verbose=False, episode:Episode=None):
    tests=load_tests(name)
    src=open(f"{QB}/python_programs/{name}.py").read()
    st=TaskState(name,src,tests); st_holder[0]=st
    forms=[ENUMERATE(0),ENUMERATE(1),ENUMERATE(2),LOCALIZE(),RESET(),DEEPEN()]
    stats={}; total=0
    while not st.solved and st.tried<budget and time.time()<st.deadline:
        f=ucb_select(forms,stats,total)
        before=st.nfail
        delta=f.run(st,budget)
        # reward: verifier-gradient movement per unit energy; DEEPEN/RESET get the
        # movement they enable later via the next form's reward (credit assigned
        # locally in v0 — a known limitation, logged as such)
        energy=max(delta["candidates"],1)
        r=(before-delta["score_after"])/energy
        pulls,mean=stats.get(f.name,(0,0.0))
        stats[f.name]=(pulls+1, mean+(r-mean)/(pulls+1))
        total+=1
        if episode: episode.add(dict(form=f.name,candidates=delta["candidates"],
                                     before=before,after=delta["score_after"],reward=r,
                                     stratum=st.stratum,tried=st.tried))
        if verbose: print(f"  [{st.tried}] {f.name}: {before}->{delta['score_after']} r={r:.4g} {delta['notes']}",flush=True)
        # stuck detection: if the last 3 picks produced zero movement and no form
        # improved anything, force the epistemic move (deepen) if available
        if total>=3 and all(abs(v[1])<1e-12 for v in stats.values()):
            if DEEPEN().applicable(st):
                DEEPEN().run(st,budget); RESET().run(st,budget)
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
        ep=Episode(name,"ucb_v0")
        st=solve_task_meta(name,episode=ep)
        ep.dump(os.path.join(os.path.dirname(os.path.abspath(__file__)),"episodes","p1.jsonl"))
        (solved if st.solved else failed).append(name)
        print(f"{name:26s} {'SOLVED' if st.solved else 'no':6s} stratum={st.stratum} mutants={st.tried:6d} {time.time()-t0:6.1f}s",flush=True)
    print(f"\n=== P1 meta-controller v0 on QuixBugs: {len(solved)}/{len(solved)+len(failed)} solved ({len(skipped)} excluded) in {time.time()-t0:.0f}s ===")
    print("solved:",solved); print("unsolved:",failed)
