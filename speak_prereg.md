# Pre-registration -- SPEAK: wording learned from any text, claims checked by re-reading (H1 + H2 + H7; `speak.py`; 2026-10-05)

Registered 2026-10-05 before the first run. Zero LLM. Tests three hypotheses of FLUENCY_HYPOTHESES.md together:
H1 (form is learned freely from all text, including a novel; only propositions are checked), H2 (closed-class words and
constructions are free skill; open-class words must be grounded), H7 (the monitor is the reader: a wording goes out only
if the engine's own reading of it recovers exactly the message).

## 1. Mechanism
- **Closed vs open class (H2), by count:** a symbol among the text model's 100 commonest symbols is closed-class; every
  other symbol is open-class (textmodel_prereg.md's counts; the cut H3 and G3 already use).
- **Skeletons (H1):** every sentence of three sources -- Wiktionary DEFINITIONS, Wiktionary EXAMPLE sentences (quotations
  from books and news), and ALICE IN WONDERLAND -- becomes a skeleton: closed-class symbols kept, each maximal run of
  open-class symbols one slot. Skeletons with exactly three slots, at most 10 tokens, seen at least 3 times, are kept,
  with their count per source. No truth check of any kind: this is form only.
- **The copula, learned from questions:** an answer is its question with the question word filled. In the engine's
  answered questions, the closed-class symbols standing between the question word and the phrase the answer's structure
  reads are counted; they are the LINKS (no list).
- **The message:** an answered question whose open-class symbols are exactly two (a property word and its argument,
  e.g. "capital", "japan"; "salary", "alice") and its value -- three fillers.
- **Candidates:** every skeleton x every assignment of the three fillers to its three slots, plus the question itself
  with its question word replaced by the value.
- **The monitor (H7, with H2 and H3):** a candidate is split at a LINK symbol into two sides; one side must be exactly
  the value's label (plus closed-class symbols); the other side is READ by the engine over its worlds, and must give one
  value, equal to the message's, with every open-class symbol of that side used by the reading's structure (H3's rule).
  Anything else is rejected. Among accepted candidates the choice may vary freely (the form side).

## 2. Gates
Messages: the chat gate's answered questions with exactly two open-class symbols (ORG, CROSS, KG lookups).

| gate | claim | bar |
|---|---|---|
| **S1** | coverage: messages with at least one accepted corpus-skeleton sentence | **>= 60 %** |
| **S2** | variety: distinct skeletons accepted overall; mean accepted wordings per covered message | **>= 5** skeletons; mean **>= 2** |
| **S3** | form from prose (H1): of the accepted skeleton types, the share attested in example sentences or Alice (not only definitions) | **>= 30 %** |
| **S4** | truth: accepted sentences whose slot assignment is false (the value is not on the value side, or the argument is) -- an audit independent of the reader | **0** |
| **S5** | KNOCKOUT (no monitor): every candidate with the value alone on one side of a link | false assignments **> 0** and **> 20 %** of them |
| **S6** | grounding (H2): accepted sentences carrying an open-class symbol that is not a filler | **0** |
| **S7** | hygiene: no English literal in speak.py's mechanism (links, classes and skeletons from counts) | structural |

PASS = S1-S7.

## 3. Predictions
P1 S1 ~70 %. P2 10-30 skeletons ("_ is the _ of _", "the _ of _ is _", "_ was the _ of _"). P3 ~40 % of accepted skeletons
are attested in examples or Alice -- a novel teaches form the definitions do not. P4 0. P5 ~45 % false (swapped slots).

## 4. What a PASS would and would not establish
Would: the engine can phrase a checked fact in wordings learned from any text, including a novel, and its own reading
keeps every wording true -- honesty at the level of propositions, not tokens. Would not: fluency for messages of more than
one fact, discourse, or any wording whose structure the reader cannot read back.

## 5. Run 1 (2026-10-05, as registered): FAIL S4 -- and the accepted sentences are garbage
8,588 three-slot skeletons (definitions 7,922, examples 2,133, Alice 48). Links learned: is 58, are 9, the 1. 40
messages, all "covered", 117 skeletons, 256 wordings per message -- and they read "a 335 in the total quantity of
doohickey", "a kyoto in the japan of japan". S4: 3,680 accepted sentences with a false slot assignment. S5 knockout 67 %
false. S6 0, S7 structural. Four defects, each a hole in the monitor or the data, not in the hypothesis:
1. a link seen once ("the") was a link, so sentences split anywhere;
2. the value side was allowed extra closed-class tokens ("a 335 in");
3. the lookup side was allowed to CONTAIN the value, and the reader "read" the value it was given;
4. nothing knew which slot of a skeleton holds a relation word ("the japan of capital" read the same as "the capital
   of japan": the reader is order-blind).
Plus yes/no questions (value = a filler: "is kyoto in japan" -> Japan) were messages.

## Amendment, run 2 (declared after run 1)
(a) links: symbols seen after the question word in at least 10 % of answered questions; (b) the value side is EXACTLY the
value; (c) messages whose value equals a filler are excluded; (d) the lookup side must hold the property and the argument
and not the value; (e) SLOT ROLES FROM THE CORPUS (H2's grammar as skill): for each skeleton, the share of its corpus
fillers that are RELATION words (the crawl store's property labels and the worlds' table headers -- data, not a list)
is counted per slot; the property filler may only go in the slot with the highest share, and a skeleton none of whose
slots reaches 30 % is not used. S4's audit is now satisfied by construction of (d); an order audit is added (S8, printed):
accepted sentences whose property/argument order is the reverse of the question's.

## Run 2 (2026-10-05): PASS as amended -- and what the sentences look like
Two fixes inside run 2, both selection bugs: the slot-role dictionary shared a name with a loop variable, and the top-400
cap was applied BEFORE requiring a link, which left only definition skeletons without one (0 accepted); the cap now
applies to skeletons that contain a link (422 of 5,981 with a relation slot). Links: is, are (the singleton "the"
dropped by (a)). 18 messages after (c) and the one-relation-filler rule.

S1 16/18. S2 159 skeletons, 153 accepted wordings per covered message. S3 88/159 skeletons attested in examples or Alice
(1 in Alice). S4 0 (by construction of (d)). S5 knockout 56 % false. S6 0. S7 structural. **S8 (printed): 1,130 of 2,448
accepted wordings reverse the property/argument order of the question** -- the reader is order-blind, so the monitor
accepts "the director by which jaws is steven spielberg" beside "steven spielberg is the director of jaws".

S9 (analysis declared after run 2): per message, the accepted wording whose weakest JOINT (a closed-class symbol next to
an open-class one) is most attested in the corpus. Seven of thirteen read as English: "michelle obama is the spouse of
barack obama", "africa is the continent of egypt", "william shakespeare is the author of hamlet", "110 is the average
salary of sales", "1410 is the largest revenue of february", "217 12 is the mean price of east" (a fraction printed
without its bar); six do not: "alice the salary is 120", "2012 is a start and judy", "40 are a maximum price of
doohickey", "a 50 or double that is 100". The QUESTION ITSELF, with its question word replaced by the value, reads back
correctly for 13 of 18 messages.

### Findings
1. **H1 holds in part:** wording learned with no truth check -- 88 of the 159 accepted skeletons come from quotations of
   books and news -- yields true sentences under the monitor, and the false-assignment rate falls from 56 % to 0.
2. **H7's monitor is only as good as the reader:** the reader is order-blind, so honesty holds (every accepted sentence
   asserts the message) while grammar does not. Word order is the missing half of comprehension, and therefore of the
   monitor.
3. **H6 is the strongest lever found:** the person's own question, re-ordered around the value, is the most reliable
   fluent wording (13/18 read back), with no corpus at all.

Registered (speak.py): "SPEAK: PASS".
