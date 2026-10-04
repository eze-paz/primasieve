# Pre-registration -- G4: A COUNTING MODEL OF TEXT (`core/textmodel.py`, `textmodel.py`; 2026-10-04)

Registered 2026-10-04 before the first run. Zero LLM. Fourth rung of GUESS_PLAN.md, run before G3 at the owner's
request (G3's "did you mean" needs a word-similarity this rung supplies). The G2 disposition pointed here: definitions
were read one word at a time; nothing knew which words go with which.

## 1. Mechanism
- **Corpus.** Every Wiktionary definition and example sentence in `_nldata/kaikki_all.sqlite` (1.7 M definitions,
  0.46 M examples, ~25 M tokens), split by a seeded hash of the HEADWORD: training headwords and held-out headwords never
  share a sentence. Tokens are the engine's own symbols (core.reason.symbols, letters and digits, lower-cased).
- **Counts, nothing else.** Unigrams; left and right neighbours; the gap triple (left, word, right). A symbol seen fewer
  than 3 times in training is one shared token for "rare". No smoothing, no probabilities.
- **Fill a blank** (left, _, right): the most specific context ever seen decides -- the triple (left, right); failing
  that, the left neighbour; failing that, the right; failing that, the commonest word. Within a context, more counts
  first. Every fill carries its reason: the context used and its count ("seen 37 times between 'the' and 'of'").
- **Similar words.** A word's contexts are its left and right neighbours. Contexts that occur with very many distinct
  words (the top 1 % by spread -- "the", "of") are dropped as uninformative, by a count, not a list. Each word keeps its 50
  most frequent remaining contexts; two words are as similar as the NUMBER of those contexts they share. The reason is
  that number.

## 2. Gates
| gate | claim | bar |
|---|---|---|
| **M1** | CLOZE on 5,000 held-out sentences (one interior token blanked, in vocabulary): top-1 accuracy | **>= 2x** the commonest-word baseline and **>** the left-neighbour-only model |
| **M2** | the same, top-5 | printed |
| **M3** | KNOCKOUT for M1: training sentences with their words shuffled | top-1 **< 60 %** of M1 |
| **M4** | SIMILARITY against WordNet: for 1,000 test words with a WordNet synonym in vocabulary, the share of top-10 neighbours that share a WordNet synset with the word | **>= 3x** the frequency baseline (the 10 commonest words) |
| **M5** | KNOCKOUT for M4: similarity from the shuffled training | **< 50 %** of M4 |
| **M6** | every fill and every neighbour carries its count reason | **100 %** |
| **M7** | hygiene: core/textmodel.py holds no word of any language; stdlib only; the model saves and loads | structural |
| **M8** | registered numbers unchanged (guess.py --quick, chat.py) | unchanged |

PASS = M1, M3-M8.

## 3. Predictions
P1 cloze top-1 ~0.25 (dictionary prose is formulaic: "a town in", "of or relating to"), baseline ~0.06, left-only ~0.15.
P2 top-5 ~0.45. P3 knockout ~0.08. P4 similarity ~0.12 vs frequency baseline ~0.005. P5 knockout similarity ~0.02.

## 4. What a PASS would and would not establish
Would: the engine has learned, by counting, which words go where and which words behave alike -- the raw material for
guessing what a sentence means (G3) and for varying the wording of replies. Would not: understanding; a model of
meaning; anything near an LLM's language model (no long context, no generalisation beyond seen neighbours).

## Amendment before the registered run (2026-10-04, after a 5 % smoke run that tested the code)
The smoke run (`--frac 0.05 --quick`, code check, not the registered run) printed: cloze top-1 0.476, left-only 0.411,
commonest word 0.269; knockout 0.320 (67 %); similarity 0.015 vs frequency baseline 0.000, knockout 28 %. The cloze as
written blanks ANY interior token, and dictionary prose is mostly function words ("Plural of X", "Synonym of X"): one
word, "of", fills 27 % of the blanks, and word order survives a shuffle for those tokens because "of" is everywhere. That
measures the function words, not the model. **Amended:** a blank is a token that is NOT among the 100 commonest symbols of
the training corpus (a count, no list); the commonest-word baseline becomes the commonest such symbol. Bars unchanged.
The similarity baseline of 0.000 makes M4's ratio trivially met; M4 is kept as registered and its absolute number is
reported beside the prediction (P4 ~0.12) -- the smoke run says it will miss the prediction by an order of magnitude.

## 5. Run (2026-10-04, full corpus): PASS
1,938,627 training sentences (definitions + examples of 90 % of headwords), 215,906 held-out; vocabulary 213,390;
1,060,216 two-sided contexts kept (count >= 2); spread cut 273 distinct neighbours. Learned in 149 s.

- **M1 PASS.** Cloze on 5,000 held-out CONTENT blanks: top-1 **0.131**; left-neighbour only 0.036; the commonest
  content word 0.001. Two-sided contexts decided 3,900 of the 5,000. **M2** top-5 0.235.
- **M3 PASS.** Shuffled training: top-1 0.010 (8 % of M1).
- **M4 PASS** as registered (0.026 vs 0.000), and the prediction MISSED by a factor of five (P4 ~0.12): sharing a
  WordNet synset is strict, and the neighbours are mostly RELATED rather than synonymous -- woolen: cotton, worsted,
  knitted, woollen; authority: authorities, jurisdiction, agency, powers; pasture: grass, graze, meadow; awful: hideous,
  bad, disgusting, horrendous. Spelling variants and inflections rank high (woollen, authorities, walk).
- **M5 PASS.** Shuffled training: similarity 0.010 (39 % of M4) -- the floor is not zero because a word's own
  co-occurring words survive a shuffle within the sentence.
- **M6, M7 PASS.** **M8** guess.py and chat.py unchanged.

Predictions: P1 MISS (0.131 vs ~0.25; the amendment made the task the content words, which is harder), P2 MISS (0.235
vs ~0.45), P3 0.010 (predicted ~0.08), P4 MISS (0.026 vs ~0.12), P5 0.010 (predicted ~0.02). The model is saved to
`_nldata/textmodel.json` for G3. Registered (textmodel.py): "G4: PASS".
