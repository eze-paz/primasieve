# Pre-registration -- LOOP ITERATION 1 (P1): AN EVENT READER -- WHO DID WHAT TO WHOM (`core/events.py`, `events.py`; 2026-10-06)

Registered 2026-10-06 before the first run. Zero LLM. First iteration of FLUENCY_LOOP_PLAN.md: the weakest blocking lines
are B5 (following a story, +3 points) and B6 (story questions, ~0), both waiting on an event reader (COMPREHENSION_PLAN.md
C6/C6b: bags of words and two-word slots did not carry who-did-what).

## 1. Mechanism
- **Verbs from data:** a symbol is a FINITE VERB when UniMorph (`_nldata/unimorph_eng.tsv`) lists it as a verb form with
  a tense (PST or PRS); its lemma is UniMorph's. No verb list is written.
- **Which side the doer stands on, learned:** over the training half of the Gutenberg corpus, the text entities
  (C6's capitalisation rule) adjacent to a finite verb are counted on its left and on its right; the side with more is
  the AGENT side, the other the PATIENT side (a count, not a rule of English).
- **An event** per finite verb: the agent = the nearest entity or noun run (open-class symbols, optionally after one
  closed-class symbol) on the agent side within the clause; the patient = the same on the patient side; pronouns (closed-
  class symbols in the agent position) resolve to the most recent agent entity.
- **Profiles for following a story (B5):** each entity accumulates (role, verb lemma) features from the events it took
  part in, read so far; a hidden mention is guessed by C6's evidence split over the hidden position's (role, verb lemma)
  features, falling back to C6b's slot features when no event covers the position.
- **Story questions (B6):** each story sentence is read into events; a question's verb lemma and content symbols select
  events; the question word at its start asks for the role the question leaves empty (a question beginning with a closed-
  class question symbol and a verb asks for the AGENT; "did X VERB" asks for the PATIENT; otherwise the first adjunct
  noun run after the patient). Answers are readings of the story, said as such.

## 2. Gates
| gate | claim | bar |
|---|---|---|
| **E1** | B5 on the battery's held-out novels: points over the frequency guess (C6b: about +3 on Alice) | **>= +8** |
| **E2** | KNOCKOUT for E1: event profiles shuffled among candidates | gain **<= +2** |
| **E3** | B6 story questions right (the drafted set; disclosed as written by the builder) | **>= 30 %** |
| **E4** | the agent side learned from the corpus | printed |
| **E5** | registered numbers unchanged (chat.py) | unchanged |
| **E6** | hygiene: core/events.py holds no word of any language | structural |

PASS = E1, E2, E3, E5, E6.

## 3. Predictions
P1 +8 to +12 ("said the Mouse" -> agent-of say). P2 ~0. P3 ~40 % (who-questions on simple SVO sentences; where/why
questions mostly missed). P4 agent side LEFT.

## 4. Run 1 (2026-10-06): FAIL E2, E3
E4 agent side LEFT (8,622 names before finite verbs vs 3,714 after, 60 training books). **E1 +11.5** points over the
frequency guess on 9 held-out novels (per book -1.9 to +21.4). **E2 knockout +8.8**: with the event profiles shuffled
the gain stays -- it comes mostly from C6b's slot fallback (used whenever no event covers the hidden position, and on these
novels worth far more than on Alice); events add about +2.7 over it. **E3 29/100**. E5, E6 pass. A defect in the chat
wiring: QUESTIONS were also read into the story's events ("Who owned the red boat?" became an event "owned ... ", and a
later question was answered "owned").

## Amendment, run 2 (declared after run 1)
A turn that ends in a question mark is not read into the story's events. Everything else unchanged (E1/E2 do not use the
chat and are not rerun).

## Run 2 (2026-10-06): NOT PASSED (E2 from run 1)
**E3 31/100** with questions kept out of the story ("Who borrowed the boat?" -> "From what you told me: brother Tomas
(brother Tomas borrow boat)"); misses are where/why questions, verbs the story phrases differently ("had" vs "owned"),
and "was waiting" (no finite-verb event for a progressive). E1 +11.5 and E2 +8.8 stand from run 1: the reader of events
works and is in the live chat, but on novels its profiles add ~3 points over the slot fallback -- the who-did-what signal
is real but small at this extraction quality. Next for this line: better events (progressives, auxiliaries, clauses),
not looser bars.
