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
