# Pre-registration -- PHASE B: THE CONVERSATION IS A WORLD (`core/transcript.py`, `chat_acts.py`; CHAT_PLAN.md phase B)

Registered 2026-10-02, before any code. Zero LLM. Offline sources only.

## 1. The claim

Speech acts and continuity come from AFFORDANCE over data the engine already has, not from an intent classifier: the
session's own history is a world (`introspect_prereg.md`'s idea in W1's form: a world is data), every reply is still one
frame, and the only English added lives in the chat layer (`frames.py`) as the engine's own realization vocabulary.
Core holds no word.

## 2. What is built

- `core/transcript.py` -- `TranscriptWorld(fields)`: the session's turns as records; `fields` is DATA handed in by the
  chat layer (word -> record field). Readings: a symbol that names a field (kind "M"). Structures: RECALL(field) over
  the most recent non-retracted turn holding that field. Evaluate: the field's content. attributed=False (the record of
  the conversation is exact). Content kinds: none (a recall word the answer did not use is not PARTIAL). The world holds
  no word; the chat layer's `fields_of(frame, text)` fills each turn's record from the realized frame.
- `frames.py` -- three new frames, each with an exact inverse: **META** (looking back: the question, the field, the
  content), **CHECK** (the world's value against a value the text itself names: match or not), **ACK** (a conversational
  move: the WordNet-classified act and what the engine can answer about). `META` word map, counted as the chat layer's
  vocabulary: the realization words frames.py already speaks (support, evidence, source, sources, answer, question) plus
  FOUR authored words: `why` -> support, `again`/`repeat` -> the previous frame re-realized, `shorter` -> the previous
  frame with one support/option/quote. Feedback words from phase A (`correct`, `wrong`) plus `no` as a denial that may
  carry a correction. Authored chat-layer words after this phase: 7.
- Acts by affordance (where each is decided):
  * META / REPEAT: the transcript world's RECALL structure wins the loop's rank (a computed value outranks a quoted gloss
    at equal coverage; a longer explicit structure of another world outranks it by coverage, so "the source of the nile"
    stays a Wikidata question).
  * CHECK (`frames.to_frame`): the top structure is unique AND the text contains, unused, an explicit reading of the
    answer world of the kind that world reads its own answer as (an entity beside a capital lookup; a number beside a
    salary lookup). Equal label -> match; different -> the stated value is reported against the world's. No ledger write
    (a yes/no question and an assertion look alike; `correct`/`wrong` remain the oracle).
  * ACK (`frames.to_frame`): no non-quoting world read any symbol AND at least one symbol is a conversational move per
    WordNet's own classification (`wn_acquire.speech_act`: a noun sense in the communication lexicographer file; the
    act label is WordNet's gloss head). Otherwise a text nothing reads stays PROPOSE.
  * CHOICE / CORRECTION (`core/session.py`): after READINGS, a turn whose symbols CONTAIN exactly one option's label
    while every other symbol of the turn is read by no non-quoting world is that choice (exact equality was W4's rule;
    "no, I meant X" and "the second one, tokyo" fall under containment). A denial word before it records the previous
    answer as contradicted (`deny`).
  * DENIAL CASCADE (`core/session.py`): `deny` marks the turn retracted; a retracted turn's values and used readings
    leave the context, so later ellipsis cannot bind to a denied answer.
  * MULTI-SENTENCE (`chat.py` Door): a text whose segmentation holds two or more sentence-final punctuation marks with
    symbols between them is run sentence by sentence through the same session; the reply is the realizations joined;
    every frame round-trips on its own.
- `chat.py`: the transcript world joins the default world list; `Door.turn` records frames into the session memory.
  The phase A gate (`python chat.py`) must still PASS on the enlarged world list (its stress words `why`, `repeat`,
  `shorter`, `again` now land in META/REPEAT frames; CONFAB 0 stands or the phase fails).

