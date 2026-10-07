# FLUENCY LOOP -- a plan for looping toward full fluency (2026-10-06)

The owner asked for a loop that runs until "full fluency". This file defines what that means in numbers, how one
iteration of the loop works, when the loop keeps going and when it stops, what it works on in what order, and which
decisions are the owner's. It builds on GUESS_PLAN.md, FLUENCY_HYPOTHESES.md and COMPREHENSION_PLAN.md.

## 1. What "full fluency" means here -- a fixed test battery

"Fluent" cannot be a feeling; it has to be a battery of tests that is built ONCE, held out, and never trained on. The loop
is finished when every line reaches its Level 3 target. Levels 1 and 2 are milestones on the way.

| # | ability | test (held out) | today | L1 useful | L2 conversational | L3 fluent |
|---|---|---|---|---|---|---|
| B1 | **honesty** | false facts stated as facts, across every gate | 0 | 0 | 0 | 0 (never relaxed) |
| B2 | **understanding questions** | 500 questions in ordinary phrasing over things the engine can know (paraphrases, typos, chatty forms) | ~50 % of the chat set; paraphrases 25 % via "did you mean" | 60 % | 80 % | 95 % answered or honestly abstained with a right reason |
| B3 | **understanding statements** | true/false statements, dictionary and conversational | 96 % / 84 % supported, 0-0.4 % false "yes" | held | held | held, on open-domain statements |
| B4 | **reading prose** | share of held-out sentences with a checked proposition (definitions / news-book quotations / a novel) | 2.2 % / 0.5 % / 0 % | 15 / 5 / 5 % | 40 / 20 / 20 % | 70 / 50 / 50 % at precision >= 0.9 |
| B5 | **following a story** | masked-name guessing in novels (Children's Book Test form), points over the frequency guess | +3 | +10 | +20 | +30 |
| B6 | **story questions** | who-did-what questions on held-out short stories | -- (no event reader) | 30 % | 60 % | 85 % |
| B7 | **saying it well** | replies whose wording is attested in prose at every joint, re-read exactly, not reversed | 15/18 messages, 0 % reversed | 80 % of all answers | 90 % | 98 % |
| B8 | **saying it naturally** | owner's blind rating of 30 replies a milestone (1 = robotic, 5 = natural) | not yet rated | 3.0 | 4.0 | 4.5 |
| B9 | **conversation** | 20 scripted multi-turn dialogues (pronouns, follow-ups, corrections, topic shifts) completed correctly | ellipsis rules exist; not measured as dialogues | 50 % | 80 % | 95 % |
| B10 | **breadth** | share of a 500-question open-domain set answered correctly with a source, or guessed and labelled | not measured | 30 % | 60 % | 80 % |

B8 is the only human-judged line: the owner rates a blind sample at each milestone (Section 6). Every other line is
automatic.

## 2. One iteration of the loop

1. **Pick the weakest line** of the battery (furthest below its next-level target, weighted by what blocks other lines;
   e.g. B6 blocks B5 and B9).
2. **Diagnose before designing**: list the failures on that line and sort them by cause (this is how C7 found that the
   monitor's real problem was two-word relations, not missing exposure).
3. **Write a hypothesis and its prereg** (theory, mechanism, gates with bars, a knockout, predictions) BEFORE code.
4. **Build, run, record.** At most three declared runs per hypothesis; every miss is recorded as a miss.
5. **Re-measure the whole battery** (not only the targeted line), so no gain hides a loss elsewhere.
6. **Commit; update the live chat** if the change is user-visible; update this file's "today" column.

## 3. When the loop continues, changes course, or stops

- **Continue** while the battery improves: at least one line gains >= 3 points (or a level) every two iterations, with B1
  still at 0.
- **Change course** when a line stalls (two hypotheses in a row move it < 3 points): the line needs a NEW CAPABILITY, not a
  tweak -- write a short capability plan (like COMPREHENSION_PLAN.md) and start it as the next phase.
- **Stop and ask the owner** when (a) a phase needs data or tools the project does not have (Section 5), (b) THIRTY phases
  in a row stall (raised tenfold from three by the owner, 2026-10-06), or (c) a fix would require relaxing B1. The loop
  never relaxes honesty to gain fluency.
- **Change-course threshold, raised tenfold (owner, 2026-10-06):** a line is declared stalled only after TWENTY
  hypotheses in a row move it < 3 points (was two); before that, the loop keeps trying new hypotheses on it.
- **Done** when every line is at Level 3 on the held-out battery, confirmed by one fresh run of everything.

## 4. Phases, in order (each a capability campaign of several iterations)

| phase | capability | lines it moves | first hypotheses |
|---|---|---|---|
| **P0** | **The battery** | all | build B2, B6, B9, B10 test sets; freeze them; measure "today" for every line |
| **P1** | **An event reader** -- who did what to whom | B5, B6, B4, B9 | verb-centred constructions learned from prose: a verb with its typed slots (agent before, patient after, in this language's order, learned not written); events kept per entity as a story is read; checked by predicting held-out mentions and answering held-out story questions |
| **P2** | **Conversational grammar** | B2, B3, B9 | constructions harvested from dialogue (novels' and plays' quoted speech) by the filled-question check; pronouns resolved by the event reader's entity tracking; questions in any word order read by licensing from far more than 96 examples |
| **P3** | **Knowledge breadth** | B10, B2, B4 | more stores (larger Wikidata crawl, other open data), the researcher on by default, the guesser over more relations; reading prose ADDS facts as readings (labelled, sourced) |
| **P4** | **Natural wording** | B7, B8 | wordings from event frames, not only lookups; junctions attested across a large prose corpus; alignment and brevity; variety on the form side; the reader as monitor for every reply |
| **P5** | **Dialogue and pragmatics** | B9, B8 | topic tracking, follow-ups, clarifying questions only when needed, corrections remembered; say what the listener needs |
| **P6** | **Consolidation** | all | one fresh run of the whole battery; owner's blind rating; whatever is weakest restarts the loop |

## 5. What the loop needs from outside (owner decisions)

1. **More text.** Fluency is learned from exposure; the project holds ~25 M words of dictionary text and one novel.
   P1, P2 and P4 need a real prose corpus -- e.g. public-domain books (Project Gutenberg, a few hundred novels and plays,
   ~50-100 M words). Downloading it needs the owner's permission (source, size, licence) before the loop fetches anything.
2. **Test sets written by a person.** B2, B6, B9 and B10 are fairest when written by someone other than the engine's
   builder. The loop can draft them, but the owner (or anyone) should review or replace them once, before they are frozen.
3. **Blind ratings (B8).** 30 replies per milestone, shown without telling which version made them; about 10 minutes.
4. **Compute and time.** An iteration is ~1-3 hours of machine time (the corpus passes dominate); a phase is days.
5. **Pushing to GitHub** needs the owner's sign-in (the commits are local until then).

## 6. Milestones and reporting

- After every iteration: a short entry in this file (line, hypothesis, verdict, battery delta) and a commit.
- At each level (L1, L2, L3): a plain-language report, the owner's blind rating (B8), and a decision point.
- The live chat always runs the latest passing version.

## 7. Honest expectations

Level 1 is plausible within the next phases (P0-P2). Level 2 needs the event reader and a real prose corpus to work.
Level 3 -- "fluent" in the sense people mean -- is a research target with no guarantee: today's engine is precise and
honest but narrow, and every line of the battery measures how far. The loop's job is to move those numbers as far as
they will go without ever trading away honesty, and to say plainly when they stop moving.

## Owner's ruling (2026-10-06): no stop condition
"There is no valid stop condition. You are as good a judge of fluency as me." The loop does not stop on stalls; a stalled
line changes course (new capability) and the loop goes on. B1 (honesty) remains a RULE every iteration obeys, not a stop.
B8 is rated by the builder against a fixed rubric (1 robotic: frame-like, evidence dumps, wrong word order; 3 plain but
correct and readable; 5 natural: the person's words, right order, no unrequested trailer), with the rated samples kept in
tests/battery/b8_rated_*.md so the owner can audit them -- disclosed as a builder's rating, not a blind one.

## Frozen test sets
The B2, B6, B9 and B10 sets were frozen AS DRAFTED on 2026-10-06 at the owner's instruction (tests/battery/FROZEN.json
holds their hashes). B8 (the owner's blind rating) is not yet rated.

## 8. Log
| date | iteration | line | hypothesis | verdict | battery delta |
|---|---|---|---|---|---|
| 2026-10-06 | -- | -- | plan written | -- | -- |
| 2026-10-06 | P0 | all | battery built (drafts), baseline measured | -- | B1 20 (later found: 14 counting, 4 memory, 1 test, 1 engine), B2 73.7 %, B9 17/20, B10 14 %, B6 4 %, B5 +11.6, B4 novels 0.07 % |
| 2026-10-06 | 1 | B5, B6 | an event reader (events_prereg.md) | NOT PASSED (E2) | B5 held-out novels +11.5 over frequency (events ~+3 of it); B6 31/100 (from ~0) |
| 2026-10-06 | 2 | B1 | the baseline's false facts (honesty_prereg.md) | H1 PASS, H2 NOT PASSED | B1 20 -> 0; B2 74.7 %; B9 17/20; B6 26/100 in the live door; B3 96/0.4 and 84/0; B7 15/18 at 0 % reversed |
| 2026-10-06 | 4 | B4 | constructions learned from 359 novels (novelgrammar_prereg.md) | NOT PASSED (null) | B4 novels 3/4,605 unchanged; statements held |
| 2026-10-06 | 3 | B10 | the 65k store: as a world (run 1), as an offline fetcher (run 2) (breadth_prereg.md) | NOT PASSED | run 1 B10 79.6 % but B1 9; run 2 B10 30.8 %, B1 2, B9 18/20 |
| 2026-10-06 | 5 | B6 | auxiliaries learned from books; synonym verbs (events2_prereg.md) | NOT PASSED | B6 26 -> 28 |
| 2026-10-06 | -- | B8 | builder's rating of the it3 sample (b8_rated_it3.md) | -- | 2.07 / 5 |
| 2026-10-06 | 6 | B8, B1 | four defects the rating exposed; learned question words; charitable statement reading (natural_prereg.md) | NOT PASSED (R1) | B3 conversational 58 -> 86.4 %; B2 76.3 %; B1 0 |
| 2026-10-06 | 7 | B10, B1 | store fetcher labels normalised; namesakes ask (research2_prereg.md) | NOT PASSED (Q1) | B10 30.8 % with B1 0 |
| 2026-10-06 | 8 | B6 | event reader: appositive commas, pronoun objects, main-verb have/be, verb-only questions (events3_prereg.md) | PASS | B6 28 -> 33 |
| 2026-10-06 | 9 | B6, B1 | questions kept out of the story memory (events4_prereg.md) | PASS (J2, J3) | B6 33 held, B1 0 |
| 2026-10-06 | -- | B8 | builder's ratings (b8_rated_it6/it7/it9.md) | -- | 2.80, 2.87, 2.87 |
| 2026-10-06 | 10 | B8 | question frames, one answer shape, short abstentions, learned wh-words (natural2_prereg.md) | PASS (N1 3.30, N2 0, N3 0) | B8 2.87 -> 3.30; B2 74.5 %; **B10 154 was inflated by 29 abstentions listing the gold: honest 125** |
| 2026-10-06 | 11 | B10 | the local store is not rationed like the web; numerals owed (research3_prereg.md) | PASS (L1, L3; L2 on inspection: 3 counted are true store claims vs unlabelled Q-id golds) | **B10 125 -> 396 (79.2 %)**; B2 74.3 %; B6 32; B8 3.40 (b8_rated_it11.md) |
| 2026-10-06 | 12 | B8, B10 | every value of a many-valued property, each certified (multivalue_prereg.md) | PASS | B10 398; B1 counted 1 (true store claim vs unlabelled Q-id); B2 74.3 %; B9 18/20 |
| 2026-10-07 | 13 | B2 | a slip one keystroke from a known word, read when unique and said (spelling_prereg.md) | PASS (knockout gain 0) | **B2 74.3 -> 89.2 %**; B1 counted 1 (true, Q-id gold); B8 3.43 |
| 2026-10-07 | 14 | B6 | verb forms learned from the dictionary's inflection glosses; coordination, infinitives, passive questions, all adjuncts (events5_prereg.md) | PASS (knockout: 8 of 11 points from the learned forms) | **B6 32 -> 43**; B5 held; B1 counted 1 (true, Q-id gold) |
| 2026-10-07 | novel 1 | B4 | every book its own world: named-doer events and appositive roles held book-locally, said "according to <book>" (bookworld_prereg.md) | NOT PASSED (K2 precision 0.86; novels 0.94) | B4-book novels 12.1 %, others 6.2 %; control (event reader's own doer) precision 0.04; frozen B4 3/4,605 unchanged |
| 2026-10-07 | novel 2 | B4 | pronoun doers resolved by the book's own counts (lift of a pronoun after a name); verb chains as written; quotations held out (bookdoers_prereg.md) | NOT PASSED (D1 0.83, D2 9.3 %) | pronoun precision 0.88 (n=25) vs knockout 0.20; novels precision 0.96; B4-book novels 12.1 -> 9.3 %; frozen B4 3/4,605 |
| 2026-10-07 | novel 3 | B4 | pronoun chains, same-sentence pronoun evidence, a learned first-person narrator, checks by repetition in the same book (bookcheck_prereg.md) | NOT PASSED (E1 0.77, E2 10.1 %, E3 0.42, E4 0/30) | narrator misread plays and multi-sentence quotations; repetition keys met by coincidence; frozen B4 3/4,605 |
| 2026-10-07 | novel 4 | B4 | whose voice: quotation parity across a paragraph, plays recognised, clitic negation, repetition with content (bookvoice_prereg.md) | NOT PASSED (F1 0.88, F2 0.81, F4 9.5 %) | **novels precision 0.98, novel pronoun/narrator 22/22**; non-fiction 0.78; repetition-with-content finds 0 checks; frozen B4 3/4,605 |
| 2026-10-07 | novel 5 | B4 | the bridge to the real world with store evidence (claims stay the book's); title runs, adverb in chains (bookbridge_prereg.md) | G1 PASS (0.91; novels 50/50), G2 MISS (bridges 0.80) | B4-book novels 9.5 % held; 25 bridges (Plato, Padua, Henry Fielding ...; wrong: given names in a biography); frozen B4 3/4,605 |
| 2026-10-07 | novel 6 | B4 | stricter bridge (item label must match; one-symbol names need two partners) and stricter pronoun abstention (bookbridge2_prereg.md) | NOT PASSED (H1 0.89, H2 3/4) | precision bought by silence: 4 bridges, no third-person pronoun readings; novels 9.5 % held; frozen B4 3/4,605. Iteration 5 remains the best setting |
| 2026-10-07 | 15 | B2, guesses | fetched worlds scoped to the conversation window; ranking credits only words read, prefers no guess and nothing left unread (scope_prereg.md) | PASS (core_selftest PASS) | B2 90.2 %; wrong labelled guesses 5 -> 1; B3 conv 87.5 % |
| 2026-10-07 | 16 | B6 | plurals are not verbs, noun phrases whole (learned linker/coordinator), pronoun doers first (events6_prereg.md) | NOT PASSED (47 vs 48) | B6 43 -> 47; all else held |
| 2026-10-07 | -- | all | ENGLISH MAP (forward, theory-driven): 114 phenomena, frequencies, 309 probes, predictions before running (83 % held) | -- | 41 confident WRONG answers found the battery never asks about |
| 2026-10-07 | 17 | honesty (map) | what did not happen is not told as happened: learned markers and conditional opener mark events irrealis (reality_prereg.md) | PASS | probes WRONG 31 -> 24; B6 47 -> 46 (predicted honest price) |
| 2026-10-07 | 18 | B6, map | the function words of stories learned from the books with the dictionary's part-of-speech labels (closedclass_prereg.md) | PASS on B6 (49); probe WRONG bar missed (23) | B6 46 -> 49; B2 90.4 %; probes RIGHT 89 -> 95 |
