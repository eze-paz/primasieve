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
    # ---- the unnamed executable inventory (given #4): a ledger claim, not a capability claim ---------------------
    "primitives": ["PRIMITIVE INVENTORY: SOUND"],
    "emergence": ["`x * x` (seen 6x)", "[7019 exprs", "[3008 exprs"],
    # ---- perception rung 1 (p1-p9; the rung CLOSES at p9) -----------------------------------------------------
    "percept_p7": ["0 confabulation, never"],
    "percept_p8": ["RESULT: PASS. ACTIVE(COLLECT)", "(0 confab): OK"],
    "percept_p9": ["RUNG 1 END CONDITION MET"],
    # ---- emergence E-6: the closure self-model (core/closure.py); E-5's null is the docstring's first lesson ---
    "em_closure": ["E6 CLOSURE CURRICULUM: PASS"],
    # ---- emergence E-7: the third verdict state (core/verdict.py ATTRIBUTED); utility bar reported, not claimed --
    "em_attributed": ["E7 ATTRIBUTED STATE: SOUND"],
    # ---- emergence E-9: the fourth verdict state (core/verdict.py CONJECTURED) -- a guess with a correction channel
    "em_conjecture": ["E9 CONJECTURED STATE: SOUND"],
    # ---- emergence E-10: the unified answer loop (core/resolve.py) -- "what is a dog" from an empty lexicon; R7 reported
    "em_resolve": ["E10 RESOLVE LOOP: SOUND"],
    # ---- emergence E-8: corpus acquisition (WordNet first-sense, both directions) + the chat acceptance test ------
    "em_corpus": ["WORDNET CORPUS ACQUISITION: SOUND"],
    "validate_chat": ["CHAT VALIDATION: PASS"],
    # ---- the E-series mechanisms kept live because core/ now holds them ----------------------------------------
    "meta_e5": ["CLOSED: recurring residual -> anti-unify -> NEW PRIMITIVE crystallized + generalizes"],
    "meta_e6": ["K2 stateless: ACTIVE 6.0 vs RAND-SHORT 44.0"],
    "meta_e7": ["'*' -> identify  cover 9/9 confab 0"],
    # ---- grounded language / dialogue -------------------------------------------------------------------------
    "phase5c": ["ASK the question that splits it"],
    # ---- Stage 4a: constructions on SLOG (relative clauses, wh-questions, center-embedding) --------------------
    "cogs_stage4a": ["4a SLOG CONSTRUCTIONS: PASS"],
    "cogs_stage4b": ["4b OPEN VOCABULARY: PASS"],
    "cogs_stage4c": ["4c REFERENCE: PASS"],
    "cogs_stage4d": ["4d GENERATION: PASS"],
    "cogs_stage5": ["5 CONSTRUCTIONS: PASS", "marker-recall 1.0000", "IDENTICAL"],
    "cogs_stage6": ["DEGREE 4 (representation extension by collision-driven selection): PASS",
                    "collision under ablation: none", "held-out truth accuracy WITH the extension: 1.000"],
    "cogs_stage7": ["STAGE 7 COMPOSED GROWTH LOOP: PASS", "first-growth collision"],
    "cogs_stage8": ["STAGE 8 MEANING-FIRST FLUENT REALIZATION: PASS", "CONFABULATION 0/1800"],
    # ---- Stage 9: FORM from raw text -- registered NULL (whole-sentence skeletons memorize; see cogs_stage9_prereg.md)
    "cogs_stage9": ["STAGE 9 FORM FROM RAW TEXT: NULL", "CONTROL DISCRIMINATES"],
    # ---- Stage 9b: compositional form -- registered NULL (64% held-out OOV; uniform symbol code loses to unigram on known)
    "cogs_stage9b": ["STAGE 9b COMPOSITIONAL FORM: NULL", "CONFAB 0"],
    # ---- the fluency loop (LOOP.md): F1 met on child-directed speech; form-only generation closed at the novelty frontier
    "loop_it7_register": ["LOOP IT.7 REGISTER: PASS", "[holds]"],
    "loop_it11_trigram": ["LOOP IT.11 TRIGRAM CONSTRAINT: PARTIAL"],
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
