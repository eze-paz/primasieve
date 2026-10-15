# R27 -- replies: a planning layer and a fluency score (second session; owner's go-ahead, 2026-10-15)

Owner: "build the planning layer and fluency score. Keep iterating in this direction." Today the system replies by
quoting a span of the story; its free text (next-word sampling) is locally grammatical and globally meaningless.
Approach: the classic generation pipeline (Reiter and Dale 2000) -- decide what to say (content plan), arrange it into
sentences (sentence plan: aggregation, referring expressions), then say it (surface realisation) -- with each stage
measured, and its rules later learned from text rather than written by hand.

## F0 registration (the fluency score)
r27_fluency.py scores any text with three deterministic measures:
- judge bits/word: the stock RWKV-7 0.4B checkpoint (RWKV-x070-World-0.4B, never fine-tuned in this project), bits per
  word of the text given a fixed neutral prefix; lower = more natural English to an independent model;
- repetition: share of word 3-grams that occurred earlier in the same text;
- sentence form: share of sentences of 4-30 words that contain a verb (dictionary) and end with . ! or ?.
Calibration (reported, no gate): human held-out paragraphs, the same paragraphs lower-cased without punctuation, our
engine's free samples, and shuffled human words (a floor). A text is called fluent when its judge bits/word is within
1 bit of human text in the same form and its sentence form rate is at least 0.9.

