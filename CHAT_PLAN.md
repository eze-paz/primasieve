# CHAT PLAN -- make primasieve behave like an LLM chat (owner's ask, 2026-10-02)

A plan, not a pre-registration. Each phase below becomes its own prereg + one runner file before any code, per
ARCHITECTURE.md's rule. Nothing here is built yet.

## What "behave like an LLM chat" means here, stated so it can fail

An LLM chat has five properties a user notices. Primasieve has one of them today.

| property | what an LLM chat does | primasieve today | status |
|---|---|---|---|
| ONE DOOR | any text in, one reply out, never a stack trace, never silence | `core/session.py` + `frames.py` give one reply per turn, bare abstain 0 (F4) -- but only inside gate runners; the live server (`emergence/en_server.py`) still runs the older rect-world path and consults the general loop only as a fallback | half |
| ANY SPEECH ACT | greetings, thanks, instructions, "why?", "shorter", "no, I meant X", assertions, multi-sentence turns | questions only; feedback is four fixed commands (`wrong`, `correct`, `forget`, `means`) | missing |
| CONTINUITY | pronouns, ellipsis, topic carried across turns, preferences remembered | W4 turns bind through context readings (12/12 on the gate set); READINGS choice binds a shape; teaching accumulates | partial, small set |
| PROSE | replies read as sentences, vary, never sound like a log line | `Answer: Paris (per Wikidata). evidence: France -capital-> Paris` -- exact, invertible, templated | missing |
| SPEED | reply in about a second | ~1 s/question warm on the KG gate, cold Wikidata lookups are seconds to tens of seconds | partial |

The sixth LLM property -- answering anything, including what it does not know -- is the one this project refuses.
The engine abstains with a next step (PROPOSE) where an LLM guesses. That stays. The target is: same door, same
continuity, same prose, same speed, with the fatal columns (confabulation, misattribution, laundering) still at zero.

## The separation that makes this admissible (answers the owner's 2026-10-02 question on probability)

Every reply is produced in two stages, and the no-probability invariant applies to exactly one of them.

- WHAT IS SAID is a FRAME: ANSWER / READINGS / PARTIAL / FOUND / PROPOSE / CONJECTURE, computed by `core/reason.py`
  through `core/session.py`, verdict-gated and exact. No sampling, no score, no temperature. Unchanged.
- HOW IT IS SAID is a REALIZATION of that frame. `frames.py` already uses RNG over meaning-preserving surfaces and
  inverts exactly. A temperature belongs here and only here: it chooses among surfaces that all parse back to the
  same frame. A realization that fails the round trip is not said. So sampling can never change a claim; it can only
  change the sentence. That is the invariant restated, not relaxed: no probability leaves the MEANING side.

Everything in this plan keeps that line. Phase C puts a temperature on the form side with zero LLM. Phase D puts an
instruct model on the form side behind the same round-trip gate; it is an owner decision because of the standing
zero-LLM rule and is off by default.

## Terminal criterion (fixed so the arc can end)

CHAT is claimed only when all of CH1-CH5 hold on transcripts the engine never saw, CONFAB 0 throughout.

  CH1  ONE DOOR      every held-out utterance gets exactly one reply from one entry point; exceptions 0; bare
                     abstain 0; p95 warm latency <= 2.0 s per turn offline.
  CH2  SPEECH ACTS   on a mixed held-out set (questions, assertions, greetings, meta, edits, corrections, multi-
                     sentence) the reply's frame kind is the pre-labelled one >= 0.90, with NO authored cue list:
                     the F4-f string-literal check (no literal in the act-selection path shares a token with any
                     test utterance) and a shuffled-vocabulary knockout.
  CH3  CONTINUITY    >= 0.80 of held-out 3-5 turn dialogues (pronoun, ellipsis, choice, correction) bind correctly;
                     the single-turn arm on the same dialogues must be clearly worse (else the set does not test
                     continuity).
  CH4  PROSE         round trip parse(realize(frame)) == frame 100% over 1000 sampled realizations per frame kind;
                     MISREPORT 0; under the independent-grammar judge of LOOP.md it.10, realized replies are no more
                     surprising in form than real replies of the chosen register; novelty >= 0.40; variety >= 3
                     surfaces per frame. Human reading printed beside it, never scored.
  CH5  FATAL COLUMNS confabulation 0, misattribution 0, laundering 0, stale 0, misreport 0 on every run of every
                     phase. A regression here fails the arc regardless of CH1-CH4.

