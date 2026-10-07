# Pre-registration -- LOOP ITERATION 20 (honesty in world answers, from the English map) (`core/rephrase.py`, `core/session.py`, `chat.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. The map's question probes (english_probe_results.json, live door) hold
confident answers to a DIFFERENT question than the one asked -- never counted by the frozen battery:
1. "who is managed by carol" / "whom does carol manage" -> "Reading 'managed' as 'manager'. The manager of carol is dave":
   the one-edit slip channel (spelling_prereg.md) "corrected" a real word into its converse.
2. "how many employees are not in support" -> "The number of employees of support is 2": the negator was not owed.
3. "who has the highest salary in sales" -> "130 has the highest salary in sales": the aligned reply put a NUMBER where
   the question word asks for a thing.

## Mechanism
(A) A slip is only a symbol OUTSIDE the vocabulary (the text model's words seen >= 3 times): a known word is never
"corrected" (it may still be OFFERED by the did-you-mean path, which asks).
(B) The learned NEGATIVE symbols (negation_prereg.md: discovered from the dictionary -- not, no, never, none, neither,
without) are never courtesy and never common: an answer whose structure leaves one unused is PARTIAL and says so.
(C) The aligned reply ("<value> is the X of Y") is used only when the value's kind fits the question word: per learned
question word, the share of its answered held-out questions whose answer is a NUMBER is counted; a numeric value is not
aligned under a question word whose answers were numbers in under 10 % of cases (and vice versa a non-number under a word
answered by numbers >= 90 %).

## Gates (measured in the same battery as negation_prereg.md; B2/B9/B10 belong to this iteration, B6 to that one)
| gate | claim | bar |
|---|---|---|
| **H1** | the three probe questions above (and Q017) | none answered with the wrong value |
| **H2** | B2 | not lower than 90.4 % - 1 point (the slip channel loses known-word "slips") |
| **H3** | B1 0 (inspected); B9, B10 held | held |

## Prediction
H1 met (abstentions or PARTIAL); B2 -0 to -1 point (items whose "typo" is a real word: "strat" -> "start"? "strat" is out
of vocabulary, kept).

## Run (2026-10-07, battery19 + a B2/B9/B10 re-run): PASS (H1-H3) after one amendment
H1: "not in support" -> PARTIAL, "but I found no way to apply not"; "who is managed by carol" no longer read as
"manager" (a dictionary gloss of "carol" instead -- not a fact); "whom does carol manage" -> PARTIAL; "who has the
highest salary in sales" -> "The highest salary of sales is 130 (records)" (true; not the person: the argmax is not
asked of the table yet). Battery19: B2 89.6 % -- 4 items lost; three were slips that are themselves real words ("prais",
"pairs" -> paris, "strat" -> start), which rule (A) as registered ("a known word is never a slip") refused.
Amended, disclosed: a KNOWN word is never read as its own relative (same stem by rephrase.family: "managed" ->
"manager" is a converse), but may be read as a slip for an unrelated word one edit away. Re-run: **B2 450/498 = 90.4 %**
(restored), B9 18/20, B10 398/500, B1 counted 1 (the "jurisdiction" item); the H1 probes unchanged.