## 3. Held-out material (fixed here)

- ACTS: a scripted session of labelled utterances (label = the act expected at that position: ANSWER, FOUND, READINGS,
  PROPOSE, CONJECTURE, META, REPEAT, CHECK, ACK, CHOICE), written in `chat_acts.py` before the first run. Target 300;
  the count written is printed and is the denominator.
- DIALOGUES: generated from the orgchart data (independent dictionary verifier, as worlds_general) and from the offline
  Wikidata cache (gold by a direct edge read on the source, not through the loop) in fixed templates: salary/manager
  chains with "and of Y", "what is the difference", "double it"; capital/currency/continent chains with "and its",
  "and of C2", "and the capital"; records->Wikidata chains; a READINGS then a correction; a `why` after an answer; a
  `wrong` then a question that must not bind to the denied value. Target 100 dialogues of 3-5 turns; count printed.

## 4. Gates (CHAT_PLAN.md CH2, CH3, CH5)

  B1  ACTS         act == label on >= 0.90 of the ACTS set; the confusion table printed; the F4-f literal check on
                   `core/transcript.py` and `core/session.py` (no literal shares a token with any utterance).
  B2  KNOCKOUT     the META word map permuted (why<->again, shorter<->source ...): the acts FOLLOW the permutation on the
                   META/REPEAT items (>= 0.90 of them land in the permuted act), so the mechanism is the map as data,
                   not a hidden list elsewhere.
  B3  DIALOGUES    dependent turns correct >= 0.80; the stand-alone arm (each dependent turn reasoned alone) clearly
                   worse (<= half); denied values never re-bound (0 binds to a retracted answer).
  B4  ROUND TRIP   parse(realize(frame)) == canonical(frame) for every reply of B1 and B3, 3 RNG samples: 100%.
  B5  FATAL        CONFAB 0 on every gold-bearing turn; LAUNDERING 0; MISATTRIBUTION 0; bare abstain 0.
  B6  PHASE A      `python chat.py` still prints ONE DOOR: PASS and CONFAB: 0 with the transcript world loaded; the six
                   shared gates and validate_chat unchanged.

## 5. Predictions (committed)

B1 0.90-0.95: ACK misses on multi-word thanks ("thank you very much": the noun is `thanks`), CHECK misses where the
text's stated value is also an entity of a second surviving structure (then READINGS, correctly). B2 holds. B3 0.85-0.95
on orgchart dialogues, lower on Wikidata chains where the offline cache lacks a label; stand-alone arm < 0.2. B4 100% by
construction. B5 0. B6 holds. Honest uncertainty: the containment rule for CHOICE may fire on an unrelated later question
that happens to contain an option label; the ACTS set includes such a trap and it counts against B1.

## 6. Declared residual
The rect scene as a World of the loop is NOT built here (phase B-2): the server still joins its two paths at the
fallback. Updating the user's own data by assertion ("alice's salary is 130") is reported as CHECK, not applied: the
confirmation channel remains `teach` with a gold.

## 7. RESULT -- filled in after the run

