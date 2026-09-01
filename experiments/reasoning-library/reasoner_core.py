"""Generic reasoner core — NO LLM anywhere. Domain-agnostic loop:

    expect -> simulate -> diff -> reconcile -> (acquire when stuck) -> repeat

A Domain supplies exact machinery (interpreter, colorimetry, CAS, ...); the core supplies the
reasoning: monotone hill-climb over enumerable moves ordered by a divergence-localized prior,
with an EPISTEMIC hatch — when the move space is exhausted or underdetermined, `acquire()`
fetches external experience (sample base / web) and INDUCES new constraints/operators, then
search continues. This is the human debug loop: sub in values, propagate, find the divergence,
make the smallest reconciling change; if you lack experience, go look at working examples.

Interface a domain implements:
    initial()            -> state
    simulate(state)      -> observation (exact execution: run tests, compute contrast, ...)
    diff(obs)            -> (score, divergence)   score: 0 = solved, lower = better
    moves(state, div)    -> iterator of (desc, candidate_state), smallest/likeliest first
    acquire(state, div)  -> str description if it learned something (mutates domain), else None
"""
import time

def reason(domain, budget=100000, verbose=False):
    """Monotone best-improvement search with epistemic acquisition. Returns (state, score, trace)."""
    t0=time.time()
    state=domain.initial()
    score,div=domain.diff(domain.simulate(state))
    trace=[("init",None,score)]; tried=0; acquired=0
    while score>0 and tried<budget:
        # SOLVE-FIRST STEEPEST SCAN: evaluate the whole move set before accepting anything.
        # Greedy first-improvement strands the search (accept a partial fix -> the true
        # single-site fix no longer completes from there). Scanning fully guarantees that
        # any single move which fully reconciles is found before we commit to a compromise.
        improved=False; best=(score,None,None,None)
        for desc,cand in domain.moves(state,div):
            tried+=1
            s2,d2=domain.diff(domain.simulate(cand))
            if s2<best[0]: best=(s2,desc,cand,d2)
            if s2==0 or tried>=budget: break
        if best[1] is not None:
            trace.append((best[1],score,best[0]))
            if verbose: print(f"  [{tried}] {best[1]}: {score:.4g} -> {best[0]:.4g}",flush=True)
            state,score,div=best[2],best[0],best[3]; improved=True
        if score==0: break
        if not improved:                       # stuck: spend an EPISTEMIC move
            got=domain.acquire(state,div) if hasattr(domain,"acquire") else None
            if got:
                acquired+=1
                trace.append((f"ACQUIRE: {got}",score,score))
                if verbose: print(f"  ACQUIRE: {got}",flush=True)
                score,div=domain.diff(domain.simulate(state))   # constraints may have changed
                continue
            break                              # truly out of moves and out of experience
    return state,score,{"trace":trace,"tried":tried,"acquired":acquired,"secs":time.time()-t0}
