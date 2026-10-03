# Pre-registration -- EVERYTHING ON, ONE LONG CONVERSATION: do the new abilities compound? (`together.py`; EMERGENCE_PLAN.md, next step 1)

Registered 2026-10-03 before any code. Zero LLM. Offline. Owner's framing: run everything together, and keep an open mind
about whether more emergence can be caused.

## 1. What is being asked

Nine abilities were added and each tested alone (EMERGENCE_PLAN.md). Several are OFF by default in the chat: memory
across sessions (`--store`), a learned word crossing between knowledge sources (`transfer`), the engine proposing its own
question (`propose`), and the honesty rule that a guess is said to be a guess. This run turns them all on in one long
session and measures three things: (a) nothing gets worse -- the fatal columns stay at zero and the 200-utterance chat
gate's correct count does not drop; (b) the price -- how often the chat now says "Probably ..." where a plain answer
would have been given; (c) COMPOUNDING, the one measurable sense of "emergence" available here: an answer that is right
only when two or more abilities act together, shown by switching each ability off and watching the answer go.

## 2. The protocol (declared)

One session, three parts, then a second session in a fresh process:
1. **The chat gate's 200 utterances** (chat.held_out(), its own order), through a Door with store, transfer and the
   definition-frequency tie-break on. Scored with the chat gate's own `score`.
