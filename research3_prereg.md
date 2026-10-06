# Pre-registration -- LOOP ITERATION 11 (B10): THE LOCAL STORE IS NOT RATIONED LIKE THE WEB (`core/research.py`, `kb_storefetch.py`; 2026-10-06)

Registered 2026-10-06 before the code. Zero LLM. B10 has been 154/500 (30.8 %) for two runs. A ceiling check
(the store fetcher asked directly for each item's entity) finds the gold among the fetched claims for **484/500**; a trace
of 10 items through a fresh live door answers 8. The gap is the researcher's RATIONING, built for slow web lookups:
1. a session-wide **budget of 400 fetch attempts** -- the battery's B10 runs 500 questions in one door, so after roughly
   the first hundred questions nothing more is looked up;
2. **4 attempts per turn**, spent longest span first;
3. spans of at most **3 symbols**: 53 of the reachable names are 4-6 symbols long ("mecklenburg western pomerania").

## Mechanism
A fetcher may declare itself LOCAL (`local = True`: an index on disk, no network). Local fetchers are exempt from the
budget and the per-turn cap, and are offered unread spans up to 6 symbols long. Online fetchers keep every limit. Nothing
else changes: the median-frequency rule, closed-class spans, the namesake rule, quoting ("store").

## Gates
| gate | claim | bar |
|---|---|---|
| **L1** | B10 | **>= 45 %** |
| **L2** | B1 | **0** |
| **L3** | B2, B9 not lower by more than 2 points; B6 not lower than 31 | held |

## Disclosed measurement caveat (found in the trace, not changed: the battery is frozen)
B10 runs in one door, so a question whose entity is not read can be "answered" from the previous turn's context with the
unread words owed ("The country of kleinmachnow is Germany, but I found no way to apply economy ; mecklenburg ...") and
the scorer counts it when the gold matches. The run reports, beside B10, the hits whose reply owes nothing ("but I ...").

## Prediction
B10 ~70 % (the ceiling less namesakes asked, fixture words that read parts of names -- "west" is a sales region -- and
context carry-over); B1 0 unless a 4-6 symbol span matches the wrong stored label.

## Amendment before the code (2026-10-06)
The honest B10 baseline is 125/500 (natural2_prereg.md run 2: 29 of the 154 were abstentions listing the gold). L1's bar
stays 45 %. The run also reports hits that owe nothing and quoted answers that miss the gold.

## Run 1 (2026-10-06, battery11, B10 part): L1 PASS (396/500 = 79.2 %), L2 FAIL -- numerals dropped from names
B10 **396/500** (388 facts, 8 labelled guesses; 389 owe nothing; 7 quoted answers miss the gold) from 125. B2 74.3 %,
B9 18/20. The B1 cases printed: three are true values of a multi-valued property whose gold is an unlabelled Q-id
(jurisdiction, jean bodin, elizabeth sung -- the scorer cannot match a Q-id); **two are false facts**: "2012 ad1" was
answered as ".ad" (country code top-level domain) and "november 11" as "calendar month" -- the 6-symbol spans let a
shorter stored name inside a longer one be fetched, and the integration rule owes only LETTER symbols, so the numerals
"2012", "1", "11" were left unread without a word.
Amended for run 2: an unused NUMERAL is owed like an unused word (a numeral is a thing since natural_prereg.md run 2).

## Run 2 (2026-10-06, battery11 + B2/B9/B10 re-run with numerals owed): L1 PASS, L3 PASS; L2 counted 3, inspected 0
**B10 396/500 (79.2 %)** from the honest 125 (388 facts, 8 labelled guesses; 389 owe nothing; 7 quoted answers miss the
gold). B2 74.3 % (-0.2), B9 18/20, B6 32 (>= 31), B5 +11.6, B4 3/4,605, B3 and B7 unchanged.
B1 as the frozen scorer counts it: **3** -- and each was inspected: "legal term or legal concept" (jurisdiction),
"jurist" (Jean Bodin), "stage actor" (Elizabeth Sung) are the store's OWN claims; the gold of those items is an
unlabelled Q-id the store has no name for, so no reply can match it. The two real false facts of run 1 ("2012 ad1",
"november 11") are now owed ("... but I found no way to apply 2012 ; 1"). Verdict: L2 met on inspection, disclosed as
such; the counted figure stays 3 in the log.
Open defect seen here: a multi-valued property is answered with ONE value ("Jurist is the occupation of jean bodin" --
the store lists six), which reads as if it were the only one.
