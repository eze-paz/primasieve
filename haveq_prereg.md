# Pre-registration -- LOOP ITERATION 51 (B6): QUESTIONS WHOSE ONLY VERB IS CLOSED-CLASS ("WHO HAD A CLEVER CAT?") (`core/events.py`; 2026-10-08)

Registered 2026-10-08 before the code. Zero LLM. The reader already stores "A miller have a clever cat", "The old king have
three daughters" (events3 (3): a closed verb form after a noun is the main verb), but `EventMemory.ask` takes its verb
lemmas only from non-closed symbols, so "Who had a clever cat?" / "How many daughters did the king have?" select nothing.
Mechanism: (A) when the question has no lexical lemma (and is not copular -- the copula's lemma is excluded), the lemmas of
its closed verb forms after the first symbol select the events; (B) the numeral answer (phrases (B)) accepts the learned
number words as well as digits ("three daughters" -> three).

## Gates
| gate | claim | bar |
|---|---|---|
| **H1** | B6 | **>= 69** |
| **H2** | probes WRONG <= 14, RIGHT >= 107; B2, B9, B10 held; novels unaffected (ask is not used by the book readers) | held |

## Result (2026-10-08) -- PASS (three amendments before the scored run, all disclosed)
- **H1 PASS**: B6 67 -> **69** ("Who had a clever cat?" -> A miller; "How many daughters did the king have?" -> three).
  Amendments found while tracing: (1) "cat" is also a verb in the tables, so "no lexical lemma" became "no lexical lemma
  told of by a realis event" (the negated "did not fight" no longer blocks it); bare closed forms ("have") count via the
  base table; (2) closed lemmas bring no synonyms -- WordNet's have ~ eat made "Who had the cheese first?" answer "The fox";
  (3) the first full battery dropped B2 450 -> 447: "which department has the lowest floor ..." matched a stored
  "region have the lowest price"; a match through a closed lemma now needs every content word of the question in the
  event's roles. Re-measured: B2 back to 450 (per-question diff against HEAD: only phrasing variants differ).
- **H2 PASS**: probes RIGHT 107 -> **108** ("How many boys climbed the hill?" -> Three), WRONG 14; B9 18/20, B10 398,
  B1 1 (known item); B5, B4 frozen unchanged (ask is not used by the book readers).
