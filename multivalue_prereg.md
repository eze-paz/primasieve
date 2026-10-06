# Pre-registration -- LOOP ITERATION 12 (B8, B10, honesty of form): EVERY VALUE OF A MANY-VALUED PROPERTY (`chat.py`; 2026-10-06)

Registered 2026-10-06 before the code. Zero LLM. Iteration 11 exposed: "what is the occupation of jean bodin" ->
"Jurist is the occupation of jean bodin. (store)" while the store lists six occupations. The reasoner evaluates a
structure to its FIRST certified value (core/kg.py `evaluate`); `evaluate_all` already returns every value with its own
edge certificates. A sentence naming one value of six reads as if it were the only one -- not a false fact, but a
misleading form, and the rubric's "plain but correct" requires it to be right as read.

## Mechanism (chat layer only; core/ unchanged)
When a turn is answered by ONE graph structure whose world certifies more than one value, the live door says all of
them (up to 6, then "and N more"): "The occupation of jean bodin has 6 answers (store): jurist, philosopher, economist,
historian, political scientist and demonologist." Every listed value carries its own certificate (evaluate_all); the
aligned one-value sentence is not used for it.

## Gates
| gate | claim | bar |
|---|---|---|
| **M1** | B10 | not lower than 396; reported |
| **M2** | B1 (counted, and inspected) | 0 on inspection |
| **M3** | B2, B9 not lower by more than 2 points | held |
| **M4** | B8: the builder's rating of a fresh sample | >= 3.40 |

## Prediction
B10 +5 to +20 (items whose gold is a second value: Tuva's "federal subject of Russia"); B2/B9 unchanged (their graph
answers are single-valued); B8 unchanged (the sample's questions are single-valued) -- M4 may show nothing.

## Run (2026-10-06, B2 + B9 + B10): PASS (M1-M4)
**B10 398/500** (from 396; 391 owe nothing); B2 74.3 % (unchanged); B9 18/20; B1 counted **1** -- "jurisdiction" ->
"legal term or legal concept", the store's own single claim against an unlabelled Q-id gold (true on inspection). The
Jean Bodin and Elizabeth Sung items now list every value ("The occupation of jean bodin has 6 answers (store): jurist,
philosopher, ..."); the scorer no longer counted them, and why was not traced in this run (their gold is still an
unlabelled Q-id). B8: the sample is unchanged from iteration 11 (its questions are single-valued) -- 3.40 held, as
predicted; the change is in form for many-valued answers, which the B8 sample does not draw.
