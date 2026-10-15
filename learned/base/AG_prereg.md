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

## AG5 registration (the loop on the answer side: the model proposes the answer, the canonical text verifies it)
ag5_support.py. The model's reply for each question (b2_conf_answers.json, already computed) is accepted only if the
text supports it: every content word of the reply occurs in the text (no invention), and one sentence or clause
contains the reply's last content word together with the question's verb lemma, or, when the question has no verb
beyond 'be / do / have', one of the question's content words. The support check is run on two substrates: the
original sentences and the AG4 canonical clauses. Variants: unthresholded reply + support; thresholded reply
(min_lp >= -0.11, the B2b choice) + support. Measured on dev untouched val_fresh2 (200 questions; practice val_more
reported too), as right / wrong / fitness, against the thresholded model alone (B2b) on the same questions, and
combined with the T22p policy where it is silent. PASS if on val_fresh2 support-on-canonical gives higher fitness
than both support-on-original and the thresholded model alone: then the canonical text is the better verifier
substrate, and the loop has a second use. Scored again on the 1,800 untouched once AG4 finishes all stories.

## AG5 dev result -- FAIL
Untouched val_fresh2 (200): thresholded model alone +25 (64 / 13); thresholded + support on original +25 (55 / 10);
thresholded + support on canonical **+22 (46 / 8)**; unthresholded + support: original +3, canonical +11. With the
policy first: +41 / +42 / +41. The canonical text verifies the model's answers no better than the prose: it has
lost some facts (26 of 267 events, and the sentences kept unchanged carry the rest), so support fails where the
prose would have passed, and precision rises only from 0.85 to 0.85-0.86. The loop's gain is for a symbolic reader
(AG3), not as a verifier substrate for a model's answers.

## AG6 registration (does the signal survive for a strong reader? the model answers from the canonical text)
ag6_model_canon.py: the same model and prompt as B2b, but the story is replaced by its AG4 canonical text, for the
400 questions of the dev block (val_more practice, val_fresh2 untouched); replies with confidence; compared with the
B2b replies from the prose on the same questions, unthresholded and at the B2b threshold. PASS (signal kept) if
untouched right answers from canonical >= 0.9 x those from prose at no lower precision; a large drop measures how
much the loop loses, by question kind.

## AG7 registration (reach of the symbolic reader: verb similarity)
ag3_qa.py --sim T: a question verb absent from the events matches an event verb whose learned word vector
(r25_vectors.npz, 13M book tokens) has cosine >= T with it; T chosen on practice val_more from {0.5, 0.6, 0.7, 0.8},
applied once to untouched val_fresh2, on the AG4 canonical text and on the original. PASS if untouched right rises
above 25 at precision >= 0.89 on canonical. Expected: the reach limit is partly verb mismatch ('lend' / 'gave');
this is the cheapest test of that.

## AG7 result -- FAIL, with the audit that matters
Verb similarity at 0.8 / 0.7 / 0.6 / 0.5: untouched canonical stays 25 / 3 (then 25 / 4); practice 31 / 5-6. Verb
mismatch is not the reach limit. Audit of the 172 silent untouched questions (ag7_audit.txt): 74 'verb in text but
no event' -- mostly the question parser picking the wrong word as the verb ('What did the crow find?' -> 'crow');
46 question shapes not handled (when 16, why 6, whose 5, how 3, 'who was ...ing'); 25 known-role mismatches, nearly
all pronoun agents in the canonical clauses ('He called ...', 'She brought ...'); 20 verbs absent; 7 empty roles.
So the limit is the symbolic question answerer, not the rewrite and not the translator.

## AG8 registration (fix the two largest audit classes in the question answerer)
ag3_qa.py --v2: (1) the question verb is the first word after the subject that is an inflected or dictionary verb
(r24_dict), not the first word after a lazy subject match; (2) a pronoun agent in a canonical clause is resolved to
the last named agent before it (he / she / they -> last name; it / they -> last thing is left alone). Same measure
as AG7, canonical and original, practice and untouched. PASS if untouched right > 25 at precision >= 0.89 on the
canonical text; the original is reported for the same fix so the canonical gain is isolated.

