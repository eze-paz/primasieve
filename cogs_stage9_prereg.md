# STAGE 9 PRE-REGISTRATION -- realization grammar + synonym classes from RAW TEXT, no paired supervision

Written BEFORE the engine ran. Gates fixed here; results go in the commit message whatever they say.
Sits on Stages 3-8 (`cogs_gram.py`, `cogs_fluent.py`, `cogs_stage8.py`), `core/generate.py` (SignatureBank),
`core/collect.py`, `core/verdict.py`, the offline sources in `emergence/kb_offline.py` (WordNet 3.1, Moby, kaikki).
Pure stdlib. Zero LLM anywhere. Every run under the 5-minute cap (alice.txt is 151 KB, ~1.6k sentences).

## The structural claim being tested

Stage 8 realizes a MEANING fluently with RNG over meaning-preserving choices, but its grammar and its synonym
classes were induced from (sentence, logical-form) PAIRS -- supervision the world does not hand a child. Stage 8's
own closing line names the next step: learn the realization grammar and the synonym classes PASSIVELY from raw
text under the MDL oracle.

The claim, stated so it can fail: **FORM is learnable from text alone.** Word classes, sentence skeletons
(frames), the determiner/terminator markers and synonym classes can be induced from `_nldata/alice.txt` plus the
offline dictionaries with no logical forms, sound-gated by (i) exact reproduction and (ii) an MDL oracle that
prefers the induced grammar to a trivial one on HELD-OUT text, and (iii) the Stage 8 round-trip invariant lifted to
form: every sentence the induced grammar generates parses back to the same skeleton.

Explicitly NOT claimed (the line the project has held since arc 2): MEANING is not learned here. A skeleton with
holes is form. Binding a hole to a referent needs a world; that is steps 2-3 of the fluency program (provenance
store, domain grounding), not Stage 9. If a reviewer reads any gate below as "the engine understands Alice", the
reading is wrong and this paragraph is the pre-committed rebuttal.

## Mechanism (fixed here so it cannot drift toward the data)

  CLASSES     words are clustered by their left/right context SIGNATURE (the multiset of neighbouring words
              within a 1-token window, plus sentence-boundary tokens), using exact signature collision through
              `core/generate.py`'s SignatureBank first (collision-extend, Stage 7 ordering), then merge by
              signature overlap under MDL: a merge is ADOPTED only if total description length drops.
  SKELETONS   two corpus sentences that agree everywhere but at positions whose words share a CLASS are
              anti-unified into a skeleton with typed holes (the same LEARN rule as `core/resolve.py`). A
              skeleton is ADOPTED only if it lowers total DL (grammar bits + corpus bits given grammar).
  MARKERS     determiners and terminators are NOT named; they fall out as the classes that occur at skeleton
              edges with near-zero hole variance (the Stage 3 route: directly observed, never authored).
  SYNONYMS    mutual synonymy in Moby AND agreement in WordNet first sense (the E-8 reading rule, reused
              verbatim), then a FORM test: a synonym pair is accepted only if substituting one for the other in
              every corpus sentence keeps the sentence parseable under the same skeleton. Certificates travel
              (ATTRIBUTED to the source); nothing enters as COMMIT.
  MDL         DL(grammar) = sum over classes and skeletons of their encoding under a fixed universal code;
              DL(corpus | grammar) = sum over sentences of the cheapest derivation, or the raw token cost if no
              derivation exists. Baseline = unigram token code. Both codes fixed before the run.
  OUTPUT      COMMIT / ABSTAIN on each held-out sentence (derivation exists or not). No probabilities leave
              the engine. Coverage is reported beside every score.

Nothing above names a word, a part of speech, a determiner, a punctuation glyph or an English fact. The R4-style
literal check from E-10 applies: the module's string literals share no token with the corpus.

## Pre-registered gates

G9a (SOUNDNESS, hard). Every TRAIN sentence the grammar derives is reproduced EXACTLY by realizing its skeleton
    with its own fillers (reproduction 1.000 on derived rows). A grammar that cannot regenerate what it parsed
    has no standing. FAIL => Stage 9 is a null.

