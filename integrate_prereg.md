# Pre-registration -- H3: EVERY CONTENT WORD INTEGRATED, OR THE ANSWER IS PARTIAL (`core/session.py` integrate, `integrate.py`; 2026-10-05)

Registered 2026-10-05 before the first run. Zero LLM. First hypothesis of FLUENCY_HYPOTHESES.md (H3; theory: a word that
cannot be given a role in the meaning is an integration failure -- the N400/P600 literature; the role requirement of
linguistics). Motivated by didyoumean_prereg.md run 1: 33 of 44 paraphrased questions answered directly were wrong
facts, because a word only the dictionary defines is "read" and an answer that ignores it is not PARTIAL.

## 1. Mechanism
- **Content position:** a symbol of the turn at or below the turn's median definition frequency (the graph world's own
  A1 criterion, already used for ranking; no list).
- **Integrated:** inside a span the answer's structure uses (any answer, context positions included).
- **The rule (opt-in, `Session(integrate=True)`):** a COMMIT / ATTRIBUTED answer from a NON-quoting world that leaves a
  content position unintegrated becomes PARTIAL, `missing` naming the words: "X is V (...), but I could not apply W."
  A quoted answer (the dictionary explaining a word) and a labelled guess are left as they are. Off by default: the
  registered gates keep their behaviour; this file measures what moves when it is on. The live chat turns it on.

## 2. Gates
| gate | claim | bar |
|---|---|---|
| **I1** | the G3 paraphrase set (didyoumean_prereg.md's builder): wrong values stated as COMMIT/ATTRIBUTED, integrate off vs on | on: **0** (fatal) |
| **I2** | the chat gate's 200 utterances with integrate on: currently-correct answers that become PARTIAL, each listed with its unintegrated word | **<= 10 %** of correct answers |
| **I3** | KNOCKOUT: every position counted as content (no frequency criterion) | correct answers lost **> 3x** I2's |
| **I4** | the live chat builds its door with integrate on | code read |
| **I5** | registered numbers unchanged with the default (chat.py, guess.py --quick) | unchanged |

PASS = I1-I5.

## 3. Predictions
P1 I1 33 -> 0-2 (a wrong answer whose unread word sits above the median would survive). P2 I2 ~5 %: questions with a
content word the answer does not need ("please", a name the context already resolved). P3 the knockout loses most
answers (every "what", "is", "the" would be owed).

## 4. What a PASS would and would not establish
Would: the engine no longer answers a different question than the one asked when it misses a word. Would not: that it
understands the word (that is G3 / H5).

## 5. Run 1 (2026-10-05, as registered): FAIL I2, I3
I1 PASS: wrong facts on 80 paraphrases 25 -> **0** (integrate off: 25 wrong COMMIT/ATTRIBUTED; on: 72 PARTIAL, 8
attributed, all right). I2 FAIL: 76 of 101 correct chat answers became PARTIAL (75 %), owing "what", "is", "who", "how",
"has". The content criterion was wrong by construction: "at or below the turn's MEDIAN definition frequency" marks half
of every turn as content, whatever its words. I3 FAIL follows (the knockout lost 96, not 3x 76).

## Amendment, run 2 (declared after run 1)
Content = a symbol NOT among the text model's 100 commonest symbols (textmodel_prereg.md's counts; the same cut
didyoumean_prereg.md uses for function words) -- a corpus-wide count instead of a per-turn median. Everything else as
registered.

## Run 2 (2026-10-05): NOT PASSED (I2 15.8 % vs 10 %; I1, I3, I4, I5 pass)
I1 wrong facts on paraphrases 25 -> **0**. I2: 16 of 101 correct chat answers become PARTIAL (15.8 %). Every one owes a
word the engine answers BY SHAPE without a reading that spans it: "how ... related" (9, the graph's PATH structure),
"how many" (3, COUNT), "between" (4, the table's difference). I3 knockout lost 96 (6x). I4 live door on. I5 chat.py
and guess.py unchanged (the rule is off by default).

### Disposition
Not registered. The rule does what it was built for -- no paraphrase is answered as a different question -- and the
cost is real but honest: the structure words its worlds answer by shape are not in any span. The fix belongs in the
worlds (a structure should SPAN the words that select it, as an operator reading does), and moves registered ranking,
so it is its own step. The live chat keeps the rule ON: "..., but I could not apply how ; related" is a worse sentence
than a plain answer and a better one than a wrong fact.
