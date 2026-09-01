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

EPIST_EVERY = 2     # after K consecutive zero-movement ENUMERATE picks, force the epistemic move

def solve_task_meta(name, budget=BUDGET, verbose=False, episode:Episode=None):
    """v1: bandit over ENUMERATE strata only; epistemic forms are forced moves, not arms.
    Sequence credit: a solve credits the last K stratum-picks (eligibility trace)."""
    tests=load_tests(name)
    src=open(f"{QB}/python_programs/{name}.py").read()
    st=TaskState(name,src,tests); st_holder[0]=st
    arms=[ENUMERATE(0),ENUMERATE(1),ENUMERATE(2)]
    stats={}; total=0; stuck=0; trace=[]   # trace: recent (form_name, energy, movement) for credit
    while not st.solved and st.tried<budget and time.time()<st.deadline:
        f=ucb_select(arms,stats,total)
        before=st.nfail
        delta=f.run(st,budget)
        energy=max(delta["candidates"],1)
        moved = delta["score_after"]<before
        r=(before-delta["score_after"])/energy
        pulls,mean=stats.get(f.name,(0,0.0))
        stats[f.name]=(pulls+1, mean+(r-mean)/(pulls+1))
        total+=1
        trace.append((f.name,energy,r))
        if episode: episode.add(dict(form=f.name,candidates=delta["candidates"],
                                     before=before,after=delta["score_after"],reward=r,
                                     stratum=st.stratum,tried=st.tried))
        if verbose: print(f"  [{st.tried}] {f.name}: {before}->{delta['score_after']} r={r:.4g}",flush=True)
        if st.solved:
            # sequence credit: the winning pick shares its reward with the previous picks
            K=3
            for i,(fn,en,_r) in enumerate(trace[-K-1:-1]):
                pl,mn=stats.get(fn,(0,0.0))
                if pl: stats[fn]=(pl, mn+(_r if en==0 else (before-0)/max(en,1))*0.5/(pl))  # bounded nudge
            break
        stuck = stuck+1 if not moved else 0
        if stuck>=EPIST_EVERY:
            stuck=0
            if st.stratum<2:
                DEEPEN().run(st,budget)          # stratum += 1
                RESET().run(st,budget)           # reset-to-pristine + re-localize
                if episode: episode.add(dict(form="DEEPEN+RESET",candidates=0,
                                             before=before,after=st.nfail,reward=0.0,
                                             stratum=st.stratum,tried=st.tried))
            else:
                LOCALIZE().run(st,budget)        # refresh evidence at max stratum
                if episode: episode.add(dict(form="LOCALIZE",candidates=len(st.tests),
                                             before=before,after=st.nfail,reward=0.0,
                                             stratum=st.stratum,tried=st.tried))
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
