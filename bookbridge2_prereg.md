# Pre-registration -- NOVEL LOOP ITERATION 6 (B4): A STRICTER BRIDGE AND A STRICTER PRONOUN (`core/bookworld.py`, `book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Iteration 5 (bookbridge_prereg.md) passed precision (0.91; novels
50/50) but its bridges were 20/25 and its pronoun readings 22/27. The five wrong bridges and five wrong pronouns have
three causes, each answered by one rule.

## Mechanism
1. **A bridge needs the item's own name.** The chosen item's label, normalised, must equal one of the book name's
   texts, normalised ("British Museum" never becomes the Ashmolean). A ONE-symbol name (a given name: "Mary",
   "Elizabeth") needs evidence from TWO different partner names of the book, not one -- two given names that vouch only
   for each other are not evidence.
2. **Titles that join a run are the learned abbreviations** (Mr, Mrs, Dr, St -- iteration 1's splitter list), not any
   closed capital before "." (". Burne Jones"); the "." a trimmed title leaves is not shown.
3. **A pronoun abstains when any OTHER person-like name in its window has an unknown pronoun** (Bunyan, whose own
   pronoun the book never shows in a countable way, must stop "he" from going to God).

## Gates
| gate | claim | bar |
|---|---|---|
| **H1** | precision, builder-judged fresh sample of 100 (50 novels, 50 others; seed 6) | **>= 0.90** |
| **H2** | bridges, builder-judged (up to 40) | **>= 0.90** |
| **H3** | pronoun/narrator precision (up to 50) | **>= 0.85** |
| **H4** | B4-book, real novels | **>= 9.5 %** (hold) |
| **H5** | honesty | 0 |

## Prediction
H1 ~0.91; bridges ~20 at ~0.95; pronoun ~0.95 with fewer readings; H4 held. Frozen B4 3/4,605.

## Run 1 (2026-10-07), superseded before judging
Bridges fell from 25 to 4 (a one-symbol name rarely has two partner names); the pronoun rule changed nothing (27
readings, the same "God" ones). Diagnosis from run 1's output: the God readings come from the CURRENT sentence's names
inside a quotation ("count me God's instrument ... He preached"), which rule 3 never looked at.
## Amendments declared before run 2
- (3') names inside an open quotation are not candidates for a pronoun outside it.
- (1') a one-symbol name needs two partner names only when every partner is itself one symbol (two given names
  vouching for each other); one multi-symbol partner suffices.

## Run 2 (2026-10-07): NOT PASSED (H1 0.89, H2 0.75); H3 PASS, H4 held, H5 0
| gate | result |
|---|---|
| H1 precision, fresh judged sample (tests/bookworld_judged_it6.json) | **89/100 = 0.89 MISS** (novels 47/50 -- three conditionals, "if Lady Jane discovered"; others 42/50) |
| H2 bridges | only **4** survive (Aristotle, the Bible, Italy right; "Mary" -> the Virgin Mary wrong): **3/4 = 0.75 MISS** |
| H3 pronoun/narrator precision | **21/22 = 0.95 PASS** -- but every one is 1422's first-person narrator: the stricter rule (any person-like name with an unknown pronoun in the window abstains) leaves NO third-person pronoun reading in the test units |
| H4 B4-book real novels | **163/1,709 = 9.5 %** held (others 84/3,000 = 2.8 %; all 247/4,709 = 5.2 %) |
| H5 honesty | 0 of 258 |
Frozen B4 (battery.py's block, re-run): **3/4,605** (unchanged).
**Reading.** The two stricter rules bought precision by silence: the bridge keeps 4 of 25 names (and still one wrong),
the third-person resolver keeps none. Iteration 5's settings are the better operating point (0.91 precision, 25 bridges
at 0.80). What remains: conditionals ("if X ...") read as assertions -- the one error class left in the novels.
