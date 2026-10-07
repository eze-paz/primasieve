# ENGLISH MAP -- a forward characterisation of English for primasieve (2026-10-07)

The owner: "instead of correcting our model once it fails to read english, do a forward pass and characterize english fully using theory to predict future issues." This file is that pass. It (1) inventories English phenomena along descriptive-grammar lines (CGEL chapters / Universal Dependencies relations), (2) estimates how often each occurs in the training Gutenberg books (`english_freq.py`, surface cues, approximate), (3) gives each phenomenon minimal probes (`tests/english_probes.json`), and (4) PREDICTS, from reading the engine's code, what the engine will do on every probe -- RIGHT, WRONG (states something false or the wrong role) or SILENT (abstains). The predictions were committed before any probe was run (engine at commit cdbf193b, with the uncommitted iteration-16 reader changes in the working tree). The Results section (appended by `english_probe.py`) scores both the engine and the predictions, and ranks phenomena by PRIORITY = frequency x (2 x wrong share + silent share).

**Size:** 114 phenomena in 14 families; 93 mini-stories with 171 questions (all through the event memory; 39 stories also through the live door), and 65 question probes over the engine's existing worlds (records and sales tables, the Wikidata fixture, the dictionary), asked in one live door.

## 1. How the engine reads English (the theory the predictions use)

Read from `core/events.py`, `emergence/kb_events.py`, `core/reason.py`, `core/session.py`, `core/rephrase.py`, `chat.py`:

- **Closed class = the 200 commonest symbols of the text model** (`tm.uni.most_common(200)`, a dictionary-text model). It holds function words but also frequent content words: verbs *made, said, found, called, take, make, see, do, used, given*, nouns *man, people, water, family, city, day, time, world, life, work*, adjectives *old, long, little, good, great*. A closed symbol is never a content verb or noun. A closed symbol beside a verb where a noun is expected is read as a PRONOUN (refers to the last agent).
- **An event per finite verb form** (UniMorph past and 3sg present, plus forms learned from dictionary glosses); auxiliary + participle also makes one; a learned marker (*to, will, would, can, could, may, t*) + base form makes an infinitive event whose agent is the sentence's first agent (or the last agent).
- **Agent = nearest noun run on the left** (skipping at most one closed symbol, one comma); a learned subject symbol (*he, she, they, I, we, who*) right before the verb = the last non-pronoun agent (no gender, number or person). **Patient = nearest noun run on the right**, skipping up to two closed symbols (so a PP object becomes the patient: *slept in the car* -> patient car); an object pronoun = the last patient. **Adjuncts** = closed symbol + noun run after the patient. Words outside the closed class that are not verb forms are nouns (so *until, across, never, every, nobody, herself, easily* are nouns).
- **Passive is not undone in the story**: *X was broken by Y* stores agent X, patient Y. A passive QUESTION maps its content to the patient; *has/had + participle* in a question is also read as passive.
- **No polarity, modality or mood**: negation (*didn't, no*), modals (*may have*), futures, conditionals and counterfactuals are stored as plain events.
- **A question** (first word closed or ending in ?) selects events by the lemmas of its NON-closed verb words (so *was, is, has, make, take, do, see, said* give no lemma; a noun that is also a verb, *keys, house, book*, gives a spurious lemma and is not content), then answers the role it leaves empty; with every core role named it returns the adjuncts; with no role shared it abstains.
- **The live door** answers a story question from the event memory only when the worlds give no clean answer: a name that a world also holds (*alice, bob, ken, grace, ivan*) can let a world answer instead; when the memory has nothing, the worlds' reply (often a dictionary gloss of a content word) is said instead. A RECALL reply carries the event in brackets, so a scorer that searches the whole reply can credit a wrong answer whose event mentions the gold.
- **World questions** are read by span coverage: each world reads spans (Wikidata fixture: only n-grams cached when the fixture was built; records/sales: induced lexicons; dictionary: any word, as a quotation). Unread content words lead to a one-edit spelling reading (if unique), a did-you-mean OFFER (never an answer), the 65k store fetcher, or the guesser. Common words (*not, more, than, after*) are ignored, so they never restrict an answer.

## 2. Frequencies (english_freq.py)

45102 sentences (1022295 words) from 60 training books (held-out books excluded by `kb_events.held_book`), a block from the middle of each book. Rates are the share of sentences on which a SURFACE CUE fires; cues miss instances and fire on look-alikes, so read them as orders of magnitude. Question types are also given as a share of question sentences (6.4 % of sentences end in ?), which is the right denominator for a question-answering door. The corpus files end lines with CR CR LF; reading them with universal newlines turns every line into a paragraph (a hazard for any paragraph-based reader).

Most frequent phenomena (by the cue rate used for priority):

| phenomenon | family | frequency (cue) |
|---|---|---|
| np.article -- articles and definiteness | noun phrase | 0.722 (np.article) |
| morph.past_regular -- regular past tense (-ed) | morphology | 0.489 (morph.past_regular) |
| ref.pronoun_gender -- pronoun resolution needing gender/number | reference | 0.446 (ref.third_person_pronoun) |
| np.possessive_det -- possessive determiners | noun phrase | 0.419 (np.possessive_det) |
| np.of_phrase -- of-phrases (genitive/partitive) | noun phrase | 0.392 (np.of_phrase) |
| ref.first_person -- first/second person in a told story | reference | 0.376 (ref.first_second_person) |
| morph.noun_verb_homograph -- plural noun = 3sg verb homographs | morphology | 0.360 (morph.plural) |
| q.declarative -- declarative (rising) questions | questions | 0.345 of questions (q.declarative; 0.022 of all sentences) |
| morph.derivation -- derivational morphology | morphology | 0.306 (morph.derivation) |
| morph.irregular -- irregular past (strong verbs) | morphology | 0.305 (morph.irregular) |
| clause.coord_clauses -- coordinated clauses | clause linkage | 0.298 (clause.coord_clauses) |
| np.quantifier -- quantifying determiners and numerals in NPs | noun phrase | 0.278 (np.quantifier) |
| clause.direct_speech -- direct speech with attribution | clause linkage | 0.249 (clause.direct_speech) |
| q.yes_no -- polar questions over worlds | questions | 0.242 of questions (q.yes_no; 0.016 of all sentences) |
| ref.pronoun_object -- object pronouns (it/him/them) | reference | 0.232 (ref.object_pronoun) |
| q.embedded -- embedded questions | questions | 0.223 of questions (q.embedded; 0.014 of all sentences) |
| morph.top200_verbs -- forms of the very commonest verbs | morphology | 0.222 (verb.top200_forms) |
| verb.copula -- copula and predicative complements | verb and argument structure | 0.211 (verb.copula) |
| clause.temporal_sub -- temporal subordinate clauses (when/after/before) | clause linkage | 0.179 (clause.subordination) |
| np.adjective -- attributive adjectives | noun phrase | 0.166 (np.adjective) |
| np.numeral -- cardinal numerals | noun phrase | 0.164 (np.numeral) |
| neg.not -- clausal negation (not / n't) | negation | 0.163 (neg.not) |
| neg.world -- negation in questions over worlds | negation | 0.163 (neg.not) |
| tam.perfect -- perfect aspect | tense, aspect, mood | 0.157 (tam.perfect) |
| ref.cataphora -- pronoun before its antecedent | reference | 0.154 (ref.cataphora_sentence_initial_pronoun) |

The full cue table is in `english_freq.json` / `english_freq.txt`.

## 3. Inventory

### morphology

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| morph.past_regular | regular past tense (-ed) | past tense formed with -ed; the commonest finite form in narrative | Nadia painted the fence. | core/events.py + emergence/kb_events.py (event memory) | 0.489 (morph.past_regular) |
| morph.irregular | irregular past (strong verbs) | past tense by vowel change or suppletion (broke, swept, went) | Kofi broke the vase. | core/events.py + emergence/kb_events.py (event memory) | 0.305 (morph.irregular) |
| morph.top200_verbs | forms of the very commonest verbs | made, said, found, called, take, make, see, do, get, use ... -- the most frequent verbs of English, all inside the engine's 200-word closed class | She made a wish. / He said that ... | core/events.py + emergence/kb_events.py (event memory) | 0.222 (verb.top200_forms) -- engine-specific consequence of a general fact: the commonest verbs are as frequent as function words |
| morph.third_sg | third-person singular present (-s) | habitual/present narrative: feeds, milks | Pablo feeds the chickens. | core/events.py + emergence/kb_events.py (event memory) | 0.036 (morph.third_sg) |
| morph.noun_verb_homograph | plural noun = 3sg verb homographs | watches, plants, kids: the -s form is a plural noun or a verb by position | Sara lost her watches. / Her brother watches the kids. | core/events.py + emergence/kb_events.py (event memory) | 0.360 (morph.plural) -- rate shown is the plural-noun cue (upper bound for the homograph risk) |
| morph.contraction | contractions (n't, 's, 'll) | clitic negation and auxiliaries attached to the previous word | Paco didn't see the deer. / what's the capital | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.028 (morph.contraction_neg) -- n't only; other clitics 3.0 % |
| morph.possessive_s | possessive 's | genitive clitic marking the possessor (Maya's dog) | Maya's dog chased the cat. / ken's salary | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.092 (morph.possessive_s) |
| morph.derivation | derivational morphology | words built by affixes (kind-ness, un-friend-ly); productive new formations | kindness / unbloggable | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) (dictionary) | 0.306 (morph.derivation) |
| morph.degree_forms | comparative/superlative forms (-er/-est, irregular) | biggest, least, smallest: degree forms the worlds were not taught | which employee has the biggest salary | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary); core/rephrase.py (one-edit spelling, did-you-mean) + core/synonyms.py | 0.035 (quant.superlative) |