### Run 1 (2026-10-02) -- FAIL B1/B3/B5; B2 (knockout 18/18), B4 (round trip 497/497), B6 (phase A PASS) hold
B1 acts 85/126 = 0.675. By family: META 12/14, REPEAT 6/6, CHOICE 3/3, READINGS 6/6, NOT-CHOICE 2/2 (the traps did not
fire); ACK 16/23 (misses: thank you, hey, cheers, great, please, thank you very much -- WordNet has no communication
noun for them, as predicted; "hello again" repeated: the recall word wins); CHECK 7/17 (three PARTIALs whose only unused
reading is the stated value; two yes/no forms that read as two structures -> READINGS; "is it 2/3" has no structure);
FOUND 3/5 (the graph reads "what" as an entity and "is a" as instance-of -- a standing offline-cache limit, see phase
A); **PROPOSE 4/24: twenty REQUESTS the engine cannot do ("write a poem about paris", "sing a song", "what time is
it") landed in FOUND (the dictionary quotes the topic, E-10's registered behaviour) or ACK (a request noun WordNet files
under communication).** The engine has NO act for a request: nothing in it tells "write a poem about paris" from "what
is a pomegranate" without syntax or a learned question frame (E-10's accepted-frame mechanism, not wired to the door).
Recorded as the headline gap of this phase, not relabelled.
B3 dependent 54/75 with 20 "confabs": every one my gold -- "what is the difference" after two values is second minus
first (turns.py D11), I had subtracted the other way. Also found: two late turns borrowed an OLDER question's column and
operator over the text's own filters and left the text's column word unread ("is the city of research berlin" -> the
lowest salary in research; "what is the city of marketing" -> a count), which the turns-gate dominance rule missed when
the borrowed structure also used an extra filter.
Amendments before run 2: the dialogue gold fixed; CHECK admits a PARTIAL whose only unused reading is the stated value;
`core/reason.py` R2 gains its other half -- a context-using structure must USE every predicate reading the text supplies
to its world. The REQUEST gap is left open by design (the fix is E-10's learned frames or syntax, an owner decision).

### Runs 2-4 (same day) and the RESULT: CONVERSATION WORLD: SOUND, acts bar NOT MET
Run 2 (gold fixed, CHECK on PARTIAL, R2 predicate half): B3 74/75 = 0.987 PASS, B5 CONFAB 0 PASS; B1 unchanged -- the
trace (a read-only `trace` list added to `core.reason`) showed WHY: in a long session an operator word borrowed from
context removed the table world's default LOOKUP (`opset = ops or [LOOKUP]` was written for explicit operator words),
so "what is the city of marketing" had no context-free structure at all; and a quoted gloss from an earlier FOUND turn
sat in context as a value. Fixed: the table keeps LOOKUP unless the operator is explicit; quoted answers never enter
context. Run 3: B1 88/126; two shared gates regressed -- F4-f on quoted words in a comment of mine, and W5-c because
"what is a pomegranate" now read as LOOKUP(the entity "What", instance of): the alias "is a" -> P31 had entered the
offline Wikidata fixture that afternoon. Vector found: the live chat (--online) re-read earlier gloss ANSWERS as context
labels through the online graph, so spans of dictionary text ("confident and assured", "death and taxes", "is a") were
searched live and written into the shared cache. Repair: 559 keys whose span text is a span of a gloss of a word typed
in the live session and of no registered question were removed (backup `_nldata/wikidata_cache.backup-20261002.json`);
`kb_wikidata.Wikidata(cache_path=...)` gives a live session its own cache file; the context fix above closes the vector.
**Run 4: B1 90/126 = 0.714 FAIL; B2 18/18; B3 74/75; B4 497/497; B5 0/0/0/0; B6 phase A PASS (p95 0.20 s); the six
shared gates and validate_chat reproduce.** By family: META 12/14, REPEAT 6/6, CHOICE 3/3, READINGS 6/6, traps 2/2,
ANSWER 29/29, FOUND 5/5, ACK 16/23, CHECK 7/17, PROPOSE 4/21. The 36 misses: 21 REQUESTS (no act exists; FOUND quotes the
topic, ACK fires on a request noun WordNet files under communication), 7 ACK words WordNet does not class as moves, 7
CHECK forms that read as two structures or have none, 2 META phrasings without a recall word ("what did i ask", "how do
you know"). Registered as SOUND (E-7's precedent), with the acts number printed beside it. Authored chat-layer words after
this phase: 7 (correct, wrong, no, why, again, repeat, shorter). The REQUEST act is the next decision: E-10's learned
question frames wired to the door (a definition question is a frame the user confirmed once; everything else no world
reads is an offer), or syntax. Phase B-2 (the rect scene as a World) stands as declared.