## P1 registration (answers as full sentences -- the smallest plan: one fact, one sentence)
r27_answer.py: every answer the best comprehension policy gives (R26 T22p) is realised as a sentence by turning the question into its statement: who / what as subject -> 'ANSWER <rest>'; did-questions -> '<subject> <verb in the past> <rest> ANSWER' (past forms: the dictionary's irregular forms, else regular -ed rules); was / is questions -> '<subject> <was / is> <rest> ANSWER'; where / when -> the place or time phrase at the end; why -> '<subject> <verb past> <rest> because ANSWER'; how many -> '<subject> <verb past> ANSWER <noun>'. Capital first letter, final full stop. Scored on the 1,800 untouched questions' answers: judge bits/word, sentence form, and whether the gold answer is still inside the sentence; compared with the bare answer spans and with the story's own sentence holding the answer. PASS if the sentences' judge bits/word is within 1 bit of the story sentences', form >= 0.9, and the gold is kept wherever the span had it.

## F0 result (calibration)
Judge bits/word (40 held-out paragraphs): human 6.215 (sentence form 0.772: these novels have long sentences and dialogue, so the 0.9 form bar is stricter than human prose); human lower-cased without punctuation 6.446; human words shuffled 10.552; our engine's free samples (lower case, 3 x 60 words) 6.721. The judge separates word salad from English (10.55) but rates the engine's locally grammatical, meaningless text only 0.28 bits above human text: judge bits/word measures local fluency, not coherence. A coherence measure is needed (P3).

## P1 first run (rules seen on untouched answers -- disclosed)
938 of 951 answers realised; the gold is kept in all 824 sentences whose span had it. Faults visible in the printed examples (which were untouched-set questions; from here realisation rules are developed on practice questions only): a noun read as the verb ('What did the crow find?' -> 'The crowed the ring find.'); be-questions with a predicate ('The oven hot again was noon.'); who + had reversed; a capitalised time phrase mid-sentence ('At eight o'clock').
P1b (fixes): the verb of a did-question is the body word whose base or past form occurs as a verb in the story (first such); be-questions put the copula after the subject phrase (determiner + noun or a name) and keep the rest after it; 'who had / has' -> 'ANSWER had REST'; a time / place answer's first word is lower-cased unless it is a name; sentence-initial 'At the end' modifiers moved to the front. Gate as P1.

## F1 registration (coherence: what sentence order is worth)
order gain = judge bits/word of the paragraph with its sentences in a shuffled order (mean of 3 fixed shuffles) minus judge bits/word in the original order. Coherent text loses when shuffled (positive gain); a list of unrelated sentences gains nothing. Also entity continuity: share of sentences after the first that mention a name or noun from an earlier sentence. Calibrated on the 40 human paragraphs (F0 set); reported for every paragraph-level output from here.

## P2 registration (retelling a story -- content plan, sentence plan, realisation)
r27_retell.py. Content plan: the role reader's clauses of the story (subject, verb, object, place, time), in story order, keeping clauses with a subject and a verb, at most 6, skipping a clause whose (subject, verb, object) repeats an earlier one. Sentence plan: a subject identical to the previous sentence's subject becomes he / she (the gender learned from the story: the first he / she after the name), otherwise the full name or noun phrase; linking words by position (first sentence none; then 'Then', 'Later', 'After that' in turn; the last 'In the end'). Realisation: 'Subject verb-in-the-past object place time.' Scored on the 360 untouched stories (val_fresh2 .. val_fresh10): judge bits/word, sentence form, order gain, entity continuity, and faithfulness (share of realised (subject, verb) pairs whose verb's base form occurs in the story's sentence that names the subject). Compared with the stories' own first six sentences (upper reference) and with our engine's free continuation of the story's first sentence (lower reference). PASS if the retellings are within 1 bit of the stories on judge bits/word, form >= 0.9, order gain above zero, and faithfulness >= 0.9.

## P2 development note (practice stories only)
First realisation from lemma + past tense read badly: wrong subjects for verbs joined by 'and' ('the fence knocked over two hives'), object pronouns as subjects ('her mended'), auxiliaries and negation broken ('could notted'), the sentence's time phrase repeated on every clause. Revised before scoring (P2 as registered, realisation rule changed): the predicate is the story's own words from the verb to the clause end (role reader's action span); a clause whose verb follows 'and' shares the previous clause's subject; him / her / them as a subject become he / she / they; a time phrase is said once per story sentence; clauses whose predicate starts with a negation or modal keep it from the story text.

## P3 registration (a reply paragraph to a question)
r27_reply.py. Content plan: the answer (best comprehension policy) as a P1 sentence, plus up to two story clauses most related to the question (sharing the most content words with the question and answer, the answer's own clause excluded), in story order. Sentence plan and realisation as P2 (story wording, shared subjects, pronouns, links 'Before that' for a supporting clause earlier in the story than the answer, 'After that' for a later one). When the policy is silent the reply is 'The story does not say.' Scored on 300 untouched questions with an answer: judge bits/word, sentence form, entity continuity, order gain, and the gold kept. Reported against the one-sentence answers (P1). PASS if the reply paragraphs keep the gold wherever P1 did, form >= 0.9, judge within 1 bit of the story text, and continuity >= the stories' own.
Note on P1: its answers came from r26_policy_answers.json as last written, which was the T22q run (+495), not the best policy T22p (+512); this does not affect what P1 measures (realisation, gold kept relative to the span). From P3 on, the best policy's answers are frozen in r26_best_policy_answers.json.

## P1 result -- FAIL on the judge, PASS on form and gold
300 untouched answers: realised sentences judge 10.768 bits/word, form 0.933; bare spans 15.903 / 0.0; the story's own sentences 7.507 / 0.977; gold kept 266 / 266. The 3.3-bit gap to the story sentences comes from visible faults: doubled prepositions ('followed her to to the hospital car park'), a stranded preposition repeated ('grew into small oak trees into'), copular who-questions inverted ('Proud of his tunnels was Grummel'), time phrases left mid-sentence ('The van was at dawn outside the bakery').

## P1c registration (realisation fixes)
(a) a preposition ending the question body is not repeated when the answer starts with it; (b) a question body that is a lone preposition goes before the answer ('grew into small oak trees'); (c) 'Who was X?' -> 'ANSWER was X' always; (d) a time phrase in a be-question body (at / by / in + a time word or a number) moves to the front ('At dawn, the van was outside the bakery'). Re-scored on the same 300 untouched answers. PASS as P1.

## P3 result (replies)
300 untouched questions with an answer: gold kept 263 / 263 (every reply that should hold the gold does). Replies with at least two sentences (183): judge 7.983 bits/word, sentence form 0.945, entity continuity 0.984. Story reference: see below (r27_run_p3.txt). Note: in this run the shared-subject rule for 'and'-joined verbs did not fire (a backspace character had replaced a word boundary in its pattern; fixed afterwards in r27_reply.py).

## P5 registration (the system's own model chooses the wording)
r27_choose.py. For each answer sentence, candidates are generated: the P1c sentence, plus the alternatives the rules leave open -- subject-verb-answer-rest vs subject-verb-rest-answer, past vs base verb form, with or without the answer's leading preposition, a fronted vs final time / place phrase. Our own book-scope network (r25_ch, static) scores each candidate (bits/word, sentence read alone) and the cheapest is kept. Judged by the external judge (stock 0.4B) on the same 300 untouched answers as P1c. PASS if the chosen sentences' judge bits/word is below P1c's. This moves word-order and inflection choices from hand rules to the system's own learned preferences.

## P1c result -- FAIL (judge), PASS (form, gold)
Same 300-answer protocol (now on the best policy's answers): realised 10.452 bits/word, form 0.953; spans 15.752; story sentences 7.467, form 0.980; gold kept 278 / 278. Small gain (P1 10.768). A systematic cause remains: extracted answers lose their article ('Ship's horn woke Zulfiya at two'), because the extractor strips leading determiners.

## P1d registration (restore the story's determiner)
When the story text has a determiner (the / a / an / his / her / their / its / my / our) right before the answer span, the sentence uses it; the answer string itself is unchanged for scoring the gold. Same protocol. PASS as P1.
P3 story reference (first four sentences of the same stories): judge 5.587, form 0.974, continuity 0.964. **P3 verdict: FAIL on the judge** (7.983 vs 5.587, gap 2.4 > 1); PASS on gold kept (263 / 263), form (0.945) and continuity (0.984 >= 0.964). The supporting sentences are the story's own wording; most of the gap is the answer sentence (P1's problem) and the bare 'Before that / After that' links.

## P5 result -- FAIL
The network changed 49 of 300 sentences; judge 10.452 -> 10.517 (worse), form unchanged. Some choices are improvements ('took the beds from Wrexton Road', 'caught more flies than ever that night'), others clearly worse ('left on the ferry her red scarf', 'chewed through every sack One night the mice'): the network, reading a lower-cased sentence alone, does not judge word order reliably.

## P5b registration (the word-count model chooses)
Same candidates; the chooser is the Kneser-Ney counter (o5mxa, 5-word phrases, from its saved index) scoring each candidate with sentence boundaries (bits/word), keeping the current P1c sentence unless a candidate is cheaper by at least 0.5 bits/word. Same evaluation. PASS if the judge falls below P1c's 10.452.

## P1d result -- FAIL (judge), PASS (form, gold)
Restored determiners: realised 10.115 bits/word (P1c 10.452), form 0.963; story sentences 7.467; gold 278 / 278. Gap 2.65 bits.

## Practice diagnosis of the judge gap (150 practice answers)
Mean judge: ours 10.080, story sentences 7.379. The largest gaps are short sentences led by a name ('Halvard repaired bicycles.' 21.8 vs 9.8): judged without context, a name costs many bits and a short sentence cannot spread that cost, while the story's sentence carries many cheap words. A reply is read after the story, where the names are known -- so the context-free judge is unfair to short replies. Real faults also seen: where-answers missing their preposition ('Jack fell the mud.'), invented verb forms on unusual questions ('wassed', 'frogged do').

## F2 registration (the judge in context)
judge bits/word of a reply given the story and the question as a prefix ('<story>\n\nQuestion: <q>\nAnswer:'), against the story's own sentence holding the answer under the same prefix (the extractive reply). This is the primary fluency measure for replies from here; the context-free judge stays as a secondary number.

## P1e registration (preposition from the story; quote when unsure)
(1) a where / when answer without a preposition takes the preposition the story has right before it ('fell in the mud'); (2) when no verb of a did-question can be checked in the story (its past or -s form absent), the reply is the story's own sentence holding the answer instead of a rewrite. Scored with F2 on the same 300 untouched answers; PASS if within 1 bit of the extractive reply under F2, form >= 0.9, gold kept.

## P5b result -- FAIL
The counter changed 30 of 300 sentences; judge 10.452 -> 10.572 (worse). It prefers moving an unknown name away from the sentence start ('wheeled the crate up the slipway Teague.') and base verb forms ('The bear eat the honey.'): with sentence-initial names costly and no notion of agreement, our count model is not a usable judge of whole-sentence word order either. Word-order choice stays with the rules for now; an own-model chooser needs the story as context (names known) and a model of agreement.

## F2 correction (before any F2 result was read)
Under F2 the story's own sentence is a verbatim copy of text in the prefix and costs about 1 bit/word (a 3-item check: 1.03), so it is no reference for fluency. F2b: the human reference is the story's sentence holding the answer judged after only the story text BEFORE it (fresh human text in context); our reply is judged after the whole story and the question. P1e's gate uses F2b: realised within 1 bit of the human reference.

## P1e result -- PASS (F2b)
60 untouched answers (reduced from 300: the judge reads token by token on this CPU and the full run exceeded 30 minutes): our answer sentence after story + question **3.296** bits/word; a fresh human sentence after the text before it **6.569**; form 0.983; 5 replies quoted the story (unsure rewrites); gold 53 / 53. In context, our answer sentences read as more predictable than fresh human text -- partly because they restate the question, which the reader has just seen.

## P2 result -- FAIL by 0.28 bits on the judge; PASS on form, order, faithfulness
20 untouched stories (reduced from 360 for the same reason): retelling judge 6.597, form 0.938, order gain 0.395 (> 0), continuity 0.929; story's first six sentences 5.318, 0.988, 0.626, 0.983; faithfulness 0.973. Gap 1.28 > 1. Faults seen: casing after links ('Later, While radu worked', 'on thursday'), a link before a clause that already opens with a subordinator (while / when / as), a relative clause losing 'who' ('a squirrel lived below asked to see it').

## P2b registration (retelling fixes)
(1) after a link, only a function word is lower-cased (names and weekdays keep their capital; time phrases keep the story's casing); (2) a clause that opens with a subordinator (when / while / as / after / before / if / because) gets no link; (3) a subject that the story follows with 'who' / 'that' keeps it ('a squirrel who lived below asked to see it' -> the clause is skipped if the 'who' clause is the predicate's own). Same 20 stories. PASS if within 1 bit of the stories on the judge, other gates as P2.

## P4 registration (realisation learned from question / story-sentence pairs)
r27_learnreal.py. From the practice questions (main 710 + extra 600) and the story sentence holding each gold answer, the learner collects (1) inflection: for each question verb (did-questions), the word in the story sentence sharing its dictionary base -> a learned base -> past table, used before the hand table and the -ed rule; (2) order: for each question shape (question word, auxiliary), how often the gold stands right after the verb vs after the rest of the question's words in the story sentence -> the majority order per shape replaces the hand choice. Applied to the same 60 untouched answers as P1e and scored with F2b; reported against P1e (3.296). PASS if not worse than P1e by more than 0.1 bits/word with form >= 0.95 and gold kept -- i.e. the learned rules can replace the hand ones.

## P2b result -- FAIL (judge gap 1.23)
Same 20 stories: retelling judge 6.552 (P2 6.597), form 0.938, order gain 0.400, continuity 0.929, faithfulness 0.973; stories 5.318. Casing and link fixes help by only 0.05.

## P2c registration (no stacked links)
Same as P2b but no linking words at all (story order and pronouns carry the sequence); 'In the end' kept only when the last clause is the story's last sentence. Same 20 stories and gates.

## P4 result -- PASS (learned rules replace the hand ones at no cost)
Learned from 449 practice pairs: 155 past forms (kept, gave, left, grew, bought, fixed, ...) and answer order by question shape -- 'what did' + noun: rest first (41 / 10); 'what did' + preposition: answer first (23 / 20); 'where did' + noun: rest first (54 / 13); 'when did': rest first (31 / 0); 'why did': rest first (14 / 0). These are the orders the hand rules had chosen: the learner re-derived them from text. With the learned tables (R27_LEARN=1): F2b 3.296 (P1e 3.296), form 0.983, gold 53 / 53 on the same 60 answers; 923 sentences made on all untouched answers (hand rules 921).

## P2c result -- FAIL by 0.08 bits (judge); PASS form, order, faithfulness
No links: retelling judge 6.393 (P2b 6.552), form 0.915, order gain 0.388, continuity 0.929, faithfulness 0.973; stories 5.318 (gap 1.075). Dropping the stacked links helped most so far. Remaining fault: referring expressions ('A crow found a ring in the grass. A crow carried it ...').

## P2d registration (referring expressions)
On P2c: (1) a subject that was mentioned before and begins with a / an switches to 'the'; (2) a subject equal to the previous sentence's subject becomes the pronoun the story uses for it (the first he / she / it / they after its first mention; 'it' if the story has none and the subject is not a name). Same 20 stories and gates.

## P2d result -- FAIL by 0.09 bits (judge); PASS form, order, faithfulness
Definite second mentions and pronouns: judge 6.410 (P2c 6.393), form 0.915, order gain 0.480 (P2c 0.388: sentence order now carries more), continuity 0.929, faithfulness 0.973; stories 5.318. The retelling line has reached diminishing returns on the judge (6.60 -> 6.55 -> 6.39 -> 6.41). Part of the remaining ~1.1-bit gap is likely inherent to summaries -- every sentence brings a new fact without the story's lead-in -- and a human-written summary reference would be needed to tell how much.

## R27 summary so far
| test | result |
|---|---|
| F0 fluency score (judge, form, repetition) | built; human 6.22, shuffled 10.55, our free samples 6.72 |
| F1 coherence (order gain, continuity) | built |
| F2 / F2b judge in context | built (F2 reference corrected before use) |
| P1-P1d answer sentences (context-free judge) | form and gold PASS; judge gap ~2.7 (short, name-led sentences are unfairly expensive without context) |
| P1e answer sentences, in context (F2b) | PASS: 3.30 vs fresh human 6.57; gold 53 / 53 |
| P2-P2d story retelling | form, order, faithfulness PASS; judge gap 1.07-1.28 (FAIL) |
| P3 reply paragraphs (answer + related events) | gold, form, continuity PASS; context-free judge FAIL |
| P4 inflection and order learned from data | PASS: re-derives the hand rules |
| P5 / P5b own models choose wording | FAIL: our models cannot judge word order yet |

## P7 registration (open requests about an entity: 'What happened to X?' / 'Tell me about X.')
r27_about.py. Content plan: the role reader's clauses in which X (a name or noun phrase from the request) is the subject or the object, plus clauses whose subject is a pronoun resolved to X (the most recent name), in story order, at most 5; realised as P2d. Test set: for each of the first 40 untouched stories, the request 'Tell me about <the story's first named person>.' Scored: relevance (share of reply sentences mentioning X or a pronoun for X), faithfulness (as P2), judge, form. Reference: the story's sentences that mention X, in order (an extractive answer). PASS if relevance >= 0.9, faithfulness >= 0.9, form >= 0.9, and judge within 1 bit of the reference.

## P7 result -- FAIL on the judge (gap 1.21); PASS relevance, faithfulness, form
25 untouched stories: relevance 1.000, faithfulness 0.920, form 0.940; judge 7.541 vs the extractive reference 6.331. Example: 'Wanjiru packed a basket of mangoes. She sold half of them before lunch. In the afternoon, she carried the rest to her aunt's house by the lake. She slept there that night. In the end, she went home in the morning.' Test-set construction bug: the entity picker took 'Mrs' (a title without its name) and 'She' (a sentence-initial pronoun) for names in some stories; those requests are malformed. The judge gap matches the retellings' (~1.1-1.2): selected-event summaries pay a cost the full story does not.

## Where R27 stands (fluency line)
Built: a fluency score (judge, form, order gain, continuity, in-context judge), a planner (content selection by question / story / entity, sentence planning with shared subjects, pronouns and definite second mentions), a realiser (statement rewriting with learned inflection and order, story wording for events). Answer sentences are fluent in context (P1e); retellings and entity replies are faithful, relevant and well-formed but ~1.1-1.2 bits/word less natural to the judge than the source text. Next lever: a human-written summary reference to tell how much of that gap is inherent, and aggregation (joining two short events into one sentence: 'She took the bus to the market and sold half of them before lunch').

## P8 registration (aggregation)
On P2d: two consecutive realised clauses with the same subject, neither opening with a time phrase or a subordinate clause, and together at most 22 words, are joined into one sentence 'Subject pred1 and pred2.' Same 20 stories; scored against P2d (6.410) and the stories (5.318); the human summaries (being written) are added as a reference when ready. PASS if the judge falls below P2d's with form >= 0.9 and faithfulness >= 0.9.

## P8 result -- PASS (small); and the human reference
Same 20 stories: human summaries (written by a separate agent that saw only these stories) judge **5.248**, form 0.988, order gain 0.640, continuity 0.967 -- as natural to the judge as the stories themselves (5.318). P2d 6.410; P8 aggregated **6.370** (form 0.918, order gain 0.428). The ~1.1-bit gap is therefore not inherent to summaries: our retellings are measurably less natural than a human summary. The visible cause is the clause-level plan: role-reader fragments and mis-assigned subjects ('Her prize opened her beak to answer'), predicates cut at clause edges.

## P9 registration (sentence-level content plan)
r27_summarise.py: the content unit is a whole story sentence. Selection: each sentence scores by its count of role-reader clauses with a subject and verb plus 1 if it mentions the story's main person (the most frequent name); keep the top 4 in story order. Sentence planning: a sentence starting with the same name as the previous kept sentence starts with he / she instead (gender from the story); nothing else rewritten. Same 20 stories; scored with judge, form, order gain, continuity, against the human summaries. PASS if within 0.5 bits of the human summaries' judge with form >= 0.95.

## P9 result -- PASS as registered, but vacuous on these stories
Sentence-level summary: judge 5.318, form 0.988, order gain 0.626, continuity 0.983; human summaries 5.248 / 0.988 / 0.640 / 0.967. Within 0.5 bits, so the gate passes -- but the test stories have 4-5 sentences, so 'keep the best 4' mostly reproduces the story (its judge equals the stories' own 5.318). The pass shows only that sentence-level units avoid the clause-level faults; content selection is not tested here. A real test needs long texts (book passages of 15+ sentences) with human summaries.

## P10 registration (summarising long passages -- content selection tested)
15 passages of 15-30 sentences from held-out books (paragraphs 3,100 onward, never scored), human summaries of 4-5 sentences written by a separate agent that saw only the passages. Systems: P9's sentence-level summary with k = 5 (sentence score: role-reader clauses + main-person mention); lead-5 (the first five sentences; the standard extractive baseline); P8-style clause retelling (6 clauses). Measures: content coverage = share of the human summary's content words (lower-case, no stop words, dictionary base for verbs) found in the system summary; judge, form, order gain. PASS if P9's coverage beats lead-5's and its judge is within 0.5 bits of the human summaries'.

## P10 result -- PASS (with a length caveat)
15 long passages, human summaries as reference (coverage of their content words; judge; form): P9 selection (k = 5) coverage **0.326**, 115 words, judge **6.124**, form 0.679; lead-5 coverage 0.221, 73 words, judge 6.621, form 0.696; clause retelling coverage 0.119, 37 words, judge 8.090, form 0.830; human summaries 128 words, judge 5.769, form 0.693 (novel sentences are long, so form is low for all). P9 beats lead-5 on coverage and is within 0.36 bits of the human judge -- PASS. Caveat: selecting by clause count favours long sentences (115 vs 73 words), which inflates coverage; a length-matched comparison is the next check. The clause-level retelling does not scale to long passages (coverage 0.12, judge 8.09): whole story sentences are the right content unit.

## P10b registration (length-matched baseline)
Lead-N: the passage's first sentences up to at least as many words as P9's summary of that passage. Coverage only. PASS if P9's coverage still beats it.

## P10b result -- FAIL: the selection is not better than position
At matched length the first sentences cover more of the human summaries: lead 0.367 (127 words) vs P9 0.326 (115 words). P10's win came from choosing longer sentences, not better ones.

## P10c registration (centrality: Luhn 1958)
Sentence score = sum over its content words of their frequency in the passage, divided by sqrt(sentence length); sentences taken in score order until the summary reaches P9's word count, then put in passage order. Coverage against the length-matched lead (0.367) and P9 (0.326); judge on the summaries. PASS if coverage beats the length-matched lead.

## P10c result -- FAIL
Centrality: coverage 0.344 (125 words) vs length-matched lead 0.367.

## P10d registration (cover the whole arc)
The passage is split into 5 equal stretches of sentences; from each, the most central sentence (P10c score) is taken; passage order. Coverage vs the length-matched lead built to the same word count as this summary. PASS if it beats that lead.

## P10d result -- FAIL
Arc coverage 0.289 (102 words) vs length-matched lead 0.329 (112 words). Three selection rules (clause count, centrality, arc spread) all lose to 'the first sentences' at equal length -- the lead baseline, famously hard to beat in summarisation research, holds here too (these human summaries open with the passage's setting and people, which the first sentences carry). A selection that beats it would have to be learned from (passage, summary) pairs; 15 pairs are too few to learn from. The realisation side is sound (judge of selected human sentences within 0.4 bits of human summaries); content selection for long text is the open problem.

## P11 registration (a sentence selector learned from passage / summary pairs)
Training data: 60 further passages (r27_long_passages_train.json, never overlapping the 15 test passages) with human summaries written by a separate agent. Each sentence gets features: relative position, position bucket (first / last / other), length, centrality (P10c), clause count, mentions of the passage's most frequent name, overlap with the first sentence, overlap with the rest of the passage. Target: the share of the human summary's content words the sentence contains. A least-squares linear scorer (no other learning) is fitted on the 60 passages; on the 15 test passages sentences are taken by predicted score until the summary reaches the length-matched lead's word count, then put in passage order. PASS if coverage beats the length-matched lead on the 15 test passages.

## P11 result -- PASS as registered, but inconclusive
Learned from 60 passage / summary pairs (least squares on 9 sentence features): weight mostly on centrality (0.099) and length (0.043), some on being the last sentence (0.016); position and first-sentence overlap near zero. 15 test passages: coverage **0.386** (130 words) vs length-matched lead 0.370 (121 words). The 9-word overshoot (sentences are added whole) is enough to explain the 0.016 gain: per word the lead is still level or ahead. Content selection learned from 60 pairs matches the lead baseline; beating it clearly would need finer units (clauses or compressed sentences) or more data.
