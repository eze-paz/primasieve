# Pre-registration -- G3: GUESSING WHAT A SENTENCE MEANS ("did you mean ...?") (`core/rephrase.py`, `didyoumean.py`; 2026-10-04)

Registered 2026-10-04 before the first run. Zero LLM. Third rung of GUESS_PLAN.md, run after G4 (textmodel_prereg.md),
whose word similarity it uses. The engine reads only the words its worlds bind; a person who says "nation" where the
engine knows "country" gets nothing. Ordinary phrasing is understood here by GUESS AND CHECK: the guess is a reading,
never an answer, until the person confirms it.

## 1. Mechanism
- **Unread content symbol.** After a turn that nothing answered (no COMMIT / ATTRIBUTED / CONJECTURED, the guesser
  included), a symbol of the turn that no non-quoting world reads and that is not among the text model's 100 commonest
  symbols (a function word, by count).
- **Candidates.** The text model's most similar symbols to it (top 30), kept only if some non-quoting world reads the
  candidate alone. Tried in order (most shared contexts first), at most 8: the turn with the symbol replaced is reasoned
  over the same worlds and context, silently. The first replacement that yields an answer is the OFFER.
- **The offer is not an answer.** The reply names the unread word, the replacement, and the count reason ("they share 7
  contexts in what I have read"), and asks. No value of the replaced reading is shown. "yes" -> the replaced question is
  answered (as whatever it is: a fact stays a fact, a guess a guess), and the substitution is kept: later turns that use
  the word are read through it, and the answer says so ("reading 'nation' as 'country', as you confirmed"). "no" -> the
  substitution is declined and never offered again; nothing is answered.
- **Persistence.** Kept and declined substitutions are the session's evidence (core/store.py).

## 2. Gates
Test set: the engine's own answerable questions (the chat gate's question set, answered COMMIT/ATTRIBUTED by the door),
each paraphrased by replacing ONE word that a world reads with a WordNet synonym (single word) that no world reads.
Every such paraphrase, seeded order, at most 80.

| gate | claim | bar |
|---|---|---|
| **D1** | paraphrases answered correctly after ONE "yes" (the answer equals the original question's) | **>= 25 %** |
| **D2** | values shown before confirmation, on any paraphrase or any "no" | **0** (fatal) |
| **D3** | after a confirmed substitution, a NEW question using the same word is answered directly, its reply naming the reading | **>= 80 %** of confirmed words |
| **D4** | KNOCKOUT: candidates in a shuffled order (the similarity removed, the world check kept) | D1 **< 60 %** of the main run, or offers that restore the original word **< 50 %** |
| **D5** | "no" to an offer: nothing answered; the same offer never repeated in the session | all |
| **D6** | registered numbers unchanged (chat.py, guess.py --quick) | unchanged |
| **D7** | hygiene: core/rephrase.py holds no word of any language | structural |

PASS = D1-D7.

## 3. Predictions
P1 D1 ~35 %: property words have good neighbours ("nation" ~ "country", "capital" has fewer). P2 D3 ~90 %. P3 the
knockout keeps some offers (the world check alone finds words that make SOME answer) but restores the original word far
less often.

## 4. What a PASS would and would not establish
Would: the engine meets an unknown phrasing by guessing a reading from what it has read, asks before answering, and
grows its vocabulary from the person's confirmations. Would not: understanding arbitrary sentences (one unknown word at a
time, and only words that behave like a word it reads).

## 5. Runs (2026-10-04): NOT PASSED (D1 missed; D2-D7 pass)
100 answerable questions; 80 paraphrases (one read word replaced by a WordNet synonym no world reads).

**Run 1 (as registered).** Offers 9, right after one "correct" 5 of 77 (6 %). The finding of the run was elsewhere: 47
paraphrases were ANSWERED DIRECTLY, and a diagnostic pass over them found **33 of 44 value answers wrong, stated as
facts** -- "what is the threefold of the salary of alice" -> 120 (the salary), "what is the washington of the country of
the eiffel tower" -> France, "who is the manager of shilling" -> another entity's manager. A word that only the dictionary
defines is "read" (it is not U), so an answer that ignores it is not PARTIAL: a pre-existing hole in the engine's
soundness, found by asking the questions a person would ask in other words.

**Amendment, run 2 (declared after run 1, recorded here before run 2's reading).** An answer from computing worlds that
leaves a content word unread no longer blocks the offer: if replacing that word with one the worlds read gives an answer
that READS the replaced position and DIFFERS from the direct answer, the reading is offered and the direct answer is
withheld (it answered another question). A quoted gloss that explains the turn's only content word is left alone ("what
is a pomegranate").

Run 2: offers 12 (7 restore the original word), right after one "correct" **6 of 77 (8 %)** -- **D1 MISS**. Examples:
"which product has the highest amount" -> "No world of mine reads 'amount'. Did you mean 'quantity'? (they share 10
contexts ...)"; "what is the medium salary of the department of erin" -> 'average'; after "correct", later turns read
through it: "Reading 'aggregate' as 'total', as you confirmed. As for the total revenue of south: 4805 ...". **D2** values
before confirmation 0. **D3** 5/6 new questions read directly with the reading named. **D4** knockout: right after yes
1 %, offers restoring the word 0/13 (main 7/12). **D5** 3 refusals, never repeated. **D6** chat.py, guess.py unchanged.
**D7** structural (a first reading failed on the word "explanation" in a comment -- the scanner's substring, reworded).

### Why D1 missed
44 paraphrases are still answered directly: the right word is rarely among the text model's top neighbours of the
unknown word (G4's similarity is RELATED more than SYNONYMOUS: 0.026 synset-sharing), and many WordNet synonyms are
senses no reader would mean ("bob" -> "shilling", "capital" -> "uppercase", "march" -> "edge"). The mechanism is sound
-- nothing shown before confirmation, vocabulary grows by the person's word -- and its reach is the similarity's.

### Disposition
Not registered. Two things follow. (1) The silent wrong answers of run 1 are a soundness defect of the engine itself,
independent of this rung: an answer that leaves a content word unread must be PARTIAL ("..., but I did not use
'threefold'"). That is the next step, with its own prereg, because it moves registered behaviour. (2) Better similarity
(a larger corpus, or contexts two words wide) is what would raise D1.
