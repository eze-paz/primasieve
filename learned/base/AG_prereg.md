# AG: is the AlphaGeometry path viable here? (registered 2026-10-14, before any run)

The path: a symbolic engine owns the reasoning; a learned translator, trained only on synthetic (sentence, symbolic
event) pairs from a world we can generate and verify, reads natural language into that engine. The path lives or dies
on the translator reading **other people's prose** better than our hand reader and our role reader do. Everything
else (the state rules, the question answering) already exists and is measured.

## Material (all existing, nothing chosen on the untouched sets)
- Synthetic world: the 2,800 generator stories of stories_train_v2.json that carry gold events (14,400 events,
  32 verb lemmas; fields: sentence index, agent, verb, patient, place, recipient). Split by story, seed 0:
  2,240 train / 280 dev / 280 test.
- Reader stack to beat: hand reader (W3, R25-cz-t) and learned role reader (W4, R25-da-t) feeding the same world
  state (World3). Their world-alone scores on val_all13.json: practice (0-309, 510-909) W3 28 right / 7 wrong,
  W4 27 / 8; untouched (310-509, 910-2509) **W3 26 / 22, W4 40 / 30** (precision ~0.55-0.57).
- Translator: ag1_translator.py. Tokens get a frozen 100-d book vector (r25_vectors.npz, 25k words from 13M book
  tokens; zero if unknown), a trainable word embedding, capitalisation and suffix features. Two small BiLSTM taggers:
  one marks event verbs; one, given a verb position, tags agent / patient / place / recipient spans (BIO). Trained
  by gradient descent on the synthetic pairs only; no hand rules in the reader. Pronoun stand-ins are tagged as
  the surface pronoun (the world state resolves them, as it does for the other readers). Under 10 minutes on CPU.

## Tests and gates (fixed now)
- **AG1 (does the translator learn the synthetic world?)** Event-level F1 on the 280 test stories, an event counted
  right when verb lemma, agent, patient and place all match the gold (surface form). PASS if F1 >= 0.95. A fail
  here means the method is broken, not the path.
- **AG1b (composition: verbs never seen).** Retrain with every training event whose verb is in {steal, borrow,
  chase, drop, return, ride} removed (stories containing them dropped from training). On test events with those
  verbs: verb-detection recall and argument F1 given the verb. Reported, no gate; it says how far the translator
  can stretch past the synthetic verb list, which is the whole question for real prose.
- **AG2 (the decisive one: real prose).** The translator is the reader of World3 on all 502 hand-written stories of
  val_all13.json (2,510 questions), world alone, practice and untouched reported as right / wrong / fitness, and
  the reader policy with the world filling silent questions against the +288 baseline (same computation as
  R25-ct-t). PASS if on the untouched sets the world fed by the translator is **better than W4 on both reach and
  precision** (right > 40 and precision > 0.57), or reaches precision >= 0.75 at >= 26 right (then it pays under
  +1 / -3, which no state route has done).
- **KILL (discard the path at this synthetic breadth):** AG2 untouched precision <= 0.57 and right <= 40. Then a
  translator trained on our own synthetic world reads strangers' prose no better than the readers we have; the
  path would need a synthetic world as broad as English itself (API-generated at scale), i.e. it collapses into
  the cost of paradigm path A, and is discarded as a separate path.
- Not a kill: AG1 or AG1b failing alone (method problems, one more variant allowed: character-level features).

