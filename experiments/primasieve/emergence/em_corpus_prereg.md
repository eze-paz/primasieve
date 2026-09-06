# E-8 — CORPUS ACQUISITION: read all of WordNet's adjectives into the ATTRIBUTED lexicon, chained

Committed BEFORE the code. Uses the E-7 state (`core/verdict.py`). Source = the WordNet 3.1 adjective database
already in `_nldata/dict` (offline, ~21k lemmas). Output = `emergence/attributed_lexicon.json`, loaded by the chat
server at startup so every reply relying on one of these words is tagged with its provenance chain.

## Reading rule (fixed, exact)
A synset's LEMMA LIST is the span. If the lemmas contain at least one known word and ALL known lemmas in it agree
on one predicate, every unknown lemma in that synset is ATTRIBUTED to that predicate, citing `(WORDNET-adj, span)`
through the anchor lemma. Known = the 19 world-learned words on pass 1, then also the words attributed so far
(CHAINING: pass k anchors on pass k−1's words; the provenance chain records the whole path). Glosses are NOT read
(free text; unsound for "not red", "red herring"). Nouns are NOT read (homonyms: the political sense of "red").
Multi-word lemmas are stored but not exposed to the chat tokenizer.

## KILLs / reports
1. Every admission passes `core.verdict.attribute` (span verbatim, reading equals claim): refused must be 0.
2. A synset whose known lemmas DISAGREE (two predicates) admits nothing and is counted as contested.
3. Chain depth capped at 3; counts per pass reported; a word reached by two chains with different predicates
   is contested and dropped.
4. AUDIT: 40 random admissions printed with their chain for a human read; my own read of them is reported as a
   number (how many look wrong to me), not hidden.
5. Laundering: nothing enters the world-learned lexicon; provenance is attached to every word.
6. Utility: the chat must accept the loaded words; sample sentences with 5 attributed words must answer as
   ATTRIBUTED, never COMMIT.

## Predictions
Pass 1 admits a few hundred (colour and size synonyms dominate); chaining adds fewer each pass; total in the low
thousands at most. Some admissions will be semantically odd (WordNet's adjective synsets are broad, e.g. the
"big" synset includes "large", "bad" in the sense of a "big mistake"); these are SOURCE-WRONG in E-7's sense and
are exactly what the tag and the retraction path are for. Zero refused, zero laundered.
