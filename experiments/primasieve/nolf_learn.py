"""PHASE 3 -- THE LEARNER SLOT (nolf_prereg.md). Imports core/ only; must never import a world.

What goes here, per the prereg: from (situation, tokens, truth) triples alone, induce word classes as
observational-equivalence classes over contexts (core.generate.SignatureBank), search (core.search) for the
smallest synchronous grammar over l0 terms whose derivations reproduce every observed truth value, fire
core.grow on a representational collision, and predict truth on new situations -- COMMIT / CONJECTURED / ABSTAIN
through core.verdict. The situation is opaque to this module except through the executable primitives in
core.primitives that can be applied to it.

STATUS (2026-09-06): NOT BUILT. This class abstains on every input so that nolf_run.py runs end-to-end and
prints the baseline bar. It is left this way deliberately rather than shipped as a bag-of-words-in-disguise:
a learner that "passes" by memorising token multisets is exactly what G3's baselines exist to expose."""


class Learner:
    def fit(self, train):
        self.n = len(train)
        return self

    def __call__(self, x):
        return None                                   # ABSTAIN: the honest output of a learner that does not exist yet
