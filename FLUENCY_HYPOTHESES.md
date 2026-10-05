# FLUENCY -- what linguistics and neuroscience say is missing, and nine testable hypotheses (2026-10-05)

The owner's question: "something is missing for true fluency -- research linguistic theories or neuroscience and make
new hypotheses." This file reads the engine's own measured failures against what is known about how people produce and
understand language, and turns the gap into hypotheses that can be preregistered and killed, one gate each.

## 1. The engine's symptoms (measured, not guessed)

| symptom | where measured |
|---|---|
| The gloss reader is sound as a READER and unsound as a VOUCHER: patterns vouch for words they do not explain, and generation emits false sentences that pass the strict inverse | gloss_width_prereg.md |
| Prose reads at 0.34; "learning from novels remains closed under the honesty rule" | gloss_width_prereg.md |
| Generation yields labels (4-5 tokens) or, longest-first, false 7-token sentences | gloss_generate / gloss_width |
| A counting model PREDICTS well (content cloze 0.131 vs 0.036 left-only) but its "similar words" are related, not synonymous (0.026) | textmodel_prereg.md |
| 33 of 44 paraphrased questions answered directly were WRONG FACTS: a word only the dictionary defines is silently ignored | didyoumean_prereg.md, run 1 |
| Replies are correct but stiff: one fixed frame per verdict, evidence trailers on every answer | chat_prose_prereg.md, live chat |

## 2. What the research says (short)

1. **Language and thought are separate systems in the brain.** The language network is distinct from the systems used
   for reasoning, and people with severe aphasia still reason; language looks primarily like a tool for COMMUNICATION
   (Fedorenko, Piantadosi & Gibson, *Nature* 2024). Mahowald et al. (*Trends in Cognitive Sciences* 2024) split
   **formal** competence (getting the form right) from **functional** competence (using language to do things in the
   world) and show they rest on different mechanisms.
2. **Words and grammar use different memory systems.** Ullman's declarative/procedural model: the lexicon (arbitrary
   word-meaning pairs) is stored like facts, in temporal-lobe declarative memory; grammar (combining, inflecting,
   ordering) is a learned skill, in frontal/basal-ganglia procedural memory, with double dissociations between them.
3. **Grammar is made of chunks and constructions learned from use.** Usage-based linguistics (Bybee; Goldberg's
   construction grammar): frequent word sequences fuse into stored units, and grammar emerges as those chunks become
   schemas with open slots -- form-meaning pairs, not rules over words.
4. **Comprehension is prediction.** The N400 brain response shrinks the more predictable a word is; current accounts
   treat it as a (semantic) prediction error (Kutas & Federmeier 2011; Nour Eddine, Kuperberg et al. 2024). Learning is
   driven by being surprised.
5. **Every word must be integrated.** A word that cannot be given a role in the sentence's meaning produces a
   measurable integration failure (N400/P600 effects for anomalous or unintegrable words); linguistics states the same as
   the requirement that every argument receive a role.
6. **Speakers monitor themselves with their comprehension system.** In Levelt's model of speaking, a message is
   formulated into words and grammar, and the speaker's own comprehension system re-hears it and catches errors (the
   perceptual loop).
7. **Dialogue partners align.** Interlocutors automatically reuse each other's words and structures (priming at many
   levels), which simplifies both producing and understanding (Pickering & Garrod 2004, 2006).
