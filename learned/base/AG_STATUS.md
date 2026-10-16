# The canonical-form line (AG) -- status 2026-10-16

Owner's idea (2026-10-15): the signal of a sentence is unique, its English renderings are not; converge each sentence
(and each question) onto one canonical form that keeps the signal, by a small model proposing and the engine
verifying, then reason over the canonical forms. Twenty registrations later (AG_prereg.md has every gate and number):

## The chain that works
1. Prose -> verified clauses. Stock RWKV-7 0.4B proposes short clauses per sentence; the engine keeps a clause only if
   its words come from the sentence, it is not a copy of context or a fragment, it parses to an event, and it does not
   swap agent and patient (ag3_canon.py / ag4_canon.py). Loops, inventions and swaps of the model are caught, not
   trusted. At scale (502 stories): 2,525 clauses, 1,426 of 1,577 events kept.
2. Clauses -> verified slot lines. RWKV-7 1.5B writes each clause as 'WHO | DID | WHAT | WHERE | WHEN | WHY', twice
   (clause alone; clause with its source sentence, which brings WHEN and WHY); exact parse, word provenance, pronoun
   WHO resolved to the last named WHO (ag10_slots.py).
3. Questions -> the same slot line with '?' in the asked slot; the formal language's own syntax decides which slot
   is asked (a bare 'Who' asks WHO, 'When did X ...' asks WHEN), so the proposer's inversions are corrected.
4. Answer = the asked slot of the first story line whose DID shares a lemma and whose other filled slots match.

## Numbers (untouched val_fresh2, 200 questions, nothing chosen on it)
| reader | right / wrong | precision | fitness |
|---|---|---|---|
| symbolic reader on raw prose (AG3 instrument) | 17 / 4 | 0.81 | +5 |
| same reader on the verified clauses (AG3) | 25 / 3 | 0.89 | +16 |
| slot lines from clauses (AG12) | 28 / 2 | 0.93 | +22 |
| AG12 + clause-with-sentence lines + regenerated question lines (AG15) | 34 / 4 | 0.89 | +22 |
| union of the clause reader and AG14 slot lines | 46 / 6 | 0.885 | +28 |
| thresholded 0.4B model answering the prose directly (B2b), same 200 | 64 / 13 | 0.83 | +25 |
Scale (1,800 untouched): clause reader on prose 156 / 50 (0.76) -> on clauses 207 / 60 (0.78); the slot-line chain is
running (about 60% of the stories done; one 1.5B model fits in memory, so runs are sequential).

## What the twenty tests settled
- Verified rewriting makes prose more readable to a symbolic engine, and loses only 7-9% of what a strong reader
  could answer (AG6). The gain holds at scale with lower precision than on the dev block.
- A learned translator in the middle (the AG1 tagger, 32 synthetic verbs) was the ceiling at every stage (AG4-AG9b);
  replacing it by a rigid formal language that the model writes directly, parsed exactly, was the breakthrough (AG10-12).
- The question side needs a proposer that can leave a blank (1.5B, not 0.4B) and a syntax rule for the asked slot.
- Failed and recorded: canonical text as a verifier substrate for the model's answers (AG5), verb similarity (AG7),
  hand parser fixes (AG8, precision drift), world-state rules over the slot lines (AG17: later transfers are missing),
  a third writing from raw sentences (AG18), the 1.5B clause loop (AG19 clauses are cleaner but fewer; AG20 chain loses).
- Reach is the limit: 34-46 of 200 answered. The remaining silences (AG15 audit): no slot line carries the question's
  verb (69: copular 'who was / who had' questions, paraphrases, clauses the loop dropped), slot mismatches (24),
  the asked slot empty (13).

## What would move it next
- The slot writer on the original sentences the clause loop kept as written (330 at scale) with the clause+sentence
  prompt, and copular lines in the few-shot: targets the 69 'no verb line' silences.
- A stronger proposer than 1.5B for the slot lines (not available on this machine; Colab).
- The honesty combination: the chain's answers (precision 0.89-0.93) as a route in the T22p policy, before the
  thresholded model, scored on the 1,800 under +1 / -3 against +620 (B2b combined).