G9b (MDL ON HELD-OUT, decisive). Induce on chapters 1-9, score on chapters 10-12. DL(held-out | induced grammar)
    must be LOWER than DL(held-out | unigram baseline) by >= 10% and lower than DL(held-out | train-memorized
    sentences) -- the grammar must beat both no-structure and pure memory on text it never saw.
    FAIL => the induced structure is memorization, not form.

G9c (ROUND TRIP ON FORM, hard). Sample 1000 sentences from the induced grammar (RNG over class fillers and
    synonyms, the Stage 8 procedure). Each parses back to the SAME skeleton: 1.000, confab 0. A generated
    sentence with no derivation is an abstention and is counted as a fluency miss, not a confabulation.

G9d (THE INVARIANT CAN FAIL). Corrupt 200 generated sentences by swapping one filler for a word of a DIFFERENT
    class; the round trip must catch >= 0.95 (parse changes skeleton or fails). Same shape as G8d: a gate that
    cannot fail proves nothing.

G9e (EXTERNAL CHECK OF CLASSES, report). For words present in both the induced classes and WordNet, class purity
    against WordNet's majority POS >= 0.70. This is the one place a dictionary judges the induction rather than
    feeding it. Below 0.70 is reported, not tuned toward.

G9f (SYNONYMS, report). Number of synonym pairs accepted by the FORM test, and the fraction of Moby+WordNet
    candidate pairs that the FORM test REJECTS. Prediction: a substantial rejection rate (sense mismatch shows up
    as skeleton failure); a rejection rate near 0 means the form test is vacuous and G9f is void.

G9g (COVERAGE, report, not a gate). Fraction of held-out sentences with a derivation. Prediction: 0.25-0.50.
    Alice is literary, long, coordinated and quoted; low coverage is expected and honest. Coverage is printed
    beside every number so nothing above can be read as open-domain parsing.

## KILL controls (each arm carries its own signal ablation, Stage 7 discipline)

K1 SHUFFLED WORD ORDER. Induce on alice with the words of every sentence shuffled (unigram statistics
   preserved, order destroyed). G9b must FAIL on this corpus (no held-out DL gain). If the shuffled corpus
   still passes G9b, the MDL oracle rewards something other than order and every gate above is void.
K2 SHUFFLED DICTIONARY. Permute Moby/WordNet entries across headwords (E-10 R5). Synonym acceptance in G9f
   must fall to the chance level of the FORM test alone. If it does not, the dictionaries contributed nothing.
K3 COST-ORDER ABLATION. Run the merge step in random order instead of collision-first. Prediction from
   Stage 7: worse DL at matched budget. Reported either way; this is not a gate, it is the standing check on
   the load-bearing ordering claim.
K4 A CONTROL THAT CANNOT DISCRIMINATE ALWAYS PASSES. Before reading any gate, confirm K1 actually fails.
   A run where K1 passes is not a Stage 9 pass with a footnote; it is a void run.

## Predictions, committed

- G9a passes trivially if the derivation is deterministic; the interesting failures are G9b and G9c.
- G9b: held-out DL improvement 15-30% over unigram. Below 10% is the registered null.
- G9c: 1.000 by construction ONLY if class fillers are truly interchangeable; expect first run to FAIL on
  determiner-noun agreement (a/an) and on quote pairing, which are FORM facts the 1-token signature misses.
  A fix must be a wider signature or a learned marker class, never an authored rule.
- G9e: 0.70-0.80 purity; function words and proper names are the predicted impurities.
- G9g: 0.25-0.50.

## What would make this a KILL rather than a pass

If G9b passes but K1 also passes, the MDL gain is not from word order: KILL, and the oracle is redesigned before
anything else runs. If G9b fails while G9a passes, the induced grammar is a memory of train, the same hollowness
Stage 1 died for: NULL, reported as such. If G9c cannot reach 1.000 without an authored agreement rule, Stage 9
stops there and the missing representation is named as the next degree, not patched.

## What a pass buys, and what it does not

A pass means the REALIZATION side of Stage 8 no longer depends on paired supervision: skeletons, fillers,
markers and synonym classes come from text plus attributed dictionaries. The engine can then verbalize a
structure using forms it read, not forms it was given. It does NOT mean the engine can parse an arbitrary prompt
to meaning; that needs the provenance store and a grounded domain, which are the next two pre-registrations.