### noun phrase

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| np.article | articles and definiteness | a/an introduces, the refers back | A dog found a bone. The dog buried the bone. | core/events.py + emergence/kb_events.py (event memory) | 0.722 (np.article) |
| np.adjective | attributive adjectives | adjective before the head noun | The tall woman lifted the heavy box. | core/events.py + emergence/kb_events.py (event memory) | 0.166 (np.adjective) |
| np.compound | noun-noun compounds | two nouns forming one head (fire truck, bus stop) | The fire truck blocked the bus stop. | core/events.py + emergence/kb_events.py (event memory) | 0.016 (np.compound) -- cue is weak (closed list of heads); compounds are far more common than 1.6 % |
| np.of_phrase | of-phrases (genitive/partitive) | head + of + NP (captain of the ship, half of her sandwich) | The captain of the ship rang the bell. | core/events.py + emergence/kb_events.py (event memory) | 0.392 (np.of_phrase) |
| np.appositive | appositives | NP, NP, -- a second description of the same referent | Sam, the old fisherman, caught a fish. | core/events.py + emergence/kb_events.py (event memory) | 0.005 (np.appositive) |
| np.possessive_det | possessive determiners | my/his/her/their + noun | Lucas lost his keys. His mother found them. | core/events.py + emergence/kb_events.py (event memory) | 0.419 (np.possessive_det) |
| np.quantifier | quantifying determiners and numerals in NPs | three boys, each boy, many | Three boys climbed the hill. | core/events.py + emergence/kb_events.py (event memory) | 0.278 (np.quantifier) |
| np.numeral | cardinal numerals | digits and number words inside NPs | Ana bought 12 apples and 3 pears. | core/events.py + emergence/kb_events.py (event memory) | 0.164 (np.numeral) |
| np.proper_name | multi-word proper names | personal and place names of several words | Mary Ann Evans wrote a long novel. | core/events.py + emergence/kb_events.py (event memory) | 0.107 (np.multiword_name) |
| np.title | titles before names | Captain Reyes, Doctor Lim, Mr. Smith | Captain Reyes steered the ship. | core/events.py + emergence/kb_events.py (event memory) | 0.045 (np.title) |
| np.frequent_noun | very frequent common nouns | man, people, day, water, family, city, time, world -- nouns frequent enough to sit in the engine's 200-word closed class | A man sold him a horse. / asked for water | core/events.py + emergence/kb_events.py (event memory) | 0.113 (np.frequent_noun) -- engine-specific: closed class = 200 commonest symbols of the text model |
| np.coordination | coordinated NPs | X and Y as one argument | Eva and Karl painted the barn. | core/events.py + emergence/kb_events.py (event memory) | 0.029 (np.coordinated_np) |

### verb and argument structure

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| verb.transitive | transitive clauses | subject-verb-object | The cat scratched the girl. | core/events.py + emergence/kb_events.py (event memory) | 0.128 (verb.transitive) -- proxy cue (pronoun/name + past verb + determiner) |
| verb.intransitive_pp | intransitive verb + locative PP | slept in the car | The baby slept in the car. | core/events.py + emergence/kb_events.py (event memory) | 0.128 (verb.transitive) -- no separate cue; share of PP adjuncts is high |
| verb.ditransitive | double-object construction | V + recipient + theme (gave Leo a book) | Mia gave Leo a book. | core/events.py + emergence/kb_events.py (event memory) | 0.011 (verb.ditransitive) |
| verb.dative_alternation | prepositional dative | V + theme + to + recipient | Nora gave a scarf to her sister. | core/events.py + emergence/kb_events.py (event memory) | 0.016 (verb.dative_to) |
| verb.particle | particle (phrasal) verbs | V + up/down/out (picked up, put down) | Nina picked up the phone. | core/events.py + emergence/kb_events.py (event memory) | 0.054 (verb.particle) |
| verb.light | light-verb constructions | take a walk, make a decision: the meaning sits in the noun | Omar took a long walk by the river. | core/events.py + emergence/kb_events.py (event memory) | 0.001 (verb.light) -- cue covers a closed list of nouns only; true rate is several times higher |
| verb.copula | copula and predicative complements | X was a nurse / X is tall | Hana was a nurse. | core/events.py + emergence/kb_events.py (event memory); chat.py Door (sentence split, recall vs world answer) | 0.211 (verb.copula) |
| verb.existential | existential there | there is/was + NP | There was a well behind the house. | core/events.py + emergence/kb_events.py (event memory) | 0.034 (verb.existential) |
| verb.control | subject and object control (want to, tell X to) | the understood subject of an infinitive | Sana wanted to learn the violin. / Mira told Tomas to close the gate. | core/events.py + emergence/kb_events.py (event memory) | 0.044 (verb.control) |
| verb.causative | causatives (make/let/have X do) | made her brother wash the dishes | Ella made her brother wash the dishes. | core/events.py + emergence/kb_events.py (event memory) | 0.017 (verb.causative) |
| verb.perception | perception-verb complements | heard the dog bark | Lina heard the dog bark. | core/events.py + emergence/kb_events.py (event memory) | 0.017 (verb.causative) -- same cue family as causatives |

### voice

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| voice.passive_by | passive with by-agent | be + participle + by NP | The window was broken by a stone. | core/events.py + emergence/kb_events.py (event memory) | 0.022 (voice.passive_by) |
| voice.passive_agentless | agentless passive | be + participle, no by-phrase | The letters were burned in the stove. | core/events.py + emergence/kb_events.py (event memory) | 0.149 (voice.passive) |
| voice.get_passive | get-passive | got bitten | Pedro got bitten by a snake. | core/events.py + emergence/kb_events.py (event memory) | 0.001 (voice.get_passive) |
| voice.passive_question | passive question over an active story | When was X done? / By whom was X done? | When was the oak tree planted? | core/events.py + emergence/kb_events.py (event memory) | 0.149 (voice.passive) |

### tense, aspect, mood

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| tam.progressive | progressive aspect | be + -ing | Lara was reading a letter. | core/events.py + emergence/kb_events.py (event memory) | 0.059 (tam.progressive) |
| tam.perfect | perfect aspect | have + participle | Tom has fixed the roof. | core/events.py + emergence/kb_events.py (event memory) | 0.157 (tam.perfect) |
| tam.future | future / will + infinitive | irrealis future events | Tomorrow Ada will visit her aunt. | core/events.py + emergence/kb_events.py (event memory) | 0.074 (tam.will_future) |
| tam.modal_epistemic | epistemic modals (may have, must have) | possibility, not fact | The thief may have taken the ring. | core/events.py + emergence/kb_events.py (event memory) | 0.059 (tam.epistemic) -- modal + have/be; includes non-epistemic uses |
| tam.conditional | conditionals | if-clause + consequence: neither is asserted | If Leo wins, his father will buy a boat. | core/events.py + emergence/kb_events.py (event memory) | 0.061 (tam.conditional) |
| tam.counterfactual | counterfactual / subjunctive | had studied ... would have passed: the event did NOT happen | If Ben had studied, he would have passed. | core/events.py + emergence/kb_events.py (event memory) | 0.005 (tam.subjunctive) |
| tam.imperative | imperatives and requests as questions | Tell me X / Give me X | Tell me the capital of Japan | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.025 (tam.imperative) |
| tam.tense_mismatch | question tense differs from story tense | story present, question past (plays / played) | Ivy plays the piano. Who played the piano? | core/events.py + emergence/kb_events.py (event memory) | 0.036 (morph.third_sg) |