8. **Fast episodes, slow consolidation.** Complementary learning systems: a fast episodic memory (hippocampus) records
   single events; a slow system (neocortex) extracts general patterns from replayed episodes (McClelland, McNaughton &
   O'Reilly 1995).
9. **Speakers say as much as the listener needs, no more.** Grice's maxims; the Rational Speech Act model: a speaker
   picks the utterance a modelled listener would interpret correctly at least cost.

## 3. The diagnosis in one sentence

**The engine treats language as thought.** It asks every WORD to answer to the truth checker, so it can learn grammar
only from sentences it can verify -- definitions -- and it can never learn the form of language from ordinary prose. The
brain does the opposite: a form system learns from everything heard, with no truth check at all, and honesty lives one
level up, in the PROPOSITIONS a sentence carries, checked by the thinking systems and by the speaker's own comprehension.

So the honesty rule should move **from tokens to propositions**: a sentence may use any wording learned from any text,
provided that when the engine's own reader reads the sentence back, the propositions it finds are exactly the verified
ones -- and every open-class word is accounted for by one of them.

## 4. Nine hypotheses (each: a theory, a symptom it explains, a mechanism, a test that can kill it)

### H1 -- Two systems: form learned freely, propositions checked (Fedorenko 2024; Mahowald 2024)
*Explains:* prose closed to learning; stiff replies. *Mechanism:* a FORM model learned from all local text (Wiktionary
examples, Alice in Wonderland, any prose): sentence skeletons with open slots, counted, no truth. A reply = a verified
message (the engine's propositions) poured into a skeleton; the engine's reader re-reads it (H7) and must recover
exactly the message. *Test:* replies over 60 engine-answered frames -- mean length, number of distinct skeletons used,
share of skeletons learned from prose rather than definitions; MISREPORT and CONFAB 0 by the re-read. *Kill:* no
skeleton learned from prose ever survives the re-read.

### H2 -- Open-class words are facts, closed-class words and constructions are skill (Ullman's declarative/procedural)
*Explains:* "reader sound, voucher unsound" -- the voucher treated "neighborhood" (a fact-bearing word) like "of" (a
skill word). *Mechanism:* split the vocabulary by distribution, not by a list: closed-class words are frequent and
occur beside very many different words (the text model's SPREAD count already measures this); open-class words are the
rest. Closed-class words and skeletons may be used freely; every open-class word in an output must be GROUNDED -- the
label of an entity in the message, or a word typed to a type that holds for the entity it describes. *Test:* rerun
gloss_width's longest-first generation under this voucher: its false sentences ("neighborhood of new orleans louisiana
portugal") -> 0, while coverage stays above the label baseline. *Kill:* the split cannot be found by distribution
(a function/content agreement with WordNet's closed classes below 0.9).

### H3 -- Every content word must be integrated, or the answer is partial (N400/P600; the role requirement)
*Explains:* the 33/44 silently wrong answers. *Mechanism:* comprehension accounts for every open-class word of the
turn (H2's split): read by a computing world, used by the answer's structure, or explicitly a name being asked about.
An answer that leaves one unintegrated is PARTIAL: "Alice's salary is 120, but I could not use 'threefold'." *Test:* the
G3 paraphrase set -> wrong facts 0 (from 33); the registered gates are rerun and every moved answer is listed and
explained. *Kill:* the rule makes more than 10 % of currently correct gate answers PARTIAL without an unread content
word to justify it.

### H4 -- Chunks from predictability (Saffran-style statistical learning; Bybee; N400 as prediction error)
*Explains:* prose reads at 0.34 -- multiword expressions ("prime minister", "in order to", "of or relating to") are read
word by word. *Mechanism:* where the text model predicts the next word unusually well (low surprise inside, high at the
edges), the sequence becomes a CHUNK: one unit for reading and for generation. *Test:* chunk inventory from the G4
counts; reading coverage of held-out prose and content cloze both rise; a knockout (shuffled corpus) yields no chunks.
*Kill:* coverage of prose does not move.

### H5 -- Synonymy is substitutability in the same slot, plus definitions that point at each other
*Explains:* G4's neighbours are related, not synonymous (0.026), so "did you mean" reaches only 8 %. *Mechanism:*
paradigmatic similarity = sharing two-sided slots (left AND right neighbour together), not single neighbours; plus
definitional cross-reference (each word appears in the other's definitions or synonyms list). *Test:* WordNet
synset-sharing among top-10 neighbours 0.026 -> >= 0.08; G3's D1 8 % -> >= 25 %. *Kill:* neither rises.

### H6 -- Align with the person (Pickering & Garrod)
*Explains:* replies ignore how the person phrased the question. *Mechanism:* realization prefers the person's own words
and the skeleton of their question ("the medium salary of erin" -> "Erin's medium salary is ..."), and after a
confirmed reading, keeps using the person's word, not the engine's. *Test:* share of the person's content words reused
in replies; the re-read still recovers the message exactly. *Kill:* alignment breaks the exact re-read more than 5 %.

### H7 -- The monitor is the reader (Levelt's perceptual loop)
*Explains:* generation either refuses (labels) or lies (false long sentences). *Mechanism:* generate MANY candidate
wordings (the form side may vary freely -- the owner's earlier "how it is said" split); the engine's own reader re-reads
each; keep only those whose read-back propositions equal the message and whose open-class words are all grounded (H2).
Temperature lives entirely before the monitor. *Test:* with the monitor, false sentences 0; without it (knockout), the
gloss_width false-sentence rate reappears. *Kill:* the monitor passes a sentence an independent audit finds false.

### H8 -- Consolidate episodes into rules (complementary learning systems)
*Explains:* every confirmed reading ("aggregate" = "total") stays one episode. *Mechanism:* a consolidation pass over
the session's confirmed episodes (readings, guesses, choices) extracts general patterns -- inflections ("aggregates"),
the same substitution in other constructions -- and holds them CONJECTURED until one predicts a new case (the existing
conjecture rule). *Test:* after consolidation, unseen variants of confirmed words are read without asking; wrong
generalisations are caught by denial. *Kill:* no consolidated rule ever predicts an unseen case.

### H9 -- Say what the listener needs (Grice; Rational Speech Act)
*Explains:* evidence trailers on every answer. *Mechanism:* among the monitored wordings (H7), choose the shortest one
the engine's own reader still maps back to the message UNIQUELY; evidence and sources move behind "why" (which the
transcript world already answers). *Test:* mean reply length down by >= 40 %; unique re-read 100 %; "why" recovers the
full evidence. *Kill:* the short forms become ambiguous to the engine's own reader.

## 5. Order, and why

1. **H3** first: it closes a soundness hole the paraphrase test exposed, and every later rung depends on the engine
   knowing which words it did not use.
2. **H2 + H7** together: the open/closed split and the monitor are the core of moving honesty from tokens to
   propositions. Gate: gloss_width's false sentences go to zero.
3. **H1**: then prose becomes learnable for FORM -- the first time the engine can learn from novels at all.
4. **H4, H5**: better units and better synonyms raise reading and "did you mean".
5. **H6, H9, H8**: alignment, brevity, consolidation -- what makes a conversation feel fluent.

## 6. What this would and would not give
Would: an engine that can learn wording from any text while every claim it makes is still checked -- fluent form,
honest content. Would not, by itself: open-ended reasoning, long-range discourse planning, or world knowledge beyond
what its sources hold. Those are the functional half (Mahowald's term), and they live in the reasoning engine, where
this project has always put them.

## Sources
- Fedorenko, Piantadosi & Gibson (2024), "Language is primarily a tool for communication rather than thought", *Nature*
  630: https://ideas.repec.org/a/nat/nature/v630y2024i8017d10.1038_s41586-024-07522-w.html ; summary:
  https://news.mit.edu/2024/what-is-language-for-0703
- Mahowald, Ivanova, Blank, Kanwisher, Tenenbaum & Fedorenko, "Dissociating language and thought in large language
  models", *Trends in Cognitive Sciences* 2024: https://arxiv.org/abs/2301.06627v1
- Ullman's declarative/procedural model: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8727903/ ;
  https://www.doi.org/10.1023/A:1005204207369
- Bybee, usage-based theory and chunking: https://ling.unm.edu/assets/documents/bybee2011ubtandgramtion.pdf ;
  https://ling.unm.edu/assets/documents/bybee2012domaingeneralprocesses.pdf
- N400 and prediction: https://pmc.ncbi.nlm.nih.gov/articles/PMC3657387 ;
  https://kuperberg.mgh.harvard.edu/wp-content/uploads/Nour-Eddine-Kuperberg-Cognition-2024.pdf
- Pickering & Garrod, interactive alignment: https://www.psy.gla.ac.uk/~simon/bbs-24.html
- From the literature, not fetched here: Levelt, *Speaking* (1989); McClelland, McNaughton & O'Reilly (1995),
  complementary learning systems; Frank & Goodman (2012), Rational Speech Act; Grice (1975); Saffran, Aslin & Newport
  (1996), statistical learning; Goldberg, *Constructions* (1995).

## 7. Results of the loop (2026-10-05) -- every hypothesis tested, one prereg each

| hypothesis | verdict | what stands | what failed |
|---|---|---|---|
| H3 integration (integrate_prereg.md) | NOT PASSED | paraphrase wrong facts **25 -> 0** | 16 % of correct answers owe a shape-read word (how / related / many / between) |
| H1+H2+H7 speak (speak_prereg.md) | **PASS** (amended) | wording learned with no truth check (88/159 skeletons from book quotations) stays true under the re-read: false assignments 56 % -> 0 | the reader is order-blind: 46 % of accepted wordings reverse the order |
| H6+H9 aligned replies (align_prereg.md) | NOT PASSED (58 % vs 60 %) | answers in the person's own words, 43 % of the old length, evidence still behind "why" (20/20) | coverage one point under the bar |
| H5 synonyms (synonyms_prereg.md) | NOT PASSED (24 % vs 25 %) | dictionary statements of sameness: "did you mean" 8 % -> 24 % | two-sided slots refuted (0.011) |
| H10 word order (wordorder_prereg.md, 4 runs) | NOT PASSED | licensing only attested attachments: reversed wordings **46 % -> 0 %**, chosen wordings read as English | coverage 10/18 from 96 questions; exposure from dictionary prose: **0 of 20,000 phrases readable** |
| H4 chunks (chunks_prereg.md) | NOT PASSED (2.7x vs 3x) | counting alone finds real units (united states, hong kong); none from shuffled text | a third are the corpus's boilerplate |
| H8 consolidation (consolidate_prereg.md) | NOT PASSED (run 1 invalid) | -- | spelling families are the wrong unit (1 %, 352/541 false offers) |

**The finding of the loop.** Every rung that produces language now keeps the engine honest -- nothing it says has been
false in any of these tests -- and the wording got shorter, aligned and partly learned from prose. Two walls remain, and
they are the same wall seen twice: the reader is order-blind (H10), and it can read almost no real text (H10d: 0 of
20,000 phrases). Fluent speech needs a monitor that understands sentences, and the monitor is the reader. **The next
campaign is comprehension: a reader of ordinary sentences, order-aware, learned from exposure** -- the place where the
brain's language network spends its millions of sentences, and where this engine has spent 96.

The live chat now has: the guesser, "did you mean" with dictionary synonyms, integration (H3), and answers in the
person's own words (H6).
