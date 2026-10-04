# GUESS PLAN -- growing toward broad intelligence by LABELLED guessing (owner's choice, 2026-10-04)

The owner chose the second path: grow the engine itself toward LLM-level breadth, rather than pairing it with a
language model. The project has so far refused every claim it could not back up, and the gloss line measured the price:
prose reads at 0.34, and "learning from novels remains closed under the honesty rule" (gloss_width_prereg.md). This
plan does not drop the honesty rule; it SPLITS it:

- **What the engine knows** stays exactly as it is: COMMIT / ATTRIBUTED only with a certificate, CONFAB fatal.
- **What the engine guesses** becomes a first-class output, under three rules:
  1. **Always labelled.** A guess is said as a guess ("My guess: ..."), never in the voice of a fact. A guess said as a
     fact is CONFAB, exactly as before -- the fatal column moves to the label, it does not disappear.
  2. **Always with its reason.** Every guess names the pattern it came from, with its counts ("41 of the 42 places
     located in Bavaria are in Germany"). Counts, never a probability.
  3. **Earned standing.** The guesser is a SOURCE with a ledger record (core/ledger.py, W6): every time an oracle (a
     fetched source, the user, a computation) checks one of its guesses, the record is written. A guesser whose record
     is bad loses to any source with a better one, by the existing rule. Nothing new decides between sources.

Learning from large data is then allowed exactly where it was forbidden before: patterns that hold MOSTLY are usable,
as guesses.

## Rungs (one prereg + one gate each; nulls reported; imports core/ only)

| rung | what | measured by |
|---|---|---|
| **G1** | **The guesser over facts.** Hold out facts from the 65k-entity crawl; guess them from patterns over the other entities' facts and names (exception-tolerant rules with counts). The guesser is a source with a record; in the chat it answers what nothing else can, labelled. | held-out precision of guesses vs a most-common-value baseline; knockout (shuffled facts) collapses; 0 unlabelled guesses |
| **G2** | **Guessing from text.** The same, with cues read from TEXT (descriptions, dictionary glosses, example sentences): "commune in the department of" -> France. The gloss line's reader, which is unsound as a voucher, becomes sound as a GUESSER because its output is labelled. | held-out precision with text cues only; coverage beyond G1 |
| **G3** | **Guessing what a sentence means.** When the parser cannot read a turn, guess the nearest reading it can (by learned word similarity from text) and ask "did you mean ...?" -- understanding ordinary phrasing by guess-and-check. | share of paraphrased test turns answered after one confirmation; 0 answers given as facts on a guessed reading |
| **G4** | **A model of text.** A counting model of what words follow what, learned from all local text; used for fill-in-the-blank, word similarity (feeds G3) and as the FORM side of replies (meaning stays exact, wording may vary -- the owner's earlier split). | cloze accuracy on held-out sentences vs baselines; replies' meaning unchanged by the varied wording |
| **G5** | **Common sense by guessing.** Type-level guesses ("a city has a population", "a person has a birth date") learned from the facts, used to ask the right question and to flag absurd claims as unlikely. | held-out type-property prediction; planted absurd claims flagged |
| **G6** | **Together in the live chat**, all on, long conversation; the guesser's record grows from real use. | together.py-style run with guesses; CONFAB 0; record written |

## What success would and would not mean
Would: an engine that answers far more than it can prove, says which is which, and gets better at guessing from its
own track record. Would not: fluency or open-ended reasoning at LLM level -- those are the rungs after these, and the
measurements here will say how far each rung moved the engine.