### negation

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| neg.not | clausal negation (not / n't) | the event did not happen | She didn't eat the soup. | core/events.py + emergence/kb_events.py (event memory) | 0.163 (neg.not) |
| neg.never | never | negative frequency adverb | Kai never visited Lima. | core/events.py + emergence/kb_events.py (event memory) | 0.026 (neg.never) |
| neg.no_det | negative determiners and pronouns (no, nobody) | No guest drank ... | No guest drank the wine. | core/events.py + emergence/kb_events.py (event memory) | 0.087 (neg.no_det) |
| neg.world | negation in questions over worlds | not / outside / except restricting a set | how many employees are not in support | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.163 (neg.not) |

### questions

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| q.yes_no | polar questions over worlds | Is X the Y of Z? | is tokyo the capital of japan | chat.py statement path (kb_constructions reader, filled-question check); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.242 of questions (q.yes_no; 0.016 of all sentences) -- share of questions |
| q.who_subject | who-questions with a content verb | who wrote / directed X | who wrote hamlet | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary); core/rephrase.py (one-edit spelling, did-you-mean) + core/synonyms.py | 0.031 of questions (q.wh_who; 0.002 of all sentences) -- share of questions |
| q.what_object | what-questions with do-support | what X does Y verb | what currency does japan use | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.082 of questions (q.object_wh; 0.005 of all sentences) -- share of questions |
| q.whom | whom / object who | who(m) did X verb | Whom did the cat scratch? | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.015 of questions (q.wh_whom; 0.001 of all sentences) -- share of questions |
| q.whose | whose-questions | possessor questions | Whose dog chased the cat? | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.001 of questions (q.wh_whose; 0.000 of all sentences) -- share of questions |
| q.which | which-questions | selection among a set | Which dog dug a hole? | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.005 of questions (q.wh_which; 0.000 of all sentences) -- share of questions |
| q.where | where-questions | location | Where did Bea hide the key? | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.027 of questions (q.wh_where; 0.002 of all sentences) -- share of questions |
| q.when | when-questions | time | When did the family visit the zoo? | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.012 of questions (q.wh_when; 0.001 of all sentences) -- share of questions |
| q.why | why-questions | reason | Why did Tim stay home? | core/events.py + emergence/kb_events.py (event memory) | 0.036 of questions (q.wh_why; 0.002 of all sentences) -- share of questions |
| q.how_manner | how-questions (manner/instrument) | with a knife, easily | How did Rita open the jar? | core/events.py + emergence/kb_events.py (event memory) | 0.044 of questions (q.wh_how; 0.003 of all sentences) -- share of questions |
| q.how_many | how many / how much | counting questions | How many boys climbed the hill? | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.004 of questions (q.wh_how_many; 0.000 of all sentences) -- share of questions |
| q.embedded | embedded questions | can you tell me what X is | can you tell me what the capital of egypt is | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.223 of questions (q.embedded; 0.014 of all sentences) -- rate over questions+statements (embedded questions mostly end with '.') |
| q.ellipsis | elliptical follow-ups | what about X? / and X? | what about frank? | core/session.py (conversation context, ellipsis) | 0.035 of questions (q.elliptical; 0.002 of all sentences) -- share of questions |
| q.tag | tag questions | statement + isn't it? | tokyo is the capital of japan, isn't it? | chat.py statement path (kb_constructions reader, filled-question check) | 0.020 of questions (q.tag; 0.001 of all sentences) -- share of questions |
| q.declarative | declarative (rising) questions | statement form + ? | the capital of brazil is brasilia? | chat.py statement path (kb_constructions reader, filled-question check) | 0.345 of questions (q.declarative; 0.022 of all sentences) -- share of questions; the cue also catches fragments |
| q.alternative | alternative questions | A or B? | is the capital of japan tokyo or kyoto | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary); chat.py statement path (kb_constructions reader, filled-question check) | 0.076 of questions (q.alternative; 0.005 of all sentences) -- share of questions |
| q.inverse_relation | relation asked from the other end | who is managed by X / which country has X as capital | who is managed by carol | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary); core/rephrase.py (one-edit spelling, did-you-mean) + core/synonyms.py | 0.149 (voice.passive) -- rate is the passive cue (inverse questions are mostly passive or 'has X as') |

### clause linkage

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| clause.coord_vp | coordinated verb phrases (shared subject) | X washed A and peeled B | Ines washed the apples and peeled the pears. | core/events.py + emergence/kb_events.py (event memory) | 0.088 (clause.coord_vp) |
| clause.coord_clauses | coordinated clauses | X did A, and Y did B | Ali fed the goats, and his wife milked the cows. | core/events.py + emergence/kb_events.py (event memory) | 0.298 (clause.coord_clauses) |
| clause.temporal_sub | temporal subordinate clauses (when/after/before) | When the bell rang, ... | When the bell rang, the children ran outside. | core/events.py + emergence/kb_events.py (event memory) | 0.179 (clause.subordination) |
| clause.open_class_connective | connectives outside the closed class (until, since, across, near) | prepositions/conjunctions rarer than the 200 commonest symbols | Max waited until the rain stopped. | core/events.py + emergence/kb_events.py (event memory) | 0.117 (clause.open_class_connective) |
| clause.relative_subject | subject relative clauses | the boy who broke the window | The boy who broke the window ran away. | core/events.py + emergence/kb_events.py (event memory) | 0.095 (clause.relative_wh) |
| clause.relative_object | object relative clauses | the cake that Mia baked | The cake that Mia baked was delicious. | core/events.py + emergence/kb_events.py (event memory) | 0.026 (clause.relative_that) |
| clause.reduced_relative | reduced relatives (participial modifiers) | the woman wearing a red coat | The woman wearing a red coat stole the bag. | core/events.py + emergence/kb_events.py (event memory) | 0.008 (clause.relative_reduced) |
| clause.complement_that | that-complement clauses | said that P / thought that P | Tom said that the bridge was closed. | core/events.py + emergence/kb_events.py (event memory) | 0.022 (clause.complement_that) |
| clause.direct_speech | direct speech with attribution | "...," said X | "The soup is cold," said Ada. | core/events.py + emergence/kb_events.py (event memory) | 0.249 (clause.direct_speech) |
| clause.purpose | purpose infinitives | went to the shop to buy milk | Lia went to the shop to buy milk. | core/events.py + emergence/kb_events.py (event memory) | 0.031 (clause.infinitive_purpose) |

### reference

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| ref.pronoun_gender | pronoun resolution needing gender/number | she after two names of different gender | Leo met Mia. She carried his bag. | core/events.py + emergence/kb_events.py (event memory) | 0.446 (ref.third_person_pronoun) -- rate = sentences with a third-person pronoun; competition between two antecedents is a fraction of these |
| ref.pronoun_object | object pronouns (it/him/them) | He adopted it. | Ken saw a puppy. He adopted it. | core/events.py + emergence/kb_events.py (event memory) | 0.232 (ref.object_pronoun) |
| ref.reflexive | reflexives | himself/herself | Zoe cut herself on the glass. | core/events.py + emergence/kb_events.py (event memory) | 0.065 (ref.reflexive) |
| ref.possessive_pronoun | independent possessive pronouns | mine, hers, theirs | Lily lent him hers. | core/events.py + emergence/kb_events.py (event memory) | 0.010 (ref.possessive_pronoun) |
| ref.one_anaphora | one-anaphora | a green one | Tom gave her a green one. | core/events.py + emergence/kb_events.py (event memory) | 0.010 (ref.one_anaphora) |
| ref.vp_ellipsis | VP ellipsis | Joe did too | Mara bought a ticket, and Joe did too. | core/events.py + emergence/kb_events.py (event memory) | 0.045 (ref.vp_ellipsis) |
| ref.gapping | gapping | Ivan ordered soup, and Olga salad | Ivan ordered soup, and Olga salad. | core/events.py + emergence/kb_events.py (event memory) | 0.000 (ref.gapping) -- cue nearly blind; literature puts gapping well under 1 % |
| ref.cataphora | pronoun before its antecedent | Before he left, Tom locked the door. | Before he left, Tom locked the door. | core/events.py + emergence/kb_events.py (event memory) | 0.154 (ref.cataphora_sentence_initial_pronoun) -- rate = sentence-initial third-person pronouns (most are anaphoric; true cataphora is rarer) |
| ref.first_person | first/second person in a told story | I lent my bike to Omar. | I lent my bike to Omar. | core/events.py + emergence/kb_events.py (event memory) | 0.376 (ref.first_second_person) -- in a told story every I/my needs the teller as referent |

### quantification and comparison

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| quant.comparative | comparatives | more than, taller than | does alice earn more than ken | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary); core/events.py + emergence/kb_events.py (event memory) | 0.035 (quant.comparative) |
| quant.superlative | superlatives | highest, most | who has the highest salary in sales | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.035 (quant.superlative) |
| quant.only | focus particle only | Only Ravi finished. | Only Ravi finished the race. | core/events.py + emergence/kb_events.py (event memory) | 0.089 (quant.only_focus) |
| quant.universal | universal quantifiers | every, each, all | Every guest brought a gift. | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.117 (quant.universal) |
| quant.counting_condition | counting under a condition | how many X after Y | how many employees started after 2015 | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.038 (quant.counting) |
| quant.arithmetic_words | arithmetic in words | twice, six times seven | what is twice the salary of bob | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.013 (quant.arithmetic_words) -- book rate; in questions to a numbers world far higher |

