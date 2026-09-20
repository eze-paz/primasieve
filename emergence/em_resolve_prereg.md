# E-10 — THE UNIFIED ANSWER LOOP: research every symbol, intent by affordance, answer by certificate

Committed BEFORE any E-10 code. Implements no_paradigm_prereg.md §5 (the one entry point, `core/resolve.py`)
for the case the owner named as the acceptance test: the engine sees the string "What is a dog?" knowing no
word, and must (1) research every symbol, (2) derive the intent, (3) answer with a cited source — with no
authored behaviour: no question-form regex, no stopword list, no "what → definition" rule, no reply template
keyed on a question type.

## The mechanism, stated so it can be judged
1. SEGMENT   symbols = maximal runs of one Unicode character category (letter / digit / punctuation / space;
             the category table is third-party data, not an authored delimiter list). Spaces are dropped as a
             category, not as a list.
2. RESOLVE   EVERY symbol is looked up in every designated source, offline first (kb_sources.research_gloss
             over WordNet all-POS and KAIKKI all-POS). A symbol's READINGS are: (i) bindings to executable
             primitives of a shape the surrounding symbols can feed (core/primitives.candidates; only where a
             verified ledger binding exists — this loop invents none); (ii) bindings to a predicate of an
             ATTACHED world's lexicon, if a world is attached; (iii) quotable glosses with certificates. A symbol
             with no reading anywhere is UNKNOWN and reported as such with the sources consulted.
3. TOPIC     the symbol the utterance is ABOUT is the unique most SPECIFIC symbol: specificity = how many of the
             dictionary's definitions mention it (document frequency over the offline sources — data, not a list;
             the same base-rate key E-9 used). A tie at the minimum → ASK which. This is the one bias in the
             loop and it is declared as such.
4. INTENT    by AFFORDANCE: the candidate actions are exactly the primitives whose PRECONDITIONS the topic's
             readings satisfy — POINT needs a world binding (ii), COMPUTE needs an executable binding (i) with
             typed arguments present, DEFINE needs a quotable gloss (iii). The survivor set over actions goes
             through core.verdict: one → COMMIT to that action; several → the CHEAPEST REVERSIBLE one is executed
             CONJECTURED (E-9) and the alternatives are named; none → refuse, naming every source consulted.
5. ANSWER    the action's output shown AS ITSELF: for DEFINE, the gloss(es) verbatim with source and sense count,
             held ATTRIBUTED; for POINT, the referent set; for COMPUTE, the value with its derivation. No sentence
             is composed by the engine; the certificate IS the response.
6. LEARN     (utterance, action, verdict) is stored as an observation. After ≥2 accepted utterances that share a
             skeleton and differ in the topic, anti-unification (meta_e5 / core.generate SLEEP) yields a FRAME
             (skeleton → action) held CONJECTURED; a frame's guess is used before affordance from then on and is
             retracted on `wrong` like any conjecture. This step is built but its long-run behaviour is measured
             only at the smallest scale here (two accepted examples → one frame).

## What is given (must pass the primitive criterion of no_paradigm_prereg §0)
The Unicode category table; the designated source list with per-source metadata; `core/primitives` with its
forcing ledger; `core/verdict` (COMMIT / ATTRIBUTED / CONJECTURED / ABSTAIN, certificates); the two feedback
words already in the chat (`wrong`, `correct`); the action-precondition table, which is the inventory of what the
engine CAN DO (three entries, each a precondition on reading TYPE, none on any word).

## Gates (pinned; each demonstrated to FAIL on today's main before the change, per the META-RULE)
R1 COLD START: with an EMPTY lexicon and no frames, "What is a dog?" → DEFINE(dog), answer = WordNet/KAIKKI
   gloss(es) with source, state ATTRIBUTED. Today's main returns "I have never seen ['what','dog'] anywhere" (an
   ABSTAIN after research reduced everything to shapes). Must also hold for "define dog", "dog?", "what does
   lofty mean" — none of these forms is listed anywhere.
R2 AFFORDANCE, NOT WORDS: with a world attached and "red" world-learned, "which one is red" has TWO feasible
   actions (POINT, DEFINE); the loop must execute the cheapest reversible one CONJECTURED and name the other, or
   ASK — never silently pick. With no world attached the same string yields DEFINE alone. The behaviour changes
   with the AFFORDANCES, not with the words.
R3 SOURCE ABLATION: remove every source → "What is a dog?" must REFUSE naming the sources consulted; zero
   glosses invented. (no_paradigm NP-5 in this loop's terms.)
R4 NO QUESTION FORMS: static gate — no string literal in `core/resolve.py` is a word of any language or a
   punctuation glyph in a lookup position (extends core/primitives.name_keyed_lookups to this file). The loop
   must not know "what", "is", "?", "define".
R5 TOPIC IS DATA-DERIVED: shuffle the dictionary (permute glosses across headwords) → the topic follows the
   permuted specificity, and the answer cites the permuted gloss. The engine reads the sources, not the spelling.
R6 FIRST FRAME: after "what is a dog" and "what is a cat" are both accepted, "what is a tree" is answered by the
   FRAME (recorded as such) and gives the same action; `wrong` on it retracts the frame with cascade (E-9 rules).
R7 HONEST OVERGENERALIZATION: "I hate my dog" at cold start resolves to DEFINE(dog) — the only affordance — and
   is reported CONJECTURED-by-affordance, not COMMIT. This is the "goed" moment and it must be visible, not hidden.
R8 FATAL COLUMNS: CONFABULATION 0 (no COMMIT the sources or world contradict), LAUNDERING 0, MISATTRIBUTION 0
   over the whole script.

## Predictions (committed)
R1–R8 pass offline. Known weakness, stated: TOPIC by specificity will pick a rare function word over a common
noun in some utterances ("whom is a dog?") — reported as a limit of the bias, not patched with a list. The frame
mechanism (R6) is demonstrated at n=2 only; its generalization is Phase 3's business.

## Files
`core/resolve.py` (steps 1–6, imports core/ and the source modules, never a world), `emergence/em_resolve.py`
(the gates; registered claim `E10 RESOLVE LOOP: PASS`), and the wiring in `en_server._diagnose`: the resolver is
consulted BEFORE the OUT-OF-WORLD / ABSTAIN replies, so the chat answers "what is a dog" with a citation instead
of refusing. `en_server`'s routing ladder is not deleted in this pass (the peer prereg's larger absorption); the
resolver is inserted at the point where today's chat gives up.
