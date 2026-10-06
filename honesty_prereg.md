# Pre-registration -- LOOP ITERATION 2 (B1): THE BASELINE'S FALSE FACTS (`honesty.py`; 2026-10-06)

Registered 2026-10-06 before the fixes run. Zero LLM. The battery's first measurement (BATTERY.json, 2026-10-06) put B1
-- false facts stated as facts -- at 20, and B1 is never relaxed, so the loop's rule makes it iteration 2. A diagnostic
listed the 21 cases (all in B2) BEFORE this file:
- 14 are dictionary glosses ("If you mean what eiffel is: ..."), counted by the battery as facts: a COUNTING defect of
  battery.py (a quoted gloss is not a claim about the question; B10 already excluded them);
- 4 are the new story memory answering what it has no basis for ("how are shakespeare and hamlet related" -> "As you
  told it: japan"): its rule answered the agent of any event with the question's verb even when no role overlapped;
- 1 is a TEST defect: the B2 generator's WordNet "synonym" turned "gadget" into "widget", another product, so the gold
  was wrong;
- 1 is a genuine engine miss: "mean quantity in the s in march" -- a one-letter symbol dropped, a different question
  answered ("the mean quantity of march"); kept, not excused.

## Fixes (declared)
1. battery.py: a quoted gloss is not counted in B1 (as in B10).
2. core/events.py: the memory answers only when at least one role of the selected event shares a content symbol with the
   question.
3. build_battery.py: a synonym is never substituted for a word a world reads as a name or a filter value; B2 is
   regenerated (it is a draft awaiting the owner's review, not yet frozen).

## Gates
| gate | claim | bar |
|---|---|---|
| **H1** | B1 on the battery after the fixes | **<= 1** (the kept engine miss), target 0 |
| **H2** | B2, B9, B6 not lower than before the fixes (B6 measured with the events on: 31/100 in events_prereg.md) | not lower by more than 2 points |

## Run (2026-10-06): H1 PASS, H2 NOT PASSED (B6) -- B1 is 0
After the three fixes and B2's regeneration, the full battery (1,617 s): **B1 0** (H1 PASS -- the one-letter case is no
longer in the regenerated B2, so the engine miss it showed is not re-measured here; it stays a known weakness). B2
372/498 = **74.7 %** (was 73.7); B9 **17/20** (unchanged); B10 70/500 as facts, 0 guesses; B3 dictionary true 95.9 % /
false-yes 0.4 %, conversational 83.9 % / 0 %; B7 15/18 = 83 % at 0 % reversed; B5 +11.6; B4 novels 3/4,605. **H2 MISS on
B6: 26/100 in the battery's live door** against the 31/100 the bar quoted -- but that 31 came from events.py's PLAIN door,
so the bar compared two different doors (a defect of this file); against the battery's own previous B6 (4/100, before the
event reader) it is +22. Recorded as written: NOT PASSED on H2.
