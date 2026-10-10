# R19 -- A WORLD STATE WITH TIME AND PLACE (2026-10-10)

Registered before any run. The owner's observation: the emergent reader is not time-aware, and place matters for this
task. The induced forms and the hand reader's events are flat per sentence; sentence order is their only time, and a
place is a string on a verb or noun. R19 adds a world state built from the events in reading order: for each entity a
timeline of location (after movement, placing, finding and leaving verbs), of possession (after giving, taking,
finding, dropping), and the order of arrivals; "now" questions read the latest valid entry, order questions read the
sequence, place questions read the location timeline. The filter the owner named follows: the state keeps the current
entry per entity. The state's update rules are written by hand in this first version (a scaffold to measure the value
of state); inducing them from verified cases is the R17 route applied to time and place, registered after this.

Validation: `val_timespace.json` (6 builder-written stories, 30 questions, all about time and place) plus the 80
story questions already in use. Compared: chunk reading (0.4B model), chunk + raw notes (R18's form), the world state
alone (exact, abstains when it has no entry), and the merged engine (world state first, then the reader, then the model).

| gate | bar |
|---|---|
| **R19-a** | on the 30 time/place questions, the world state alone answers >= 18 with precision >= 0.90 |
| **R19-b** | merged engine on the 30: >= chunk reading + 8 |
| **R19-c** | on the 80 story questions the merged engine with the world state is not worse than without it (>= 69) |
| **R19-d** | B6 once, only if a-c pass: >= 85 with the 0.4B model |

## Progress (2026-10-10, `worldstate.py`, world state alone on the 30 time/place questions)

First build 14 matched / 11 right (0.79); after repairing place-phrase extraction (clause words, time words and
determiners excluded from place noun phrases; "at the end of X" read as a place; waiting / finding fix a location):
**15 matched / 14 right (precision 0.93)**. R19-a: precision PASS, coverage 15 < 18 **MISS by three**. The 15 unanswered
are: role questions that belong to the reader or the model (who found the key, who took the boat), copular states the
reader has no event for ("the key was on the hook"), particles between verb and object ("set the lantern down"), and
pronoun patients ("dropped it"). The merged engine (world state -> reader -> model) is scored next on the same 30.

## Result (2026-10-10, `r19_results.json`)

| set | model alone (chunk) | world state alone | merged: world -> reader -> model |
|---|---|---|---|
| time/place questions (30) | 14 | 14 (15 matched, 14 right) | **24** |
| story questions (80) | 59 | 0 (no entry: the world abstains) | **69** |

| gate | measured | bar | verdict |
|---|---|---|---|
| **R19-a** | world alone 15 matched at 0.93 | >= 18 at >= 0.90 | MISS by three on coverage |
| **R19-b** | merged 24 vs chunk 14 (+10) | >= chunk + 8 | **PASS** |
| **R19-c** | merged on the 80 story questions 69 | >= 69 | **PASS** (at the bar; the world never fires there and never harms) |
| **R19-d** | B6 once | only if a-c pass | not run (R19-a) |

Reading: on questions about time and place the learned model reads the whole story and gets 14 of 30; a world state
built as the text is read, consulted first, lifts the engine to 24 of 30, and costs nothing on the other questions.
Set beside R18 (an unfiltered log of the same events added one answer in 80), this is the owner's hypothesis confirmed
in the form that matters: comprehension of time and place depends on the text being parsed into a *state* -- what is
current for whom, in order -- not on how much of the text is in view. The state's update rules are hand-written here;
making them emergent (induced from verified cases, with the R17 route) is the registered continuation, as is raising
the world's own coverage (copular states, particles, pronoun patients) before B6 is run once.
