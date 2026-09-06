"""CLOSURE -- the engine's SELF-MODEL: what its own library can reach by composition, exactly, without an oracle.

`core.generate` grows a library; `core.select` chooses among moves when the space is too big to enumerate.
Neither knows what the library can CURRENTLY reach. This module is that knowledge: the set of signatures
obtainable as an entry or as one ordered composition of two entries, maintained incrementally, and a schedule
that reads it. It is domain-free -- it takes the thread's own `compose` and `sig` functions -- and it is SOUND
by construction, because membership is exact full-signature equality (no partial credit, no score).

MEASUREMENTS this module carries (emergence thread, E-5 -> E-6; em_curriculum.py, em_closure.py):

  A SOUND BINARY VERDICT GIVES A CURRICULUM NOTHING TO CLIMB (E-5, NULL). Learning-progress bandits (plain UCB
  on progress, and core.select's cost-aware form) did NOT beat a shuffled round-robin on a 26-task pool with 6
  dead ends: every failed attempt costs the same and returns the same 0, so "not yet reachable" and "never
  reachable" are indistinguishable. The cost-aware form fell into the cheap-mastered-task trap (54k-107k
  zero-progress re-probes; max k 2 on its worst seed). The only graded signal present -- partial component
  match -- was DECEPTIVE (the dead ends share a component with real tasks).

  THE CLOSURE IS THE GRADED, SOUND SIGNAL THE ENGINE ALREADY OWNS (E-6, PASS on every pre-registered kill).
  Distance to a task = 0 solved / 1 one composition away / inf. A policy reading it -- distance-1 tasks first,
  blind search at most ONCE per task ever (blind is deterministic and library-independent, so a failure is
  permanent knowledge), HALT when nothing is at distance 1 and everything has been probed -- reached all 20
  family tasks on every seed with NO authored order (a shuffled sweep missed 2), probed each dead end EXACTLY
  once (authored sweep: 38 probes; memory-only knockout: 293-357), and halted with precisely the dead ends
  unsolved at 76k-101k of a 320k budget. 0 unsound distance-1 calls; the deceptive partial matches never
  registered. Closure maintenance and every distance query were CHARGED to energy (890-978 evals).

  MEMORY OF FAILURES ALONE IS NOT ENOUGH. The BLIND-ONCE knockout (remember blind failures, no closure) also
  reached everything, but never halted and took 4-5x the energy to the top task: the closure's contribution is
  prioritisation and the halt, not reachability.

  THE AUTHORED ORDER IS STILL FAR CHEAPER TO FIRST REACH (recorded, not spun). It knows the base task is first
  and pays no blind failure on the way (energy-to-k=20: 431). The closure arm pays one full blind failure per
  task the presentation puts before the base: 75-98x above authored, past the pre-registered 10x line. It wins
  only on the long horizon, where the authored sweep burns 6 dead-end probes per cycle forever.

  PREDICTION MISS: the closure cascade does NOT solve in ascending order (rho ~0.1). The ascending order seen
  in E-5 was a property of round-robin sweeps. Recorded as a miss.

  WHAT IT ALSO GIVES FOR FREE: an exact SLEEP/invent trigger (closure growth stalls with tasks still at inf --
  the compounding boundary, measured rather than guessed) and an honest ABSTAIN for horizon tasks.

  SCOPE: one family that closes under composition by construction + 6 distractors; pair-closure (depth 1).
  Families that collapse extensionally (E-2a) and the depth-3 blind horizon are untouched."""

INF = float("inf")


class Closure:
    """sig -> witness for every signature an entry or an ordered pair of entries reaches. `compose(a, b)` and
    `sig(item)` are the thread's own; `sig` may return None for an undefined composition. Every signature
    computed and every distance query increments `cost`, in the thread's energy unit -- the self-model is
    knowledge the engine PAYS for, never free."""

    def __init__(self, compose, sig, pair_cache=None):
        self.compose, self.sig = compose, sig
        self.sigs = {}; self.names = []; self.cost = 0
        self._pairs = pair_cache if pair_cache is not None else {}     # wall-time only; does not change cost

    def _pair(self, a, b, lib):
        key = (a, b)
        if key not in self._pairs:
            fr = self.compose(lib[a], lib[b]); self._pairs[key] = (fr, self.sig(fr))
        return self._pairs[key]

    def add(self, name, item, lib):
        """register a new entry: its own signature + every NEW ordered pair (with existing entries and itself)."""
        self.cost += 1
        s = self.sig(item)
        if s: self.sigs.setdefault(s, ("entry", name))
        for other in self.names + [name]:
            for a, b in {(name, other), (other, name)}:
                self.cost += 1
                _, s2 = self._pair(a, b, lib)
                if s2: self.sigs.setdefault(s2, (a, b))
        self.names.append(name)

    def distance(self, target_sig):
        self.cost += 1
        return 1 if target_sig in self.sigs else INF

    def witness(self, target_sig):
        return self.sigs.get(target_sig)


HALT = None


def schedule(closure, unsolved, target_sig, probed):
    """The E-6 policy. -> (name, mode) or HALT.
    mode 'closure'      a task at distance 1: guaranteed solvable by one composition, take it first
    mode 'blind-probe'  nothing at distance 1: the first unsolved task never blind-probed (blind runs ONCE, ever)
    HALT                nothing at distance 1 and everything probed: nothing further can succeed -- stop spending.
    `unsolved` is in the thread's presentation order (no authored order is assumed or needed)."""
    near = [n for n in unsolved if closure.distance(target_sig(n)) == 1]
    if near:
        return near[0], "closure"
    far = [n for n in unsolved if n not in probed]
    if far:
        return far[0], "blind-probe"
    return HALT
