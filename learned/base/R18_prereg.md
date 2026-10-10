# R18 -- DOES COMPREHENSION DEPEND ON HOW THE TEXT IS READ? (2026-10-10)

Registered before any run. The owner's hypothesis: a reader that takes a paragraph phrase by phrase and builds a
hierarchy of short-term models as it goes (who is where, what happened to whom, what we were told earlier) understands
more than one that takes the paragraph as a single chunk. R18 tests it on the learned model with no training: the same
questions, the same model (`ckpt_read1b.pth`, the 0.4B reading engine), four input forms:

| form | what the model sees |
|---|---|
| **chunk** | the whole story, then the question (R1b's prompt) |
| **windows** | two-sentence windows one at a time (the engine's grep form), first answer wins |
| **chunk + notes** | the story, then "Notes:" -- one line per event the hand-rule reader extracted while reading sentence by sentence, in order ("a bear broke the fence"; "Nadia gave Osip a pot of honey"), then the question |
| **notes only** | the notes, then the question |

Validation: `val_stories.json` + `val_fables.json` (80 questions). B6 (100) is run once per form only if R18-a holds.

| gate | bar |
|---|---|
| **R18-a** | on validation, chunk + notes beats chunk by **>= 5** right answers |
| **R18-b** | B6 once: chunk + notes >= 85 (chunk: 80) |
| **R18-c** | notes only is reported: how much of comprehension survives when the text is replaced by its model |

Prediction: notes help on who-did-what questions and hurt on where/why questions the reader's events do not carry;
net +3 to +8 on validation. If notes-only is close to chunk, the model mostly reads the notes anyway, which argues
for an engine that builds the model first and reads the text only where the model is silent.

## Result (2026-10-10, `r18_results.json`, validation 80 questions, 0.4B engine, no training)

| form | right |
|---|---|
| chunk (whole story) | 59 |
| windows (two sentences at a time) | 58 |
| chunk + notes (the reader's events, in reading order) | **60** |
| notes only | 41 |

R18-a **MISS**: raw notes add one answer. Notes alone keep 41 / 59 = 70% of the chunk's comprehension, so the model does
read the notes, but an accumulated log of events adds nothing to the text it is appended to. The owner's reading of
this, made before the result was in: notes must be a filtered *state*, not a log -- what is current per entity, in time
order -- which is R19. The hypothesis that reading-as-you-go beats reading-a-chunk is not refuted by this run; it is
untested until the notes carry state.