### discourse and dialogue

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| disc.courtesy | greetings, please, thanks | social formulae around a question | Hello! Could you please tell me the capital of Brazil? | chat.py Door (sentence split, recall vs world answer); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.019 (disc.vocative_courtesy) -- book rate; in chat far higher |
| disc.user_belief | user states a (possibly false) belief | I think X, right? | I think the capital of Egypt is Alexandria, right? | chat.py statement path (kb_constructions reader, filled-question check) | 0.042 (disc.hedge) |
| disc.marker | discourse markers | well, so, now | Well, who is the manager of Ken? | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.023 (disc.marker) |
| disc.multi_sentence | several sentences in one turn | statement + question | My name is Sam. What is the capital of Italy? | chat.py Door (sentence split, recall vs world answer) | 0.129 (orth.long_sentence) -- proxy only |
| disc.correction | user corrections | no, I meant X | no, I meant Ken | core/session.py (conversation context, ellipsis) | 0.023 (disc.marker) -- no corpus cue; chat-specific |
| disc.story_world_collision | story names that are also world entities | a story about Alice and Bob while the records world holds alice and bob | Alice gave Bob a present. | chat.py Door (sentence split, recall vs world answer) | 0.016 (np.world_name) -- sentences naming something a world holds (11 employee names + fixture places and works) |
| disc.topic_continuity | topic continuity across sentences | a character carried by pronouns across sentences | Grace planted roses. Two weeks later she sold them. | core/events.py + emergence/kb_events.py (event memory) | 0.154 (ref.cataphora_sentence_initial_pronoun) |

### lexical semantics

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| lex.synonym_verb | verb synonymy between story and question | purchased / buy, repaired / fixed | Pam purchased a lamp. What did Pam buy? | core/events.py + emergence/kb_events.py (event memory) (dictionary sameness) | 0.074 (lex.converse_pairs) -- no cue; any question not echoing the story verb |
| lex.synonym_noun | noun synonymy in world questions | wage/pay for salary | what is the wage of alice | core/rephrase.py (one-edit spelling, did-you-mean) + core/synonyms.py | 0.074 (lex.converse_pairs) -- no cue |
| lex.converse | converse relations | sell/buy, manager/reports to | Mia sold her bike to Tom. Who bought it? | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.074 (lex.converse_pairs) |
| lex.hypernym | hypernymy (collie -> dog) | a question names a superordinate | A collie chased the sheep. What did the dog chase? | core/events.py + emergence/kb_events.py (event memory) | 0.074 (lex.converse_pairs) -- no cue |
| lex.idiom | idioms and non-compositional phrasal verbs | kicked the bucket, gave up | Grandpa kicked the bucket. | core/events.py + emergence/kb_events.py (event memory) | 0.053 (lex.idiom) |
| lex.polysemy | polysemous words | bank, bat | what does bank mean | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) (dictionary) | 0.053 (lex.idiom) -- no cue; most frequent words are polysemous |

### inference

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| inf.consequence | event consequences | won the race -> came first; no info about losers | Juan won the race. | core/events.py + emergence/kb_events.py (event memory) | 0.045 (inf.cause) -- no direct cue |
| inf.temporal_order | temporal order | then / before / after | Kira ate breakfast. Then she went to school. | core/events.py + emergence/kb_events.py (event memory) | 0.082 (inf.temporal) |
| inf.cause | cause (because, so) | why something happened | The ice melted because the sun was hot. | core/events.py + emergence/kb_events.py (event memory) | 0.045 (inf.cause) |
| inf.state_from_event | states that follow from events | hid X under Y -> X is under Y; gave X to Y -> Y has X | Where is the key? | core/events.py + emergence/kb_events.py (event memory) | 0.082 (inf.temporal) -- no cue |
| inf.unasked | questions the story cannot answer | the right answer is to abstain | What color did Omar paint the door? | core/events.py + emergence/kb_events.py (event memory) | 0.045 (inf.cause) -- no cue; honesty test |

### orthography and noise

| id | phenomenon | definition | example | component | frequency |
|---|---|---|---|---|---|
| orth.typo | typing slips | one-edit misspellings | what is the captial of italy | core/rephrase.py (one-edit spelling, did-you-mean) + core/synonyms.py | 0.050 (estimate: share of chat turns with a slip (no corpus cue; typed chat, not edited books)) -- chat-specific; no corpus cue |
| orth.casing | casing (all caps, lower-case names) | WHO IS ..., tom | WHO IS THE MANAGER OF KEN | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary); core/events.py + emergence/kb_events.py (event memory) | 0.028 (orth.allcaps) |
| orth.missing_punct | missing punctuation / run-on text | no period, no question mark | Ava fed the cat then she washed the dishes | core/events.py + emergence/kb_events.py (event memory); core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.129 (orth.long_sentence) -- proxy |
| orth.abbreviation | abbreviations with a period | Dr. Patel, Mrs. Gomez: a period that does not end the sentence | Mrs. Gomez thanked Dr. Patel. | chat.py Door (sentence split, recall vs world answer); core/events.py + emergence/kb_events.py (event memory) | 0.028 (orth.abbreviation) |
| orth.apostrophe_missing | missing apostrophes | whats, alices | whats the capital of japan | core/rephrase.py (one-edit spelling, did-you-mean) + core/synonyms.py | 0.030 (morph.contraction_other) -- chat-specific |
| orth.noise_punct | repeated / stray punctuation | ?!!, ??? | capital of france??? | core/reason.py + chat.py worlds (records, sales, Wikidata fixture, dictionary) | 0.053 (disc.exclamative) |

## 4. Predictions (made before running; from the code reading in Section 1)

Story probes: `pred` = the event memory alone, `door` = the live door (stories marked door=yes run there; others only in the event memory). Question probes: the live door.

Predicted totals -- event memory: RIGHT 92, WRONG 30, SILENT 49 (of 171); door stories: RIGHT 29, WRONG 24, SILENT 20; question probes: RIGHT 38, WRONG 8, SILENT 19 (of 65).

### 4a. Story probes

