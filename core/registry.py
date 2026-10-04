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
    # ---- the fluency loop's FORM line (LOOP.md): F1 met on child-directed speech; realization closed at the novelty frontier
    "fluency_form": ["LOOP IT.7 REGISTER: PASS", "[holds]", "LOOP IT.11 TRIGRAM CONSTRAINT: PARTIAL"],
    # ---- KG multi-hop over Wikidata with cited edges (kg_multihop_prereg.md): run 4, CONFAB 0, 25/40 (needs network or cache)
    "kg_multihop": ["CONFAB (wrong value answered): 0", "KG MULTI-HOP: PASS"],
    # ---- tables and numbers (tables_numbers_prereg.md): induced operator lexicon, exact arithmetic, run 6
    "tables_numbers": ["TABLES AND NUMBERS: PASS", "CONFAB on held-out: 0"],
    # ---- F4: replies realized from epistemic frames over the unified loop (f4_prereg.md); uses the offline Wikidata cache
    "f4_dialogue": ["F4 EPISTEMIC FRAMES: PASS", "BARE ABSTAIN: 0"],
    # ---- general (general_prereg.md): worlds as data, composition across worlds, library in the loop, turns, research
    "worlds_general": ["GENERAL WORLDS: PASS", "TOTAL CONFAB: 0"],
    # ---- W6 (critical_prereg.md): contradictory claims and the record of a source; conjecture, never a vote
    "critical": ["W6 CRITICAL THINKING: PASS", "CONFAB: 0"],
    # ---- turns over longer dialogues (turns_prereg.md): competing antecedents, ellipsis of either argument, cross-world chains, controls
    "turns": ["TURNS BIND: PASS", "CONFAB: 0"],
    # ---- CHAT phase A (chat_prereg.md): the one door -- 200 utterances in one session, exceptions 0, bare abstain 0, fatal columns 0
    "chat": ["ONE DOOR: PASS", "CONFAB: 0"],
    # ---- CHAT phase B (chat_acts_prereg.md): the conversation as a world. SOUND, not PASS: knockout, continuity, round
    #      trip and the fatal columns hold; the acts bar (0.90) is missed at 0.71 because the engine has no act for a
    #      REQUEST it cannot perform (recorded gap, owner's call), plus WordNet-less thanks and two-structure yes/no forms
    "chat_acts": ["CONVERSATION WORLD: SOUND", "CONFAB: 0"],
    # ---- CHAT phase C (chat_prose_prereg.md): sentences over the understood structure, exact inverse, the user's words
    "chat_prose": ["PROSE FRAMES: PASS", "MISREPORT 0"],
    # ---- the REQUEST act (chat_request_prereg.md): an intent guess learned per skeleton from feedback, E-10's frames + their negative
    "chat_request": ["REQUEST ACT: PASS"],
    # ---- nolf incremental enumeration table (nolf_rebuild_prereg.md): the library pass's table is equivalent to a full build;
    #      the speedup missed its bar and is not registered
    "nolf_rebuild": ["INCREMENTAL TABLE at max_ops=2 (the library pass): EQUIVALENT"],
    # ---- EMERGENCE_PLAN.md S6 (negative_prereg.md): a denial of the engine's own answer is elimination; SOUND, not PASS:
    #      the registered "other hypothesis" bar is missed because a word bound from two examples is a COMMIT (a guess)
    "negative": ["S6 NEGATIVE EVIDENCE: SOUND", "REPEAT 0"],
    # ---- EMERGENCE_PLAN.md S8 (persist_prereg.md): evidence outlives the process; a fresh process re-induces and verifies
    "persist": ["S8 PERSISTENCE: PASS", "CONFAB: 0"],
    # ---- EMERGENCE_PLAN.md S5 (order_prereg.md): argument order and nesting as induced evidence in the exec world
    "order": ["S5 WORD ORDER: PASS", "CONFAB: 0"],
    # ---- EMERGENCE_PLAN.md S4 (transfer_prereg.md): a word moves between worlds by behaviour, held CONJECTURED
    "transfer": ["S4 TRANSFER: PASS", "LAUNDERING: 0"],
    # ---- EMERGENCE_PLAN.md S3 (depth_prereg.md): pairs of inners, the region rule, nesting as evidence in the graph
    "depth": ["S3 DEPTH: PASS", "CONFAB: 0"],
    # ---- EMERGENCE_PLAN.md S9 (goals_prereg.md): the engine's own questions by the split; SOUND (the recency knockout)
    "goals": ["S9 GOALS: SOUND"],
    # ---- EMERGENCE_PLAN.md S7 (dynamics_prereg.md): a world with time; SOUND (a one-transition guess is a COMMIT)
    "dynamics": ["S7 DYNAMICS: PASS"],
    # ---- together_prereg.md: everything on in one long conversation; a second session from the store; compounding counted
    "together": ["TOGETHER: PASS", "CONFAB: 0"],
    # ---- selfconfirm_prereg.md: a guess confirmed by an independent computation; circular routes refused
    "selfconfirm": ["SELF-CONFIRMATION: PASS"],
    # ---- research_prereg.md: an unread symbol becomes a fetch, a fetch becomes a world (recorded cache; NOT RUN without it)
    "research": ["RESEARCH BY ITSELF: PASS", "CONFAB: 0"],
    # ---- crosscheck_prereg.md: two fetched sources, corroborated / contested the W6 way, never voted (recorded caches)
    "crosscheck": ["CROSSCHECK: PASS"],          # PASS since conjectured_prereg.md: a one-transition program is CONJECTURED
    # ---- guess_prereg.md (GUESS_PLAN.md G1): a labelled guesser of mostly-true patterns, with a record (the crawl store)
    "guess": ["G1: PASS"],
    # ---- textmodel_prereg.md (GUESS_PLAN.md G4): a counting model of text -- cloze and word similarity (Wiktionary store)
    "textmodel": ["G4: PASS"],
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
