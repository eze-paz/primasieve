# R21 — the exact reader as a learned reader (pre-registration, 2026-10-10)

**Why.** R20 showed the state rules can be induced from the generator's exact events (18 verbs, induced world on
val_timespace 21/30 matched, 19 right — level with the hand world). At read time the world still eats the HAND
reader's events, which are the noise source (R20's clean-teaching diagnosis). The owner's order: the non-LLM part must be
emergent; the language part may use gradients. So the reader becomes a learned map sentence -> event lines, trained on
the same exact events, and the hand event reader (core/events.py) leaves the read path.

**Data.** r21_data.py: for each sentence of a generator story with exact events, prompt = previous sentence + the
sentence, answer = its events as lines `agent | verb | patient | place | recipient` (`-` empty, `none` for no event).
Pronouns resolve from the previous sentence (the answer carries the name). Held-out: 100 fresh generator stories
(seed 777, names free), never trained on. Validation: val_timespace (hand-written stories, 30 questions).

**Model.** RWKV-7 World 0.4B from the base weights, top 6 blocks + head, finetune.py `--data r21_train.json
--layers 6 --batch 4 --lr 2e-5 --hours 2.5 --tag r21 --keep-every 500`, one run, detached.

**Reader.** r21_reader.py: greedy decode of the event lines, parsed into the InducedWorld's exact-event dicts
(place keeps its preposition). The induced table r20_joint_table.json is NOT re-fitted.

**Gates (one run each, last checkpoint).**
- R21-a (held-out generator sentences, 100 stories): exact event-line match on >= 80% of sentences.
- R21-b (val_timespace, learned reader -> induced world): matched >= 18 at precision >= 0.85
  (reference: hand reader -> induced world = 21 at 0.90; hand reader -> hand world = 20 at 0.95).
- R21-c (disclosure only): the same on val_stories / val_fables (80 questions) with the merged engine is NOT run here;
  the reader's coverage of non-generator sentences is the thing R21-b measures.

**Predicted failures.** Verbs absent from the generator (slip, fell, met, wash, ate, hang, pick) will be emitted with
a guessed lemma or dropped; the induced table has no binding for them anyway. Wording outside the generator's
templates ("Jane met him by the river") may yield wrong agents. A miss on R21-b with a pass on R21-a means the
generator's language is too narrow, not that the learned reader is wrong — the next step is then widening the
generator's sentence forms (paraphrase skeletons), not hand rules.

**Run 1 (context = previous sentence only), stopped at step 630 (loss 0.000 on its own data) after an interim preview of the step-500 checkpoint:** R21-a 30/50 = 0.60 on 10 held-out stories -- every miss is a pronoun whose antecedent sits TWO sentences back ('When he came back, Melissa was waiting at the door' -> the model invents a training name); R21-b learned reader -> induced world on val_timespace 20 matched, 14 right (0.70). A one-sentence context cannot resolve those pronouns, so run 1 was stopped before its registered end (disclosed; the interim numbers above are NOT a gate result). **Run 2 (registered now): context = the whole story so far**, same model, data, budget and gates.

**Run 2 SUSPENDED by the owner (2026-10-10) to start R24 (the next-word game through the epistemic layers). Stopped at the step shown in train_r21b.out; the step-500 checkpoint ckpt_r21b_s500.pth is kept and can be evaluated with r21_reader.py --ckpt ckpt_r21b_s500.pth when the queue allows. Not a gate result.**