2. **A dependent batch** that needs the new abilities: arithmetic words taught only on the records ("the difference
   between 9 and 4", "the total of 3 and 4": transfer -> a conjecture); the user confirms one ("correct") -> the word
   becomes the arithmetic world's own and the next such question is a plain answer; a denial of a wrong guess ("wrong")
   -> never repeated; a records question through a word taught only in arithmetic ("the salary of research minus support").
3. **Proposals.** The gate asks the engine for its own question (a proposal word mapped as data, like the transcript's
   fields); the engine proposes; the gate, as the user, ASKS that question; the engine answers; the gate confirms it when
   the independent verifier agrees ("correct") or denies it ("wrong"). Up to five rounds; a proposal is never repeated.
4. **Session 2**: a fresh process loads the store, answers the dependent batch again and ten of the chat items: what was
   confirmed in session 1 is a plain answer now, what was denied stays denied, nothing is re-searched.

Arms: ALL (as above); BASE (the chat gate's Door: no store, no transfer, no proposals); and one ablation per ability
(ALL minus transfer; ALL minus proposals; session 2 without the store). Every arm sees the same utterances.

## 3. Gates

- **E1 nothing worse.** On the 200 chat utterances: CONFAB 0, LAUNDERING 0, MISREPORT 0, exceptions 0; correct count in
  ALL >= BASE; p95 latency <= 2 s.
- **E2 the price, reported.** The share of value answers that are CONJECTURED ("Probably ...") in ALL, over the 200 and
  over the dependent batch; the count of those that the verifier says are right.
- **E3 the dependent batch.** Transfer answers CONJECTURED and right; after "correct" the next same-word question is a
  COMMIT; after "wrong" the denied value never returns; the records-through-arithmetic question answers. BASE answers
  none of these (NOT FOUND / PROPOSE): FAILS ON MAIN.
- **E4 proposals.** At least one proposal; every proposed question is a question the session had seen with one symbol
  changed or a symbol the session saw; answering it and confirming reduces the residue (goals count falls); no
  proposal repeated; no proposal on an irreducible goal.
- **E5 session 2.** From the store, in a fresh process: the confirmed words answer as COMMIT, the dependent batch's
  answers equal session 1's post-confirmation answers, 0 words re-searched; WITHOUT the store the same process answers
  none of the dependent batch (FAILS ON MAIN).
- **E6 compounding, counted.** For every item right in ALL: which ablations lose it. Items lost by two or more ablations
  are JOINT -- right only because abilities combined. Their count and list are the result; the prediction is at least
  three (transfer + confirmation; confirmation + store; proposal + confirmation + store).
- **E7 registered numbers unchanged** (chat.py, chat_prose.py, persist.py, transfer.py, goals.py).

PASS = E1, E3, E4, E5, E7 with E2 and E6 reported. SOUND = E1 and E7 with any of E3-E5 missed for a recorded reason.

## 4. Where more emergence could come from, to be looked at with this run's data (not claimed)

(i) The engine's proposals answered by the engine itself when another world can compute the answer (self-teaching) --
only sound where the computing world is an oracle (attributed=False) and independent of the conjecture's source, which
transfer's behavioural match makes circular; the run will show whether any proposal has such an independent answerer.
(ii) Conjectures that several independent chains reach (a value both a records hop and a graph chain compute) -- a
confirmation without a user, if the chains share no source. (iii) The goals residue as a curriculum across sessions:
what session 2 should ask first. Each becomes its own prereg only if this run shows the data for it.

## 5. Runs (2026-10-03): PASS, joint 2 against a prediction of 3

E1 the 200 chat utterances with everything on: correct 101 = BASE, CONFAB 0, LAUNDERING 0, MISREPORT 0, exceptions 0, p95
0.19 s. E2 the price: 0 of 132 value answers over the 200 are "Probably" (no chat item needs a borrowed or unconfirmed
word); over the dependent batch 3 of 4 (the transfer answers, as they should be). E3 the batch: "the difference between
9 and 4" -> Probably 5; "correct" -> "the difference between 20 and 8" -> a plain 12; "the total of 3 and 4" -> Probably 7;
"wrong" -> the next ask is the dictionary's gloss, never 7 again; "the salary of research minus support" -> Probably 495;
BASE answers none of these. E4 five proposals, each a seen question with one word changed; three were the engine's own
swapped questions ("what is the result of 9 sum 2", "what is the plus price in the west", "minus in quantity between north
and south"), each answered as a guess, confirmed, and settled; the two READINGS proposals (multi-question stress turns)
drew no choice. E5 session 2 from the store: the batch identical, the confirmed words plain answers, 0 re-searched, the
denial still standing; without the store the confirmed word is a guess again. E6 compounding: two plain answers exist only
with transfer AND the store together (the confirmed `difference`); the third predicted joint item stayed a conjecture
because the proposals chose other goals that round. E7 unchanged; core_selftest green.

Found on the way, each a defect of the engine in long use and each fixed with its rule:
- the bridge ran only after a teach, so a session over pre-taught worlds borrowed nothing until the user confirmed
  something (now also at the session's opening and after a store is loaded);
- a BORROWED operator word replaced the table's default lookup, hiding "salary of alice" as a plain value and so its
  composite ("the salary of alice plus 30" became Probably 120); a borrowing is one more option beside the default;
- after a denial the refused word vanished from the readings, so the ellipsis rules read "total of 3 and 4" as an
  arguments-only fragment and borrowed the previous turn's operator (COMMIT -1); a refused word stays visible as an
  unresolved operator reading the answer owes;
- a refusal was not stored, so session 2 re-borrowed the denied word;
- the table worlds re-induced from the session's pairs alone at the first confirmation and lost the lexicon they were
  built with (the records kept only `minus`; "how many employees are in support" then took the context's difference: a
  confabulation); a world's evidence only grows, and the chat hands its tables their teaching as evidence;
- a confirmed swapped question let the preposition of the difference questions cover one question more than the
  difference word and take the operator, which the bridge then exported to arithmetic; the cover now keeps a word already
  bound to the operator (stability) and, among the rest, prefers the word new to the covered questions (a filler stays a
  filler).
On "more emergence": the one new thing this run shows is the engine closing a loop on its own words -- it proposes a
question it formed, answers it as a guess, and the user's one word turns the guess into knowledge that then crosses worlds
and survives the session. The three self-teaching ideas of section 4 found no data here: no proposal had an independent
answerer, and no conjecture was reached by two source-free chains. Registered (together.py): "TOGETHER: PASS", "CONFAB: 0".
