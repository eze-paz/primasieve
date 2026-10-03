# Pre-registration -- WINDOW WIDTH AGAINST DATA, AND A GENUINELY DIFFERENT REGISTER (`gloss_width.py`)

Registered 2026-10-03 before the first run, after gloss_generate_prereg.md: emitted replies are labelled edges because
the reader's patterns are three tokens wide. Owner's ask: do the width test, and consider text genuinely distinct from
definitions, such as novels.

## 1. Why not novels directly, and what stands in for them
The reader admits a pattern only when its truth condition holds for every occurrence, which needs a checkable world
behind the text. A novel mentions places and people the graph knows, but almost never in a relation the graph holds, so
its sentences would yield patterns with no verifiable condition and the strict inverse would refuse them -- correctly.
The store already holds a register that is genuinely distinct from definitions AND checkable: the Wiktionary EXAMPLE
sentences attached to entries, which are quotations from books, newspapers and speech ("Spain fought with France
constantly from 1494 through the 1540s"). They are prose, not definitions, and their mentions align to the graph the
same way. That is the "novels" of this experiment. Alice in Wonderland and the Brent corpus are in the store too and are
used for one measurement only: how many of the reader's patterns occur in them at all (form overlap), with no claim.

## 2. Mechanism
`gloss_scale.Scale` unchanged except the window width W, and the item set: definitions (as before), examples (new:
an example sentence of an entry that mentions one of the headword's claim objects), or both. Generation and selection
as gloss_generate.py.

## 3. Configurations and gates (same store, same seeded split by headword)
| config | W | register |
|---|---|---|
| A (baseline) | 3 | definitions |
| B | 5 | definitions |
| C | 7 | definitions |
| D | 3 | definitions + examples |
| E | 5 | definitions + examples |

| gate | claim | bar |
|---|---|---|
| **X1** | per config: windows admitted, held-out soundness, shuffled knockout | printed; soundness **>= 0.85** wherever >= 50 windows exist |
| **X2** | width: windows at W = 5 and 7 as a fraction of W = 3, on the same register | printed; the prereg predicts **< 25 %** at 5 and **< 5 %** at 7 |
| **X3** | register: examples add windows the definitions did not have (distinct keys) and shapes (distinct left/right token tuples) | printed; **>= 500** new windows at W = 3 |
| **X4** | reading: held-out content words accounted for, per config | printed |
| **X5** | generation (configs D and E, 30 frames): coverage, two-fact compositions, mean emitted length in tokens, and the sentences themselves | printed; the question is whether E's sentences are longer AND still accepted |
| **X6** | form overlap: fraction of the reader's windows (D) whose left+right tokens occur in Alice / Brent | printed, no claim |

## 4. Predictions
- **P1** B admits 10-25 % of A's windows, C under 5 %: a window of width w needs the same w-token context to recur three
  times, and definitions vary too much past three tokens at this data size.
- **P2** Examples add 500-2,000 windows at W = 3 and the new ones are shaped like prose ("fought with {E}", "the king of
  {E} and"), but their held-out soundness is lower (0.75-0.85): quotations assert more than the graph holds.
- **P3** E's emitted sentences are longer (mean > 6 tokens vs ~4) and fewer; some read as clauses rather than labels.
- **P4** X6 under 10 %: the reader's patterns are definitional and barely occur in narrative text -- which is the honest
  measure of how far a novel is from anything this reader can currently verify.

## 5. What a PASS would and would not establish
Would: whether width or register is the lever, with numbers. Would not: fluency; a path to learning from novels without
a world behind them, which this file argues does not exist under the honesty rule and measures (X6) rather than asserts.

## 6. MEASURED (2026-10-03) -- `python gloss_width.py --frames 30` and `--long`: width is NOT the barrier; the reader-as-voucher is

| config | windows | held-out soundness | knockout | reading |
|---|---|---|---|---|
| A  W=3 definitions | 2,178 | 0.964 | 66 | 0.440 |
| B  W=5 definitions | 3,221 | 0.953 | 90 | 0.458 |
| C  W=7 definitions | 3,871 | 0.951 | 110 | 0.461 |
| D  W=3 definitions + examples | 2,264 | 0.955 | 88 | 0.339 |
| E  W=5 definitions + examples | 3,403 | 0.945 | 123 | 0.348 |

- **X2 -- P1 REFUTED, in the good direction.** W=5 admits **1.48x** the W=3 windows and W=7 **1.78x** (predicted under
  0.25 and 0.05), at soundness 0.95: wider patterns DO recur three times in this data. The windows were three tokens wide
  because W was 3, not because the data stopped there. Reading gains little from them (0.44 to 0.46).
- **X3 -- examples add 1,067 windows (496 new shapes)** at W=3, soundness 0.955. But the new shapes are the same
  prepositional ones ("of {E:country}" x266, "in {E:country}" x167), and held-out reading FALLS to 0.34 because the
  held-out set now contains prose sentences, two thirds of whose words nothing accounts for. Quotations from books and
  news are two-thirds unreadable to this reader; that is the measured distance from a novel.
- **X5 -- generation, standing-first (D, E):** coverage 16/30 either way, mean length 4.6 and 4.4 tokens; the wide windows
  never reached the output because the shortest, most frequent windows have the highest standing.
- **X5-long -- longest vouched-for candidate first (E, declared amendment):** mean length **7.1** tokens, two-fact 9, and
  the sentences are **false**: "Portuguese: neighborhood of new orleans louisiana portugal", "Tsum: neighborhood of new
  orleans louisiana nepal", "Holy Roman Emperor: a country in the emperor of carolingian roman emperor until". Every one
  passed the strict inverse. The window "neighborhood of new orleans louisiana {E:country}" was admitted from New Orleans
  neighbourhoods' definitions with a condition of ONE relation (country holds), because "neighborhood" never bound a
  type; applied to any headword with a country claim, it vouches for words plainly false of that headword. Misreports
  among emitted: 0 by the edge test -- which is exactly the problem: the edge is right and the sentence is wrong.
- **X6:** 38 % of the reader's window sides occur as n-grams in Alice in Wonderland, 12 % in the Brent corpus, because
  they are function-word fragments ("of", "in", "and"). No claim, as declared.

### The finding, stated once
A construction's truth condition must explain EVERY token it carries, or the tokens it does not explain are untyped
assertions. In READING that gap is harmless: the sentence came from the source and the unexplained words were true there.
In GENERATION the same window is applied to a new headword that satisfies only the condition, and the unexplained words
become claims nobody checked. Soundness 0.95 on held-out definitions therefore does not transfer to generation, and the
41 % knockout acceptance of gloss_generate_prereg.md was this hole seen from the other side. **The reader is sound as a
reader and unsound as a voucher.** The honesty rule as implemented -- every content word inside some admitted window --
was too weak; it needed every content word TYPED by the window's condition. Under that stricter rule the windows able to
generate are those whose every word is a function word or a typed word ("of {E}", "in {E}", "a city in {E}"), and the
output is labels again, truthfully.

### Prediction ledger
P1 REFUTED (good direction). P2 half (windows yes; lower soundness no; prose-like shapes no). P3 MISS as stated: longer
sentences came only with the longest-first amendment and they were false. P4 MISS (38 %, trivially).

### Disposition
Not registered. Two things stand: wider patterns exist and are sound (width is a free parameter, not a wall), and example
sentences add verified patterns. One thing is closed: constructions with relation-only conditions cannot vouch for their
own words in generation. The next lever is the TYPE lexicon -- "neighborhood", "emperor", "faith" must bind types for
their windows to be usable in output -- and the rung-1 and rung-2 nulls on headword-type binding say that needs a different
binding target (the type of the entity a word predicates, found by its position relative to the slot) or an order of
magnitude more headwords. Learning from novels remains closed under the honesty rule: 0.34 reading on prose, and nothing
in a novel to check against.