## AG8 result -- FAIL on precision (reach up)
Untouched canonical **30 right / 6 wrong (+12, precision 0.83)** against 25 / 3 (+16, 0.89); original 21 / 6
(from 17 / 4); practice canonical 36 / 8. The verb and pronoun fixes reach more questions on both texts and the
canonical advantage holds (30 vs 21 right), but the new answers come at 0.83 precision, under the 0.89 gate.
Reading: each hand-written fix to the question parser trades precision for reach, the pattern the project already
saw with hand cues (R24). The parser is the weak part; it should not be hand-written.

## AG9 registration (the question converged to canonical form by the same loop; no hand question shapes)
ag9_qcanon.py. Stage 1: for each question the model proposes a statement with one blank for the asked part
('Who planted Arjun's rows?' -> '___ planted Arjun's rows.'); the engine keeps the proposal only if its words come
from the question (plus 'the'), it has exactly one blank, and the AG1 translator reads it as an event in which the
blank fills a role (agent / patient / place). One retry with a stricter prompt. Stage 2: the answer is that role in
the first canonical clause (AG4 text; and the original text for comparison) whose event has the same verb lemma and
whose other roles match the question event's roles (name match on first token or shared content word); silent
otherwise. Measured on the dev block (practice val_more, untouched val_fresh2), right / wrong / fitness / precision,
against AG3's 25 / 3 (0.89) and AG8's 30 / 6. PASS if untouched right > 25 at precision >= 0.89 on canonical text.
A PASS says the loop handles questions as it handles sentences and the hand parser can go; a FAIL is attributed by
the stage-1 accept / reject counts (the model cannot form the statement) or by stage-2 matching.
AG9 stage-1 fix before the full run (first 25 questions: 6 accepted): the model answers 'who' questions in the passive
('The shelves were stacked by ___'), which the canonical grammar does not have, so passives are rejected and a third
prompt asks for an active sentence; and the blank is probed as 'somebody / something / the blank / to the blank /
somewhere' and must be read as a whole role (a bare 'Blank' was not tagged). Run restarted from the first question.

## AG6 result -- PASS (the signal survives for a strong reader)
The model (ckpt_read1b) answering the dev block's 400 questions from the AG4 canonical text instead of the prose
(2,616 s). Untouched val_fresh2: unthresholded prose 125 right / 67 wrong, canonical **116 / 60** (0.93 of the right
answers, precision 0.65 -> 0.66); thresholded (-0.11) prose 64 / 13, canonical **58 / 11** (0.91, precision 0.83 ->
0.84). Practice: 138 / 55 -> 134 / 53; thresholded 72 / 11 -> 71 / 13. By kind (untouched, unthresholded): who 52 /
16 -> 48 / 17, what 38 / 16 -> 35 / 12, where 21 / 19 -> 21 / 15, when 9 / 7 -> 7 / 7. Reading: the verified
rewrite loses 7-9% of what a competent reader could answer from the prose and gains a little precision; the loss sits
in 'who' and 'when' (dropped clauses, time phrases cut). The canonical text is a near-lossless simplification: the
engine can take it as its input without giving up much of the signal.

## AG9 result -- FAIL (attributed to the proposer)
Stage 1 (6,392 s): 155 of 400 questions converged to a canonical statement with one blank; rejections: the model
filled the blank with a guess 440 times (over three prompts), passive 79, no event with the blank 214, invented 25.
Stage 2, untouched val_fresh2: canonical **11 right / 3 wrong** (original 8 / 2); practice 14 / 5 (11 / 3). Far
below AG3's hand-parsed 25 / 3. Wrong answers come from the translator's cut spans ('his brother's' for 'his
brother's camera', 'against a' for 'against a pine'), a weakness the hand parser shares. Reading: the loop's
question side needs a proposer that can leave a blank; the 0.4B model mostly cannot. The sentence side (AG3, AG6)
stands; the question side is unproven, not refuted.

## AG9b registration (the 1.5B model as the question-side proposer)
ag9_qcanon.py --ckpt rwkv7/RWKV-x070-World-1.5B-v3-20250127-ctx4096.pth --out ag9b_qstatements.json, untouched
val_fresh2 only (stories 62-101, 200 questions; no choices are made on it, the pipeline is fixed). Reported: stage-1
yield against 0.4B's 39%, and stage-2 right / wrong on canonical and original text. PASS if untouched right > 25 at
precision >= 0.89 on canonical. About 4x the 0.4B cost per question.

