# R25 -- the learner revises its own store from its own score

Owner, 2026-10-11: "i want our epistemic system to be super emergent and be able to make its own programs/relations ... maybe you need to let the model see its own score and try to learn rather than nuking it every iteration?"

## Design
- A persistent store (r25_store.json) of relations the learner adds itself. It is loaded at every run and never rebuilt.
- The learner answers its practice questions with its learned readers only (no model, no hand cue reader) and scores itself: +1 right, -3 wrong, 0 silent.
- From its own failures it proposes revisions with general operators, tests each on the practice questions it touches, and keeps it only if its own score rises.
- Operators in R25-a: SHAPE-ALIAS (an unrendered question shape is read as a learned shape one edit away); VERB-ALIAS (a question verb absent from the story is read as a verb the story has).
- Practice: the old 110 validation questions plus fresh m1-m20 (210). Holdout, aggregate only and never used to choose: fresh m21-m40 (100). B6 is not touched by the learner; it stays a sealed check, run once per registration through the policy with --store.

## Gates
- R25-a passes if holdout fitness after > holdout fitness before.
- If it passes, the policy runs once with --store; B6 once.

## Base
R24-ap2 configuration (dictionary on, reinterpretation on, closed-loop readers).

## R25-a result (gate failed)
Practice fitness 14 -> 30 (59/15 -> 75/15) with 13 revisions kept, but holdout -9 -> -10 (21/10 -> 23/11). The 5 shape aliases are general (a preposition the template did not need: 'who V to REF' read as 'who V REF'); the 8 verb aliases are memorisation, each fixing one question ('walk' -> 'refuse', 'own' -> 'like', 'say' -> 'slide'). Keeping any +1 revision memorises single questions.

## R25-b registration (transfer rule, self-pruning)
- A revision is kept only if it improves practice questions in at least two different stories and worsens none.
- --prune: at the start of a run the learner re-judges every stored revision by the same rule (remove it, rescore, keep it only if it meets the rule) and drops those that fail, logging them in the store's history. The store is not wiped; the learner revises it.
- Gate: holdout fitness at the end of the run > holdout fitness with an empty store (-9). If met, the policy runs once with --store and B6 once.

## R25-b result (gate failed; self-pruning works)
Pruning removed 11 of 13 stored revisions by the learner's own transfer rule (all 8 memorised verb aliases, 3 single-story shape aliases); 2 shape aliases with support in >= 2 stories remain. No new revision met the rule (204 candidates). Holdout -12 with the store vs -9 empty. Finding: with 210 practice questions nearly every failure is unique to one story; the learner cannot discover transferable relations from that little signal. Next: a large self-supervised signal -- prediction of real book text.

## R25-c registration (the learner refines its own word groups by predicting real text)
- Signal: prediction of real book text. Groups are scored by a class-bigram model's bits per token on held-out books (Gutenberg books the counts never saw); millions of training tokens instead of 210 questions.
- Persistence: groups live in r25_classes.json and are refined further at every run; first run starts from the induced k-means classes (200).
- Operator: exchange -- each of the 8,000 most frequent words moves to the group with the highest training likelihood; a pass is kept only if held-out bits fall.
- Downstream gate (next registration, R25-d): the answer-type check that failed in R24-am because the groups were too crude ('doctor', 'nephew', 'dusk') is rerun with the learner's refined groups; it passes if it removes wrong answers on validation without losing right ones; then B6 once.
- Gate for R25-c itself: held-out bits/token fall below the starting groups'.

