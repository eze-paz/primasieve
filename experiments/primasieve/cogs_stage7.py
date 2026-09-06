"""STAGE 7 -- COMPOSE the two growth triggers (closure stall + representational collision) into ONE loop.

core.grow runs both arms with a fixed, load-bearing priority: REPRESENTATION extension (a collision, degree 4)
before LIBRARY invention (a closure stall, degree 3), because a collision means the representation cannot even
STATE the target distinction, so reachability judgments about it are unreliable until it is resolved.

The two arms are the real mechanisms:
  COLLISION arm  cogs_scope: an external truth-discriminator separates the two scope readings while the flat
                 representation forces one form -> extend the representation (adopt scope_order).
  LIBRARY arm    core.closure over a tiny op-library: tasks reachable by one composition are solved and grow
                 the closure; a task no composition reaches STALLS the closure -> SLEEP/invent the primitive.

Gates:
  G7a  on a pool where BOTH signals are present, the loop fires extend exactly once AND invent exactly once,
       solves the reachable tasks, and HALTS honestly.
  G7b  ORDER: the first growth action is the representation extension, not the library invention.
  G7c  INERTNESS: on a pool with no collision and no unreachable task, no growth fires (only solves, then halt).
  G7d  SIGNAL-ABLATION (collision arm): ablate the discriminator -> no collision -> extend never fires, while
       the library arm still solves and invents. The collision growth is driven by the signal, not by priors.
  G7e  HONEST HALT / ABSTAIN: with invention disabled, a stalled unreachable task makes the loop ABSTAIN
       (invent-failed -> HALT), never spin -- the closure's contribution is the halt (E-6 established memory
       alone never halts).

Usage:  python cogs_stage7.py"""
import os, sys, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.grow import grow, summarize, HALT
from core.closure import Closure
from cogs_scope import R0, R1, make_items, eval_form, reading_from_R1
from core.registry import selfcheck


# ---------------------------------------------------------------- the library arm (arithmetic over a sample)
SAMPLE = (1, 2, 3, 4, 5)
BASE = {"inc": (lambda x: x + 1), "dbl": (lambda x: 2 * x)}
CANDIDATES = {"sq": (lambda x: x * x), "dec": (lambda x: x - 1)}   # inventable primitives (the SLEEP pool)


def sig(fn):
    try:
        return tuple(fn(x) for x in SAMPLE)
    except Exception:
        return None


def compose(a, b):
    return lambda x: a(b(x))


TASKS = {"x+2": sig(lambda x: x + 2), "x+3": sig(lambda x: x + 3), "x*x": sig(lambda x: x * x)}
#         reachable by inc.inc      reachable after x+2 is added   needs the invented primitive `sq`


class World:
    def __init__(self, discriminator=True, can_invent=True, tasks=None):
        self.rep = "flat"
        self.discriminator = discriminator
        self.can_invent = can_invent
        self.tasks = dict(TASKS if tasks is None else tasks)
        rng = random.Random(7)
        self.scope_train = make_items(rng, 200)
        self.scope_test = make_items(rng, 200)
        self.extended = False
        self.lib = dict(BASE)
        self.solved = set()
        self.closure = Closure(compose, sig)
        for name, fn in self.lib.items():
            self.closure.add(name, fn, self.lib)
        self.budget = [200000]

    # -- collision arm -------------------------------------------------------
    def _form(self):
        return R1 if self.rep == "scoped" else R0

    def _reading_of(self):
        return reading_from_R1 if self.rep == "scoped" else (lambda f: None)

    def _has_collision(self):
        if not self.discriminator:
            return False
        by = {}
        for it in self.scope_train:
            by.setdefault((self._form()(it), frozenset(it["R"]), tuple(it["D"])), set()).add(it["truth"])
        return any(len(v) > 1 for v in by.values())

    def _acc(self, form, reading_of):
        ok = 0
        for it in self.scope_test:
            f = form(it)
            ok += (eval_form(f, reading_of(f), it["C"], it["D"], it["R"]) == it["truth"])
        return ok / len(self.scope_test)

    def collision(self):
        return self._has_collision()

    def extend(self):
        # adopt the scope extension iff it resolves the collision AND raises held-out truth accuracy
        base = self._acc(R0, lambda f: None)
        self.rep = "scoped"
        if not self._has_collision() and self._acc(R1, reading_from_R1) > base + 0.05:
            self.extended = True
            return True
        self.rep = "flat"
        return False

    # -- library arm ---------------------------------------------------------
    def reach(self):
        pending = [t for t in self.tasks if t not in self.solved]
        if not pending:
            return "done"
        for t in pending:
            if self.closure.distance(self.tasks[t]) == 1:
                return ("solve", t)
        return "stall"                          # nothing reachable by one composition -> the closure has stalled

    def solve(self, task):
        # realise the task as a new library entry (its witness), growing the closure
        self.solved.add(task)
        w = self.closure.witness(self.tasks[task])
        name = "t_" + task
        self.lib[name] = _lookup(self, self.tasks[task])
        self.closure.add(name, self.lib[name], self.lib)

    def invent(self):
        if not self.can_invent:
            return False
        # SLEEP: adopt the candidate primitive that puts a stalled task within reach (sound: it must actually
        # reach). Triggered by the stall, exactly as meta_e5 invents from a recurring residual.
        pending = [t for t in self.tasks if t not in self.solved]
        for cname, cfn in CANDIDATES.items():
            if cname in self.lib:
                continue
            if any(sig(cfn) == self.tasks[t] for t in pending):
                self.lib[cname] = cfn
                self.closure.add(cname, cfn, self.lib)
                return True
        return False


