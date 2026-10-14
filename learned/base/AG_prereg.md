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
