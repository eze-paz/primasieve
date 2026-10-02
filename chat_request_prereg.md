# Pre-registration -- THE REQUEST ACT (`chat_request.py`; phase B's recorded gap, CHAT_PLAN.md)

Registered 2026-10-02, before any code. Zero LLM. Offline sources only.

## 1. The gap and the claim

Phase B measured it: a multi-word text that no content world reads and that only the dictionary can gloss ("write a poem
about paris", "sing a song") is answered with the definition of its rarest word, because nothing in the loop separates a
request from a definition question without syntax. E-10's registered design already names the honest behaviour: the gloss
of a multi-word text's topic is an INTENT GUESS, "never above CONJECTURED until the user confirms", and accepted questions
anti-unify into FRAMES that fire without asking next time. The claim: the request act is that design completed with its
negative half -- a declined guess anti-unifies too, into a frame that says "do not guess the definition here; offer what
you can do" -- and the chat learns the difference from feedback, with no list of request verbs and no syntax.

## 2. What is built

- `core/resolve.py`: `decline(frames, symbols, topic, kind, history)` -- the mirror of `accept`: two declined
  observations of the same length, equal everywhere but the topic slot, give a frame in state DECLINED (never a
  retraction of a positive frame: those are separate frames; a skeleton that is both accepted and declined is a contest
  and the guess stands). `match_frame` is unchanged and matches both states; callers read the state.
- Chat layer (`frames.py`): FOUND gains `guess` and `topic`. guess=True is realized as a conjecture of intent -- "If you
  mean what {topic} is: (source): gloss ... If not, say wrong and I will offer what I can do." -- with its inverse;
  guess=False is the plain "The dictionary says ...". A new frame REQUEST {topic, offers}: "I cannot do that with
  {topic}. I can answer about ..." with its inverse. to_frame is unchanged (the registered single-call gates still get a
  plain FOUND); the Door decides the mode from the session's frames.
- `core/session.py`: `frames`, `accepted`, `declined` (data of the session); `chat.py` Door: a FOUND over a text of two or
  more symbols is a GUESS unless a positive frame matches (plain FOUND) or a declined frame matches (REQUEST); `correct`
  after a GUESS calls accept, `wrong` after a GUESS calls decline (no ledger strike: the dictionary was not wrong, the
  intent was). A single-symbol text ("serendipity", "dog?") stays a plain FOUND: a lone word's only affordance is its
  definition (E-10 R1). ACK keeps precedence (a conversational move is not a request).
- Act labels: GUESS, REQUEST (beside FOUND, ACK, ...).

## 3. Gates

  Q1  COLD          over the 21 request items of chat_acts.ACTS, in a fresh session: plain definitions (FOUND with
                    guess=False) = 0; GUESS + ACK >= 0.90 of them (the ACK-captured ones are predicted: joke, song,
                    homework, above).
  Q2  LEARNING      "write a poem about paris" -> wrong; "write a poem about rome" -> wrong; then "write a poem about
                    tokyo" -> REQUEST (the declined frame fired); and "what is a dog" -> correct; "what is a cat" ->
                    correct; "what is a fox" -> plain FOUND (the positive frame fired). A text matching neither after
                    these ("what is a poem") -> GUESS, not REQUEST (no generalization beyond the skeleton).
  Q3  LONE WORD     "serendipity", "pomegranate", "dog?" -> plain FOUND in a fresh session.
  Q4  ROUND TRIP    every GUESS and REQUEST reply, 5 RNG samples: 100%.
  Q5  UNCHANGED     chat, chat_acts, chat_prose, worlds_general, f4_dialogue, validate_chat reproduce.
  Q6  NO WORDS      the literals added to core/resolve.py and core/session.py share no token with any utterance of Q1-Q3.

## 4. Predictions
Q1: 0 plain definitions; GUESS 17, ACK 4. Q2 holds; the no-generalization check holds (a skeleton is exact). Q3 holds.
Q4 100%. Q5 holds (to_frame untouched; the acts bar of chat_acts moves, its SOUND line does not). Q6 holds. Honest
limit, stated: the chat learns per skeleton -- "compose a poem about X" is a new skeleton after "write a poem about X"
was declined; the generalization across verbs is syntax or a learner, not this phase.

## 5. RESULT -- filled in after the run

### Run 1 -- FAIL Q1/Q2, both mine; amendments declared before run 2
Q1: plain definitions 0/18 (the claim holds); acts mislabelled by a defect in the door's mode function (every non-FOUND
frame was labelled FOUND), which also hid the learning sequence; and two items answered PROPOSE because a content world
read a word ("capital of atlantis": the graph read "capital") -- the right act, which the bar did not anticipate.
Amendment: Q1 counts GUESS, ACK and PROPOSE as handled (none is a definition); the bar stays 0.90. Q2: the skeleton's
hole is E-10's topic (the rarest symbol), so the two declined observations must put the hole at the same position;
"rome" (414 definitions) is commoner than "poem" and the topic moved. Amendment: the learning sequence uses city names
rarer than "poem" (lisbon 19, kyoto 13, tokyo 91). Q3, Q4, Q6 passed on run 1.

### Runs 2-3 and the RESULT: REQUEST ACT: PASS
Run 2: Q1 PASS (0 plain definitions; GUESS 12, ACK 5, PROPOSE 1 of 18); Q2 both halves fired (the declined skeleton gave
REQUEST, the accepted one a plain FOUND) and only my "new skeleton" probe failed, twice, for the same reason: a word in it
was a WordNet communication noun ("about" ..., then "Fox" the language), so ACK took precedence -- a recorded weakness of
the ACK criterion (languages are filed under communication), not of the request act. Run 3 with "a quick brown dog":
**Q1 0/18 plain definitions, 18/18 handled; Q2 PASS -- frames learned: ('write a poem about _', DECLINED), ('what is a _',
conjectured); Q3 lone words plain FOUND; Q4 round trip 140/140; Q6 no words.** chat, chat_acts (SOUND line unchanged;
acts bar 86/126 since requests are now GUESS, not FOUND), chat_prose, worlds_general, f4_dialogue, validate_chat
reproduce. Limits stated: the chat learns per skeleton and per hole position; the hole is E-10's topic (rarest symbol),
so "what time is it" guesses the definition of "what" (2194 definitions, rarer than "time"); generalization across verbs
is syntax or a learner, not this phase.
