# Pre-registration -- READING GLOSSES, RUNG 2: TYPES and CONSTRUCTIONS (`gloss_types.py`)

Registered 2026-10-03 before the first run. Follows gloss_prereg.md (rung 1, NULL), whose three measured facts fix this
file's design: too few headwords; bare relations are the wrong alphabet; the rest of a sentence is constructions.

## 1. Data step (not research): labels for the whole cache
The offline Wikidata cache holds 3,817 entities with claims and 55,438 distinct claim objects, of which 3,449 and 54,977
have no cached label, so they could not be matched to Wiktionary entries or recognised as mentions. Labels are fetched
in batches of 50 through the same API the cache already uses (`wbgetentities`, props=labels), written as `label:<qid>`
keys -- data the README already calls regenerable. The count of headwords with a Wiktionary entry before and after is
printed. This changes nothing about the mechanism; it changes its power.

## 2. Mechanism
- **Types.** A TYPE is a (relation, value) pair of a headword's claims, e.g. (instance of, city). A gloss word w BINDS a
  type t iff every training headword whose aligned definition contains w carries t (exact, zero counterexamples), w has
  >= 3 such headwords, and t's base rate over training headwords is <= 0.5. All exact types of a word are kept, ordered
  by base rate (most specific first). This is rung 1 with the right alphabet: `city` can now mean (instance of, city).
- **Mentions.** A cached label in a gloss that is an object of the headword's claims is a verified mention; it is
  abstracted to a slot `{E:p}` carrying the relation p the headword bears to it (several relations: `{E}`).
- **Constructions.** A skeleton is a gloss with its mentions abstracted. A skeleton is ADMITTED as a construction iff it
  occurs with >= 3 distinct training headwords and its TRUTH CONDITION -- the conjunction of the types bound to its
  words and the slot relations -- holds for every one of them (exact, as nolf admits a construction only when the term
  fits every row). Its words that bind no type (`in`, `and`, `largest`, `one of`) are construction material: accounted
  for by the construction, not by a lexicon.
