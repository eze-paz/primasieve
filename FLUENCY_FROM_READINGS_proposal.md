# Fluency from the system's own verified readings (proposal, 2026-10-17; no runs)

## The observation
The AG chain (AG_STATUS.md) turns prose into verified slot lines: `WHO | DID | WHAT | WHERE | WHEN | WHY`, each
checked for word provenance, event parse and role order. At scale it has produced ~2,400 lines from 448 stories,
and it runs on any English text. Every kept line is paired with the human sentence it came from. That is a
**parallel corpus (meaning -> English) that the system builds itself**, as large as the text we feed it (the
21M Gutenberg tokens give millions of sentences; the chain is the bottleneck, ~1.3 min/story on CPU, hours on Colab).

Everything tried so far learned fluency from raw text (MDL forms, class bigrams, counts, 6M models, 0.4B as
proposer). Nothing learned the much smaller problem: **given a fixed meaning, say it in English**.

## Two untried mechanisms

### A. A tiny realiser trained on (slot line -> sentence)
- Model: a small seq2seq or decoder (1-10M params; the L-line showed 6M trains on CPU in hours) whose input is the
  slot line plus the previous sentence's slot line (for pronouns and links) and whose output is the human sentence.
- Data: the AG chain run over as much Gutenberg as Colab allows; only verified lines (provenance + parse + role check).
- Why it should work where the L-line did not: the realiser never has to know what to say or any fact; its whole
  job is inflection, function words, order, agreement and referring expressions, which 21M tokens of pairs cover far
  better than 21M tokens cover open prediction. TinyStories-scale models write fluent English when the content is
  constrained; here the content is given exactly.
- Verifier (keeps the honesty rule): **round trip.** Re-read the realiser's sentence with the same AG chain and
  require the same slot line (same lemma in DID, same heads in the filled slots). A sentence that reads back
  differently is rejected or quoted from the source instead. Confabulation stays 0 by construction, measured.
- Fluency score: R27's F2b in-context judge (stock 0.4B), plus the human-summary reference already built (P8).

### B. Retrieve-and-edit from the same corpus (no training)
- Index the human sentences by slot-line *shape* (DID lemma, which slots are filled, WHO type: name / pronoun /
  noun phrase). For a planned slot line, retrieve a human sentence of the same shape and substitute the content
  slots (with the determiner and preposition the source sentence carries, which fixed P1c/P1d's faults).
- Novelty is substitution into attested frames; the judge in LOOP it.9 charged rarity, not form, and F2b in context
  does not. This is the fallback when A is unsure, and the baseline A must beat.

## How it runs, step by step (worked example)
1. **Reading (exists today, AG chain).** Story sentence: "At dawn the baker wheeled the crate up the slipway."
   -> 0.4B proposes clauses, engine verifies provenance / parse / role order -> 1.5B writes the slot line, exact
   parse -> `the baker | wheeled | the crate | up the slipway | at dawn | -`. Stored as the pair (line, sentence),
   with the previous sentence's line beside it.
2. **Training (new).** A 1-10M-parameter encoder-decoder (or decoder with the line as prefix) learns
   line + previous line -> sentence over all stored pairs. Byte or word-piece tokens; CPU hours (L-line scale).
3. **Planning (exists, R27 planner).** The reply plan is a sequence of slot lines, e.g.
   `Teague | wheel | crate | slipway | dawn | -`, with the previous line for pronoun and link choice.
4. **Realisation (new).** The network writes "At dawn Teague wheeled the crate up the slipway."
5. **Round-trip check (new, uses the existing chain).** The sentence is read back by the same AG chain. Shown only
   if the re-read line matches the plan (DID lemma, filled heads). "The slipway wheeled Teague at dawn" reads back
   with a different WHO and is rejected.
6. **Fallback (new, no model).** On rejection, retrieve a human sentence with the same shape (DID lemma, filled
   slots, WHO type) from the stored pairs and substitute the content slots; if none, quote the source sentence.

## Is the realiser an LLM?
Strictly it is a neural sequence model trained by gradients (allowed since 2026-10-08), so a small language model.
It differs from an LLM on every axis the project cares about: 1-10M parameters, not billions; input is a formal
meaning line, not free text; it holds no facts (meaning is supplied, the corpus is Gutenberg prose); it never
decides what to say; every output is verified by the reader before it is shown. The 0.4B / 1.5B models remain
proposers inside the verified reading chain and the external judge; they never write a reply. Variant B needs no
trained model at all.

## Gates (to register before any code)
- F-A1: round-trip agreement >= 0.90 on held-out lines (the honesty gate; sentences failing it are never shown).
- F-A2: in-context judge (F2b) within 0.5 bits/word of the human sentence for the same line (R27's best so far:
  retellings 1.1-1.3 bits behind; G2b 0.90 behind at sentence level).
- F-A3: novelty >= 0.5 of word 3-grams versus the source sentence (so this is not copying).
- F-B1: retrieve-and-edit must be within 1 bit on F2b; A must beat B on F-A2 or it is not worth training.
- Kill: if round trip fails above 30 % with form >= 0.9, the chain's slot language is too coarse to carry meaning
  back out (it would show the AG representation is a reading aid, not a meaning representation).

## What it would unlock if it passes
Replies in the system's own words from any plan expressed in slot lines (R27 P2/P3/P7 all failed on exactly this),
with faithfulness guaranteed by the reader rather than by the writer, and no world facts in any trained weight.
What it would not unlock: content planning (R27 P10-P12 open) and dialogue beyond single facts.

## Cost
Chain over ~2,000 stories or ~1M Gutenberg sentences on Colab (days of GPU, not hours); realiser training on CPU
in hours; scoring with the existing R27 tooling. Proposal only; nothing started.