## What is not being tested
Whether the symbolic side can reason beyond the state questions (it answers only the registered question kinds),
and whether a model could propose constructions for the engine (AlphaGeometry's second half); both are moot if
the translation layer cannot read real text.

## AG1 result -- PASS
Dev and test event F1 1.000 (1,466 / 1,375 gold events; verb recall 1.0, argument F1 1.0). The translator learns the
synthetic world completely. Cost: 48 min of training with one sentence per step (over the 30-minute cap; the
held-out run uses 2 epochs).

## AG2 result -- KILL condition met
World3 fed by the translator, world alone: practice 30 right / 7 wrong (+9); **untouched 21 / 18 (-33), precision
0.54** (W3 hand reader 26 / 22; W4 role reader 40 / 30). Policy with the world filling silent questions: untouched
+275 against +288. Precision <= 0.57 and right <= 40: the path is discarded at this synthetic breadth, as registered.

Diagnostic (ag_diag.py, the 200 untouched stories of val_fresh2): the translator fires on 768 sentences 649 events
over **161 verb lemmas, half of them outside the 32 synthetic verbs**, with mostly sensible arguments ('a theatre
ordered a dragon', 'a squirrel carried the crust', 'horn woke her'); places are often cut to the preposition. So the
gradient-trained reader with book vectors does stretch past its synthetic verb list, more than expected. The loss is
on the symbolic side: World3's update rules know the effects of only the synthetic verbs (give / take / release /
move sets), so 'ordered', 'woke', 'filled' produce no state, and the questions those stories ask are about such
events. Reading: the translation layer is learnable and generalises somewhat; the knowledge-acquisition bottleneck
has moved to the symbolic rules, which is where GOFAI met it. The path is not viable as 'symbols first' unless the
rules too are learned from a world broad enough to cover English verbs, which again is the cost of paradigm path A.

## AG1b result (verbs never seen; reported, no gate)
Trained on the 624 stories without the six held-out verbs, 2 epochs (so the in-distribution score also drops:
test event F1 0.44, a data-and-epochs confound). On test events whose verb was never seen: verb detection recall
0.17, argument F1 given the verb 0.655, event F1 0.0. The translator can place arguments around a verb it has
never seen about two thirds of the time, but it rarely recognises that an unseen word is an event verb at all.
Composition past the synthetic verb list is partial, consistent with the AG2 diagnostic.

## Verdict
AlphaGeometry path discarded as a separate path (kill rule met). What survives: a gradient-trained translator over
synthetic gold plus book vectors reads real prose into structure about as well as the readers built by hand over
weeks, in 50 minutes of training, which is evidence for the learned-translation half of paradigm path A/B, not for
"symbols first". The bottleneck is now the breadth of the symbolic world (its verbs and their effects), which can
only be bought with a far broader synthetic corpus.

## AG3 registration (owner's idea, 2026-10-15: converge each sentence onto canonical clauses that keep the signal)
Smoke test first (ag3_rewrite.py, 5 stories, stock RWKV-7 0.4B, whole story at once): the free rewrite loops and
swaps agents ('Ilse sold her roses' for Greta's sale), so a rewrite is worthless unless something checks the signal.
AG3 (ag3_canon.py) makes the engine that check. Per sentence, with its predecessor as context, the model proposes
numbered simple sentences; the engine keeps a clause only if (1) every content word is in the sentence, its predecessor
or a name seen so far (no invention), (2) it has no pronoun, (3) the AG1 translator parses it to an event with an
agent, and (4) its agent is not the original reading's patient for the same verb (no swap). No accepted clause:
one retry with a stricter prompt, then the sentence stays as written. The canonical story is the accepted clauses.
Measured on val_more (practice, stories 22-61) and val_fresh2 (untouched, stories 62-101), World3 world state alone
with the hand reader and with the translator, reading the original text and the canonical text; plus the verifier's
accept / reject counts and the share of the original reading's events recovered in the kept clauses.
PASS if on val_fresh2, for either reader, the canonical text gives more right answers at no lower precision than the
original. A PASS says a verified rewrite loop can make free prose more readable to a symbolic engine without an LLM
judge; a FAIL with high rejection rates says the 0.4B model cannot propose faithful clauses (then the 1.5B model is
the one more variant); a FAIL with high acceptance says the readers' limits are not sentence shape.

## AG3 result -- PASS (on the question-answering instrument; the world-state instrument was too sparse)
Rewriting (stock RWKV-7 0.4B proposing, engine verifying; 80 stories, 10,456 s under CPU contention): 238 of 307
sentences rewritten, 69 kept as written; 361 clauses accepted; rejected: no event 294, fragment 97, invented words
42, copies context 25, agent swap 1. Signal: 240 of 266 events of the original reading reappear in the kept clauses.
World3 world alone answered under 10 questions per cell on these stories (state questions are rare in val_more and
val_fresh2): hand reader untouched 3 / 2 original -> 4 / 4 canonical, translator 2 / 5 -> 4 / 3; inconclusive.
Symbolic question answerer over the translator's events (ag3_qa.py; who / what / where shapes; same reader on both
texts), untouched val_fresh2 (200 questions): original **17 right / 4 wrong (+5, precision 0.81)**, canonical
**25 right / 3 wrong (+16, precision 0.89)**; practice val_more: 18 / 4 -> 25 / 4. Nineteen questions changed
outcome, 15 of them from silent or wrong to right ('Who planted Arjun's rows?' silent -> Meera; 'Who hired a fishing
boat?' winds -> Sefa; 'What did Keiko paint?' 'a new' -> 'a new sign'); 2 went the other way (a dropped clause).
Reading: the owner's loop works at this scale. A small model proposes, a symbolic verifier keeps only clauses whose
words, event structure and roles survive, and the canonical text is more readable to a symbolic engine than the
prose, at higher precision. The model's own errors (loops, agent swaps, inventions) were caught, not trusted.
Limits: 14% of questions reached; the largest rejection class ('no event', 294) is the translator's narrow idea of an
event (no copular or existential clauses); the 0.4B model costs ~2 min per story on this CPU.

## AG4 registration (the loop one level deeper, on every story)
ag4_canon.py: as AG3 with (1) depth 2: a clause rejected as 'no event' or 'fragment' is itself sent back to the model
once ('WHO DID WHAT WHERE'), its pieces through the same verifier; (2) copular clauses ('X was ADJ / NP / PP') count
as events (verb 'be') when the translator finds none, in the verifier and in the question answerer (ag3_qa.py
--copular, new question shape 'what / where was X'); (3) all 502 stories, the 80 AG3 stories first.
Instrument: ag3_qa.py (--canon ag4_canon.json --copular), original vs canonical, same reader on both.
Gates: dev (val_fresh2, 200 questions, AG3 canonical 25 / 3): PASS if right > 25 at precision >= 0.89. Scale (the
1,800 untouched questions, scored once when all stories are done): PASS if canonical gives more right answers than
the original at no lower precision. Expected: the depth-2 pass recovers part of the 294 'no event' rejections; the
copular rule reaches 'what was in the jar' questions. Cost: about 1.3 min per story once B2b frees the CPU, so the
full 502 is an overnight run (resumable, checkpoint per story).

## AG4 dev result -- FAIL on the dev gate (no gain on untouched; the yield is no longer the bottleneck)
Dev block (stories 22-101, 10,519 s): 415 clauses accepted (AG3 361), 36 of them rescued at depth 2, 13 copular;
rejected: no event 455, fragment 131, invented 110, copies 33, swap 1; signal 241 of 267 events kept.
Symbolic QA, untouched val_fresh2: canonical **25 / 3** (AG3 25 / 3; original 17 / 4) -- unchanged; practice 30 / 5
(AG3 25 / 4). The copular rule changed no answer. Reading: more accepted clauses do not become more answers because
the question answerer reaches only 14% of questions (172 silent of 200); the rewriting yield is no longer the limit,
the reader's reach is. The full-502 run continues for the scale measurement, but the next registration moves the
loop to the answer side.