A phase that misses its gate is a recorded null, as in LOOP.md. A WALL (every remaining hypothesis null) ends the arc
and is reported as such.

## Phases -- each one file + one prereg, imports `core/` only

### Phase A -- the one door (`chat.py`, `chat_prereg.md`)
Build the single entry point the user actually types into, and route the server through it.
- `chat.py`: a REPL (stdin/stdout, also piped) over ONE `core.session.Session` holding every live world:
  `core/kg.py` (Wikidata, offline cache), `core/table.py` records for every JSON under `worlds/`, `core/exec.py`
  (arithmetic, operator words), `core/gloss.py` (dictionaries), `core/triples.py` sources, plus `core/ledger.py`.
  Every turn -> `Session.turn` -> `frames.to_frame` -> `frames.realize`. Feedback (`wrong`, `correct`) becomes
  `Session.teach` through the same door, not a side channel.
- `emergence/en_server.py` `/api/say` calls the same function; the rect world becomes one more world in the list
  (it is already a World in spirit: readings/structures/evaluate). The two chat surfaces become one.
- A transcript file format (`.jsonl`: `{"turn": text, "frame": ..., "reply": ...}`) so every later gate is a
  replayable transcript and the human can read it.
- Latency: profile a 100-turn transcript, warm. The known cost centres are KG two-hop search and gloss lookups;
  cache readings per symbol tuple inside a session.
Gate: CH1 on a 200-utterance held-out set drawn from the existing gates' prompts plus new ones; CH5.
Prediction: passes except latency on cold KG; the per-session reading cache fixes it. Risk: unifying the server's
older reply strings with frames deletes behaviour `validate_chat` 21/21 asserts; that gate is re-pointed, not
loosened.

