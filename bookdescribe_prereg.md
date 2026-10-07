# Pre-registration -- NOVEL LOOP ITERATION 7 / LOOP ITERATION 23: DESCRIBED DOERS IN BOOKS ("the old man gave no heed") (`book_battery.py` hook; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Under the owner's ruling every book is its own world. The book reader
(core/bookworld.py, iteration 5 settings) reads **9.4 %** of the real novels' test sentences (161/1,709) at hand-judged
precision 50/50, because it admits only NAMED doers. A sample of its unread novel sentences shows readable events whose
doer is a DESCRIPTION: "The absorbed old man gave no heed to their words", "The man took him again", "The inbred pride of
the great lady began to appear". The story reader (core/events.py) now has learned determiners, the closed class of
stories, plural/verb disambiguation, reality status and negation (iterations 16-21).

## Mechanism
For a test sentence the book reader leaves unread, the story reader's events are admitted when ALL hold: the event is
realis (not negated, not irrealis); its doer's words occur in the sentence itself (no pronoun or carried-over referent);
the doer begins with a learned determiner (phrases_prereg.md) or is capitalised (a name); the sentence holds no quotation
mark. The proposition is the book's: "<title>: <doer> <verb> <patient>", never stated as world fact.

## Gates
| gate | claim | bar |
|---|---|---|
| **D1** | B4-book, real novels: sentences read | **>= 15 %** (from 9.4 %) |
| **D2** | precision on a fresh builder-judged sample of the ADDED propositions (50 novels + 50 others; disclosed as the builder's judgement) | **>= 0.80** novels |
| **D3** | K3 honesty: book propositions said without context | 0 |
| **D4** | frozen B4 | reported (expected unchanged: 3/4,605) |

## Prediction
D1 ~18 %; D2 ~0.8 (wrong patients more often than wrong doers).

## Run 1 (it 7, as registered): D1 30.4 % but D2 FAIL -- precision 23/50 novels (0.46), 18/50 others
The builder's labels (tests/bookworld_judged_it7.json): subordinate clauses read as main ("When the last dish was removed
..." -> "the last dish remove bottles"), passives reversed ("the walls ... were covered with bits of paper" -> "the walls
cover bits"), stray attachments; and one old-reader honesty slip ("Industry does not need them" -> "Industry do need").
## Amendment, run 2 (it 8): the main clause's own subject only
The doer phrase begins the sentence (a learned determiner may precede it) and is not a closed symbol; the verb follows the
doer at once (or after one open-class symbol: "Poussin looked alternately", "The captain interfered gently"); the verb is a
finite lexical form, not after a learned auxiliary (no passive, no progressive), not a closed-class verb. Run 2: **novels
14.2 %, others 7.0 %**; builder's precision (tests/bookworld_judged_it8.json): **novels 43/50 = 0.86**, others 29/50 = 0.58.
Also fixed in core/bookworld.py (an honesty defect of the book reader itself): a learned negative symbol within 3 symbols
before or 2 after the verb drops the event (6 propositions, "Industry do need" among them). Final: **novels 14.0 %**
(239/1,709), others 6.9 %, K3 honesty 0 of 464.
**Verdict: D1 NOT met (14.0 vs 15 %), D2 met (0.86), D3 met (0).** D4: the frozen B4 is unchanged by construction (it
reads store propositions only): 3/4,605.
