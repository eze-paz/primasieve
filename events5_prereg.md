# Pre-registration -- LOOP ITERATION 14 (B6): VERB FORMS THE MORPHOLOGY TABLE LACKS, LEARNED FROM THE DICTIONARY; FIVE READER GAPS (`kb_events.py`, `core/events.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. B6 is 32/100: who 23/46, what 9/30, where 0/11, when 0/5, how 0/3,
why 0/2. A dump of the event reader over the stories (no door) shows the largest cause is DATA, not grammar: the
UniMorph English table lacks the past tense of common verbs -- "found" is listed only under the obscure lemma "foind",
"wanted" and "played" have no finite entry at all -- so "Ada found them", "Sana wanted to learn", "Sana played a song"
make no event or a wrong one; and rare homograph lemmas turn other words into verbs ("red" -> "rede", "loaves" -> "loave").

## Mechanism
(A) **Inflection glosses learned from the dictionary.** For every (form, lemma) pair UniMorph lists as finite past,
third-person present or participle, the KAIKKI dictionary's VERB senses of that form are read; a gloss of the shape
"<T> of <lemma>" counts template T for that cell. A template is kept for a cell when it was seen >= 20 times with it and
in >= 30 % of its uses. Every dictionary entry with a verb sense "<T> of <L>" for a kept template then adds form -> L to
that cell ("found": "simple past and past participle of find"). No template is written by hand.
(B) **A verb form whose lemma is rare is not that verb**: a lemma seen fewer than 1/100 as often as the form in the text
model's counts is dropped ("red" 6,463 vs "rede" 24).
(C) **Coordinated verbs share the doer**: a verb with no agent in its clause, after another event of the same sentence,
takes that event's agent ("the fox came by and flattered the crow").
(D) **"to" + a base verb is an event** with the clause's agent ("climbed the mast to fix a torn sail" -> Bram fix sail);
the infinitive marker is LEARNED as the closed-class symbol most often followed by a base form in the training books.
(E) **A question that names every core role asks for the rest**: when the question's content fills the agent and the
patient (or the agent of an event with no patient), the answer is ALL the event's adjuncts, in order ("across the lake to
the island"); a PASSIVE question (a learned auxiliary, then a participle of the verb, no agent named) maps its content to
the PATIENT ("when were the tomatoes planted" -> the adjuncts of Rosa plant tomatoes).

## Gates
| gate | claim | bar |
|---|---|---|
| **V1** | B6 (live door) | **>= 40** |
| **V2** | B5 (held-out novels) not lower by more than 1 point -- the independent check | held |
| **V3** | B1 | 0 (counted; inspected) |
| **V4** | knockout of (A) (templates learned from SHUFFLED gloss-lemma pairs) | V1 gain attributable to (A) printed |

## Prediction
B6 ~42: who/what gain most (A, B, C); where/when gain from (E) where the adjunct holds the gold; why/how stay ~0.

## Amendments before the battery run (2026-10-07), from the event dump over the stories (no door)
- (D) the learned marker: the single best symbol by share was a modal ("may"); every closed symbol followed by a VERBAL
  base form in >= 25 % of its uses is a marker instead (learned: can, could, may, t, to, will, would). A verbal base form
  is a lemma whose finite forms occur in the books at least as often as the bare form.
- (G) a turn ending in "?" is a question for the event memory even when its first symbol is not among the 200
  commonest ("where" is not).
- (H) a question that shares an ADJUNCT with an event ("who challenged whom to a race") is a basis for answering its agent.
- (F) tried and DROPPED: "a verb form after a symbol that never precedes a verb is not a verb" ("a lost puppy") -- the
  learned set (closed symbols followed by a finite form < 2 % of the time) held modals and prepositions, not "a"/"the",
  because plural nouns and third-person verbs share forms.
Event memory alone over the stories (no door): 32 -> 42/100 with (A)-(E), (G), (H).

## Run (2026-10-07, battery14 + knockout): PASS (V1-V4)
**V1 B6 43/100** (from 32). V2 B5 +11.6 (held). V3 B1 counted 1 (the "jurisdiction" item, a true store claim against an
unlabelled Q-id gold), none in B6. V4: with (A)'s templates learned from SHUFFLED form-lemma pairs, no template survives
(0 kept) and B6 is **35** -- (A) accounts for 8 of the 11 points, (B)-(E), (G), (H) for 3. Seven templates were learned
from the dictionary: simple past; simple past and past participle (two cells); past participle; present participle;
present participle and gerund; third-person singular simple present indicative -- 148,925 forms added.
B2 89.2 %, B9 18/20, B10 398/500, B3 and B7 unchanged, B4 3/4,605. B8 sample unchanged (3.43).
Still missed: answers that need inference ("who flattered the crow" -- the story says the fox TOLD the crow her voice
must be beautiful; "who won the race"), why/how questions, and verbs the question words differently ("return" / "gave
back").
