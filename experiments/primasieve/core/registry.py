"""THE REGISTRY OF PUBLISHED CLAIMS -- one source of truth for "what did this experiment establish".

Every live experiment file registers the computed verdict line(s) its published result rests on. Two things
read this registry:

  1. THE FILE ITSELF, on every run. `selfcheck(__file__)` installs a tee on stdout and, at exit, checks that
     the run's output still contains its registered claims, printing one PUBLISHED-CLAIM line. A result that
     silently stops reproducing is caught by the file that owns it, not months later by someone else.
  2. `core_selftest.py` C2, which re-runs the registered modules and requires the same claims. So there is
     ONE list to maintain, and adding an experiment to the live surface means adding its claim here.

The needles are COMPUTED verdict lines -- a string the code prints only when the measured condition holds --
never static banner text. A needle that would print regardless of the outcome protects nothing, and Stage 3d's
lesson applies to gates as much as to models: a control that cannot discriminate always passes."""
import atexit
import io
import os
import sys

PUBLISHED = {
    # ---- current frontier -------------------------------------------------------------------------------------
    "l0": ["PASSES: all 6 parametric operators", "trunc     with abs/sign: E=109203"],
    "emergence": ["`x * x` (seen 6x)", "[7019 exprs", "[3008 exprs"],
    # ---- perception rung 1 (p1-p9; the rung CLOSES at p9) -----------------------------------------------------
    "percept_p7": ["0 confabulation, never"],
    "percept_p8": ["RESULT: PASS. ACTIVE(COLLECT)", "(0 confab): OK"],
    "percept_p9": ["RUNG 1 END CONDITION MET"],
    # ---- the E-series mechanisms kept live because core/ now holds them ----------------------------------------
    "meta_e5": ["CLOSED: recurring residual -> anti-unify -> NEW PRIMITIVE crystallized + generalizes"],
    "meta_e6": ["K2 stateless: ACTIVE 6.0 vs RAND-SHORT 44.0"],
    "meta_e7": ["'*' -> identify  cover 9/9 confab 0"],
    # ---- grounded language / dialogue -------------------------------------------------------------------------
    "phase5c": ["ASK the question that splits it"],
    # ---- Stage 4a: constructions on SLOG (relative clauses, wh-questions, center-embedding) --------------------
    "cogs_stage4a": ["4a SLOG CONSTRUCTIONS: PASS"],
    "cogs_stage4b": ["4b OPEN VOCABULARY: PASS"],
}


def claims_for(path_or_module):
    name = os.path.splitext(os.path.basename(path_or_module))[0]
    return name, PUBLISHED.get(name, [])


class _Tee(io.TextIOBase):
    def __init__(self, real):
        self.real, self.buf = real, io.StringIO()

    def write(self, s):
        self.buf.write(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()


def selfcheck(path):
    """Call once at the top of an experiment's __main__. Verifies the published claims at exit."""
    name, claims = claims_for(path)
    if not claims:
        return
    tee = _Tee(sys.stdout)
    sys.stdout = tee

    def _verify():
        sys.stdout = tee.real
        out = tee.buf.getvalue()
        missing = [c for c in claims if c not in out]
        if missing:
            print(f"\nPUBLISHED-CLAIM CHECK [{name}]: FAIL -- no longer reproduced: {missing}")
        else:
            print(f"\nPUBLISHED-CLAIM CHECK [{name}]: OK ({len(claims)} claim{'s' if len(claims) != 1 else ''})")

    atexit.register(_verify)


def verify_output(name, out):
    """For core_selftest: -> [(claim, found)] for a module's captured output."""
    return [(c, c in out) for c in PUBLISHED.get(name, [])]