| id | phenomenon | story / question | gold | pred | door | reason |
|---|---|---|---|---|---|---|
| S01.1 | morph.past_regular | Nadia painted the fence. Later Omar washed the car. // **Who painted the fence?** | nadia | RIGHT | RIGHT | -ed form in the verb table; agent = nearest noun run on the left |
| S01.2 | morph.past_regular | **What did Omar wash?** | car | RIGHT | RIGHT | agent run 'Later Omar' still contains omar; patient 'car' |
| S02.1 | morph.irregular | Kofi broke the vase. Then he swept the floor. // **Who broke the vase?** | kofi | RIGHT | -- | UniMorph lists broke -> break |
| S02.2 | morph.irregular | **What did Kofi sweep?** | floor | RIGHT | -- | 'he' (learned subject) -> last agent Kofi |
| S03.1 | morph.top200_verbs | Lena found a coin. She made a wish. // **What did Lena find?** | coin | RIGHT | RIGHT | events3 main-verb rule: a name right before a closed verb form makes an event |
| S03.2 | morph.top200_verbs | **What did Lena make?** | wish | SILENT | SILENT | 'made' after a pronoun and 'make' are closed-class: no event, no question lemma |
| S04.1 | morph.third_sg | Every morning Pablo feeds the chickens. His sister milks the cow. // **Who feeds the chickens?** | pablo | RIGHT | -- | -s form after a noun is a verb (events6 A); agent run 'Every morning Pablo' contains pablo |
| S04.2 | morph.third_sg | **What does Pablo's sister milk?** | cow | RIGHT | -- | agent 'sister' shares a content word |
| S05.1 | morph.noun_verb_homograph | Sara lost her watches. Her brother watches the kids. // **What did Sara lose?** | watches | RIGHT | -- | after 'her' a third-person form is a noun (events6 A) |
| S05.2 | morph.noun_verb_homograph | **Who watches the kids?** | brother | RIGHT | -- | after a noun the same form is a verb; question lemma watch |
| S06.1 | morph.contraction | Paco didn't see the deer. His dog saw it. // **Who saw the deer?** | dog | SILENT | -- | 'see' after 't' is closed-class (no event); 'saw it' finds no earlier patient -> see(dog, None) shares nothing with 'deer' |
| S06.2 | morph.contraction | **Did Paco see the deer?** | no | SILENT | -- | no event with Paco; polarity not represented |
| S07.1 | q.whose | Maya's dog chased the cat. // **Whose dog chased the cat?** | maya | SILENT | SILENT | agent run stops at 's: 'dog'; both roles filled, no adjunct to return |
| S07.2 | morph.possessive_s | **What did Maya's dog chase?** | cat | RIGHT | RIGHT | agent 'dog' shares a word; patient 'cat' |
| S08.1 | np.article | A dog found a bone. The dog buried the bone. // **What did the dog bury?** | bone | RIGHT | -- | plain transitive |
| S08.2 | np.article | **What did the dog find?** | bone | RIGHT | -- | 'found' after the noun 'dog' -> main-verb rule |
| S09.1 | np.adjective | The tall woman lifted the heavy box. // **Who lifted the box?** | woman | RIGHT | -- | noun run 'tall woman' |
| S09.2 | np.adjective | **What did the tall woman lift?** | box | RIGHT | -- | patient run 'heavy box' |
| S10.1 | np.compound | The fire truck blocked the bus stop. // **What blocked the bus stop?** | fire truck | RIGHT | -- | noun run keeps both nouns |
| S10.2 | np.compound | **What did the fire truck block?** | bus stop | RIGHT | -- | 'stop' is a base form, not finite -> noun |
| S11.1 | np.of_phrase | The captain of the ship rang the bell. // **Who rang the bell?** | captain | RIGHT | RIGHT | learned linker 'of' extends the run (events6 C) |
| S11.2 | np.of_phrase | **What did the captain of the ship ring?** | bell | RIGHT | RIGHT | agent run contains captain/ship |
| S12.1 | np.appositive | Sam, the old fisherman, caught a huge fish. // **Who caught a huge fish?** | sam, fisherman | RIGHT | RIGHT | one comma crossed; agent 'fisherman' |
| S12.2 | np.appositive | **What did Sam catch?** | fish | SILENT | SILENT | the name is not linked to 'fisherman': no role shares 'sam' |
| S13.1 | np.possessive_det | Lucas lost his keys. His mother found them under the sofa. // **Who found the keys?** | mother | SILENT | SILENT | 'found' is closed in the question; 'keys' is a verb form (key) -> the only lemma is 'key' |
| S13.2 | np.possessive_det | **Where did his mother find the keys?** | under the sofa, sofa | WRONG | WRONG | 'keys' is not content (verb form) -> patient not filled -> answers 'keys' |
| S14.1 | np.quantifier | Three boys climbed the hill. Each boy carried a flag. // **Who climbed the hill?** | boys | RIGHT | -- | agent run 'boys' |
| S14.2 | q.how_many | **How many boys climbed the hill?** | three, 3 | SILENT | -- | no count role; both roles filled, no adjunct |
| S14.3 | np.quantifier | **Who carried a flag?** | boy | RIGHT | -- | 'each' closed, skipped; agent 'boy' |
| S15.1 | np.numeral | Ana bought 12 apples and 3 pears. // **What did Ana buy?** | apples | RIGHT | -- | patient run '12 apples and 3 pears' |
| S15.2 | np.numeral | **How many apples did Ana buy?** | 12 | SILENT | -- | both roles filled, no adjunct |
| S16.1 | np.proper_name | Mary Ann Evans wrote a long novel. // **Who wrote a long novel?** | mary ann evans | RIGHT | -- | capitalised run kept whole |
| S16.2 | np.proper_name | **What did Mary Ann Evans write?** | novel | RIGHT | -- | 'long' closed, skipped |
| S17.1 | np.title | Captain Reyes steered the ship. Doctor Lim treated the sailors. // **Who steered the ship?** | reyes | RIGHT | -- | title + name is one noun run |
| S17.2 | np.title | **Who treated the sailors?** | lim | RIGHT | -- | same |
| S18.1 | np.frequent_noun | Ivan walked to the fair. A man sold him a horse. // **Who sold a horse?** | a man, man | WRONG | WRONG | 'man' is closed -> read as a pronoun -> last agent Ivan (honesty risk) |
| S18.2 | np.frequent_noun | **Who walked to the fair?** | ivan | RIGHT | RIGHT | plain |
| S19.1 | np.frequent_noun | A stranger knocked on the door. The stranger asked for water. // **Who asked for water?** | stranger | RIGHT | -- | 'water' closed so the question has no content; most recent 'ask' event |
| S19.2 | np.frequent_noun | **What did the stranger ask for?** | water | WRONG | -- | 'water' closed -> no patient -> falls back to last patient 'door' |
| S20.1 | np.coordination | Eva and Karl painted the barn. // **Who painted the barn?** | eva and karl | RIGHT | -- | learned coordinator 'and' extends the run |
| S20.2 | np.coordination | **What did Karl paint?** | barn | RIGHT | -- | agent run contains karl |
| S21.1 | verb.transitive | The cat scratched the girl. The girl cried. // **Who scratched the girl?** | cat | RIGHT | -- | patient filled -> agent |
| S21.2 | q.whom | **Whom did the cat scratch?** | girl | RIGHT | -- | agent filled -> patient |
| S21.3 | verb.transitive | **Who cried?** | girl | RIGHT | -- | no content -> most recent 'cry' agent |
| S22.1 | verb.intransitive_pp | The baby slept in the car. // **Where did the baby sleep?** | car | RIGHT | -- | PP object taken as patient (skips 'in the'); the answer is still the car |
| S22.2 | verb.intransitive_pp | **Who slept in the car?** | baby | RIGHT | -- | patient filled -> agent |
| S23.1 | verb.ditransitive | Mia gave Leo a book. // **What did Mia give Leo?** | book | RIGHT | RIGHT | agent+patient(Leo) filled -> adjunct 'a book' |
| S23.2 | verb.ditransitive | **Who gave Leo a book?** | mia | RIGHT | RIGHT | patient filled -> agent |
| S23.3 | verb.ditransitive | **What did Mia give?** | book | WRONG | WRONG | the recipient is stored as patient -> answers 'Leo' |
| S23.4 | inf.state_from_event | **Who has the book now?** | leo | SILENT | SILENT | 'has' closed; no lemma |
| S24.1 | verb.dative_alternation | Nora gave a scarf to her sister. // **Who did Nora give the scarf to?** | sister | RIGHT | -- | agent+patient filled -> adjunct 'to her sister' |
| S24.2 | verb.dative_alternation | **Who got the scarf?** | sister | SILENT | -- | converse verb 'get' has no event |
| S25.1 | verb.particle | Nina picked up the phone. Then she put down the cup. // **What did Nina pick up?** | phone | RIGHT | -- | particle is closed, skipped |
| S25.2 | verb.particle | **Who put down the cup?** | nina | RIGHT | -- | 'she' -> Nina |
| S26.1 | verb.light | Omar took a long walk by the river. // **Where did Omar walk?** | river | SILENT | -- | no 'walk' event |
| S26.2 | verb.light | **What did Omar take?** | walk | SILENT | -- | 'take' is closed-class -> no question lemma |
| S27.1 | verb.copula | Hana was a nurse. Her husband was a pilot. // **Who was a nurse?** | hana | SILENT | WRONG | be(Hana, nurse) is stored, but 'was' is closed so the question has no lemma |
| S27.2 | verb.copula | **What was Hana's husband?** | pilot | SILENT | WRONG | same; in the door the dictionary likely quotes a gloss instead |
| S28.1 | verb.existential | There was a well behind the house. A frog lived in the well. // **What was behind the house?** | well | SILENT | -- | 'There was' makes no event (no noun before 'was') |
| S28.2 | verb.existential | **Who lived in the well?** | frog | RIGHT | -- | 'well' closed -> no content -> most recent 'live' agent |
| S29.1 | verb.control | Sana wanted to learn the violin. // **What did Sana want to learn?** | violin | RIGHT | -- | infinitive event learn(Sana, violin) is most recent among equal scores |
| S30.1 | verb.control | Mira told Tomas to close the gate. // **Who did Mira tell to close the gate?** | tomas | RIGHT | RIGHT | tell(Mira, Tomas): agent filled -> patient |
| S30.2 | verb.control | **Who will close the gate?** | tomas | WRONG | WRONG | infinitive takes the clause's first agent (Mira): object control not modelled |
| S31.1 | verb.causative | Ella made her brother wash the dishes. // **Who washed the dishes?** | brother | SILENT | -- | bare 'wash' is read as a noun inside 'brother wash'; no wash event |
| S31.2 | verb.causative | **Who made her brother wash the dishes?** | ella | SILENT | -- | 'made' closed in the question; 'dishes' -> lemma dish |
| S32.1 | verb.perception | Lina heard the dog bark. // **Who heard the dog?** | lina | RIGHT | -- | patient run 'dog bark' contains dog |
| S32.2 | verb.perception | **What barked?** | dog | SILENT | -- | no bark event (bare form read as a noun) |
| S33.1 | voice.passive_by | The window was broken by a stone. // **What broke the window?** | stone | RIGHT | RIGHT | stored reversed (agent=window, patient=stone); an active question reverses back |
| S33.2 | voice.passive_by | **What was broken?** | window | WRONG | WRONG | passive question returns the stored patient 'stone' (honesty risk) |
| S34.1 | voice.passive_agentless | The letters were burned in the stove. // **What was burned?** | letters | WRONG | -- | patient slot holds 'stove' (PP object) |
| S34.2 | voice.passive_agentless | **Where were the letters burned?** | stove | RIGHT | -- | same slip gives the right answer by accident |
| S35.1 | voice.get_passive | Pedro got bitten by a snake. // **What bit Pedro?** | snake | SILENT | -- | 'got' is not a learned auxiliary -> no 'bite' event |
| S35.2 | voice.get_passive | **Who got bitten?** | pedro | RIGHT | -- | event get(Pedro, bitten) |
| S36.1 | voice.passive_question | Grandpa planted the oak tree in 1950. // **When was the oak tree planted?** | 1950 | RIGHT | RIGHT | events5 E: passive question with patient named -> adjuncts |
| S36.2 | voice.passive_question | **By whom was the oak tree planted?** | grandpa | WRONG | WRONG | same rule returns the adjunct 'in 1950' |
| S37.1 | tam.progressive | Lara was reading a letter. Her cat was sleeping on the bed. // **What was Lara reading?** | letter | RIGHT | -- | auxiliary + participle -> event |
| S37.2 | tam.progressive | **Where was the cat sleeping?** | bed | RIGHT | -- | PP object as patient |
| S38.1 | tam.perfect | Tom has fixed the roof. // **What has Tom fixed?** | roof | RIGHT | -- | 'has' skipped in the agent search |
| S38.2 | tam.perfect | **Who has fixed the roof?** | tom | SILENT | -- | 'has' + participle in the QUESTION reads as passive (events5 E); patient named, no adjunct -> nothing |
| S39.1 | tam.future | Tomorrow Ada will visit her aunt. // **Who will Ada visit?** | aunt | SILENT | -- | an infinitive event in the first sentence takes no agent (none before it) |
| S40.1 | tam.future | Ada cooked dinner. Later she will wash the plates. // **Did Ada wash the plates?** | no, not yet, will | WRONG | WRONG | future stored as a plain event; answers 'plates' |
| S41.1 | tam.modal_epistemic | Inspector Ross searched the house. The thief may have taken the ring. // **Who took the ring?** | thief | WRONG | WRONG | 'thief' 2 closed symbols away; 'have' read as a pronoun -> last agent Inspector Ross (honesty risk) |
| S41.2 | tam.modal_epistemic | **What did Inspector Ross search?** | house | RIGHT | RIGHT | plain |
| S42.1 | tam.conditional | If Leo wins, his father will buy a boat. // **Who will buy a boat?** | father | WRONG | -- | infinitive takes the sentence's first agent Leo |
| S42.2 | tam.conditional | **Did his father buy a boat?** | no, not yet, if | WRONG | -- | patient filled -> agent 'Leo' |
| S43.1 | tam.counterfactual | If Ben had studied, he would have passed the exam. // **Who passed the exam?** | @ABSTAIN, nobody, no one | WRONG | WRONG | pass(Ben, exam) stored as fact (honesty risk) |
| S43.2 | tam.counterfactual | **Did Ben pass the exam?** | no | SILENT | SILENT | both roles filled, no adjunct |
| S44.1 | tam.tense_mismatch | Ivy plays the piano every evening. // **Who played the piano?** | ivy | RIGHT | -- | lemma matching across tenses |
| S44.2 | tam.tense_mismatch | **What does Ivy play?** | piano | RIGHT | -- | patient run 'piano every evening' contains piano |
| S45.1 | neg.not | Rosa cooked dinner. She didn't eat the soup. // **Who ate the soup?** | @ABSTAIN, nobody, no one | WRONG | WRONG | 't' is a learned marker -> eat(Rosa, soup) stored as fact (honesty risk) |
| S45.2 | neg.not | **Did Rosa eat the soup?** | no | SILENT | SILENT | both roles filled, no adjunct |
| S46.1 | neg.never | Kai never visited Lima. // **Who visited Lima?** | never, nobody, no one | RIGHT | -- | 'never' is not closed -> agent run 'Kai never'; the reply happens to say 'never' |
| S46.2 | neg.never | **Did Kai visit Lima?** | no | SILENT | -- | both roles filled, no adjunct |
| S47.1 | neg.no_det | No guest drank the wine. // **Who drank the wine?** | no guest, nobody, no one | WRONG | WRONG | 'no' closed, dropped -> agent 'guest' (honesty risk) |
| S48.1 | neg.no_det | Nobody opened the gift. // **Who opened the gift?** | nobody, no one | RIGHT | -- | 'Nobody' is not closed -> agent 'Nobody' |
| S49.1 | q.which | Two dogs ran into the yard. The black dog dug a hole. // **Which dog dug a hole?** | black | SILENT | -- | agent 'black dog' and patient both filled; no adjunct |
| S50.1 | q.where | Bea hid the key under the mat. // **Where did Bea hide the key?** | mat | RIGHT | RIGHT | adjunct 'under the mat' |
| S50.2 | inf.state_from_event | **Where is the key?** | mat | SILENT | SILENT | 'is' closed; no lemma |
| S51.1 | q.when | On Sunday the family visited the zoo. // **When did the family visit the zoo?** | sunday | SILENT | SILENT | 'family' closed -> agent None; fronted time phrase not an adjunct |
| S52.1 | q.why | Tim stayed home because he was sick. // **Why did Tim stay home?** | sick | RIGHT | RIGHT | adjunct scan picks up 'he was sick' |
| S53.1 | q.why | The road was closed, so Dan took the bus. // **Why did Dan take the bus?** | closed | SILENT | -- | 'take' closed in the question -> no lemma |
| S54.1 | q.how_manner | Rita opened the jar with a knife. // **How did Rita open the jar?** | knife | RIGHT | -- | adjunct 'with a knife' |
| S55.1 | q.how_manner | Leo won the race easily. // **How did Leo win the race?** | easily | SILENT | -- | 'easily' joins the patient run; no adjunct left |
| S56.1 | clause.coord_vp | Ines washed the apples and peeled the pears. // **Who peeled the pears?** | ines | RIGHT | -- | previous patient is not the next doer (events rule) -> shared agent |
| S56.2 | clause.coord_vp | **What did Ines peel?** | pears | RIGHT | -- | plain |
| S57.1 | clause.coord_clauses | Ali fed the goats, and his wife milked the cows. // **Who milked the cows?** | wife | RIGHT | RIGHT | agent run 'wife' |
| S57.2 | clause.coord_clauses | **What did Ali feed?** | goats | RIGHT | RIGHT | plain |
| S58.1 | clause.temporal_sub | When the bell rang, the children ran outside. // **Who ran outside?** | children | RIGHT | -- | comma bounds the clause |
| S58.2 | clause.temporal_sub | **What rang?** | bell | RIGHT | -- | most recent 'ring' agent |
| S59.1 | clause.temporal_sub | After Nora finished her homework, she called her friend. // **When did Nora call her friend?** | homework | SILENT | SILENT | 'called' is closed-class after a pronoun -> no call event at all |
| S60.1 | clause.open_class_connective | Max waited until the rain stopped. // **Who waited?** | max | RIGHT | -- | plain |
| S60.2 | clause.open_class_connective | **What did Max wait for?** | rain | WRONG | -- | 'until' read as a noun -> patient 'until' |
| S61.1 | clause.relative_subject | The teacher looked outside. The boy who broke the window ran away. // **Who broke the window?** | boy | WRONG | WRONG | 'who' is a learned subject -> resolved to last agent 'teacher' (honesty risk) |
| S61.2 | clause.relative_subject | **Who ran away?** | boy | WRONG | WRONG | agent 'window' = previous patient -> previous agent 'teacher' |
| S62.1 | clause.relative_object | The cake that Mia baked was delicious. // **What did Mia bake?** | cake | WRONG | WRONG | patient search goes right: 'delicious' |
| S62.2 | clause.relative_object | **Who baked the cake?** | mia | SILENT | SILENT | no role contains 'cake' |
| S63.1 | clause.reduced_relative | The woman wearing a red coat stole the bag. // **Who stole the bag?** | woman | WRONG | -- | nearest noun run on the left is 'red coat' (honesty risk) |
| S63.2 | clause.reduced_relative | **What was the woman wearing?** | red coat, coat | SILENT | -- | 'wearing' without an auxiliary makes no event |
| S64.1 | clause.complement_that | Tom said that the bridge was closed. // **What did Tom say?** | bridge was closed | WRONG | WRONG | say(Tom, bridge): the clause is cut to its first noun |
| S64.2 | clause.complement_that | **Was the bridge closed?** | said, tom | SILENT | SILENT | close(bridge) has no patient or adjunct to return |
| S65.1 | clause.direct_speech | "The soup is cold," said Ada. // **Who said the soup is cold?** | ada | SILENT | SILENT | 'said' after a quote: no noun before it, closed -> no event; question has no lemma |
| S66.1 | clause.direct_speech | "I saw a wolf," cried the boy. // **Who saw a wolf?** | boy | SILENT | -- | 'I' has no referent; 'the boy' is read as the patient of 'cried' |
| S67.1 | clause.purpose | Lia went to the shop to buy milk. // **Why did Lia go to the shop?** | buy milk | RIGHT | -- | adjunct 'to buy milk' |
| S67.2 | clause.purpose | **What did Lia buy?** | milk | RIGHT | -- | infinitive event buy(Lia, milk) |
| S68.1 | ref.pronoun_gender | Leo met Mia at the station. She carried his bag. // **Who carried the bag?** | mia | WRONG | WRONG | pronoun = last agent (Leo); gender not used (honesty risk) |
| S68.2 | ref.pronoun_gender | **Where did Leo meet Mia?** | station | RIGHT | RIGHT | adjunct 'at the station' |
| S69.1 | ref.pronoun_object | Ken saw a puppy. He adopted it. // **What did Ken adopt?** | puppy | RIGHT | -- | object pronoun -> last patient |
| S69.2 | ref.pronoun_object | **Who adopted the puppy?** | ken | RIGHT | -- | patient filled -> agent |
| S70.1 | ref.reflexive | Zoe cut herself on the glass. // **Who did Zoe cut?** | herself, zoe | RIGHT | -- | 'herself' not closed -> patient 'herself' |
| S70.2 | ref.reflexive | **What did Zoe cut herself on?** | glass | RIGHT | -- | both roles filled -> adjunct 'on the glass' |
| S71.1 | ref.possessive_pronoun | Sam lost his pen, so Lily lent him hers. // **What did Lily lend Sam?** | pen | WRONG | -- | patient 'hers' returned unresolved |
| S71.2 | ref.possessive_pronoun | **Who lent Sam a pen?** | lily | SILENT | -- | no 'lend' role contains sam or pen |
| S72.1 | ref.one_anaphora | Kim wanted a red apple, but Tom gave her a green one. // **What did Tom give Kim?** | green apple, green one | WRONG | -- | 'one' closed -> patient 'green' |
| S72.2 | ref.one_anaphora | **Who gave Kim an apple?** | tom | SILENT | -- | 'apple' not in the give event |
| S73.1 | ref.vp_ellipsis | Mara bought a ticket, and Joe did too. // **Who else bought a ticket?** | joe | WRONG | WRONG | only buy(Mara, ticket) exists -> 'Mara' |
| S73.2 | ref.vp_ellipsis | **Did Joe buy a ticket?** | yes | WRONG | WRONG | patient filled -> agent 'Mara' |
| S74.1 | ref.gapping | Ivan ordered soup, and Olga salad. // **What did Olga order?** | salad | SILENT | -- | no verb in the second conjunct |
| S74.2 | ref.gapping | **What did Ivan order?** | soup | RIGHT | -- | plain |
| S75.1 | ref.cataphora | Before he left, Tom locked the door. // **Who left?** | tom | SILENT | -- | 'he' resolves backward only (no earlier agent) -> agent None |
| S75.2 | ref.cataphora | **Who locked the door?** | tom | RIGHT | -- | plain |
| S76.1 | ref.first_person | I lent my bike to Omar. // **What did I lend Omar?** | bike | SILENT | SILENT | 'I' resolves to no one -> agent None; no role shares 'omar' except an adjunct, and the agent is empty |
| S76.2 | ref.first_person | **Who has my bike?** | omar | SILENT | SILENT | 'has' closed |
| S77.1 | quant.comparative | Ana is taller than Ben. // **Who is taller?** | ana | SILENT | -- | copula and 'taller' make no event |
| S78.1 | quant.only | Only Ravi finished the race. // **Who finished the race?** | ravi | RIGHT | -- | 'only' closed, skipped |
| S78.2 | quant.only | **Did Sita finish the race?** | no | WRONG | -- | patient filled -> agent 'Ravi' (no polarity) |
| S79.1 | quant.universal | Every guest brought a gift. // **Who brought a gift?** | guest | RIGHT | -- | agent run 'Every guest' |
| S80.1 | disc.story_world_collision | Alice gave Bob a present. // **What did Alice give Bob?** | present | RIGHT | WRONG | event memory alone is right |
| S80.2 | disc.story_world_collision | **Who gave Bob a present?** | alice | RIGHT | WRONG | door: the records world reads 'bob' and answers cleanly (e.g. his manager), overriding the recall |
| S81.1 | disc.topic_continuity | Grace planted roses. Two weeks later she sold them at the market. // **Who sold the roses?** | grace | RIGHT | RIGHT | 'she' -> Grace; 'them' -> roses |
| S81.2 | disc.topic_continuity | **Where did Grace sell the roses?** | market | WRONG | WRONG | 'roses' is a verb form (not content) -> answers the patient 'roses' |
| S82.1 | lex.synonym_verb | Pam purchased a lamp. Jon repaired the fence. // **What did Pam buy?** | lamp | RIGHT | RIGHT | dictionary sameness buy = purchase (events2) |
| S82.2 | lex.synonym_verb | **Who fixed the fence?** | jon | RIGHT | RIGHT | fix = repair |
| S83.1 | lex.converse | Mia sold her bike to Tom. // **Who bought Mia's bike?** | tom | SILENT | SILENT | no 'buy' event; converse not known |
| S83.2 | lex.converse | **Who sold the bike?** | mia | RIGHT | RIGHT | plain |
| S84.1 | lex.hypernym | A collie chased the sheep. // **What did the dog chase?** | sheep | SILENT | -- | 'dog' shares no role word |
| S84.2 | lex.hypernym | **What chased the sheep?** | collie | RIGHT | -- | plain |
| S85.1 | lex.idiom | Grandpa kicked the bucket last winter. // **Did Grandpa die?** | yes | SILENT | SILENT | no 'die' event |
| S85.2 | lex.idiom | **When did Grandpa die?** | last winter, winter | SILENT | SILENT | same |
| S86.1 | lex.idiom | Ravi gave up smoking. // **Did Ravi stop smoking?** | yes | SILENT | -- | no 'stop' event |
| S88.1 | inf.consequence | Juan won the race. // **Who lost the race?** | @ABSTAIN | RIGHT | RIGHT | no 'lose' event -> abstains (correct) |
| S88.2 | inf.consequence | **Who came first?** | juan | SILENT | SILENT | no 'come' event; consequence not inferred |
| S89.1 | inf.temporal_order | Kira ate breakfast. Then she went to school. // **Where did Kira go after breakfast?** | school | RIGHT | RIGHT | go(Kira, school): agent filled -> patient |
| S89.2 | inf.temporal_order | **What did Kira do before school?** | breakfast | SILENT | SILENT | 'do' closed; no lemma |
| S90.1 | inf.cause | The ice melted because the sun was hot. // **Why did the ice melt?** | sun was hot, hot | WRONG | -- | 'because' closed, skipped -> patient 'sun' |
| S90.2 | inf.cause | **What melted?** | ice | RIGHT | -- | plain |
| S91.1 | inf.unasked | Omar painted the door. // **What color did Omar paint the door?** | @ABSTAIN | RIGHT | RIGHT | both roles filled, no adjunct -> abstains |
| S91.2 | inf.unasked | **Who painted the window?** | @ABSTAIN | RIGHT | RIGHT | no role shares 'window' -> abstains |
| S92.1 | orth.casing | the dog bit tom. // **who bit tom?** | dog | RIGHT | -- | the reader does not need capitals |
| S93.1 | orth.missing_punct | Ava fed the cat then she washed the dishes // **Who washed the dishes?** | ava | RIGHT | RIGHT | 'she' -> Ava; 'dishes' as noun after 'the' |
| S94.1 | orth.abbreviation | Dr. Patel examined the patient. Mrs. Gomez thanked Dr. Patel. // **Who examined the patient?** | patel | RIGHT | RIGHT | split after 'Dr.' still leaves 'Patel examined the patient.' |
| S94.2 | orth.abbreviation | **Who did Mrs. Gomez thank?** | patel | WRONG | WRONG | split after 'Dr.' -> patient 'Dr' |

