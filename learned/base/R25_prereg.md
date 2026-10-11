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
