"""GROW -- one loop over the two sound growth triggers the engine now owns.

The project has two DISTINCT, sound signals that the current system is inadequate, each at a different degree:

  REPRESENTATIONAL COLLISION (degree 4, core.grow + cogs_scope)  an external discriminator separates two inputs
      that the current representation forces to the SAME form -> the representation cannot EXPRESS the
      distinction. Response: extend the representation's TYPE (select from a hand-given extension library).

  CLOSURE STALL (degree 3, core.closure)  the library's reachable set (what it obtains by one composition) stops
      growing while tasks remain at distance infinity -> the library cannot REACH the target with the
      vocabulary it has. Response: SLEEP/invent a new combinator (grow the vocabulary within the type).

These compose into one controller, and the composition has CONTENT -- it is not just "try both". The priority
is fixed and load-bearing:

  REPRESENTATION BEFORE LIBRARY. A collision means the representation cannot hold the target distinction, so
  every reachability judgment about that distinction is unreliable until it is resolved -- you cannot ask "can
  the library reach this?" about a target the representation cannot even state. So the loop resolves collisions
  FIRST, then judges reachability, then invents. (The reverse order would invent combinators to chase a
  distinction the representation silently drops -- baroque structure swallowing a difference it cannot see.)

Each trigger keeps ITS OWN signal-ablation gate (the standing principle: every epistemic layer carries a gate
keyed to its own signal, and the terminal criterion is the floor). Ablate the discriminator and the collision
arm must fall silent; take the closure away and the stall arm loses its halt. The loop below fires the MINIMAL
sufficient growth at each step and HALTS honestly when neither signal is present -- it never grows for its own
sake, which is the failure mode (a proposer optimising coverage invents structure to swallow noise) the whole
project rejects."""


HALT = "HALT"


def grow(ops, budget):
    """Run the composed growth loop. `ops` supplies the two arms plus the base actions; `budget` is a
    mutable [int] charged by the arms (the self-model is knowledge the engine PAYS for). Returns a TRACE of
    (trigger, action) steps ending in ('none', HALT) -- the trace is the evidence of what fired and in what
    order, which is what the gates read.

    ops contract (all domain-free; the caller wires them to a thread):
      collision()      -> bool                      is the representation forcing one form on distinguishable inputs?
      extend()         -> bool                      adopt the minimal representation extension that resolves it
      reach()          -> ('solve', task) | 'stall' | 'done'
                                                    'solve': a task is one composition away, take it
                                                    'stall': closure grew as far as it can, tasks remain at inf
                                                    'done':  every task reached (or unreachable and probed)
      solve(task)      -> None                      realise the distance-1 task, growing the closure
      invent()         -> bool                      SLEEP: invent a combinator that reaches a stalled task
    """
    trace = []
    while budget[0] > 0:
        # 1. REPRESENTATION first: a collision makes reachability judgments unreliable.
        if ops.collision():
            ok = ops.extend()
            trace.append(("collision", "extend" if ok else "extend-failed"))
            if not ok:
                break                                 # cannot resolve the collision -> stop, do not paper over it
            continue
        # 2. REACHABILITY: the library's own self-model decides.
        r = ops.reach()
        if r == "done":
            trace.append(("none", HALT))              # no collision, nothing reachable-or-inventable -> honest halt
            break
        if r == "stall":
            ok = ops.invent()
            trace.append(("stall", "invent" if ok else "invent-failed"))
            if not ok:
                trace.append(("none", HALT))          # stalled and nothing invents -> abstain on the horizon
                break
            continue
        task = r[1]
        ops.solve(task)
        trace.append(("reachable", "solve"))
    return trace


def summarize(trace):
    """Compact tally of what the loop did, for the gates."""
    import collections
    c = collections.Counter(t for t, _ in trace)
    return dict(extend=sum(a == "extend" for _, a in trace),
                invent=sum(a == "invent" for _, a in trace),
                solve=sum(a == "solve" for _, a in trace),
                halted=trace[-1][1] == HALT if trace else False,
                first_growth=next((t for t, a in trace if a in ("extend", "invent")), None),
                triggers=dict(c))
