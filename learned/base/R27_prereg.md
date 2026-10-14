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
