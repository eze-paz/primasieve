# Pre-registration -- C6: A WORLD BUILT FROM THE TEXT BEING READ (`core/textworld.py`, `textworld.py`; 2026-10-06)

Registered 2026-10-06 before the first run. Zero LLM. Rung C6 of COMPREHENSION_PLAN.md: C2 read nothing of Alice in
Wonderland, because nothing it names is in the store. A reader of a novel must build the novel's own world as it goes.

## 1. Mechanism
- **Text entities, from the text alone:** a symbol that appears with an initial capital in a NON-initial position of a
  sentence at least 5 times, and capitalised more often than not (case is the cue; a script without case would need
  another -- declared). No list of names.
- **The world, built incrementally:** for each entity, a PROFILE: counts of the open-class symbols (outside the text
  model's 100 commonest) of the sentences that mention it -- from sentences ALREADY READ only.
- **A masked mention (the Children's Book Test's form, Hill et al. 2016):** in a sentence that mentions exactly one text
  entity, the mention is hidden; the candidates are the 10 entities mentioned most so far; the guess is the candidate
  whose profile shares the most counted symbols with the sentence (each sentence symbol scores its count in the
  candidate's profile divided by the candidate's total -- a ratio of counts; ties to the more frequent). Labelled a guess.

## 2. Gates
Test items: every sentence after the first 100 of Alice's text that mentions exactly one text entity, whose entity is
among the 10 candidates.

| gate | claim | bar |
|---|---|---|
| **W1** | text entities found; printed | **>= 8** |
| **W2** | masked-mention accuracy vs the better of two baselines: the most frequent entity so far; the most recent entity mentioned in the previous 3 sentences | **>= baseline + 10 points** |
| **W3** | KNOCKOUT: profiles shuffled among the candidates at each step | accuracy **<= frequency baseline + 3 points** |
| **W4** | hygiene: core/textworld.py holds no word of any language | structural |

PASS = W1-W4.

## 3. Predictions
P1 ~15 entities (Alice, Rabbit, Queen, King, Hatter, Gryphon, Turtle, Duchess, Dormouse, Cat, Mouse, Caterpillar).
P2 ~45 % vs frequency ~30 % (Alice dominates) and recency ~35 %. P3 ~30 %.

## 4. Run 1 (2026-10-06): FAIL W2
39 text entities, including non-entities "i", "oh", "yes", "five", "chapter" (capitalised after quotation marks or as
the pronoun). W2 29/229 = **12.7 %** vs frequency 40.2 % (which guesses "i") and recency 33.2 %; W3 knockout 11.8 %.
Two defects: (1) the pronoun and interjections pass the capitalisation test; (2) dividing by a profile's total makes small
profiles win every guess.

## Amendment, run 2 (declared after run 1)
(1) A symbol among the text model's 100 commonest is not an entity. (2) Each sentence symbol is EVIDENCE split among the
candidates by their counts of it: a candidate scores, per symbol, its share of that symbol's occurrences across the
candidates' profiles (a symbol mostly seen with the Rabbit counts for the Rabbit); summed; ties to the more frequent.

## Run 2 (2026-10-06): NOT PASSED (W2 58.5 % vs frequency 58.1 %) -- a clean null
38 entities ("i" gone; "oh", "yes", "five", "chapter" remain). W2 148/253 = **58.5 %**; frequency 58.1 % (Alice is the
answer in most masked sentences); recency 40.3 %; W3 knockout 11.1 %. The profiles carry information (the shuffle
destroys it, 11 %), and some guesses beat frequency ("Ahem said the Mouse ...", "That's right shouted the Queen"), but on
balance a bag of co-occurring words adds nothing over guessing the protagonist.

### What it means
A world built from a novel cannot be a bag of words per character. What tells the reader that the hidden name is the
Mouse is WHO DOES WHAT -- "said the ___ with an important air", "begged the ___ to tell" -- the roles of the sentence,
the thing C1's constructions capture for stored relations and nothing yet captures for a story's own events. The next
rung would read each sentence's (agent, action, patient) and track them per entity; that is a reader of events, which
this engine does not have.

## C6b -- THE SLOT, NOT THE SENTENCE (declared after run 2, before its run)
Claim: the words AROUND a mention (its slot: up to two symbols on each side, with their side and distance) carry the
role -- "said the ___", "begged the ___ to" -- where the sentence's bag did not. Each entity's profile is the counts of
(side, distance, symbol) seen around its earlier mentions; a hidden mention is guessed by the same evidence split over the
masked position's slot. Gates as W2-W3 (>= baseline + 10 points; shuffle <= frequency + 3).

## C6b run (2026-10-06): NOT PASSED (61.8 % vs frequency 58.6 %; +3.2 points, bar +10)
The slot carries a little role: "... cried the ___ in a shrill passionate voice", "... said the ___" -> the Mouse, against
the frequency guess (Alice); knockout 12.7 %. Three points over guessing the protagonist, not ten. The two words beside a
name are a weak stand-in for who-does-what; an event reader remains the missing piece.
