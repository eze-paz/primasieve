# Pre-registration -- LOOP ITERATION 41 (novel 24): THE BOOK READERS IN THE LIVE DOOR -- A PASTED PASSAGE IS ITS OWN SOURCE (`emergence/kb_bookread.py`, `chat.py`; 2026-10-07)

Registered 2026-10-07 before the chat code. Zero LLM.
(A) Refactor: the readers move from book_battery.py into emergence/kb_bookread.py (verified: book_battery --it 14 gives
identical counts and the identical judged sample: 645/1,709, 1,437 propositions).
(B) kb_bookread.read_text(text, title): the passage becomes a one-book world; the whole reader chain (iteration 39
settings) reads it; -> [(sentence, propositions)].
(C) The live door: a turn of >= 3 sentences without a question mark is a PASSAGE: it is read as its own source ("your
text") and the reply says what was read -- "I read k of n sentences. According to your text: ..." (at most 5 readings,
each in its context) -- and its sentences also enter the story memory (questions about it are answered as before).

## Gates
| gate | claim | bar |
|---|---|---|
| **T1** | book_battery numbers identical after the move | identical |
| **T2** | B6, B9, B2 unchanged (they send one sentence per turn) | unchanged |
| **T3** | a pasted passage from an UNSEEN novel (526 Heart of Darkness, 6 sentences) gets a reading reply; a follow-up story question is answered from it | shown |
| **T4** | nothing said without "according to your text" | 0 |

## Run (2026-10-07): PASS (T1-T4)
T1: book_battery --it 14 after the move: 645/1,709, 1,437 propositions, the identical judged sample (checked). T2: B6 56,
B9 18/20, B2 90.4 % (after one amendment below), B10 398, B5 +11.6, B1 counted 1 (true); probes RIGHT 105 / WRONG 15.
T3, the live door on six sentences of "Heart of Darkness" (never used in development):
  passage -> "I read 2 of 6 sentences. According to your text, the wind is nearly calm; according to your text, The air is
  dark above Gravesend. Ask me about it."
  "What rested on the low shores?" -> "From what you told me: haze"
  "What was dark above Gravesend?" -> "By your account: The air"
T4: every reading said "according to your text". Amended during the run: identity facts skip a copula with a learned
wh-word beside it ("what is ..."), which let iteration 36's over-strict predicate test ("dark" is also a verb lemma) be
narrowed to finite verbs; the chat passes its learned wh-words to the story memory.
Seen and left for later: "The Nellie, a cruising yawl, swung to her anchor" (an apposition between subject and verb) and
"A haze rested on the low shores" are not read; "Was the wind calm?" (a yes/no copular question) is not answered.