- **Reading.** A content word of a held-out gloss is ACCOUNTED FOR if it lies in a verified mention, is a literal
  relation label the headword carries, binds a type the headword carries, or lies inside an admitted construction whose
  truth condition the headword satisfies. Content words = not in more than half of the training glosses (E-8's rule).
- **The reader in the strict inverse.** `realize.Inverse(strict=True, reader=...)`, where the reader may `prepare(reply,
  s, o)` to match constructions over the whole reply and then answers per word.

Declared biases: >= 3 headwords, base rate <= 0.5, exactness; nothing names a word, a type or a relation.

## 3. Gates (split by headword, 80/20, seed 1)
| gate | claim | bar |
|---|---|---|
| **T0** | data: headwords with claims, a label and an aligned Wiktionary definition, before and after the label fetch | printed |
| **T1** | type lexicon: size and bindings printed; expected members of the gloss register (city, capital, river, island, language, country, province) appear | **>= 5 of those 7 bound** (a prediction, checked by printing; not word-coded) |
| **T2** | held-out reading: content words accounted for, names+labels (today) vs names+labels+types+constructions | lift **>= +0.15** |
| **T3** | held-out soundness: bound types that hold / fire; admitted constructions whose truth condition holds on held-out occurrences | both **>= 0.80** |
| **T4** | KNOCKOUT shuffled glosses | type bindings and constructions each < 25 % of the main run; held-out lift < 0.05 |
| **T5** | `realize.py` strict inverse with the reader | coverage from 0/116 to **>= 0.10** |
| **T6** | hygiene: no English literal in the binding, construction or reading path; the knockout and split are seeded | structural |

## 4. Predictions
- **P1** headwords grow from 158 to over 1,000 after the label fetch; aligned definitions over 2,000.
- **P2** T1: the gloss nouns bind to (instance of, class) types; 6 of 7 named nouns appear.
- **P3** T2: baseline ~0.20 -> 0.45-0.55 with types; constructions add 0.05-0.10 on top.
- **P4** T3 ~0.85 for types; constructions ~0.9 (exactness over >= 3 headwords generalizes).
- **P5** T4 collapses this time: with ~1,000 headwords chance bindings are rare.
- **P6** T5: 0.10-0.25. The residue is dates and adjectives outside any recurring skeleton.

## 5. What a PASS would and would not establish
Would: gloss nouns read as types, recurring gloss shapes read as verified constructions, with zero authored words, and a
measured fraction of a declarative reply the engine can vouch for. Would not: fluency; time and number; anything
outside the register of dictionary definitions of places and people.

## 6. MEASURED (2026-10-03) -- `python gloss_types.py`: NOT PASSED overall; the first sound, non-accidental piece of gloss reading

| gate | measured | |
|---|---|---|
| **T0** | after two data steps (56,814 labels; 1,784 class entities, two rounds of subclass-of): 5,601 entities, 4,992 labelled, 1,906 with a Wiktionary entry; **2,210 aligned texts over 1,193 headwords** (rung 1: 312 over 158); train 1,755 / test 455 | printed |
| **T1** | 224 words bind a headword type, but the gloss nouns do not: `city` occurs in 176 glosses whose headwords are mostly COUNTRIES ("Capital and largest city: Paris") -- it predicates the mentioned entity, not the headword. The test was the wrong test; recorded | FAIL as written |
| **T2** | held-out content words accounted for: 0.18 -> 0.20 (+types) -> **0.22** (+constructions); lift +0.04 | **FAIL** |
| **T3** | held-out soundness: headword-type bindings **0.59** (fail); typed-slot constructions **163/180 = 0.91** (pass) | half |
| **T4** | shuffled glosses: types 49 of 224, **constructions 2 of 141**, held-out lift +0.01 | **PASS** -- the constructions are not chance |
| **T5** | strict inverse with the rung-2 reader: **0/113** | **FAIL** |
| **T6** | hygiene | PASS |

The 141 constructions are the right ones and they are typed: `capital {E:capital}` x16, `and largest city {E:most
populous urban area}` x13, `city of {E:capital of}` x11 with filler type sovereign state, `of {E:country} capital` x18,
`in {E:located in/on physical feature} official name` x17. Each was admitted only because its condition held for every
training occurrence, and 91 % hold on held-out headwords; shuffling the glosses leaves two.

### Four amendments, made after measurements and recorded in order
1. **Tolerance** (Phase 6): a type binds when it holds for all but 10 % of a word's headwords once it has five -- the
   alignment is distant supervision and a single wrong-sense gloss killed every exact binding.
2. **Non-vacuous conditions**: a slot relation counts only under the base-rate cap (the namesake link `different from`
   at 0.61 verifies nothing) and a condition with no type and no slot is not a construction -- the shuffled knockout had
   admitted 39 such skeletons against 17 real ones.
3. **Subclass closure** (data step 2): an entity typed `big city` is typed `city`; before it, the 176 `city` headwords
   spread over `big city`, `city`, `largest city`, `city in the United States` and no class reached a binding.
4. **Local typed windows** instead of whole-gloss skeletons: up to three tokens on each side of a mention slot, with
   the relation and the fillers' shared most specific type in the condition -- `city` in "largest city: {E}" types the
   filler. Whole-gloss skeletons recurred 5-17 times; windows 141 times at 0.91 held-out soundness.

### Why the reading lift is still +0.04 and the inverse still 0
A window accounts for the three tokens beside a verified mention. Most content words of a gloss -- "a federal city,",
"one of 67 in", "formed in 1949", "the most active province of New" -- sit further from any mention than that, or beside
a name the headword has no claim to. The strict inverse's 51 rejections are those words: in `Paris: A federal city, the
capital and largest city of France`, `city of {E:capital of}` is read and sound, and `federal` and the first `capital`
(four tokens from the mention) are not. Wider windows need more occurrences than 1,193 headwords supply; the honest
remedy is more headwords (the cache grew 6x with two fetches and could grow 100x), and windows anchored on the headword's
own mention as well as on its claim objects.

### Prediction ledger
- **P1 HIT** (1,193 headwords, 2,210 texts). **P2 MISS** -- and the reason is the finding: gloss nouns type the
  filler, not the headword; the construction route reaches them, the lexicon route cannot. **P3 MISS** (+0.04).
  **P4 half**: constructions 0.91, types 0.59. **P5 HIT**: the knockout collapses to 2 of 141 (rung 1's did not).
  **P6 MISS** (0.00).

### Disposition
Not registered (no gate on reading or the inverse passed). What stands, measured: typed-slot local constructions over
glosses are inducible with zero authored words, sound on held-out headwords at 0.91 and not chance at 2/141 -- the
first mechanism in the project that reads any English beyond two names and a relation word. What does not stand:
headword-type bindings for gloss nouns (wrong hypothesis), and any effect on the strict inverse at this data size.