## R25-c result (PASS)
Held-out book bits/token 9.8298 -> 9.1414 -> 9.1301 (pass 3 9.1336 rejected by the learner's own score); 4,925 then 1,748 words moved; groups saved to r25_classes.json. Groups now gather by meaning without labels: 'doctor' with king, maid, colonel, dentist, baron, countess (also sun, moon); 'nephew' with mother, wife, son, daughter, sister, cousin; 'dusk' with dawn, midnight, noon, breakfast, lunch; 'lend' with give, tell, teach, allow; 'eleven' with the numbers. 'mole' still sits with time / counting nouns.

## R25-d registration (downstream use of the learner's own groups)
The answer-type check of R24-am is rerun with --classes (the learner's refined groups) on the R24-ap2 configuration. Passes if, on validation, it removes wrong answers while losing at most as many right answers as it removes (R24-am with the old groups lost 16 right on all 310), and validation precision after admission >= 0.90; then B6 once.

## R25-d result (negative)
Type check with the learner's refined groups: removed 18 right and 4 wrong answers on validation; precision after admission 73/76; **B6 once 79** (spoke 26, right 24). Cause: the groups are fine, the answer-type table is not -- it is learned from the generator's gold answers, which use a few dozen objects and places, so 'the seedlings', 'the feast', 'a gale', 'the picnic' are refused for never having been a generator answer; 'why' answers are typed by their last word ('the salt was dry' -> 'dry').

## R25-e registration (roles learned from the books)
From the training books, the learner counts which of its own word groups fill the object slot and the subject slot of each verb group (a verb followed within three words by a determiner phrase; a name or noun right before a verb). An answer to 'what did X V' is refused when its group never fills V's object slot in the books although at least 5 such fillers were expected from the group's frequency; an answer to 'who V' likewise for the subject slot (names always allowed). 'Why' and 'how' answers are not typed. Gate as R25-d: removes more wrong than right answers on validation, precision after admission >= 0.90; then B6 once.

## R25-e result (neutral)
Roles counted from the books: 127,896 verb-object and 261,555 subject-verb pairs over 164 verb groups. The check removed no answers, right or wrong: at the level of about 200 groups nearly every verb group has met nearly every noun group once, so nothing is confidently never seen. B6 once 82 (spoke 28, right 27).

## R25-f registration (the learner's own groups used for understanding, not filtering)
When a question's verb is absent from the story, the question reader reads it as the single story verb in the same learned group (R25-c groups; e.g. 'lend' with 'give'); if no or several story verbs share the group, nothing changes. One general rule, measured as a whole: readers-alone fitness (+1 / -3 / 0) on practice and on the holdout (fresh m21-m40), with and without the rule, same store. Passes if holdout fitness rises; then the policy runs once with it and B6 once.

## R25-f result (negative)
Practice 63/15 (fitness 18) -> 64/19 (7); holdout -12 -> -15. Group-level verb swaps are too coarse: the group of 'lend' also holds 'tell', 'let', 'kill', 'thank'.

## R25-g registration (graded similarity, threshold chosen by the learner)
- The learner builds its own word vectors from the training books with no labels: each of 15,000 words gets a profile of the words within two places of it (positive pointwise mutual information over 3,000 context words), compressed to 100 dimensions; similarity is the cosine (r25_vectors.npz).
- A missing question verb is read as the most similar story verb when the similarity reaches a threshold. The learner chooses the threshold itself from {none, 0.8, 0.7, 0.6, 0.5, 0.4} by its practice fitness (+1 / -3 / 0).
- Passes if holdout fitness at the chosen threshold beats no swap; then the policy runs once with it and B6 once.

## R25-g result (the learner rejected verb swaps itself)
Vectors from 6.97M book tokens: nearest to 'lend' give, show, allow, bring; 'nephew' brother, son, cousin, uncle; 'dusk' dawn, twilight, sunset, midnight; 'parcel' envelope, packet, package, basket. Blind spots: 'own' sits with my / your / their (the adjective sense); 'count' with colonel, baron, duke. Practice fitness by threshold: none 18, 0.8 15, 0.7 6, 0.6 7, 0.5 2, 0.4 -1 -- every swap level adds wrong answers faster than right ones; the learner chose no swap; holdout unchanged (-12). Finding: similarity bolted onto the template reader does not help; it needs a reader that uses similarity natively.

## R25-h registration (a similarity-native reader)
Each name / thing span in the story is a candidate; score = match (mean over question content words of the best cosine to a word in the candidate's sentence, learner's own vectors) + LAM x type (cosine of the candidate's head word to the prototype of that question kind, averaged from the generator's gold answers). It answers only when the best beats the second by MARGIN. LAM and MARGIN are chosen by the learner on its practice questions (who / what / where / when / whom). Gate: holdout fitness (+1 / -3 / 0) > 0 on its own (the existing learned readers score -9 there); then it joins the policy as a third reader and B6 runs once.

## R25-h result (gate met narrowly)
Always answering, the similarity reader's top candidate is right on 84 of 192 practice questions (44%; wrong 108); the learner chose LAM 0.5, MARGIN 0.3 (practice 13 right / 3 wrong); holdout 5 right / 1 wrong (fitness +2 > 0). Alone it is precise only at tiny coverage; as a ranker it is right more often than the template readers answer at all.

## R25-i registration (the similarity reader as a third vote)
In the policy (R24-ap2 configuration), routes gain a '+soft' mark when the similarity reader's top candidate matches the answer; a lone unconfident cue answer (withdrawn in R24-ao) returns as 'cue-alone-loose+soft' when the similarity reader independently picks it and no learned reading dissents; 'soft-alone' when only it speaks with MARGIN >= 0.3. Admission by the disagreement rule against the model (R24-ak/al). Gate: validation precision after admission >= 0.90; B6 once.

## R25-i result (learner improves on fresh text; B6 merge falls)
Fresh 200, learner alone: 70 spoke / 58 right (R24-ap2: 53 / 45); old 110 61 / 57. Three-way agreement 'agree+soft' 35/35; 'cue-alone-loose+soft' 14/17. Validation after admission 104/100 (0.96). **B6 once 78** (spoke 36, right 31). Same pattern as R24-ad..an: every added reader answer at ~0.85 precision replaces a B6 model answer that is usually right (model 0.80 on B6, mostly on the easy questions the readers can read).

**Measure change (stated):** the owner's goal is the non-LLM learner's understanding; the battery is the instrument. From here the primary measure is the learner alone on the fresh questions (right / wrong out of 200, fitness +1 / -3 / 0 on the holdout half); B6 merged stays a secondary check run once per registration that changes the policy.

## R25-j registration (the similarity reader learns what to weigh)
The match score gains two book-learned signals: word informativeness (inverse document frequency over training-book paragraphs; a question word's weight) and proximity (cosine contributions decay with the distance between the matching sentence word and the candidate). Weights chosen by the learner on practice: IDF on/off, decay in {none, 0.8, 0.6}, LAM in {0, 0.5, 1}. Measured: top-1 right when always answering on practice and holdout, holdout fitness at the learner's chosen margin. Passes if holdout top-1 right rises above R25-h's.

## R25-j result (neutral)
Informativeness (book IDF over 45,997 words) and proximity decay barely move the similarity reader: practice top-1 right when always answering 82-90 of 192 across settings (R25-h settings 88); the learner kept the R25-h settings; holdout top-1 39/95 for both. A bag-of-similar-words ranker plateaus near 45%: it knows which words are near the answer, not who did what to whom.

## R25-k registration (a role reader that matches loosely)
Roles come from the learned constructions (subject, object, place, time of each verb occurrence, clause-bounded); matching comes from the learner's vectors: the story verb most similar to the question verb, with the question's other arguments matched to the clause's names / things by cosine. The answer is the filler of the asked role (who V -> subject; what / who did X V -> object; where -> place; when -> time span). The learner chooses the verb-similarity and argument-match thresholds on practice (+1 / -3 / 0). Gate: holdout fitness > 0 with more right answers than R25-h (5); the exact-verb-only setting is reported as the reference for what loose verb matching adds.

## R25-k result (PASS)
Holdout (fresh m21-m40, 100 questions): **22 right / 3 wrong, fitness +13** (template readers alone 21 / 10, -9; similarity reader 5 / 1, +2). The learner chose verb similarity >= 0.8 and argument match >= 0.5 (practice 54 / 11, +21). The exact-verb setting scores the same on the holdout (22 / 3): the gain comes from learned roles plus loose argument matching rather than from similar verbs.

## R25-l registration (the role reader joins the policy)
Policy = R25-i configuration plus the loose role reader at the learner's thresholds: routes gain '+role' when it agrees; 'role-alone' when only it speaks; a lone unconfident cue answer returns when the role or similarity reader independently picks it. Admission by disagreements against the model. Primary measure: learner alone on the fresh 200 (right / wrong); secondary: validation precision after admission >= 0.90 gate, then B6 once.

## R25-l result (primary measure up again)
Learner alone, fresh 200: **67 right / 14 wrong** (R25-i 58 / 12; R24-ap2 45 / 8); holdout half m21-40 35 / 6 (R25-i 29 / 5). Old 110: 63 / 6. Four-signal agreement 'agree+soft+role' 20/20. Validation after admission 117/113 (0.97). B6 once 80 (spoke 38, right 34; R25-i 78).

## R25-m registration (actions and complements as roles)
Practice-only error analysis (old 110 + fresh m1-m20; the holdout half not inspected): 22 silent 'what did' questions and several wrong answers ask for an action ('What did the magpie do one evening?' -> 'dropped a shiny button'), which no reader can return. The loose role reader gains two roles: 'do' (the verb and what follows it to the clause end, in the clause whose subject matches the one the question names) and 'comp' ('What did the donkey refuse to do?' -> the complement of 'refuse'). Flag --do. Measured first in the reader harness (thresholds re-chosen by the learner; gate: holdout fitness > R25-k's +13), then in the policy (learner alone on fresh 200; B6 once).

## R25-m result (gate failed)
Reader harness with action / complement roles: practice 54 / 11 (+21) -> 57 / 10 (+27); holdout 22 / 3 (+13) -> 22 / 4 (+10). Negative by the registered gate.

Practice-only look at the action role: 4 of 6 right ('ate half', 'to climb the hill', 'to be lame', 'moved every jar behind glass'); the 2 wrong picked the subject's first clause because the question's time phrase ('every noon', 'one evening') never takes part in matching.

## R25-n registration (time phrases are arguments)
A clause's time phrase joins its arguments for loose matching (--time-args), with the R25-m roles on. Same harness, thresholds re-chosen by the learner; gate: holdout fitness > R25-k's +13.

## R25-n result (gate failed by one point)
Holdout 24 right / 4 wrong (+12) vs R25-k 22 / 3 (+13); practice 60 / 12 (+24). Negative by the registered gate. The 100-question holdout can no longer separate differences of one or two answers, and its totals have now been read four times; finer tuning on it stops here.

## R25-o registration (states: 'where was X')
About 19 practice questions ask for a state ('Where was Beth at the end?', 'Where was the key at noon?'). The loose role reader gains a state role (--state): the clauses in which X is the subject or the object and a place is named; the question's time words choose among them by loose matching to each clause's time phrase, otherwise the latest clause wins; the answer is that clause's place. Base: the R25-k configuration (no --do). Gate: holdout fitness > +13.

## R25-o result (the state role never fired) and R25-o2
R25-o reproduced R25-k exactly (holdout 22 / 3): with the dictionary on, 'was' is read as the verb 'be', so 'Where was X ...?' never reached the state role. Checked on a practice story: once reached, 'Where was the key at noon?' picks the noon clause ('Rosa took the key to the garden') -> the garden (right). R25-o2: the state role accepts a question whose only verb is 'be'. Same registration; the holdout total is reported, and the role is also measured on the new untouched set (val_fresh2) when it arrives.

## R25-o2 result (negative)
With the state role firing: practice 55 / 14 (+13), holdout 23 / 6 (+5) against R25-k 22 / 3 (+13). A last-mention place is often not where the thing is ('Rosa took the key to the garden. She dropped it near the well.'): states need the learned world layers (moves, holders), not a shortcut. The state role stays off.

## R25-c2 registration (do the learner's groups keep improving across runs?)
r25_classes.py is run again; it starts from its own saved groups (r25_classes.json, 9.1301 bits) rather than the k-means start. Passes if held-out book bits fall further.

## R25-c2 result
Starting from its own saved groups (9.1301), one more exchange pass moved 809 words but held-out bits rose to 9.1321; the learner rejected it. With a fixed number of groups, exchange is at a local optimum.

## R25-c3 registration (the learner may split groups)
A new operator: for each of the 30 most frequent groups, split it in two by the learner's own word vectors (2-means) and keep the split only if held-out book bits fall. The number of groups is then the learner's choice. Fix: after a rejected exchange pass the saved groups are really restored. Passes if held-out bits fall below 9.1301.

## R25-c3 result (PASS)
12 of 30 splits kept by the learner's own held-out score; groups 202 -> 213; held-out book bits 9.1301 -> 9.1273. Splits found real distinctions with no labels: know / say / think / believe / feel vs want / wish / expect / beg; came / went / looked / turned / fell vs stood / lay / sat / arrived; will / can / must / should / may vs didst / wilt / shalt / mayst; little / new / small / large / big vs great / mere / sudden / single; paid / spent / obtained / counted vs made / got / put / brought. Some kept splits are small rare-word noise.

## R25-c4 registration (the next cycle continues from the saved state)
Exchange then splits again, starting from the 213 saved groups: up to 2 exchange passes, then splits over the 60 most frequent groups. Passes if held-out bits fall below 9.1273.

## R25-p registration (clean checkpoint on an untouched set)
val_fresh2.json: 40 stories, 200 questions (who 70, what 60, where 40, when 16, why 6, whose 5, how 3), written by a separate agent barred from the tests folder and b6_ files; verified here: every gold form occurs in its story. No choice has been made on it. Caveat from its author: five fables retell well-known Aesop plots (the learner has no knowledge of them; the model may).
The model (ckpt_read1b) is run once on all 510 validation questions. Then the R25-l configuration (role and similarity readers, dictionary, no-loose, disagreement admission) runs once. Primary measure: the learner alone on val_fresh2 (right / wrong out of 200), compared with the earlier configuration R24-ap2 run on the same 200 in the same pass. Secondary: B6 once.

## R25-c4 result (PASS)
From the saved 214 groups: exchange 9.1273 -> 9.1259 -> 9.1233; then 26 of 60 splits kept -> 240 groups, held-out 9.1196. New distinctions: man / woman / girl / child / boy split from rare nouns; white / black / red / blue vs cold / hot / warm / dry; wine / music / fish / bread vs water / light / gold / paper / stone; seen / done / taken / given vs filled / covered / surrounded; up / down / away / off / forth as a group.

## R25-c5 registration
The next cycle from the 240 saved groups (2 exchange passes, 80 split tries). Passes if held-out bits fall below 9.1196.

## R25-c5 result (PASS)
From 241 saved groups: exchange 9.1196 -> 9.1142 -> 9.1086; 28 of 80 splits kept -> 269 groups; held-out 9.1037. Distinctions: mind / heart / tongue / conscience vs mother / wife / friend / husband; state / story / scene / situation vs town / city / point / book; natural / simple / sweet / proper vs strange / beautiful / terrible / wonderful; men / people / women / children as a group; door / window / river / road / wall as a group.

## R25-c6 registration
Next cycle from the 269 saved groups (2 exchange passes, 100 split tries). Passes if held-out bits fall below 9.1037.

## R25-c6 result (PASS)
From 270 saved groups: exchange 9.1037 -> 9.1004 -> 9.0975; 29 of 100 splits kept -> 299 groups; held-out 9.0931. Distinctions: between / behind / beside vs upon / against / toward(s); company / conversation / friendship vs interest / pleasure / service; said / quoth apart from motion verbs; learned / discovered / expected vs found / allowed / believed.

## R25-p partial (today's best configuration, R25-l, on the untouched set)
Learner alone: val_fresh2 98 spoke / 69 right / 29 wrong (0.70); val_more 81 / 67 / 14 (0.83); old 110 69 / 63 / 6. Right answers per 200 hold on untouched text (69 vs 67); precision falls (0.70 vs 0.83): the size of the remaining overfitting. Merged validation 387/510 vs model 336/510. B6 once 78 (spoke 37, right 31). The R24-ap2 comparison on the same questions is running.

## R25-c7 registration
Next cycle from the 299 saved groups (2 exchange passes, 120 split tries). Passes if held-out bits fall below 9.0931.

## R25-p result (clean checkpoint)
Learner alone on the untouched set val_fresh2 (200): this morning's configuration R24-ap2 64 spoke / **46 right / 18 wrong** (0.72); today's R25-l 98 / **69 right / 29 wrong** (0.70). On val_more: 53 / 45 / 8 -> 81 / 67 / 14. Today's gains hold on text nothing was tuned on: +23 right (+50%), +11 wrong, precision about equal. Errors on the untouched set by route (aggregate only): learned-alone-exact 6, cue-alone-loose+soft 5, agree 4, cue-alone-strict 3, soft-alone 3, learned-alone-exact-r 3, state-agree 1, role-alone 1 -- mostly the older routes and the similarity confirmation of unconfident cue answers, not the role reader. Model alone on val_fresh2: 125/200. R24-ap2 did not pass the validation precision gate on 510, so its B6 did not run; R25-l B6 78.

## R25-q registration (the learner chooses which of its routes to trust)
From the R25-p run's per-question lines, a route is kept when its practice fitness (+1 / -3 / 0) on the old 110 and val_more 200 is above zero; the kept set is applied once to the untouched val_fresh2 (total only). Passes if the untouched-set fitness with kept routes is higher than with all routes.

## R25-q result (PASS)
The learner kept 16 of 21 routes by its practice fitness and dropped cue-alone-loose+soft, learned-alone-exact, learned-alone-noword, role-alone, soft-alone (each answers on one weak source). Practice 130 / 20 (fitness 70) -> 112 / 7 (91). **Untouched val_fresh2: 69 / 29 (fitness -18) -> 47 / 13 (+8), precision 0.70 -> 0.78**, decided on practice only and applied once. Trade-off set by the -3 weight for a wrong answer (a choice the owner may change).

## R25-c7 result (PASS)
From 300 saved groups: exchange 9.0931 -> 9.0912 -> 9.0875; 37 of 120 splits kept -> 337 groups; held-out 9.0830. Newer splits are increasingly among rare words.

## R25-r registration (the verb-role check with the learner's finer groups)
R25-e's book-learned verb roles refused nothing at ~200 groups. With 337 learner-refined groups the same check (--selpref) is added to the R25-l configuration; route trust is then chosen by the learner on practice (r25_trust.py) and applied once to the untouched set. Passes if untouched fitness with trusted routes beats R25-q's +8.

## R25-r result (neutral)
At 337 groups / 226 verb groups the zero-count role check still refused nothing; trusted-route results identical to R25-q (untouched 47 / 13, +8).

## R25-s registration (graded role score, cut-off chosen by the learner)
Each answer gets a role score: how much more or less often the books pair the question verb's group with the answer's group in that slot than chance ((observed + 0.5) / (expected + 0.5)). Nothing is refused in the run (--lift-only); afterwards, on top of the routes the learner trusts, it picks a cut-off from {none, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8} by practice fitness and applies it once to the untouched set. Passes if untouched fitness beats +8.

## R25-s result (neutral)
Only 88 of 248 answers get a role score (who / what questions built on a verb). Practice fitness by cut-off: none 91, 0.05-0.1 91, 0.2-0.3 90, 0.5 86, 0.8 91 (103 / 4); the learner kept no cut-off; untouched unchanged (+8). The remaining trusted errors are not mostly role-type errors. The verb-role line is closed.

## R25-t registration (the role reader's three practice errors, fixed together, judged with learner-chosen trust)
Practice-only look at the role reader alone: 15 right / 6 wrong. Causes: the question's time words are ignored when choosing a clause (R25-n), no action / complement answers (R25-m), modal verbs swallowed into name spans ('the beaver must', new: --modal-stop). R25-m and R25-n each missed the old 100-question holdout by one point; here the three are combined (--do --time-args --modal-stop) on the R25-l configuration, the learner re-chooses its trusted routes on practice, and the untouched set is reported once as a total. Passes if untouched fitness beats +8.

## R25-t result (negative)
Combined role fixes: practice (trusted) 112 / 7 (+91) -> 120 / 9 (+93); untouched 47 / 13 (+8) -> 49 / 19 (-8). With the fixes the learner also trusted cue-alone-loose+soft, which added untouched errors. Pattern stated: what transferred today was learned from large data (vectors, groups, role reader, route trust); narrow fixes chosen on ~300 practice questions do not. Next: more practice signal (two more hand-written sets of 200, by separate agents barred from the tests folder), and continued group cycles.

## R25-c8 registration
Next group cycle from the 337 saved groups (2 exchange passes, 150 split tries). Passes if held-out bits fall below 9.0830.

## R25-u registration (route trust chosen on 710 practice questions)
Two more practice sets (val_practice_a / _b, 200 questions each, separate writers barred from the tests folder and b6_ files; verified: every gold form in its story; no digit forms in B). Practice becomes 710 (old 110 + val_more 200 + A 200 + B 200); val_fresh2 stays the untouched judge (total only). The model is run once on all 910. The R25-l configuration runs once; the learner chooses its trusted routes on the 710 (r25_trust.py --big). Passes if untouched fitness beats +8 (R25-q). Note: story ids f1-f6 repeat between val_fables and val_fresh2; alignment is by question text and order, asserted per question.

## R25-c8 result (PASS)
From 338 saved groups: exchange 9.0830 -> 9.0784 -> 9.0777; 42 of 150 splits kept -> 380 groups; held-out 9.0735.

## R25-c9 registration
Next cycle from the 380 saved groups (2 exchange passes, 180 split tries). Passes if held-out bits fall below 9.0735.

## R25-c9 result (PASS)
From 381 saved groups: exchange 9.0735 -> 9.0724 -> 9.0704; 50 of 180 splits kept -> 431 groups; held-out 9.0653. Gains per cycle are shrinking.

## R25-c10 registration (more text, same saved groups)
The group refinement continues from the 431 saved groups but counts 400,000 training sentences instead of 150,000 (about 7M tokens, the same text the vectors use). Held-out books unchanged. Passes if held-out bits fall below the start-of-run value measured with the larger counts (reported), and below 9.0653.

## R25-u result (PASS)
Model on 910: 610 (practice A+B 274/400). Learner's route trust chosen on 710 practice questions: kept 14 routes, all with at least two readers agreeing (plus learned-alone-exact+soft, role-alone+soft, state-agree); dropped the lone routes, including the hand cue reader alone even when confident (12 / 6 on practice), the template reader alone (14 / 11), the role reader alone (16 / 8). Practice 277 / 63 (+88) -> 186 / 10 (+156). **Untouched val_fresh2: 42 right / 6 wrong, precision 0.875, fitness +24** (R25-q, trust on 310: 47 / 13, +8). B6 once 79 (spoke 41, right 35).

## R25-v registration (the role fixes re-judged with trust chosen on 710)
R25-t's fixes (--do --time-args --modal-stop) hurt when trust was chosen on 310 practice questions. With 710, they are run again: R25-l configuration plus the fixes, all 910 questions, trust chosen on the 710 (--big). Passes if untouched fitness beats +24.

## R25-v result (negative)
Role fixes with trust chosen on 710: practice (trusted) 186 / 10 (+156) -> 209 / 16 (+161); untouched 42 / 6 (+24) -> 44 / 12 (+8). The fixes are closed.

## R25-w registration (the role reader's thresholds re-chosen on 710 practice questions)
The loose role reader's verb-similarity and argument-match thresholds were chosen on 210 practice questions. The learner re-chooses them on the 710 (r25_soft.py --k --big; argument grid 0 / 0.3 / 0.5 / 0.65 / 0.8 / 1.0), the policy reads them (--role-json), and route trust is chosen on the 710 again. Base: R25-u. Passes if untouched fitness beats +24.

## R25-c10 result (PASS)
Same saved groups counted on 400,000 sentences (6.97M tokens, 31,717 words): held-out 9.0653 -> 8.9619 from the data alone; exchange 8.9429 -> 8.9370; 24 of 100 splits kept -> 456 groups; held-out 8.9355. Distinctions: england / france / europe / america vs paris / london / rome; strange / terrible / sad / dreadful vs beautiful / charming / wonderful / lovely; thoughts / ideas / feelings / hopes vs movements / songs / smiles; fat / solid / stiff / slender vs dark / cold / bright / pale / soft; always / often / usually vs really / simply / actually.

## R25-c11 registration
Next cycle on the same larger text from the 456 saved groups (2 exchange passes, 150 split tries). Passes if held-out bits fall below 8.9355.

## R25-w result (stable settings)
Re-choosing on 710 practice questions, the learner picked the same role thresholds as on 210 (verb >= 0.8, args >= 0.5); downstream identical to R25-u (untouched +24; B6 79). Role reader alone on the untouched 200 at those settings: 46 right / 7 wrong (0.87).

## R25-x registration (the learner's word vectors from all the training text)
Training books hold 22.1M words / 944k sentences; the vectors used 7M. Rebuild from all of it (--sents 1000000), vocabulary 25,000 words, 4,000 context words; previous vectors kept as r25_vectors_7m.npz. Then the role reader re-chooses its thresholds on the 710 practice questions (r25_soft.py --k --big), the R25-u policy runs with them (--role-json), and route trust is chosen on the 710. Passes if untouched fitness beats +24; the role reader alone on the untouched 200 (R25-w: 46 / 7) is also reported.

## R25-x result (PASS)
Vectors from 13.0M tokens (all training paragraphs the reader keeps; 25,000 words x 4,000 contexts): nearest to 'lend' give / repay / send / grant / pay; 'parcel' package / packet / bundle / envelope; 'nephew' cousin / son / brother / heir. Role reader alone (thresholds unchanged, 0.8 / 0.5): practice 177 / 41, untouched 48 / 8. Policy with trust chosen on 710: practice 195 / 11 (+162); **untouched 46 right / 6 wrong, precision 0.885, fitness +28** (R25-u +24). B6 once 80 (spoke 38, right 33).

## R25-y registration (directional contexts)
The learner's word profiles count left and right neighbours separately (--directional; 2,500 context words per side, 25,000 words, same 13M tokens); previous vectors kept as r25_vectors_13m.npz. Same chain as R25-x: role thresholds re-chosen on 710, policy, trust on 710. Passes if untouched fitness beats +28.

## R25-c11 result (PASS)
From 457 saved groups on 400k sentences: exchange 8.9355 -> 8.9312 -> 8.9296; 42 of 150 splits kept -> 499 groups; held-out 8.9261.

## R25-c12 registration (groups on all the training text)
From the 499 saved groups, counting all training paragraphs the reader keeps (--sents 1000000, about 13M tokens). Passes if held-out bits fall below the start-of-run value with the larger counts (reported) and below 8.9261.

## R25-y result (neutral)
Directional contexts: the learner chose exact verbs (verb >= 1.0) on practice; role reader alone untouched 48 / 7; policy with trust on 710: untouched 46 / 6, +28 -- equal to R25-x, not above it. R25-x's vectors and thresholds are restored (r25_vectors_13m.npz, verb >= 0.8).

## R25-z registration (the practice questions teach the readers)
The 710 practice questions (old 110, val_more, practice A / B; never val_fresh2) have only judged and chosen so far. Now they teach: for each, the story sentence holding a gold form and the question's verb gives a (question, sentence, answer) pair for the question reader; then the question reader renders each practice question as a statement with the gold answer, added to the sentence reader's training for that story. Built on R25-x. Caveat: practice scores become partly in-sample, so the trust choice made on practice may over-trust; only the untouched set can show it. Passes if untouched fitness beats +28.

## R25-z result (gate failed; B6 best yet)
Practice teaching: 485 question-sentence pairs from 142 practice stories; question-reader evidence 22,695 -> 23,976; 589 statements for the sentence reader. Untouched, all routes 70 / 30 -> 74 / 35; with trust chosen on the (now taught) practice: 45 / 8, +21 < +28 -- gate failed; the learner over-trusted, as the caveat predicted (practice became in-sample). **B6 once 84** (spoke 36, right 34; best yet, one below the bar) -- secondary, and its admission also used the taught practice.

## R25-z2 registration (teach on one half, choose trust on the other)
The readers learn from val_more + practice A (400 questions); route trust is chosen on old 110 + practice B (310), which taught nothing (--teach-half, r25_trust.py --trust-half). Untouched val_fresh2 judges; B6 once. Passes if untouched fitness beats +28.

## R25-z2 result (negative; practice teaching closed)
Teaching on val_more + A (268 pairs, 315 statements), trust chosen on old 110 + B: untouched all routes 71 / 37 (R25-x 70 / 30), trusted 44 / 14, +2. Teaching the readers from the practice questions adds wrong answers on new text even with separate trust data; R25-z's B6 84 most likely came from in-sample admission. R25-x stays the best (+28).

## R25-aa registration (trust per route and question kind)
On R25-x's logged answers, no rerun: the learner trusts a (route, question kind) when it has >= 10 practice answers with fitness > 0, otherwise decides at the route level as in R25-u. Chosen on the 710 practice questions; untouched scored once. Passes if untouched fitness beats +28.

## R25-aa result (negative)
Trust per (route, question kind) chosen on 710 practice: practice 198 / 10 (+168); untouched 46 / 10, +16 < +28. More decisions on the same evidence overfit; route-level trust stays.

## R25-ab plan (more practice evidence)
Trust chosen on 310 -> 710 practice questions moved untouched fitness +8 -> +24. Two more practice sets (C, D; 200 each) are commissioned from separate writers barred from the tests folder and b6_ files, avoiding every name already used; trust will then be chosen on 1,110. Registered when the sets arrive.

## R25-c12 result (PASS)
From the 500 saved groups counted on all training paragraphs (13.0M tokens, 41,195 words): held-out 8.9261 -> 8.8689 from the data alone; exchange 8.8441 -> 8.8437; 25 of 120 splits kept -> 525 groups; held-out 8.8421. The groups are not yet used by the best reading configuration (the readers use the vectors).

## R25-c13 registration
One more cycle on all text from the 525 saved groups (2 exchange passes, 150 split tries). Passes if held-out bits fall below 8.8421.

## R25-ab registration (trust chosen on 1,110 practice questions)
Practice sets C and D (200 each; separate writers barred from the tests folder and b6_ files; verified: every gold form in its story; C and D share only ordinary capitalised words). Practice becomes 1,110 (old 110, val_more, A, B, C, D); val_fresh2 stays the untouched judge (total only). The model runs once on all 1,310. The R25-x configuration runs once; trust is chosen on the 1,110 (r25_trust.py --big). Passes if untouched fitness beats +28. B6 once.

## R25-ab result (negative)
Model on 1,310: 877 (C+D 267/400). Trust chosen on 1,110 practice: kept more routes (only those under 0.75 practice precision drop under the -3 weight); practice 338 / 36 (+230); untouched 53 / 13, +14 < +28. More practice did not keep helping past 710.

**Selection caution (stated):** val_fresh2's total has now been the gate in about 14 registrations (R25-p to R25-ab). Picking the best of many results on the same 200 questions makes the best (+28, R25-x) optimistic. A fourth hand-written set, val_fresh3 (200), is commissioned; the best configuration (R25-x: vectors from 13M tokens, role thresholds 0.8 / 0.5, trust chosen on the 710) will be scored on it exactly once, with B6 once. That number is the day's reportable result.

## R25-c13 result (PASS, diminishing)
From 526 saved groups on all text: exchange 8.8421 -> 8.8400 -> 8.8389; 45 of 150 splits kept -> 571 groups; held-out 8.8361. Group cycles are paused: gains are small and the reading configuration does not use the groups.

## R25-ac registration (the learner's groups in the next-word game, against a fair baseline)
Same tokens (lowercase words), same training text (all training paragraphs) and same held-out books as R25-c: (a) the learner's class-bigram model (its 571 groups) and (b) an interpolated word-bigram model with its mixing weight chosen on a slice of the training text; bits per token on the held-out books. Also (c) the two mixed, weight chosen on the training slice. Reported as is.

## R25-ac result
Held-out books, 270,358 predictions, same tokens and text: word-pair model 8.8078 bits/token; the learner's 572 groups (class-pair) **8.7897**; both mixed **8.6294**. The learner's groups beat the word-pair model with far fewer parameters (about 330k group-pair counts against millions of word-pair counts), and they carry information the word pairs lack (-0.18 bits mixed).

## R25-ad registration (two words of context through the learner's groups)
Predict the next group from the previous two groups, backing off to the previous one when evidence is thin (interpolation weight chosen on the training slice), times the word-given-group probability; mixed with the word-pair model (weight on the training slice). Held-out books scored once. Passes if bits fall below 8.6294.
R25-ad first run: the two-group block never ran (an import reset sys.argv); arguments now captured at the top; rerun, same registration.

## R25-final registration (one clean score of the best configuration)
val_fresh3.json: 40 stories, 200 questions (who 71, what 58, where 40, when 16, how 9, why 4, whose 2), written by a separate agent barred from the tests folder and b6_ files; verified here: every gold form occurs in its story. Nothing has been chosen on it and it will be scored exactly once. Configuration: R25-x unchanged (vectors from 13M tokens, role thresholds 0.8 / 0.5, similarity and role readers, dictionary, no-loose, disagreement admission), route trust chosen on the same 710 practice questions (old 110, val_more, A, B). The model answers all 1,110 (old, val_more, val_fresh2, A, B, val_fresh3). Reported: learner alone on val_fresh3, all routes and trusted routes; B6 once.

## R25-ad result (PASS)
Two groups of context: 8.5651 bits/token alone (better than every earlier mix); mixed with the word-pair model 8.4313 (word-pair alone 8.8078; -0.38 bits). The chosen backoff strength (500) was the top of the grid offered.

## R25-ae registration (wider backoff range; three groups of context)
Backoff strength chosen from {200, 500, 1500, 5000} on the training slice; a three-group context (previous three groups) added with its own backoff to the two-group estimate; each mixed with the word-pair model. Held-out books once. Passes if bits fall below 8.4313.

## R25-ae result (PASS)
Wider backoff range: the two-group model still chose 500 (now inside the range), 8.5651. Three groups of context (backoff 200): 8.5344; mixed with the word-pair model **8.3886** (word-pair alone 8.8078: -0.42 bits). Further next-word work is paused while the final clean evaluation runs, to give it the processor.

## R25-final result (the day's reportable number)
Model on val_fresh3: 127 / 200. R25-x reproduced exactly on the earlier sets (practice 195 / 11; val_fresh2 46 / 6). **val_fresh3, scored once: all routes 73 right / 32 wrong; trusted routes 43 right / 13 wrong, precision 0.768, fitness +4.** The breadth gain holds on clean text (this morning's configuration got 46 right on a comparable untouched set; today's 73); the trusted-route precision does not (0.885 on the over-consulted val_fresh2 vs 0.768 here): about a third of it was selection among many results on the same 200 questions. The B6 gate (validation precision after admission) did not pass, so B6 did not run.

## R25-af registration (a stronger baseline for the next-word claim)
An interpolated word-triple model (previous two words, backing off to the word-pair and single-word models; weights chosen on the training slice), same tokens, training text and held-out books. Compared with the learner's three-group model (R25-ae, 8.5344 alone) and mixed with it (weight on the training slice). Reported as is; the claim 'the learner's groups beat a standard word model' stands only if the groups (alone or as the larger share of a mix) beat the word-triple model.

## R25-af result (baseline under-tuned)
Word-triple model 9.0016 bits/token -- worse than the word-pair model (8.8078), with its backoff strength at the top of the grid (10): under-smoothed, not yet a fair strong baseline. Learner's three-group model 8.5344; word-triple mixed with the groups 8.2902 (best next-word score so far). No head-to-head claim until the baseline is tuned.

## R25-af2 (same registration, wider backoff grid for the baseline)
Word-triple backoff strength chosen from {10, 30, 100, 300, 1000, 3000} on the training slice; everything else unchanged.

## R25-af2 result (fair baseline)
Word-triple model properly tuned (backoff 300, inside the grid): 8.5648 bits/token. The learner's three-group model: **8.5344** -- better than a tuned standard word-triple model by 0.03 bits on 270,358 predictions, with far fewer parameters. Mixed: 8.2943 (-0.27 bits against the word-triple model alone): the groups carry information the word sequences lack.

## R25-ag registration (four groups of context)
The group model gains a four-group context (previous four groups, backed off to the three-group estimate, strength chosen on the training slice from {50, 200, 1000, 5000}); alone and mixed with the tuned word-triple model. Held-out books once. Passes if the mix falls below 8.2943.

## R25-ag result (PASS, diminishing)
Four groups of context: 8.5130 alone; mixed with the tuned word-triple model **8.2826** (from 8.2943). Context depth is nearly exhausted (about 0.01 bits per extra group).

## R25-c14 + R25-ah registration
Group refinement resumes on all training text from the 571 saved groups (2 exchange passes, 200 split tries; gate: held-out class-pair bits below 8.8361); then the next-word model of R25-ag is re-scored with the refined groups (gate: mix below 8.2826).

## R25-c14 + R25-ah results
Groups on all text from 572: exchange 8.8361 -> 8.8328 (pass 2 rejected); 61 of 200 splits kept -> 633 groups; held-out 8.8290. Next-word with the refined groups: four groups alone 8.5061, mixed **8.2822** (from 8.2826; a negligible 0.0004). The next-word line has converged for this method: word-pair 8.8078 -> learner's groups + tuned word-triple 8.2822.

## R25-ai registration (vectors from all 22M training words; one pre-registered comparison on a new untouched set)
The vectors so far use the 13M tokens the paragraph filter keeps; the training books hold 22.1M words. Vectors are rebuilt from every sentence of the training books (--all), same size (25,000 words, 4,000 contexts). A fifth hand-written set, val_fresh4 (200), is commissioned. Exactly two configurations are then scored once each on it: R25-x as is (13M vectors) and R25-x with the full-text vectors; route trust chosen on the 710 practice questions for both. Reported as is.

R25-ai: val_fresh4.json delivered and verified (40 stories, 200 questions, every gold form in its story). Full-text vectors built from 21.2M tokens (r25_vectors_all.npz). Now: model on all 1,310 (old, val_more, val_fresh2, A, B, val_fresh3, val_fresh4); configuration 1 = R25-x as is; configuration 2 = R25-x with R25_VEC=r25_vectors_all.npz; same role thresholds (0.8 / 0.5); trust chosen on the same 710 for each; val_fresh4 scored once per configuration.
R25-ai first attempt: both configurations crashed before scoring (my edit to r25_soft.py commented out the line that builds the word table); fixed and checked (25,000 words load); both configurations rerun, nothing else changed; the model's answers on the 1,310 are reused.

## R25-ai result (pre-registered comparison, val_fresh4 scored once per configuration)
Model on val_fresh4: 140 / 200. Configuration 1 (13M-token vectors): all routes 86 / 19; trusted 53 / 5, precision 0.914, fitness +38. Configuration 2 (vectors from all 21.2M training tokens): all routes 85 / 19; **trusted 57 / 5, precision 0.919, fitness +42** -- adopted (R25_VEC=r25_vectors_all.npz). Set-to-set variation is large: configuration 1 scored 43 / 13 (+4) on val_fresh3 and 53 / 5 (+38) here. Over the two clean sets, the learner alone answers about 80-85 of 200 right across all routes, and its trusted answers (about a quarter of the questions) are right about 85% of the time. B6 gate not met; no B6. (First attempt crashed on my own edit to r25_soft.py; the scorer then needed to tolerate accented names; the scored runs are the clean reruns.)

## R25-aj registration (vector size, one pre-registered comparison on a sixth untouched set)
Full-text vectors at 200 dimensions (r25_vectors_all200.npz) against the adopted 100. A sixth hand-written set, val_fresh5 (200), is commissioned. Exactly two configurations are scored once each on it: R25-x with R25_VEC=r25_vectors_all.npz and with R25_VEC=r25_vectors_all200.npz; role thresholds 0.8 / 0.5; trust chosen on the same 710.
R25-aj: val_fresh5.json delivered and verified (40 stories, 200 questions, every gold form in its story, ASCII names). Model on all 1,510; configuration A = R25_VEC=r25_vectors_all.npz (100 dims); configuration B = R25_VEC=r25_vectors_all200.npz (200 dims); trust on the 710; val_fresh5 scored once each.

## R25-aj result (pre-registered comparison, val_fresh5 scored once per configuration)
Model on val_fresh5: 133 / 200. 100 dims (adopted full-text vectors): all routes 77 / 28; **trusted 54 / 6, precision 0.900, fitness +36**. 200 dims: all routes 76 / 29; trusted 45 / 6, 0.882, +27 -- not adopted. Across the two latest clean sets (val_fresh4, val_fresh5) the adopted configuration's trusted answers are 111 right / 11 wrong (precision 0.91) on about 30% of questions; all routes about 80 of 200 right.

## R25-ak registration (action and time roles, one pre-registered comparison on a seventh untouched set)
Practice (710) silences: 'what did' 68, 'where was / were' 58, 'where did' 24, 'when did' 22. The action / complement roles (--do) and time phrases as arguments (--time-args) target the largest gap; they were last judged on an over-consulted or too-small set. A seventh hand-written set, val_fresh6 (200), is commissioned. Exactly two configurations are scored once each on it: the adopted configuration (full-text 100-dim vectors) as is, and with --do --time-args; trust chosen on the same 710 for each.
R25-ak: val_fresh6.json delivered and verified (40 stories, 200 questions, every gold form in its story). Model on all 1,710; configuration A = adopted (R25_VEC=r25_vectors_all.npz); B = A plus --do --time-args; trust on the 710; val_fresh6 (positions 1510-1710) scored once each.

## R25-ak result (pre-registered comparison, val_fresh6 scored once per configuration)
Model on val_fresh6: 136 / 200. A (adopted): all routes 83 / 12; trusted 54 / 3, 0.947, fitness +45. **B (adopted + action and time roles, --do --time-args): all routes 85 / 15; trusted 62 / 3, 0.954, fitness +53** -- adopted. Earlier negative verdicts on these roles rested on a too-small or over-consulted set and on trust chosen with less evidence.

## R25-al registration (the state role, one pre-registered comparison on an eighth untouched set)
Practice silences: 'where was / were' 58. The state role of R25-o2 (--state: places of the clauses about X, chosen by time words, else the latest) is retested with trust chosen on the 710. An eighth hand-written set, val_fresh7 (200), is commissioned. Exactly two configurations, scored once each: the adopted configuration (B above) and B plus --state.
R25-al: val_fresh7.json delivered and verified (40 stories, 200 questions, every gold form in its story). Model on all 1,910; configuration A = adopted (full-text vectors, --do --time-args); B = A plus --state; trust on the 710; val_fresh7 (positions 1710-1910) scored once each.

## R25-al result (pre-registered comparison, val_fresh7 scored once per configuration)
Model on val_fresh7: 135 / 200. A (adopted): all routes 70 / 20; trusted 49 / 2, 0.961, +43. **B (adopted + state role): all routes 74 / 18; trusted 51 / 2, 0.962, +45** -- adopted (a small margin).

## R25-am registration (the verb after 'did', one pre-registered comparison on a ninth untouched set)
Practice-only diagnosis of silent 'where did' / 'when did' questions: the question verb is not recognised ('sign', 'pack', 'stitch' read as nouns; 'Mrs Bello' gives two name slots; 'the heron watch' glues the verb onto a thing). With --did-verb the role reader reads the word after 'did' and its subject (the end of a run of name slots) as the verb, base form from the dictionary, or splits a dictionary verb off the end of a thing span; checked on four practice questions. A ninth hand-written set, val_fresh8 (200), is commissioned. Two configurations scored once each: adopted (full-text vectors, --do --time-args --state) and adopted + --did-verb.
**R25-am disclosure:** the brief for val_fresh8 asked the writer to include 'where did / when did' questions with everyday verbs such as pack, sign and stitch -- the verbs the fix targets. The test therefore leans toward configuration B; a win for B is weaker evidence than earlier pre-registered comparisons, and a loss for B would be strong evidence against it.
R25-am: val_fresh8.json delivered and verified (40 stories, 200 questions, every gold form in its story). Model on all 2,110; A = adopted; B = adopted + --did-verb; trust on the 710; val_fresh8 (positions 1910-2110) scored once each.

## R25-am result (pre-registered comparison, val_fresh8 scored once per configuration; set leaned toward B)
Model on val_fresh8: 141 / 200. A (adopted): all routes 76 / 19; trusted 48 / 7, 0.873, +27. B (adopted + --did-verb): all routes 77 / 19; trusted 49 / 7, 0.875, +28. Within noise even on a set whose brief leaned toward B; adopted under the rule (no cost, a true fact of English), recorded as neutral. The answers it unlocks come mostly through the role reader alone, a route the learner's trust rule does not use.

## R25-an registration (bug fix: name arguments in the role reader)
Practice-only trace: the role reader's argument match averaged only over question words that have a vector; names rarely have one, so for questions whose arguments are all names the average was empty (not a number) and every candidate lost -- e.g. 'What did Zainab hold for Ruben?' found the right clause (object 'a float') and returned nothing. This defect has been present since R25-k. Fix: an exact match counts 1.0 with or without vectors; a word without a vector counts 0 against a different word. Checked on three practice questions (now right). The old behaviour is kept behind --old-args for the comparison. A tenth hand-written set, val_fresh9 (200), is commissioned with a neutral brief. Two configurations scored once each: adopted with --old-args (as measured until now) and adopted with the fix.
R25-an: val_fresh9.json delivered and verified (40 stories, 200 questions, every gold form in its story; neutral brief). Model on all 2,310; A = adopted with --old-args (behaviour until now); B = adopted with the fix; trust on the 710; val_fresh9 (positions 2110-2310) scored once each.

## R25-an result (pre-registered comparison, val_fresh9 scored once per configuration)
Model on val_fresh9: 152 / 200. A (old argument match, with the empty-average behaviour): all routes 89 / 21; trusted 74 / 12, 0.860, +38. B (fixed): all routes 89 / 22; trusted 75 / 14, 0.843, +33. The fix lets the role reader answer name-only questions but those answers are not more often right: the old behaviour acted as a filter. Under the rule, A stays: the adopted configuration keeps --old-args (recorded as a known quirk that helps precision).

## R25-ao registration (the language model on the next-word game, matched)
Same lowercase word sentences from the held-out books, the first 3,000; words 2.. predicted from the earlier words of the same sentence; the model's cost for a word is the sum over its sub-word tokens (checkpoint ckpt_read1b, the one used throughout). The learner's next-word models (word-pair, groups, four-group + tuned word-triple mix) are re-scored on the same 3,000 sentences. Reported as is.

Owner, 2026-10-12: 'go ahead' with the five-step plan (LLM next-word measurement; copy memory and long-range associations; agent axis for who-questions; verb-sequence table; a small attention network over the learner's vectors). Item 5 read as approval to build and test.

## R25-ap registration (copy memory in the next-word game)
Paragraph scope: the base model (four groups + tuned word-triple, as R25-ag) keeps its short context; a copy memory gives each word already used earlier in the paragraph a probability in proportion to its use; mixed with weight from {0, 0.03, 0.06, 0.1, 0.15, 0.2} chosen on held-out training paragraphs. Held-out books' paragraphs scored once: base vs base + memory.

## R25-aq result (item 3, decided on practice)
Agent axis = principal direction 3 of the learner's vectors (people end: client, rector, engineer, physician, visitor, waiter, foreman; other end: threw, brought, struck, took, gave, carried). On the 710 practice questions, trusted routes: no cut-off 226 / 22 (+160); loosest 225 / 22; strictest tried 201 / 21. The learner chose no cut-off: its remaining wrong 'who' answers are the wrong person, not the wrong kind of word. No untouched set is spent on it.

## R25-ap result (PASS)
Held-out paragraphs, 270,358 predictions: base (four groups + tuned word-triple) 8.2798 bits/word; with copy memory **8.2022** (weight 0.03, chosen inside the grid on training paragraphs). Words already used in the story are worth about 0.08 bits/word, with counts only.

## R25-ar registration (item 5: a small attention network over the learner's vectors)
Two-layer causal self-attention (128 wide, 4 heads, context 64 words of the paragraph; about 5.0M parameters), embeddings initialised from r25_vectors_all.npz and tuned; trained 75 minutes on the CPU on the training paragraphs; scored on the same 270,358 held-out predictions as R25-ap (words outside its 20,000-word vocabulary charged their share of the unknown mass). Reported against the count models (8.2022 with copy memory) and the language model (R25-ao).

## Item 4 redirected (practice-only analysis)
Of 710 practice questions, 62 mention order or cause; 43 are silent, 15 right, 4 wrong. The silent ones track a thing or person through the story's own events ('Where was the umbrella at the end?', 'Who had the roll after Petra?', 'Where was the half roll before the dog took it?'). World verb sequences from the books cannot answer these; the story's own timeline can. The learned world layers (holder rules: take / steal / find hold, drop / leave / put release, give passes; place memory) already track it but answer only when a reader agrees.

## R25-as registration (the world layers alone, judged with 710-question trust, on the eleventh untouched set)
val_fresh10.json delivered and verified (40 stories, 200 questions, every gold form in its story; neutral brief). Two configurations scored once each on it (positions 2310-2510): adopted (full-text vectors, --do --time-args --state --did-verb --old-args) and adopted + --state-alone (the world layers answer on their own; trust chosen on the 710). Started after the R25-ar training to avoid processor contention.

## R25-ao result (matched next-word comparison)
Same lowercase word sentences, first 3,000 held-out sentences, 47,478 predictions, sentence scope: **language model 7.6694 bits/word**; learner's best (four groups + tuned word-triple) **8.7663**; word-pair 9.2137; learner's groups alone 9.2211. Gap 1.10 bits/word (the model narrows each next word to about half as many candidates). This subset is harder than the full held-out set (learner 8.77 here vs 8.28 overall).

## R25-ar result (attention network, 75 minutes)
Two-layer causal attention over the learner's vectors, 4,998,149 parameters, 7,765 steps (about 1.2 passes over the training paragraphs), training loss still falling: **held-out paragraphs 8.0587 bits/word** over the same 270,358 predictions -- better than the best count model (8.2022 with copy memory) by 0.14. The language model's 7.67 was measured on a different subset at sentence scope; not yet comparable.

## R25-ar2 registration (continued training, detached)
Resume from r25_attn.pt (75-minute weights kept as r25_attn_75min.pt), train 4 more hours as a detached process with checkpoints every 500 steps, then score the same 270,358 held-out paragraph predictions; afterwards score it on the language model's 47,478 sentence-scope predictions for a three-way comparison.

## R25-as result (item 4: world layers alone -- negative)
Model on val_fresh10: 148 / 200. A (adopted) and B (adopted + world layers alone) score identically on val_fresh10 (all routes 67 / 22; trusted 50 / 6, 0.893, +32): the world-layer route never fired there. Elsewhere it is mostly wrong: practice 17 answered, 5 right / 12 wrong; earlier untouched sets 23 answered, 6 right / 17 wrong. The learner's trust rule refused it, correctly. The world layers were learned from the generator's tidy events and read hand-written stories poorly; 'where was X at the end' and 'who had X after' need a new learned state tracker, not these layers.

## R25-at registration (three-way next-word comparison)
The attention network, at its 75-minute weights and at the end of R25-ar2, is scored on exactly the language model's predictions of R25-ao (first 3,000 held-out sentences, sentence scope, 47,478 predictions; long sentences use the last 63 words as context). Compared with the language model (7.6694) and the learner's count models (8.7663) on the same predictions.

## R25-ar2 result (continued training)
18,630 steps in all (about 2.9 passes): **held-out paragraphs 7.8042 bits/word** over the 270,358 predictions (75 minutes: 8.0587; best count model with copy memory: 8.2022). Still falling. Weights kept as r25_attn_ar2.pt.

## R25-at result (three-way next-word comparison, same 47,478 predictions, sentence scope)
| model | bits/word |
|---|---|
| language model (RWKV-7, 0.4B) | 7.6694 |
| attention network, 4 h 15 min (5.0M) | 8.3858 |
| attention network, 75 min | 8.5929 |
| learner's count models | 8.7663 |
The gap to the language model fell from 1.10 to 0.72 bits/word, with about 80 times fewer parameters.

## R25-ar3 registration (third round of training, detached)
Resume from r25_attn.pt, train 4 more hours (same data, settings, checkpoints every 500 steps), then score the 270,358 held-out paragraph predictions and the 47,478 matched predictions. Pass if held-out paragraphs fall below 7.8042; also report the matched score against 7.6694.

## Correction to R25-ar2
The step counter restarts on every resume. R25-ar2 trained 18,630 steps on top of R25-ar's 7,765: 26,395 steps in all (about 4.1 passes over the 13.0M training tokens), not "18,630 in all, about 2.9 passes".

## R25-ar3 result (third round) -- PASS
25,067 more steps (51,462 in all, about 8 passes): **held-out paragraphs 7.7313 bits/word** (R25-ar2 7.8042; gate < 7.8042, pass). Matched predictions: **8.3135** (language model 7.6694; gap 0.64, was 0.72). Gains are slowing: about 0.075 bits per doubling of training, down from about 0.16. At that rate the gap would need about 8 more doublings, so more of the same training will not close it; more text and a larger network are the levers.

## R25-au registration (mixing)
r25_mix.py: per held-out paragraph prediction, mix the R25-ar3 network with the R25-ap model (count models + copy memory); the mixing weight is chosen on the first half of the held-out paragraphs and reported on the second half only, with each model alone on the same half. Pass if the mix beats the network alone on the second half.

## R25-au result (mixing) -- PASS
Second half of the held-out paragraphs, 122,818 predictions: attention network alone 7.4566; count models + copy memory 7.9477; **mix 7.3647 bits/word** (attention weight 0.75, chosen on the first half; copy-memory weight 0.03). The counting models still add information the network has not learned (-0.09 bits/word).

## R25-av registration (more text and a larger network)
r25_attn.py gains --all-text (every paragraph of the training books, 21.2M tokens / 354,551 paragraphs, instead of the filtered 13.0M), --width, --layers, --out. New network: width 256, 4 layers, 10.3M parameters, same vectors as starting embeddings, same held-out predictions. Trained 8 hours detached from scratch (weights r25_attn_av.pt). Gate: held-out paragraphs below 7.7313 (the 5.0M network after about 10.5 hours on the filtered text). Then scored on the 47,478 matched predictions against the language model's 7.6694.

## R25-av stopped (owner's order)
The 10.3M-parameter attention run had already stopped by itself at step 800 (no process left; the log ends at 1,051 s). Not restarted: the owner replaced it with R25-aw.

## R25-aw registration (brain-like network: running state + small sparse look-up)
r25_rnn.py. Two GRU layers of width 128 read the words in order (the running state); the look-up lets the current state fetch only the 4 best-matching earlier moments of the paragraph by one similarity match and adds what it fetched. 4,857,605 parameters (attention network 4,998,149). Same starting vectors, same filtered 13.0M training tokens, same windows of 64 words, batch, optimiser and unknown-word charge; about the same speed (about 1.8 steps per second on 6 threads in a probe). Held-out paragraphs are read whole (most paragraphs are under 64 words, so the attention network's windows rarely cut context).
Runs, one after the other, detached, 75 minutes each, 6 threads:
- A: running state + look-up of 4 (r25_rnn_k4.pt)
- B: running state alone (r25_rnn_k0.pt)
Compared with the attention network after 75 minutes: held-out paragraphs 8.0587, matched predictions 8.5929 (language model 7.6694).
Verdicts: the brain-like design PASSES if A is at or below 8.0587 on held-out paragraphs. The look-up PASSES if A beats B. Both also reported on the matched predictions.

## R25-aw result A (running state + look-up of 4) -- brain-like design PASS
7,748 steps in 75 minutes (attention network: 7,765). **Held-out paragraphs 7.9758 bits/word** (attention network at 75 minutes 8.0587; gate at or below 8.0587: pass). **Matched predictions 8.5098** (attention 8.5929; language model 7.6694). Run B (running state alone) in progress.

## R25-aw result B (running state alone) -- look-up FAILS
8,288 steps in 75 minutes (faster: no look-up). **Held-out paragraphs 7.9545** (A with look-up 7.9758; attention 8.0587). **Matched 8.5100** (A 8.5098). The look-up does not beat the running state alone (gate: A beats B -- fail). B had 7% more steps, so at equal steps the two are about even; either way the look-up adds nothing measurable to next-word prediction. The running state alone also beats the attention network at equal time (7.9545 vs 8.0587).
Reading: next words depend mostly on recent words, which the running state already holds. If the look-up matters, it should show on questions that need an exact earlier detail, not on next-word bits.

## R25-ax registration (running state alone, longer)
Resume r25_rnn_k0.pt for 180 more minutes (255 in all, the attention network's R25-ar + R25-ar2 budget), same settings, detached. Compared with the attention network at the same budget: held-out paragraphs 7.8042, matched 8.3858. Pass if at or below 7.8042.

## R25-ax result -- PASS
21,117 more steps (29,405 in all; attention network at the same budget 26,395). **Held-out paragraphs 7.7894** (attention 7.8042; gate at or below 7.8042: pass). **Matched 8.3955** (attention 8.3858; language model 7.6694): even on the matched set. The running state alone matches attention at equal time and size.

## R25-ay registration (running state alone, third round)
Resume r25_rnn_k0.pt for 240 more minutes (495 in all, the attention network's R25-ar3 budget), same settings, detached. Compared with the attention network at the same budget: held-out paragraphs 7.7313, matched 8.3135. Pass if at or below 7.7313.

## R25-ay interrupted and resumed
The PC disconnected at 12:03 (step 17,400 of the round, 10,515 s of 14,400). The last checkpoint was step 17,000 (10,288 s). Resumed from it for the remaining 69 minutes (run_ay2.ps1, log r25_run_ay2.txt); the optimiser state restarts, as at every earlier resume. Gate unchanged: held-out paragraphs at or below 7.7313.

## R25-ay result (running state alone, third round) -- FAIL
After the interruption the round got 22,527 steps (attention's third round: 25,067), with two optimiser restarts. **Held-out paragraphs 7.7972** (gate at or below 7.7313: fail; its own previous round 7.7894, so no gain). **Matched 8.4000** (attention after its third round 8.3135). The running state tied attention at 255 minutes but stalled after that, while attention kept improving. Possible causes, not separated: the running state overfits the 13.0M tokens sooner (about 8 passes now), or the repeated restarts at full learning rate undo progress.

## R25-az registration (learning-rate decay on both, equal time)
Neither network has ever had its learning rate lowered; both restarted at 1e-3 on every resume. Both final weights (attention r25_attn_ar3.pt, running state r25_rnn_k0_495min.pt) get 45 more minutes with the learning rate falling linearly to zero (--decay), run one after the other on 6 threads, writing r25_attn_az.pt and r25_rnn_az.pt. Compared on held-out paragraphs (attention scored by r25_attn.py, running state by r25_rnn.py, same 270,358 predictions) and the matched 47,478 predictions (r25_attn_eval.py for attention). Reported as is: whether decay helps each, and which design leads after it.

## R25-az result (learning-rate decay, 45 minutes each)
| network | held-out paragraphs | matched predictions |
|---|---|---|
| attention, before / after decay | 7.7313 / **7.6906** | 8.3135 / **8.2942** |
| running state, before / after decay | 7.7972 / **7.7852** | 8.4000 / 8.4174 |
Decay helps attention clearly (-0.04) and the running state barely (-0.01 held-out, +0.02 worse on the matched set). Attention leads by 0.09 on held-out paragraphs. The running state's stall is not mainly the missing decay.

## R25-ba registration (diagnosis of the stall, no training)
r25_diag.py scores every saved checkpoint of both networks on two fixed samples: 2,000 training paragraphs and 2,000 held-out paragraphs, each cut to its first 64 words (deterministic, one thread). Reading, fixed in advance: if the running state's training bits keep falling across checkpoints while its held-out bits stop, the stall is overfitting (too little text for it); if its training bits also stop, it is a capacity limit (state too small); attention is the reference.

## R25-ba result (diagnosis) -- the running state's limit is capacity, not memorising
| checkpoint | training sample | held-out sample | gap |
|---|---|---|---|
| running state 75 min | 7.1940 | 8.2302 | 1.04 |
| running state 255 min | 6.9174 | 8.1043 | 1.19 |
| running state mid round 3 | 6.8534 | 8.0897 | 1.24 |
| running state end round 3 | 6.8683 | 8.1063 | 1.24 |
| running state after decay | 6.8088 | 8.1048 | 1.30 |
| attention 75 min | 7.3189 | 8.3150 | 1.00 |
| attention 255 min | 6.9300 | 8.1065 | 1.18 |
| attention end round 3 | 6.7728 | 8.0332 | 1.26 |
| attention after decay | 6.7056 | 7.9974 | 1.29 |
Both networks' gaps grow at the same rate, so the running state does not memorise more than attention. The difference is that after 255 minutes the running state's training score nearly stops (6.92 to 6.81) while attention's keeps falling (6.93 to 6.71); held-out follows training in both. By the reading fixed in advance: a capacity limit -- the 128-number state cannot hold more. Also visible: the restart after the disconnect made the running state slightly worse on both samples (6.85 to 6.87, 8.09 to 8.11).

## R25-bb registration (a wider running state)
r25_rnn.py gains --hidden (GRU state width, projected back to 128 before the output) and --steps (a fixed step budget instead of minutes, for repeatability). Run: state width 384, look-up off, from scratch, exactly 8,288 steps (what the 128-wide state did in its first 75 minutes), 6 threads, detached; 6,187,909 parameters (128-wide: 4,857,605). PASS if held-out paragraphs fall below 7.9545 (the 128-wide state at the same steps). If it passes, it continues with the same schedule as before, to test whether the stall moves later.

## R25-bc / R25-bd measurement (where the next-word bits go)
Four-group model, first 3,000 held-out paragraphs, 168,995 predictions. With the learner's 634 groups: which kind of word 6.631 bits, which word of that kind 2.162 (total 8.793). With the groups merged into 30 grammar-sized classes (k-means on group mean vectors; r25_classes_coarse.json): which kind of word 4.090, which word of that kind 5.838 (total 9.928). Grammar-sized choice is about 40% of the cost; content about 60%.

## R25-bb stopped (owner: skip the memory test; minutes-scale tests from now on, multi-hour runs go to Colab)

## R25-be registration (the network predicts groups; a count table picks the word)
r25_rnn.py --groups: the running state (128 wide, look-up off) predicts which of the learner's 634 groups comes next (plus one group for words without a group and one for unknown words); P(word) = P(group) x the word's training count share inside its group. 2,359,391 parameters (word-output version 4,857,605); about 3 times as many steps per second. From scratch, single runs, scored on the first 1,000 held-out paragraphs (--fast: no matched set):
- A: word output, 2,000 steps
- B: group output, 2,000 steps (equal steps)
- C: group output, 6,000 steps (about A's time)
PASS if C beats A (the factorisation wins at equal time). B vs A shows whether it wins per step too.

## R25-bf registration (word groups seeded from the WordNet dictionary)
r25_wn_groups.py: each word's main WordNet class (most-tagged part of speech, its most frequent sense's lexicographer file, e.g. noun.food, verb.motion); the 300 most frequent words and words WordNet lacks keep their learned group. Two group sets: dictionary-seeded (r25_classes_wn.json, 461 groups) and learned x dictionary intersection (r25_classes_wnx.json, 6,072 groups). Same group-output network as R25-be B (2,000 steps, first 1,000 held-out paragraphs, --fast), run locally in parallel with fixed steps (the Colab upload was refused by the session's safety check). Compared with R25-be B (learned 634 groups). PASS for either if it beats B.

## R25-bf result (dictionary-seeded groups), with R25-be A and B
2,000 steps each, first 1,000 held-out paragraphs (50,114 predictions):
| network output | bits/word | time |
|---|---|---|
| words (R25-be A) | 8.7392 | 1,214 s |
| learned 634 groups (R25-be B) | 8.8071 | 384 s |
| dictionary-seeded 461 groups | 8.9901 | 455 s (shared processor) |
| learned x dictionary 6,072 groups | **8.7437** | 958 s (shared processor) |
Dictionary classes replacing the learned groups: FAIL (+0.18). Dictionary classes splitting the learned groups: PASS (-0.06 vs B), equal to word output per step. The dictionary helps as a refinement of what the learner found, not as a replacement.

## R25-be result C -- PASS
Group output, 6,000 steps: **8.6436** bits/word in 1,188 s, against word output 8.7392 in 1,214 s (A). At equal time the network that predicts groups, with a count table picking the word, wins by 0.10 bits/word with half the weights.

## R25-bg registration (best of both: learned x dictionary groups at about equal time)
Group output with r25_classes_wnx.json, 4,000 steps, 6 threads, same scoring. Compared with C (8.6436, 1,188 s); time reported. PASS if lower bits in no more time than C.

## R25-bh registration (quick win, no training: blend the trained networks and the count models)
r25_ens.py: word-output network (2,000 steps), group-output network (6,000 steps), learned x dictionary group network (2,000 steps), count models + copy memory. Probability blends with weights on a 0.1 grid chosen on held-out paragraphs 0-499 and reported on 500-999 only. PASS if any blend beats the best single model on 500-999.

## R25-bh result (blends, no training) -- PASS
Held-out paragraphs 500-999 (weights chosen on 0-499): alone W 8.4002, G 8.3011, X 8.4118, counts+copy C 8.4211. Blends: G+X 8.2450; W+G+X 8.2180; G+X+C 8.1095; **W+G+X+C 8.0967** (weights W 0.2, G 0.4, C 0.4). The blend beats the best single model by 0.20 bits/word with no training: the networks and the count models make different mistakes.

## R25-bg result (learned x dictionary groups, 4,000 steps)
**8.5947** bits/word in 1,533 s (learned groups, 6,000 steps: 8.6436 in 1,188 s). Lower bits: pass on quality. The time gate is not judged: the processor was shared with R25-bh for most of the run.

## R25-bi registration (blend with the better dictionary network)
r25_ens.py r25_bg.pt: the R25-bh blend with X = the 4,000-step learned x dictionary network. Same halves. Compared with R25-bh's best blend 8.0967.

## R25-bi result (blend with the 4,000-step dictionary network)
Alone X 8.3084 (was 8.4118). Best blend W+G+X+C **8.0814** (weights 0.1/0.2/0.3/0.4; R25-bh 8.0967): -0.015.

## R25-bj registration (rare words predicted through their own group)
The group network's output no longer needs the 20,000-word input vocabulary: a word outside it that has a learned group (41,195 words have one) is predicted as P(its group) x its count share in the group, in training targets and in scoring; only words with no group stay in the unknown bucket (charged their share among those words). r25_rnn.py --groups --oov-groups, learned groups, 6,000 steps, 6 threads, first 1,000 held-out paragraphs. Compared with R25-be C (8.6436, same settings without the change). PASS if lower.

## R25-bk registration (read whole stretches of books: the state carries across paragraphs)
r25_chapter.py: group-output running state (learned groups, rare words through their group), training paragraphs in book order joined into one stream, 32 parallel streams read 64-word window by window, 6,000 steps each.
- A (--reset): state empty at every window in training, at every paragraph in scoring (paragraph scope).
- B: state carried from window to window in training (gradients stop at window edges) and through all 1,000 scored held-out paragraphs in book order.
Same 50,114 predictions as R25-be/bj. PASS if B beats A. Runs alongside R25-bj (fixed steps, so sharing the processor changes only the time).

## R25-bj result (rare words through their own group) -- FAIL
**8.6487** bits/word (R25-be C without the change 8.6436): no gain (+0.005, within run-to-run noise). The unknown-word charge already priced rare words about as well as their groups do. Not adopted for the blend; R25-bk keeps it on (registered before this result), so its A/B is unaffected.

## R25-bk result (book-scope reading) -- PASS
A reset (paragraph scope) **8.6295**; B carried through the book **8.5987** (-0.031), same 50,114 predictions, about 985 s each on a shared processor. Carrying the state across paragraphs helps, modestly.

## R25-bl registration (book-scope reading with learned x dictionary groups)
r25_chapter.py --groups-file r25_classes_wnx.json, carried state, 6,000 steps. Compared with R25-bk B (8.5987) and the best paragraph-scope network R25-bg (8.5947, 4,000 steps). PASS if below both.

## R25-bm registration (gradient-free running state: reservoir + closed-form output; owner's priority)
r25_reservoir.py: fixed seeded random recurrent state 1,024 wide reading the first 4,000,000 training tokens in book order (32 streams); output fitted once by ridge regression to the next word's group; ridge strength and softmax scale chosen on the last 5% of the training streams; word = group x count share, unknown words as in the group networks. Scored on the first 1,000 held-out paragraphs, state carried (as R25-bk B). Probe (256 wide, 200,000 tokens): 10.68 bits/word. Compared with the gradient-trained book-scope network R25-bk B (8.5987) and reported with its time. Reported as is.

## R25-bm result (gradient-free reservoir) -- far behind
1,024 wide, 4,000,000 training tokens, 1,183 s: **10.4855** bits/word (gradient-trained book-scope network 8.5987). The closed-form ridge output predicts groups worse than plain group counts (8.18 bits per group on its held-in slice; the four-group count model spends 6.6): a fixed random memory plus a linear least-squares output does not give usable probabilities here.

## R25-bn registration (spectral hidden-state model, no gradients)
r25_spectral.py, k = 64: counts of groups, group pairs and triples over the training paragraphs; the Hsu-Kakade-Zhang spectral construction; clipped and renormalised predictions mixed 0.99/0.01 with group frequencies; word = group x count share. Paragraph scope, the same 50,114 predictions. Compared with the gradient-trained paragraph-scope group network (R25-bk A 8.6295) and the reservoir. Reported as is.

## R25-bo registration (sequence memoizer, approximated deterministically)
The sequence memoizer's own inference is stochastic (Monte Carlo); its fixed-depth deterministic approximation is interpolated Kneser-Ney (Teh 2006). r25_kn.py: word Kneser-Ney up to 4 words, continuation counts, per-order discounts, 65,534 own-id words plus a shared rare id split by counts. Same 50,114 predictions. Compared with the count four-group model + copy (C: 8.4211 on paragraphs 500-999) and the best single network (G: 8.3011). Probabilities saved for R25-bp.

## R25-bp (to register after R25-bo): context mixing -- PAQ-style weights selected by a context (how deep the Kneser-Ney match went), over all components.

## R25-bn result (spectral hidden-state model, k = 64) -- behind
After fixing a shape error in the first run (no result), **9.8256** bits/word in 577 s, no gradients (gradient-trained paragraph-scope group network 8.6295; reservoir 10.4855). Better than the reservoir, well behind training. Likely causes, not separated: 64 hidden dimensions, clipped negative estimates, and only group triples as evidence.

## R25-bo result (Kneser-Ney, the memoizer's deterministic form)
13.8M training tokens, built and scored in 26 s: **8.5120** on paragraphs 500-999 (8.7626 on all 1,000). Behind the count four-group model + copy (8.4211) and the best network (8.3011) alone; its value is as a mixing component (R25-bp, running).

## R25-bp result (context mixing) -- PASS
Paragraphs 500-999: alone W 8.4002, G 8.3011, X 8.3084, C 8.4211, Kneser-Ney K 8.5120. One global blend with K: **7.9954** (without K, R25-bi: 8.0814). Weights selected by Kneser-Ney match depth: **7.9876**. Adding the memoizer-style counts is worth -0.09; depth-selected weights add -0.008 more. First result under 8 bits/word.

## R25-bl result (book-scope reading + learned x dictionary groups) -- PASS
**8.4507** bits/word on all 1,000 paragraphs (book scope with learned groups 8.5987; best paragraph-scope network 8.5947). The two gains compound: -0.15.

## R25-bq registration (book-scope network into the mix)
The weights of R25-bl were not saved; r25_chapter.py gains --save. Re-run R25-bl exactly (same seed, 6,000 steps) with --save, then r25_cm.py with it as component B. Compared with R25-bp 7.9876.

## R25-bq result (book-scope network in the mix) -- PASS
The re-run reproduced R25-bl exactly (8.4507: the runs are deterministic). On paragraphs 500-999 the book-scope network alone is **8.1568**, the best single model. Global blend 7.9352; weights by Kneser-Ney depth **7.9227** (R25-bp 7.9876).

## R25-br registration (book-wide copy memory as a component)
r25_bookcopy.py: probability of reusing an earlier word of the book (all earlier held-out paragraphs in order, weight 0.999^distance). Added to r25_cm.py with B as component Y. Compared with R25-bq 7.9227.

## R25-br result (book-wide copy memory) -- PASS, large
86.7% of next words already appeared earlier in the held-out text. Copy memory alone is useless (12.02) but in the mix: global **7.6689**, by depth **7.6650** (R25-bq 7.9227): -0.26 bits/word, the largest single gain today. (The memory reads earlier held-out text only, in order, as a reader would; the mixing weights come from paragraphs 0-499.) Not comparable with the language model's 7.6694, which was measured at sentence scope on a different subset.

## R25-bs registration (copy memory decay)
Same mix with the copy memory's decay at 0.99 (short memory) and 0.9999 (long memory) instead of 0.999; one run each; reported as is.

## R25-bs result (copy memory decay)
Decay 0.99 (about the last 100 words): **7.6435**; 0.999: 7.6650; 0.9999: 7.7257. Shorter memory is better.

## R25-bt registration (two copy memories, and a shorter one)
(a) decay 0.97 alone as Y; (b) two copy memories at once, 0.99 and 0.999, with the word network W dropped (weight 0 in every blend so far) to keep the weight grid small. Compared with R25-bs 7.6435.

## R25-bt result
(a) decay 0.97: 7.6753 (worse). (b) two copy memories 0.99 + 0.999, W dropped: **7.6361** (-0.007 vs 7.6435). Diminishing returns from copy memories.

## R25-bu registration (train the best network longer)
Book-scope, learned x dictionary groups (R25-bl configuration), 12,000 steps instead of 6,000, saved as r25_bu; then mixed as B. Compared with R25-bl 8.4507 alone and R25-bt 7.6361 mixed.

## R25-bv registration (PAQ-style online mixing weights)
r25_cm.py with R25_ONLINE=1: start from the depth weights (floored at 0.02), then after every prediction multiply each component's weight by (its probability / the mix's)^eta and renormalise, per depth; eta from {0.005, 0.02, 0.05, 0.1} chosen on paragraphs 0-499, weights carried into 500-999. Uses only past predictions, like PAQ. Compared with R25-bt 7.6361 (same components).

## R25-bv result (online mixing) -- FAIL
**8.1521** (static depth weights 7.6361); eta chose the smallest value offered (0.005), i.e. less updating was always better. Likely cause: the copy memories give near-zero probability to every word not seen yet, so each such word shrinks their weight multiplicatively and the update erodes the most useful components. Not pursued; static depth-selected weights stay.

## R25-bw registration (fast count variants, about a minute each)
r25_kn2.py generalises R25-bo (hashed n-grams, any order); its order-4 run reproduces R25-bo (8.5119 vs 8.5120 on paragraphs 500-999). Variants, each scored once on the same predictions: o4m (modified Kneser-Ney, 3 discounts), o5m, o6m (longer phrases), o5mx (context crosses sentence boundaries in the paragraph), o5ma (all 21M training tokens), o5mxa (both). Reported alone; the best goes into the mix as K.

## R25-bw result (fast count variants), paragraphs 500-999
o4 8.5119 -> o4m (modified KN) 8.4600 -> o5m 8.4537 -> o6m 8.4493; o5mx (across sentences) 8.4035; o5ma (21M tokens) 8.4011; **o5mxa 8.3580** in 128 s -- the counts alone now beat the four-group count model (8.4211) and approach the networks (8.30). Gains: modified discounts -0.05, context across sentences -0.05, more text -0.05, longer phrases small.

## R25-bx registration (best counts into the mix)
r25_cm.py with K = o5mxa (and its match depth as the mixing context), components as R25-bt. Compared with 7.6361.

## R25-bx result (best counts in the mix) -- PASS
K = o5mxa alone 8.3580; mix global 7.6190, by depth **7.6188** (R25-bt 7.6361).

## R25-by measurement (where the best mix loses bits; paragraphs 500-999, 11,812 predictions)
Content words: 32% of predictions, 50% of bits, 11.8 bits each; the 300 most frequent words: 68%, 50%, 5.6 each. Frequency bands: words seen 10,000+ times in training take 41% of bits (5.3 each); 1,000-9,999: 25% (9.0); 100-999: 20% (12.2); rarer: 13%. Words not yet used in this text: 6.6% of predictions, 14% of bits (16.1 each). Position in the sentence makes almost no difference (7.5-7.9). Reading: half the loss is in choosing among very common words (grammar-like choices such as the / a / his), the other half in content words.

## R25-bz registration (skip-phrase counts: the word just before the target is skipped)
r25_kn2.py --skip: the context is the 1-4 words before the previous one (for example "the ___ dog" counts toward "the old dog" and "the big dog"); modified Kneser-Ney, across sentences, all text, order 5. Added to the mix as a further component S. Compared with R25-bx 7.6188.

## R25-bz result (skip-phrase counts) -- FAIL
The edited counter still reproduces R25-bo (8.5119). Skip counts alone 9.6959; the mix gives them weight 0 (7.6193 vs 7.6188). Skipping the word right before the target throws away too much here.

## R25-bu interrupted
The 12,000-step book-scope run stopped silently after step 1,500 at 23:23 (no error in its log; it ran alongside the 21M-token count builds, likely memory pressure). Restarted alone, unchanged.

## R25-ca registration (the learner derives its own counting rules -- first rung of a rule-discovery engine)
Owner, 2026-10-14: give the system flexible primitive operators and time to derive rules from the corpus itself, starting with what Chen and Goodman found by hand. r25_discover.py gives primitives only (count patterns; compare with held-out training text; bucket by count; two backoff kinds; score on held-out training text) and no discount formula. The learner measures per length and bucket how much counts over-state future use, chooses the number of buckets and the backoff kind by its score on a held-out training slice, then rebuilds on all training text and is scored once on paragraphs 500-999. Order 4, same text as R25-bw. PASS if at or below plain Kneser-Ney (8.5119); reported against Chen-Goodman (8.4600).
Later rungs (to register): more primitive families (pattern shapes with gaps, word groups as context, copy and position features, mixing by context) searched under a time budget, every kept rule scored on held-out training text only, the library of kept rules persisting across runs.

## R25-ca result (self-derived counting rules) -- PASS
Given only primitives, the learner chose backoff by the number of distinct words before a pattern (Kneser-Ney's idea; raw-count backoff was 0.2 bits worse on its held-out slice in every setting) and two count buckets with its own measured discounts per length (length 4: 0.92 for once-seen, 1.44 for twice or more; length 1: 0.0 / 0.89). Paragraphs 500-999: **8.4812** -- better than plain Kneser-Ney (8.5119), 0.02 short of the hand-derived Chen-Goodman formula (8.4600). The two main ideas of modern count smoothing were re-derived from the corpus.

## R25-cb registration (rung 2: search over context shapes)
r25_discover2.py: the same primitives plus context shapes -- previous words (lengths 1-5, within and across sentences), previous learned groups (634), previous learned x dictionary groups, previous word endings (last two letters) -- each built as a self-derived count model (R25-ca procedure). Greedy forward selection: start with the best single shape, add the shape that most lowers bits of an equal-weight-searched mixture on held-out training text, stop when nothing helps by 0.005. The chosen mixture is rebuilt on all training text and scored once on paragraphs 500-999, against the same-text word model across sentences (o5mx 8.4035; 13.0M tokens, to keep memory low while R25-bu trains).

## R25-cb result (rung 2: the learner searches context shapes) -- PASS
Held-out training slice, single shapes: words within sentences 8.5279, words across sentences 8.5364, dictionary-split groups 8.5940, groups 8.7172, dictionary classes 8.8068, word endings 9.3752. Greedy selection kept words + dictionary classes (8.3928) + learned groups (8.3667) and stopped (dictionary-split groups added only 0.002). Paragraphs 500-999: **8.3469** (same-text word model across sentences 8.4035; it also beats o5mxa, 8.3580, which counted 21M tokens). The learner found that coarse class contexts (dictionary classes, learned groups) complement exact words, a class-backoff rule it was not given.

## R25-cc registration (self-searched counts into the best mix)
r25_cm.py with K = o5mxa (depth context) plus the R25-cb mixture as component Q, components as R25-bx. Compared with 7.6188.

## R25-cc result
Q alone 8.3469; global blend gives it weight 0 (7.6190), depth-selected mixing 7.6137 (-0.005 vs 7.6188): in the full mix it overlaps with K. Its value is as a self-built replacement for hand-built counters, not an extra.

## R25-bu result (best network trained twice as long) -- PASS
12,000 steps: **8.3708** on all 1,000 paragraphs (6,000 steps 8.4507); alone on 500-999 8.0693 (was 8.1568). Mix with K = o5mxa, both copy memories and Q: global 7.5809, by depth **7.5721** (R25-cc 7.6137).

## R25-ce registration (rung 3: a new primitive family -- long-range word associations)
r25_trigger.py: content-word pairs within 30 words in training paragraphs give P(w | earlier content word c); the component averages over the content words among the previous 30 words of the held-out text. Added to the R25-bu mix as R. Compared with 7.5721.

## R25-ce result (trigger associations) -- FAIL
36M pair occurrences, built in 9 s; nonzero for 32.5% of predictions; alone useless (32.09). In the mix it gets weight 0 on the 0.1 grid (7.5727 vs 7.5721); a fine weight chosen on 0-499 (0.005) gives 7.5717 on 500-999 (-0.0004). Averaging association probabilities into a linear mix cannot use them: an association should multiply the odds of related words, which needs a multiplicative (normalised) combiner -- the operator family to add next.

## R25-cf registration (rung 2 on all 21M training tokens)
r25_discover2.py --all-text: the same shape search and learned rules, counting all training paragraphs. Alone compared with R25-cb (8.3469) and o5mxa (8.3580); then in the R25-bu mix as Q. Compared with 7.5721.

## R25-cf result (shape search on 21M tokens) -- PASS alone, small in the mix
Learner kept words across sentences, dictionary classes, groups, words within sentences. Paragraphs 500-999 alone **8.2933** (13M: 8.3469; o5mxa 8.3580). Mix: by depth **7.5699** (7.5721), with Q taking weight 0.3 and K dropping to 0.1: the self-searched counter replaces the hand-built one.

## R25-cg registration (best network, 12,000 more steps)
r25_chapter.py --init r25_bu.pt: continue the 12,000-step book-scope network for 12,000 more (24,000 in all; fresh optimiser state, as at every resume), saved as r25_cg; then the R25-cf mix with it as B. About 70 minutes alone. Compared with R25-bu alone 8.3708 (all 1,000) and the mix 7.5699.

## R25-cg result (best network, 24,000 steps) -- PASS
All 1,000 paragraphs **8.3189** (12,000 steps 8.3708); alone on 500-999 8.0246 (8.0693). Mix by depth **7.5509** (7.5699). (Finished about 03:00; reported late.)

## R25-ch registration (12,000 more steps: 36,000 in all)
Same procedure from r25_cg.pt, saved as r25_ch, then the same mix. Compared with 8.3189 alone and 7.5509 mixed.

## R25-ch result (36,000 steps)
All 1,000 paragraphs **8.2963** (24,000: 8.3189); alone on 500-999 8.0096; mix **7.5430** (7.5509). Gains per 12,000 steps are shrinking (-0.08, -0.05, -0.02): the capacity limit diagnosed in R25-ba again.

## R25-ci registration (wider running state in the best configuration)
Book scope, learned x dictionary groups, group output, state 256 wide projected to 128 (--hidden 256), 6,000 steps from scratch, saved as r25_ci. Compared at equal steps with R25-bl (128 wide, 8.4507), time reported.
