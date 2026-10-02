# Pre-registration -- READING GLOSSES, RUNG 1: a word -> relation lexicon by cross-situational elimination (`gloss_lexicon.py`)

Registered 2026-10-02 before the first run. Owner's ask: apply the grammar induction to English glosses, so the engine can
read back a declarative reply word by word (realize_prereg.md: the strict inverse licensed nothing because the engine
reads a gloss as two names and a relation word).

## 1. What "grammar induction" can mean here, stated so the claim is the right size

The project's inducers need either a sealed world with sequence atoms (`nolf_learn`: (situation, sentence, truth)) or a
logical form per sentence (COGS). A gloss has neither. What it has is a HEADWORD whose knowledge-graph claims are the
situation it describes, and that supports the project's oldest mechanism -- cross-situational elimination (the lexicon
work; `core/induce.py`; `exec.induce_lexicon`) -- applied to WORDS and RELATIONS: a gloss word denotes a relation if,
every time the word appears in a gloss, its headword carries that relation. That is rung 1: a lexicon, not a grammar.
Constructions (which words combine, modifier vs relation, apposition) are rung 2 and are not claimed here; this file
names them as the next step and measures how far rung 1 alone carries the strict inverse.

## 2. Data (fixed by the sources)
The definitions of `realize.py`'s register (972 aligned definitions; 312 distinct (headword entity, gloss) texts over 158
headword entities with claims). Split by headword entity, 80/20, seed 1. Content words of a gloss = its symbols whose
definition frequency is below the gloss's median (the engine's own name/word discriminator, `KGWorld.readings`), so no
stoplist is written.

## 3. Mechanism
- **Binding.** For each content word w with >= 3 training glosses and each property p (any Wikidata pid in the headwords'
  claims): w -> p is BOUND iff p holds for the headword of EVERY training gloss containing w (exact, zero counterexamples)
  and p's base rate over training headwords is <= 0.5 (a relation nearly every entity has -- "instance of" at 0.85 --
  binds every word and says nothing; declared). A word may bind several properties; all are kept.
- **Names.** A label in the gloss is a VERIFIED MENTION if it is the headword or an object of one of its claims.
- **Reading.** A content word is ACCOUNTED FOR if it lies in a verified mention, is a literal property label present in the
  claims (what the engine reads today), or is bound to a property the headword carries.
- **The reader in the inverse.** `realize.Inverse(strict=True, reader=...)`: a content symbol of a reply is also accepted
  when the lexicon binds it to a property that holds for either of the frame's two entities.

## 4. Gates
| gate | claim | bar |
|---|---|---|
| **G1** | lexicon: size and bindings printed; each exact on train and with base rate <= 0.5 | structural |
| **G2** | held-out reading: fraction of content words accounted for, names+labels (today) vs names+labels+lexicon | lift **>= +0.15** absolute |
| **G3** | held-out soundness of bindings: over test occurrences of bound words, the fraction where the bound property holds | **>= 0.80**, printed per binding |
| **G4** | KNOCKOUT: glosses shuffled across headwords before binding | lexicon < 25 % of the main run; G2 lift < 0.05 |
| **G5** | the lift in `realize.py`'s STRICT inverse on its 116 frames with the reader | coverage from 0.00 to **>= 0.10**; edge misreports emitted 0 |
| **G6** | hygiene: no English literal in the binding or reading path; imports core/ and the offline sources only | structural |

## 5. Predictions
- **P1** 15-40 bound words: nouns of the gloss register (city, capital, country, river, island, language, province ...).
- **P2** G2: baseline ~0.30, with the lexicon ~0.50.
- **P3** G3 ~0.85: a few bindings are accidents of a small corpus and fail on held-out headwords.
- **P4** G4 collapses.
- **P5** G5: strict coverage 0.05-0.20. The residue is adjectives, dates and apposition ("largest", "former", "1871",
  "a federal city,"), which no lexicon of relations accounts for -- that residue is rung 2's size, and it is printed.

## 6. What a PASS would and would not establish
Would: that gloss vocabulary can be bound to graph relations with zero authored words and used to read back part of a
declarative. Would not: constructions, modifiers, apposition, time; fluency.

## 7. MEASURED (2026-10-02) -- `python gloss_lexicon.py`: NOT PASSED. Rung 1 is underpowered on this corpus, and the knockout says so.

| gate | measured | |
|---|---|---|
| **G1** | 57 bound words (first run 45), exact on train, base rate <= 0.5 -- but they are proper-name fragments and incidental words (`clarke`, `athens`, `kingdom`, `during`, `much`) bound to Wikimedia maintenance relations (`category for people born here`, `topic's main Wikimedia portal`) that co-occur across a place-heavy corpus; `city` and `capital` never bind | structural PASS, substantively empty |
| **G2** | held-out content words accounted for: 0.16 -> 0.19, lift **+0.02** (first run 0.20 -> 0.22) | **FAIL** (bar +0.15) |
| **G3** | held-out soundness of the bindings that fire: 31/36 = 0.86 | PASS (they hold, they just account for nothing that matters) |
| **G4** | shuffled glosses still bind **27** words (47 % of the main run); held-out lift +0.02 either way | **FAIL** -- half the lexicon is accident |
| **G5** | strict inverse with the reader: coverage **0/116 -> 0/116** | **FAIL** |
| **G6** | hygiene | PASS |

### Amendment, made after the first run and recorded
The first run took content words by the engine's definition-frequency median, which made `capital` and `city` function
words and left proper-name fragments as the content. Replaced by the E-8 rule (words in more than half of the training
glosses are function words: `a`, `of`, `the`). The lexicon grew from 45 to 57 words and nothing else moved.

### Why it is a null, in three measured facts
1. **158 headwords is too few for exact elimination over ~1,500 relations.** With that many candidate relations and so
   few situations per word, some relation holds for every headword of any word by chance; the shuffle knockout keeping
   47 % of the bindings is that chance, measured.
2. **The relation inventory is the wrong alphabet.** Wikidata's item-valued properties on places are dominated by
   maintenance relations shared by most entities (`category for ...`, `topic's main ...`); the base-rate cap of 0.5 keeps
   `instance of` out and lets these in. The relations a gloss word actually denotes (`capital`, `city`, `river`) are
   expressed in Wikidata as `instance of <class>` -- a relation plus a VALUE -- which a word-to-relation binding cannot
   state. The right unit is (relation, value class), i.e. a type, and that is a different induction.
3. **Nothing attested is made only of names and relations.** Even a perfect rung-1 lexicon leaves adjectives, dates,
   apposition and quantifiers ("largest", "former", "1871", "one of 67 in") unaccounted for, which is why G5 cannot move
   from zero: the strict inverse's 48 rejections are those words.

### Prediction ledger
- **P1 MISS** (57 words, not the gloss nouns). **P2 MISS** (+0.02). **P3 HIT** (0.86). **P4 MISS** (the knockout does
  not collapse: the bindings were half chance to begin with). **P5 MISS** (0.00).

### Disposition
Not registered; nothing in core/. The two numbers that matter: a rung-1 lexicon moves held-out reading by +0.02 and the
strict inverse by 0. Reading glosses needs (a) more headwords than the offline cache holds (hundreds of thousands exist in
the Wiktionary index; the limit is the Wikidata cache, which is built on demand by questions), (b) types rather than bare
relations as the thing a word denotes, and (c) constructions for the rest of the sentence. (a) is a data-loading step; (b)
and (c) are rung 2 and are the honest size of "the engine reads English".