### Phase B -- the conversation is a world (`core/transcript.py` + runner `chat_acts.py`, `chat_acts_prereg.md`)
This is the move that gives speech acts and continuity without an intent classifier (session.py's rule: no speech-
act taxonomy, no question-form classifier). It implements the pre-registered but unbuilt introspection world
(`introspect_prereg.md`) in the "a world is data" form of W1.
- The session's own history is a RECORDS world: each turn is a record {text, frame kind, values, supports, sources,
  missing, options}. References induce from the data as in `core/table.py` (a value that is the key of an earlier
  turn's option is a reference). No code per predicate; the trace is the data.
- Then by affordance, with nothing authored:
  * "why" / "how do you know" -> a structure over the previous record's supports/sources (META is a question the
    transcript world answers);
  * "shorter", "again", "in one line", "the first one" -> readings over the previous frame's own slots: a CHOICE or
    a re-realization of the SAME frame with a different realization parameter (the frame is unchanged, so it is
    form, not meaning);
  * an utterance with no question reading that the exec/table worlds read as (entity, property, value) is an
    ASSERTION: it goes through `Session.teach` if a world can learn from it; otherwise it is held ATTRIBUTED to the
    source "user" with its own `core/ledger.py` record (W6 makes the user a source whose record can be contradicted
    by a world, exactly like Wikidata's);
  * "no, I meant X" -> a correction: the previous turn's frame is retracted (cascade through Beliefs) and X is bound
    as the reading, via the existing READINGS-choice path extended to a value not in the option list;
  * greetings, thanks, "ok": utterances whose every symbol resolves to nothing in any world except the gloss world
    are an ACK frame (seventh frame, `frames.py`), realized as a short acknowledgement with the engine's standing
    offer (what it can answer about). ACK is the honest form of chit-chat: the engine says what it is.
- Multi-sentence turns: segment on sentence boundary (Unicode category), run the loop per sentence, PIPE across
  them as across worlds (W2's mechanism, one more pass).
Gate: CH2 on a 300-utterance labelled held-out set (labels are frame kinds, written before the run), CH3 on 100
held-out dialogues of 3-5 turns, both with the shuffled-vocabulary knockout and the string-literal check; CH5.
Prediction: CH2 passes for META/CHOICE/ASSERTION/ACK; the weak cell is CORRECTION where X is itself ambiguous
(READINGS again, which is right). CH3 reaches 0.80 on pronoun/ellipsis, misses on corrections stacked two deep.
Null to report honestly if it appears: an utterance both the transcript world and a content world read (e.g. "the
first one" when a table has a column "first") -> READINGS, and the user is asked. That is the price of no list.

### Phase C -- replies that read as prose, zero LLM (`frames.py` growth + `chat_prose.py`, `chat_prose_prereg.md`)
Make the realization a sentence, keep the inverse exact, and put the temperature where it is admissible.
- Realization = an ATTESTED SKELETON from a dialogue register with the frame's slots pinned as the words the
  situation selects (LOOP.md's own conclusion: form from text, meaning from grounding; the frame is the grounding).
  Candidate skeletons are the class sequences of `core/seqform.py` induced on the register; fillers around the
  pinned slots are chosen under the attested-pair constraint of it.9 with a TEMPERATURE over the class-bigram code
  length of the candidates (declared as a form parameter; it ranks surfaces, it never touches the frame).
- parse() stays the inverse: a realization is emitted only if parse recovers the frame exactly; otherwise the next
  candidate; if none, the Phase-A template (which always round-trips). MISREPORT 0 by construction, measured anyway.
- The register is an owner decision stated here: candidates are (a) a small authored set of reply sentences per frame
  kind (honest: authoring, counted and printed, like the seeded schemas of Phase 3); (b) Wiktionary example sentences
  filtered to declarative/interrogative forms; (c) the owner's own chat logs. (a) is the fallback; (b) is zero-
  authoring and is tried first.
- ANSWER with several values, READINGS with many options, long supports: realization gets length control (the
  "shorter" edit of Phase B is a realization parameter, so it costs nothing new).
Gate: CH4 (round trip 1000/kind, the it.10 judge on the register, novelty >= 0.40, variety >= 3); CH5; and CH1
re-run so prose did not cost latency.
Prediction: round trip 100% (by construction), judge within the it.10 band (form 70-85% of the way from shuffled to
real), novelty 0.4-0.6 because the pinned slots are novel by nature. Risk, stated: on register (b) the skeletons may
not cover READINGS/CONJECTURE shapes (lists with alternatives); then those two frames stay templated and the count of
templated frames is the printed number, as in Phase 3.

### Phase D -- an instruct narrator at the edge, behind the same gate (`chat_narrator.py`, prereg) -- OWNER DECISION
The E-13 pattern: a small instruct model paraphrases the Phase-C realization; the engine's parse() must recover the
same frame on the paraphrase, and the paraphrase must evaluate identically on fresh situations where the frame has
world content; MISREPORT 0 or the paraphrase is dropped and the Phase-C sentence is said. Temperature lives in the
narrator. Off by default; `--narrator` flag; every gate runs with it off and on, and the frames must be identical
between the two arms by construction (the frame is fixed before the narrator sees anything).
Why it is a separate phase: LOOP.md's standing rule is zero LLM anywhere; E-13 used one at the edge with the owner's
ask; this phase needs the same explicit go-ahead and is not required for CH1-CH5.

### Phase E -- breadth as data, no new mechanism (data-loading steps, each a one-line note in ARCHITECTURE.md)
An LLM feels broad. The engine is exactly as wide as its worlds, so width is a loading job: the plant telemetry as a
records world (named in LOOP.md as the owner's grounded domain), more `worlds/*.json`, the full offline Wiktionary
and the Wikidata cache already present under `_nldata/`. Each new world must pass W1's bar (zero code, teaching
pairs only) and `critical.py` (its record in the ledger). No gate of its own beyond CH5.

## Order and dependencies
A first (everything replays through it). B next (acts and continuity; it is the introspection world the project
already registered). C after B (the "shorter" edit is defined in B, realized in C). D only on the owner's go-ahead,
any time after C. E in parallel with any phase.

## What this plan does not promise
- Open-ended generation (summaries, essays, code, opinions): no world checks them, so the engine would be guessing.
  Out of scope; a request for one gets a PROPOSE naming what it can do.
- Facts outside the attached sources: PROPOSE, by design.
- A confidence percentage: never. CONJECTURE already says "probably X rather than Y" with the record of each source,
  which is the honest form of the same information.

## Numbers to watch, in the project's style
The count of authored reply sentences (Phase C), the count of frames still templated, the count of utterances sent to
READINGS by the transcript world colliding with a content world (Phase B), p95 latency, and the five fatal columns.
The EM-style accuracies are secondary to those.