def _lookup(world, target_sig):
    """A function with the target signature: prefer an existing library fn, else its pair witness."""
    for fn in world.lib.values():
        if sig(fn) == target_sig:
            return fn
    w = world.closure.witness(target_sig)
    if w and w[0] != "entry":
        a, b = w
        return compose(world.lib[a], world.lib[b])
    return world.lib[w[1]]


def run(world):
    def ops():
        pass
    ops.collision = world.collision
    ops.extend = world.extend
    ops.reach = world.reach
    ops.solve = world.solve
    ops.invent = world.invent
    return grow(ops, world.budget)


if __name__ == "__main__":
    selfcheck(__file__)
    print("STAGE 7 -- one loop over BOTH growth triggers (closure stall + representational collision).")
    print("Priority: REPRESENTATION extension before LIBRARY invention.\n")

    # G7a / G7b -- both signals present
    w = World()
    tr = run(w)
    s = summarize(tr)
    print("G7a/G7b  full pool (collision + a stall-only task present):")
    print("  trace:", " -> ".join(f"{t}:{a}" for t, a in tr))
    print(f"  extend {s['extend']}  invent {s['invent']}  solve {s['solve']}  halted {s['halted']}  "
          f"first-growth {s['first_growth']}")
    g7a = s["extend"] == 1 and s["invent"] == 1 and s["halted"] and w.solved == set(TASKS)
    g7b = s["first_growth"] == "collision"
    print(f"  G7a both arms fire + halt + all tasks solved -> {'PASS' if g7a else 'FAIL'}")
    print(f"  G7b representation extension BEFORE library invention -> {'PASS' if g7b else 'FAIL'}")

    # G7c -- inertness: no collision (discriminator off) AND no unreachable task (drop the invent-needing one)
    reachable_only = {"x+2": TASKS["x+2"], "x+3": TASKS["x+3"]}
    w2b = World(discriminator=False, tasks=reachable_only)
    tr2 = run(w2b)
    s2 = summarize(tr2)
    g7c = s2["extend"] == 0 and s2["invent"] == 0 and s2["halted"]
    print(f"\nG7c  INERT pool (no collision, all tasks reachable): extend {s2['extend']} invent {s2['invent']} "
          f"halted {s2['halted']} -> {'PASS' if g7c else 'FAIL'}")

    # G7d -- discriminator ablation: collision arm must fall silent, library arm still works
    w3 = World(discriminator=False)
    tr3 = run(w3)
    s3 = summarize(tr3)
    g7d = s3["extend"] == 0 and s3["invent"] == 1 and s3["halted"]
    print(f"\nG7d  DISCRIMINATOR ABLATED: extend {s3['extend']} (must be 0) invent {s3['invent']} "
          f"halted {s3['halted']} -> {'PASS' if g7d else 'FAIL'}")
    print("     -> the collision growth is driven by the discriminator signal; remove it and only the library")
    print("        arm fires. Each arm carries its own signal-ablation gate inside the one loop.")

    # G7e -- honest halt/abstain when invention is disabled
    w4 = World(discriminator=False, can_invent=False)
    tr4 = run(w4)
    s4 = summarize(tr4)
    g7e = s4["halted"] and ("x*x" not in w4.solved) and any(a == "invent-failed" for _, a in tr4)
    print(f"\nG7e  INVENTION DISABLED: the stalled unreachable task -> {[a for t,a in tr4 if t=='stall']}, "
          f"then HALT (abstain), x*x unsolved={'x*x' not in w4.solved} -> {'PASS' if g7e else 'FAIL'}")

    allpass = g7a and g7b and g7c and g7d and g7e
    print(f"\nSTAGE 7 COMPOSED GROWTH LOOP: {'PASS' if allpass else 'FAIL'}")
    print("  One loop: representational collision (degree 4) resolved before closure stall (degree 3),")
    print("  each fired only on its own signal, halting honestly when neither is present.")
