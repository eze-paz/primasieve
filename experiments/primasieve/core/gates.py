"""THE GATE HARNESS -- pre-registered gates, knockout ladders, sanity controls, standard baselines.

This is the asset the project has actually accumulated, and it was scattered across nine files' worth of
hand-written `PASS if ...` strings and four separate copies of the Memorize/Analogy baselines. The discipline
it encodes was paid for twice:

  STAGE 1 was KILLED by the nearest-neighbour ANALOGY baseline: the engine scored well and the baseline
  scored 0.951, at ceiling, so the task was memorizable and the engine's number meant nothing. Hence
  `Analogy` ships here, and every new testbed runs it BEFORE the engine.

  STAGE 3a scored 0.999 on COGS and looked finished. Stage 3b's KNOCKOUT LADDER showed ten of its eleven
  load-bearing structural pieces were hand-written, and the score survived only because the test set shared
  those assumptions. Hence `knockout_ladder` and `sanity_control` ship here, in that order:

      A SANITY CONTROL MUST PASS FIRST, or a failure is not evidence -- it is a broken harness.
      A FULLY RANDOM ADVERSARY ATTRIBUTES NOTHING, because it varies several dimensions at once. Only
      SINGLE-DIMENSION knockouts name the assumption that broke.

  STAGE 3d added the third: A CONTROL BUILT TO VARY STRUCTURE DOES NOT TEST ROBUSTNESS. The synthetic
  adversary reported confabulation 0.0000 even at 90% training corruption while real COGS reported 9.6%
  from 10%, because synthetic grammars contain no genuinely contested decisions. So `Gate` records what a
  gate does NOT cover, and `report` prints it.

Standing failure mode from arc 1, printed by `report` as a reminder because it recurs:
A CONTROL THAT CANNOT DISCRIMINATE ALWAYS PASSES."""
import collections


class Gate:
    """One pre-registered gate. `covers`/`not_covers` are free text and are printed, because Stage 3d's
    lesson is that a gate's blind spot is as load-bearing as its threshold."""

    def __init__(self, name, claim, threshold, direction=">=", not_covers=""):
        self.name, self.claim, self.threshold = name, claim, threshold
        self.direction, self.not_covers = direction, not_covers

    def verdict(self, value):
        ok = value >= self.threshold if self.direction == ">=" else value <= self.threshold
        return "PASS" if ok else "FAIL", ok


def report(results, title="GATES"):
    """results -> [(Gate, value)]. Prints the standard block and returns (n_passed, n_total)."""
    print(f"\n{title}")
    passed = 0
    for g, v in results:
        verdict, ok = g.verdict(v)
        passed += ok
        print(f"  {g.name:<8} {g.claim:<52} {v:>9.4f} {g.direction}{g.threshold:<7} {verdict}")
        if g.not_covers:
            print(f"           NOT covered by this gate: {g.not_covers}")
    print(f"  -> {passed}/{len(results)} gates passed")
    if passed < len(results):
        print("  (a control that cannot discriminate always passes -- check the sanity control before "
              "reading any failure)")
    return passed, len(results)


# ---------------------------------------------------------------- the standard baselines
class Memorize:
    """Exact lookup. The FLOOR: it measures how much of a test set is verbatim in train. If this scores at
    all highly, the split is leaking."""

    def __init__(self, train, key=None):
        k = key or (lambda x: x)
        self.m = {k(a): b for a, b, *_ in train}
        self.k = k

    def predict(self, x):
        return self.m.get(self.k(x))


class Analogy:
    """THE KNOCKOUT THAT KILLED STAGE 1. Copy the answer of the most token-similar training input; never
    abstains. Run it on every new testbed BEFORE the engine. If it scores well, the task is memorizable and
    the engine's number is not evidence of composition.

    Reference points to compare against: 0.951 exact match on English inflection (Stage 1, at ceiling, which
    is why Stage 1 died) versus 0.000 on all 21000 COGS gen items (Stage 3, which is why COGS was the right
    testbed)."""

    def __init__(self, train, tokenize=None, cap=300):
        self.tok = tokenize or (lambda s: s.split())
        self.train = [(self.tok(a), b) for a, b, *_ in train]
        self.cap = cap
        self.index = collections.defaultdict(list)
        for i, (t, b) in enumerate(self.train):
            for w in set(t):
                self.index[w].append(i)

    def predict(self, x):
        t = self.tok(x)
        ts = set(t)
        cand = collections.Counter()
        for w in ts:
            for i in self.index.get(w, ())[:2000]:
                cand[i] += 1
        best, bs = None, -1
        for i, _ in cand.most_common(self.cap):
            t2, b = self.train[i]
            u = len(ts | set(t2))
            s = (len(ts & set(t2)) / u if u else 0) * 10 - abs(len(t2) - len(t)) * 0.1
            if s > bs:
                bs, best = s, b
        return best


# ---------------------------------------------------------------- controls
def sanity_control(build, run, label="sanity control"):
    """MUST PASS FIRST. `build()` produces a case that matches the target's own structure but shares no
    surface with it (Stage 3b used COGS's structure with a wholly synthetic lexicon). If this fails, stop:
    nothing below it is evidence."""
    r = run(build())
    print(f"  {label}: {r}")
    return r


def knockout_ladder(dims, defaults, build, run, label="knockout"):
    """One case per NON-DEFAULT value, every other dimension pinned. This is what makes a failure
    ATTRIBUTABLE; a fully random draw differs on several dimensions at once and names nothing.

    dims -> {dimension: values}; defaults -> the target's own values.
    -> {(dimension, value): result}, and the caller reports which assumptions the engine depends on."""
    out = {}
    for d in sorted(dims):
        for v in dims[d]:
            if v == defaults[d]:
                continue
            overrides = dict(defaults)
            overrides[d] = v
            out[(d, v)] = run(build(overrides), f"{label} {d}={v}")
    return out
