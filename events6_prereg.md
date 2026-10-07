# Pre-registration -- LOOP ITERATION 16 (B6): PLURALS ARE NOT VERBS, NOUN PHRASES WHOLE, PRONOUN DOERS FIRST (`core/events.py`, `kb_events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. B6 is 43/100. The event dump over the stories (no door) shows three
general reader defects, none story-specific:
1. **Plural nouns read as verbs.** "a pair of boots", "caught rabbits", "two oranges", "the ropes", "Two friends": the
   plural shares its form with the third-person present verb ("boots" = boot.3SG), so each makes a false event.
2. **Noun phrases cut to their head.** "asked for a pair of boots and a bag" -> patient "pair"; "gave him half of her
   sandwich" -> "half"; "Eva and her uncle Karl drove" -> agent "uncle Karl".
3. **A pronoun doer skipped for a farther noun.** "In the evening they cooked the fish" -> agent "evening".

## Mechanism (every class learned by counting over 60 training books; no word written)
(A) SUBJECT-LIKE symbols: closed-class symbols that are not verb forms themselves and are followed by a PAST-tense finite
form (UniMorph/gloss "PST" cell, not also third-person present) in >= 20 % of their uses (measured: she, he, they, i,
we, who). A third-person present form is a verb only right after a subject-like symbol or a noun; elsewhere it is a noun.
(B) A subject-like symbol right before a verb is its doer (its referent, as pronouns are now resolved), before any
farther noun.
(C) The LINKER: closed symbols with both neighbours noun-like in >= 45 % of uses (measured: of -- next 0.34); the
COORDINATOR: the closed symbol most often between two capitalised names, the linker excluded (measured: and). A patient
or agent noun run is extended across a linker or coordinator followed by another noun run (one closed symbol may sit
between: "and a bag", "of her sandwich").

## Gates
| gate | claim | bar |
|---|---|---|
| **W1** | B6 (live door) | **>= 48** |
| **W2** | B5 not lower by more than 1 point (independent check) | held |
| **W3** | B1 | 0 (counted; inspected) |
| **W4** | B2, B9 held | held |

## Prediction
B6 ~48 (s15 boots/bag, s16 sandwich/oranges, s19 ropes, s20 they-cooked, s14 Omar and Ines).

## Amendments before the battery run (2026-10-07)
(A) measured over the morphology table's OWN lemmas (the gloss pass of iteration 14 adds odd ones -- "they" became a verb
lemma and was excluded); and a symbol that follows a learned marker ("to", "will", ...) in >= 20 % of its uses is a verb
form, not a subject ("be" had entered). Learned: subjects {he, i, she, they, we, who}; linker {of}; coordinator {and}.
Event memory alone over the stories: 42 -> 45/100 ("pair of boots and a bag", "half of her sandwich", "rabbits",
"oranges", "Eva and her uncle Karl").

## Run (2026-10-07, battery16): NOT PASSED (W1 47 vs 48) -- W2, W3, W4 held
**B6 43 -> 47/100**, one short of the bar. W2 B5 +11.6 (held). W3 B1 counted 1 (the "jurisdiction" item, true on
inspection). W4 B2 90.2 %, B9 18/20. B10 398/500, B3 97.65/0.59 and 87.5/0, B7 15/18 at 0 %, B4 3/4,605 -- unchanged.
Kept (a gain, nothing lower); the remaining story misses are planned from the English phenomenon map (ENGLISH_MAP.md)
rather than from this dump alone.
