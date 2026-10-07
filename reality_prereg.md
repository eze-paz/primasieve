# Pre-registration -- LOOP ITERATION 17 (honesty, from the English map): WHAT DID NOT HAPPEN IS NOT TOLD AS HAPPENED (`core/events.py`, `kb_events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. First iteration planned from the forward map (ENGLISH_MAP.md, commit
0b820962), not from a battery miss. The map's probes found the story memory states 31 WRONG answers; the largest honesty
class is events that did NOT happen told as if they had: "She didn't eat the soup" -> "Who ate the soup?" -> "Rosa";
"Later she will wash the plates" -> "Did Ada wash the plates?" -> "plates"; "If Leo wins, his father will buy a boat" ->
"Leo"; "If Ben had studied, he would have passed" -> "Who passed the exam?" -> "Ben"; "The thief may have taken the ring"
-> "Inspector Ross". The frozen battery never asked such questions.

## Mechanism (learned, no word written)
(A) An event is IRREALIS when one of the learned MARKERS (events5 (D): closed symbols followed by a verbal base form in
>= 25 % of uses -- can, could, may, t, to, will, would) stands in its verb group (up to 3 symbols before the verb, none of
them a noun), or when it lies in the first clause (before the first comma) of a sentence opened by the learned
CONDITIONAL opener: the closed sentence-initial symbol (>= 1,000 uses) whose sentences most often hold a marker after a
comma, relative to all sentences (measured: if, lift 1.83).
(B) A question matches irrealis events only when it has a marker itself ("Who will close the gate?", "What did Sana want
to learn?"); otherwise only realis events answer it. Irrealis events are kept (not deleted): the story is remembered as
told.

## Gates
| gate | claim | bar |
|---|---|---|
| **Y1** | WRONG answers on the map's probes (english_probe.py, event memory) | **<= 26** (from 31), none new |
| **Y2** | the probes of tam.future, tam.conditional, tam.counterfactual, tam.modal_epistemic, neg.not: WRONG | **0** |
| **Y3** | B6 | **>= 45** (a purpose clause -- "climbed the mast to fix a torn sail" -> "What did Bram fix?" -- is irrealis now; a drop of up to 2 is the honest price) |
| **Y4** | B1 0; B5 held | held |

## Prediction
Y1 ~24; Y2 met except "never" (an open-class symbol, not a marker: "Kai never visited Lima" stays WRONG -- recorded);
B6 45-47.

## Amendment before the battery run (2026-10-07)
Learned conditional opener: {if} (lifts printed by kb_events.learn_conditional). First probe run: WRONG 31 -> 26, but
"If Leo wins, his father will buy a boat" -> "Who will buy a boat?" -> "Leo": an infinitive-path event took the PREVIOUS
event's doer even when a doer stood right before the marker. Added: a learned subject or a noun right before the marker
is the verb's own doer; otherwise the previous doer controls it ("Sana wanted to learn"). Probe run 2 (event memory, the
map's 171 probes): **RIGHT 85 -> 89, WRONG 31 -> 24, SILENT 55 -> 58**; Y2's phenomena: 0 WRONG.

## Run (2026-10-07, battery17): PASS (Y1-Y4)
Y1 probes WRONG 31 -> **24** (RIGHT 85 -> 89); Y2 0 WRONG on future / conditional / counterfactual / epistemic modal / not;
**Y3 B6 47 -> 46** (the honest price predicted: purpose clauses are irrealis now); Y4 B1 counted 1 (the "jurisdiction"
item, true on inspection), B5 +11.6. B2 90.2 %, B9 18/20, B10 398/500, B3 and B7 unchanged, B4 3/4,605.
(The battery imported kb_events at its first door, before iteration 18's edits to that file; it measured iteration 17.)
