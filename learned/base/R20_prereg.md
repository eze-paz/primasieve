# R20 -- EMERGENT STATE RULES: VERB -> STATE OPERATOR BY ELIMINATION (2026-10-10)

Registered before any run. R19/R19b proved the value of a time/place world state; its update rules (which verbs move
the actor, which move the thing, which change the holder, which fix a place) are hand-written. R20 makes them emergent
with the project's own mechanism: `core/induce.py` binds a word to an operator by ELIMINATION -- a word keeps an
operator only if, in every teaching case containing the word, that operator reproduces the confirmed answer and no
other does. Here the words are verbs (and the preposition that follows), the operators are a small fixed inventory of
state updates (actor -> destination; thing -> destination and holder := actor; thing -> place and holder := none;
holder := recipient; holder := actor; actor -> place; no change), and the confirmed answers are time/place questions
with gold answers that the story generator can emit for free (its skeletons know where every thing and person ends up).

## Method
1. Extend `stories_gen.py` to emit time/place questions with gold ("Where was X at the end?", "Who had X at the end?",
   "Where did X leave Y?") for the skeletons that move things and people -- the generator's own state is the truth.
2. For each verb (+ following preposition) seen in those stories, induce its operator by elimination over the cases
   (`core/induce.induce`); a verb with no surviving operator stays unbound (the state abstains on it).
3. Replace `worldstate.py`'s hand-written verb lists by the induced table; run the same validation (val_timespace,
   30 questions) and the 80 story questions.

| gate | bar |
|---|---|
| **R20-a** | the induced table binds >= 15 verbs, each to exactly one operator, with zero hand-written verb lists remaining in the state |
| **R20-b** | val_timespace with the induced rules: world alone >= 18 matched at >= 0.90 (R19b: 20 at 0.95) |
| **R20-c** | merged on the 80 story questions >= 69 |

If R20-b holds, the world state is emergent in the project's sense: its rules are induced from cases and verified by
reproduction, and they grow as the generator (or verified use) supplies more cases.

## First run (2026-10-10, `r20_induce.py`)

600 teaching stories, 131 verbs. The elimination bound **2 verbs** (fetch, find -> holder := recipient); the induced
world alone scored 9 / 30 matched, 6 right on val_timespace. R20-a MISS (2 < 15), R20-b MISS. Diagnosis in progress:
per-operator scores on the most used verbs, and how many of the generator's state questions the world can address at
all with an empty table (a question the state cannot address with any binding cannot eliminate anything).

## Second run (same day; ties -> simplest operator; state questions for three more skeletons)

Bound **7 verbs** in two passes: borrow -> holder := actor; reach -> actor to destination; take -> thing to place and
released (the tie with "thing to destination and held" broke to the simpler operator, and no question in the cases
distinguished them); fetch, find, hang, name -> holder := recipient (the last two are wrong: a reader artefact,
"hung it back" / "a boy named Erlend", with cases that happened to agree). Induced world alone on val_timespace:
**11 / 30 matched, 7 right (0.64)**. R20-a MISS (7 < 15), R20-b MISS.

Reading: the mechanism works -- bindings come from cases, not from me, and the right ones (borrow, reach) are the ones
the cases discriminate. What is thin is the teaching signal: the generator's state questions ask about the holder far
more than about the place, so verbs that move things cannot be told apart from verbs that release them, and the hand
reader's event errors (name, hang) become bindings when the few cases they touch happen to agree. Two next steps,
registered here: (1) every state-moving skeleton emits BOTH a holder question and a place question after each verb,
plus a question that asks about the actor's own place -- the cases must discriminate every operator pair; (2) a
minimum support of 10 agreeing cases before a verb is bound, and a verb bound only if its binding reproduces >= 90% of
its cases (the reader's noise then stays unbound rather than wrongly bound). Both are mechanical and run on the same
validation. The hand-written state (R19b) remains the engine's state layer until the induced one matches it.

**Third run:** support >= 10 and >= 90% of ALL state questions in the verb's stories: **0 verbs bound** (a verb's binding can only answer the questions its own effect decides; the 90%-of-everything rule was mis-specified). Fourth run: elimination proper -- an operator that loses any case 'none' reproduces is out; the best consistent operator wins with support >= 10 gained cases; up to 80 teaching stories per verb.

**Fourth run:** elimination by no-regression, support >= 10, 80 stories per verb, holder+place questions: **the same 7 verbs, the same table, 11 / 30 at 0.64** -- the added questions did not separate 'take' from 'leave' and did not unbind the two reader artefacts. R20-a MISS, R20-b MISS after four runs. Open diagnosis (not resolved today): which cases the artefact bindings gain from, and why the place question after 'take' does not favour the holding operator -- likely the reader's event for 'He took it to X' (pronoun agent and patient) is not the event the simulation assumes. The hand-written state (R19b) stays the engine's layer; R20 continues with per-verb case inspection, registered as its next step.

**Fifth run (traced):** the same 7 verbs, the same 11 / 30. The trace shows why, and it is the project's own Stage 3b
lesson: for 'walk', 'carry' and 'give' every operator scores the same because the state questions that would tell them
apart depend on OTHER verbs being bound too ('steal' matters only once 'drop' releases; 'walk ... to X' only decides a
place question when the later 'went to the well' and 'returned' are bound), and a per-verb elimination from an empty
table never gets its first foothold -- "coordinate descent strands on interacting dimensions" (`core/search.py`).
'take' binds to release rather than hold by 190 to 185 because the cases mix 'took it to X' (hold) with 'took the X
back' (hold, but then an unbound 'row home' decides the end state). Next design, registered, not run today: induce the
bindings of the verbs that co-occur in one skeleton JOINTLY (an exhaustive search over the 8^k assignments of a
skeleton's k state verbs, k <= 4, scored by the skeleton's own questions -- the mechanism of `core/search.exhaustive`),
then merge the per-skeleton tables where they agree and leave the rest unbound. The hand-written state remains the
engine's layer until the induced one reaches it. R20 as run: four MISSES on R20-a/b, each with its cause written down.

## Joint search (same day, `r20_joint.py`)

14 story shapes with 1-4 state verbs; exhaustive search over each shape's operator assignments. Bound **5 verbs**
(reach -> actor to destination; return, find -> holder := recipient; borrow -> holder := actor; take -> thing to place,
released), no conflicts; induced world alone **11 / 30 at 0.64** (unchanged). R20-a MISS (5 < 15), R20-b MISS.

The joint search settles the question of method: for the shapes where the simulation can reproduce anything, it finds
the same bindings coordinate ascent did, cleanly ("borrow, come, take": 79 of 80 reproduced). The limit is elsewhere:
for six shapes **no assignment reproduces a single question** ("arrive, meet, walk": 0 of 20; "carry, find, run, shed":
0 of 80; "give, knock, steer": 0 of 20). On those shapes the hand reader's events are wrong or missing ("shed" and "it"
as verbs, "One night Alain" as an actor, no event for "walked ... to X" with a place), so the state cannot be driven
to the gold by ANY rule -- the induction has nothing to choose between. The teaching substrate, not the search, is
the bottleneck, the same substrate (the hand reader) whose coverage bounded R9-R14.

Next design, registered: the generator EMITS the events of each sentence it writes (agent, verb, patient, place,
recipient) alongside the text, so the teaching signal is exact; the induction binds verbs on exact events; the
validation keeps the reader at read time, since that is the real condition. If the induced table then matches the
hand-written state on validation, the state layer is emergent and the reader is the only hand-written piece left,
which is R17's job.