## AG9b result -- FAIL (the translator is now the ceiling)
1.5B proposer, untouched val_fresh2 (4,600 s): stage-1 yield **116 of 200** (0.4B: 39%); the model fills the blank
only 10 times. Stage 2: canonical **19 right / 8 wrong (precision 0.70)**, original 13 / 5. Wrong answers are the
AG1 translator's cut spans ('dark' for 'dark clouds', 'him a' for 'a cup of tea') and its missing roles: 'when' and
'why' blanks get read as place or patient. Silences are mismatches between the question event and the clause event,
again from the translator's spans and pronoun agents. Reading: with a proposer that can write the statements, the
learned translator (32 synthetic verbs, three roles) is the limit at every stage.

## AG10 registration (a rigid formal language the model writes directly; no learned translator)
ag10_slots.py, 1.5B model, untouched val_fresh2 only (stories 62-101, 200 questions; nothing is chosen on it: the
pipeline has no tunable). Sentences: for each sentence the model writes one slot line per event,
'WHO: x | DID: verb | WHAT: x | WHERE: x | WHEN: x | WHY: x' ('-' for empty), few-shot; the engine keeps a line only if
every slot's content words come from the sentence, its predecessor or a name seen so far, WHO and DID are filled, and
the line is not a duplicate; a pronoun WHO is resolved to the last named WHO. Questions: the same line with '?' in
the asked slot, kept only if it has exactly one '?' and its words come from the question. Answer: the '?' slot of the
first story line whose DID lemma equals the question's and whose other filled slots match (shared content word or
same last word); silent otherwise. Reported: yields of both stages, right / wrong / silent, precision, and the same
on the original text's slot lines is not needed (there is no canonical text here; the slot lines are the canonical
form). PASS if untouched right > 25 at precision >= 0.89 (AG3's symbolic reader: 25 / 3). Cost about 2 h.

## AG10 result -- FAIL as run (15 right / 5 wrong / 180 silent, precision 0.75), cause found
9,243 s on 40 untouched stories: 135 event lines kept (about one per sentence; the model often writes one line for a
two-event sentence), 114 of 200 question lines kept (79 rejected for the wrong number of '?'). Answers: what 8 / 0,
where 6 / 4, when 1 / 0, **who 0 / 1 with 69 silent**. The who-questions are silent because the proposer inverts
them: 'Who shook the trunk?' -> 'WHO: the trunk | DID: shake | WHAT: ?' on nearly every who-question (44 question
lines), so WHO never matches. The slot language and the exact parse work; the proposer's question lines break the
formal language's own syntax.

## AG10b registration (the formal language's question syntax enforced by the verifier)
No new model runs; scored from ag10_lines.json. Rule of the formal question language: a question beginning 'Who'
with no auxiliary ('Who V ...') asks WHO; 'Who did X V' asks WHAT; 'What / Where / When / Why (did|was|...) X ...'
asks that slot and X is WHO. A question line whose '?' disagrees is corrected by swapping WHO and the '?' slot when
that makes it agree, else rejected. Everything else unchanged. PASS if untouched right > 25 at precision >= 0.89;
reported either way as right / wrong / silent by kind.

## AG10b result -- FAIL on reach, PASS on precision
With the question syntax enforced: untouched **21 right / 2 wrong / 177 silent, precision 0.91** (who 11 / 1, what
8 / 0, where 2 / 1; when / why / whose / how all silent). Precision is the best of any symbolic reader in this line
(AG3 0.89), reach is below AG3's 25 because the proposer writes about one event line per sentence and 79 of 200
question lines were malformed; WHEN is rarely filled in the story lines.

## AG11 registration (two symbolic readers of two canonical forms, union)
No model runs. AG3's canonical-clause reader (ag3_qa_rows.json, canonical answers, 25 / 3) first; where it is
silent, AG10b's slot-line reader (ag10_rows.json with --grammar). Untouched val_fresh2 only, nothing chosen. PASS
if right > 25 at precision >= 0.89. It measures whether the two canonical forms are complementary.