### 4b. Question probes (one live door, in order)

| id | phenomenon | setup | question | gold | pred | reason |
|---|---|---|---|---|---|---|
| Q001 | morph.contraction |  | **what's the capital of egypt** | cairo | RIGHT | 's splits off as a common symbol; capital+egypt read by the Wikidata fixture |
| Q002 | morph.possessive_s |  | **what is ken's salary** | 110 | RIGHT | 's is a common symbol; salary+ken read by the records table |
| Q003 | morph.derivation |  | **what does kindness mean** | @DICT | RIGHT | listed word: the dictionary world quotes its gloss |
| Q004 | morph.derivation |  | **what does unbloggable mean** | @ABSTAIN | RIGHT | nonce derivation: no gloss, no one-edit neighbour -> abstains (correct) |
| Q005 | morph.degree_forms |  | **which employee has the biggest salary** | dave | SILENT | 'biggest' unread; at best a did-you-mean offer for 'largest'/'highest' |
| Q006 | morph.degree_forms |  | **who earns the least** | heidi | SILENT | 'earns' and 'least' unread |
| Q007 | tam.imperative |  | **Tell me the capital of Japan** | tokyo | RIGHT | imperative words are not read; capital+japan cover the turn |
| Q008 | tam.imperative |  | **Give me the salary of Grace** | 95 | RIGHT | salary+grace read by records |
| Q009 | neg.world |  | **how many employees are not in support** | 9 | WRONG | 'not' is a common symbol, ignored -> counts support (2) |
| Q010 | neg.world |  | **what is the total salary outside engineering** | 1100 | WRONG | 'outside' unread; total salary in engineering (380) or overall (1480) |
| Q011 | q.yes_no |  | **is tokyo the capital of japan** | yes | RIGHT | echo answer + CHECK -> Yes |
| Q012 | q.yes_no |  | **is rome the capital of japan** | no | RIGHT | CHECK contradicted by Tokyo -> No |
| Q013 | q.who_subject |  | **who wrote hamlet** | shakespeare | SILENT | 'wrote' is not a property label of the fixture; at most a did-you-mean |
| Q014 | q.who_subject |  | **who directed jaws** | spielberg | SILENT | 'directed' is 2 edits from 'director' |
| Q015 | q.what_object |  | **what currency does japan use** | yen | RIGHT | currency+japan cover the content; 'use' closed |
| Q016 | q.what_object |  | **what language do people speak in brazil** | portuguese | SILENT | 'language' alone may not map to 'official language'; 'speak' unread |
| Q017 | q.whom |  | **whom does carol manage** | bob | WRONG | 'manage' one edit from 'manager' -> manager of carol = dave (inverse lost) |
| Q018 | q.whose |  | **whose manager is frank** | erin, grace | WRONG | reads manager+frank -> manager of frank = dave |
| Q019 | q.which |  | **which department is in berlin** | research | RIGHT | records: department filtered by city |
| Q020 | q.where |  | **where was napoleon born** | ajaccio | SILENT | 'born' is not 'place of birth' |
| Q021 | q.when |  | **when did judy start** | 2012 | RIGHT | records 'start' column |
| Q022 | q.how_many |  | **how many people work in sales** | 2 | RIGHT | 'people','work' closed; COUNT over sales |
| Q023 | q.embedded |  | **can you tell me what the capital of egypt is** | cairo | RIGHT | politeness frame ignored; capital+egypt |
| Q024 | q.embedded |  | **do you know who directed jaws** | spielberg | SILENT | 'directed' unread |
| Q025 | q.ellipsis | what is the salary of alice | **what about frank?** | 130 | RIGHT | context: previous structure with frank substituted |
| Q026 | q.ellipsis | what is the capital of japan | **and italy?** | rome | RIGHT | same |
| Q027 | q.tag |  | **tokyo is the capital of japan, isn't it?** | yes | RIGHT | statement check -> Yes |
| Q028 | q.tag |  | **alice works in sales, doesn't she?** | no, engineering | SILENT | records facts are not in the statement store |
| Q029 | q.declarative |  | **the capital of brazil is brasilia?** | yes | WRONG | filled check compares 'brasilia' with the label 'Brasilia' with an accent: likely a No (diacritic mismatch) |
| Q030 | q.declarative |  | **bob earns 150?** | yes | SILENT | 'earns' unread |
| Q031 | q.alternative |  | **is the capital of japan tokyo or kyoto** | tokyo | RIGHT | capital of japan read; Tokyo stated |
| Q032 | q.alternative |  | **is alice in engineering or sales** | engineering | SILENT | two filters, no structure |
| Q033 | q.inverse_relation |  | **who is managed by carol** | bob | WRONG | 'managed' read as 'manager' (one edit) -> manager of carol = dave (honesty risk) |
| Q034 | q.inverse_relation |  | **which country has paris as its capital** | france | RIGHT | country of paris = France, by luck of the composition |
| Q035 | quant.comparative |  | **does alice earn more than ken** | yes | SILENT | 'earn','more','than' unread; no comparison structure |
| Q036 | quant.superlative |  | **who has the highest salary in sales** | frank | RIGHT | taught 'which employee has the highest' shape |
| Q037 | quant.superlative |  | **which product has the highest price** | doohickey | RIGHT | sales table argmax |
| Q038 | quant.universal |  | **what is the salary of each employee in support** | 70, 75 (all) | SILENT | list-of-values over a filter has no structure |
| Q039 | quant.counting_condition |  | **how many employees started after 2015** | 5 | WRONG | 'after' comparison not read; counts something else |
| Q040 | quant.counting_condition |  | **how many departments are in lisbon** | 1 | RIGHT | COUNT with city filter |
| Q041 | quant.arithmetic_words |  | **what is twice the salary of bob** | 300 | SILENT | 'twice' unread (the exec world knows 'double') |
| Q042 | quant.arithmetic_words |  | **what is six times seven** | 42 | SILENT | number words are not read as numbers |
| Q043 | disc.courtesy |  | **Hello! Could you please tell me the capital of Brazil?** | brasilia, brasília | RIGHT | sentences split; courtesy words not content |
| Q044 | disc.courtesy |  | **thanks, and what is the currency of brazil** | real | RIGHT | currency+brazil read |
| Q045 | disc.user_belief |  | **I think the capital of Egypt is Alexandria, right?** | cairo, no | RIGHT | statement check contradicts with Cairo |
| Q046 | disc.user_belief |  | **maybe ken's salary is 200?** | 110, no | SILENT | records facts not in the statement store |
| Q047 | disc.marker |  | **Well, who is the manager of Ken?** | bob | RIGHT | 'well' closed; manager+ken |
| Q048 | disc.marker |  | **So what is the city of the sales department?** | rome | RIGHT | city + sales |
| Q049 | disc.multi_sentence |  | **My name is Sam. What is the capital of Italy?** | rome | RIGHT | each sentence answered; the second is the question |
| Q050 | disc.multi_sentence |  | **I work in sales. How many employees are in my department?** | 2 | WRONG | 'my department' not linked to sales -> counts all employees |
| Q051 | disc.correction | what is the salary of bob | **no, I meant Ken** | 110 | SILENT | 'no' is feedback on the last answer; 'meant' unread |
| Q052 | disc.correction | what is the capital of france | **sorry, I meant Spain** | madrid | RIGHT | context ellipsis with spain substituted |
| Q053 | lex.synonym_noun |  | **what is the wage of alice** | 120 | SILENT | did-you-mean offer at best |
| Q054 | lex.synonym_noun |  | **what is the pay of erin** | 90 | SILENT | same |
| Q055 | lex.converse |  | **who reports to bob** | alice, ken | SILENT | 'reports' unread |
| Q056 | lex.polysemy |  | **what does bank mean** | @DICT | RIGHT | dictionary quotes the senses |
| Q057 | lex.polysemy |  | **what is a bat** | @DICT | RIGHT | same |
| Q058 | orth.typo |  | **what is the captial of italy** | rome | RIGHT | one swap -> 'capital', unique |
| Q059 | orth.typo |  | **waht is the salray of bob** | 150 | RIGHT | 'salray' -> 'salary' unique; 'waht' not content |
| Q060 | orth.casing |  | **WHO IS THE MANAGER OF KEN** | bob | RIGHT | symbols are lower-cased |
| Q061 | orth.missing_punct |  | **capital of japan** | tokyo | RIGHT | fragment read by coverage |
| Q062 | orth.apostrophe_missing |  | **whats the capital of japan** | tokyo | RIGHT | coverage ignores the unread 'whats' |
| Q063 | orth.apostrophe_missing |  | **what is alices salary** | 120 | RIGHT | one edit 'alices' -> 'alice' |
| Q064 | orth.noise_punct |  | **what is the capital of japan ?!!** | tokyo | RIGHT | punctuation dropped by symbols() |
| Q065 | orth.noise_punct |  | **capital of france???** | paris | RIGHT | same |

## 5. Expected weak spots (theory, before the run)

- **Honesty risks the theory predicts (WRONG, not SILENT):** frequent nouns read as pronouns (*a man sold him a horse* -> the last agent sold it); *who* in relative clauses resolved to the last agent; negation, modality, conditionals and counterfactuals stored as facts; passive questions over passive stories; pronouns resolved without gender; the recipient of a double-object verb taken as the thing given; relation questions asked from the other end (*managed by*, *whose manager*) answered as the forward relation; *not* ignored in world questions.
- **Largest silent areas:** copula and existential sentences (20 % and 3 % of sentences), the commonest verbs (22 % of sentences contain one of *made, said, found, take, make, see, do, ...*), quotations and speaker attribution (25 % of sentences hold a quotation mark), counting, comparison, synonyms/converses/hypernyms, and every verb a world was not taught (*wrote, directed, born, earns*).
- **Frequency x failure** therefore points first at: the closed-class definition itself (frequent content words), copula/predication, pronoun resolution, quotations, polarity/modality, and passive voice -- not at the rarer constructions (gapping, one-anaphora, tag questions) that the battery happened to expose.

