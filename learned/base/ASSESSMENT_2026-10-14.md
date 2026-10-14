# Is "competitive with LLMs" realistic? Assessment, 2026-10-14 (no runs; written from the registered record)

## Where the record puts us
| axis | ours | reference | source |
|---|---|---|---|
| next word, held-out paragraphs 500-999 | 7.1524 bits/word | RWKV-7 0.4B 6.7001 (same 50,114 predictions) | R25-co, R25-cs |
| gap over the week | 0.64 -> 0.62 -> 0.45 | each step smaller and dearer | R25-cs, cv, co |
| question panels, +1 / -3 / 0, 1,800 untouched | +288 (519 right / 77 wrong) | model ~70% right, never scored on this rule | R26 plan |
| clean once-only set val_fresh3 | trusted routes 43 / 13, precision 0.77, fitness +4 | model 127 / 200 | R25-final |
| B6 (sealed) | best 84, bar 85 | model 80 | R25-z |
| compute per bit | never measured | T31 registered, not run | R26 plan |

Three facts in the record decide the question:
1. Count-side work is saturated: 26 components, EM gives six of them all the weight (R25-cn); more books and better shapes moved the mix 0.00-0.02 (R25-cv, cw). The one component carrying the mix is the adapted book-scope network (weight ~0.45) and the single biggest gain all week was dynamic evaluation of that network (a 2010/2018 neural idea).
2. The language model's lead is not memory of these books (R25-ct) and is spread over every word kind, largest on rare words (R25-cu). That is the signature of distributed context representation, which counts cannot reproduce at any order. This is why PPM/PAQ-style compressors lost to neural models around 2015-2018 and why the current compression leaders (cmix, nncp) are themselves neural.
3. RWKV-7 0.4B is a small, older model. A 2026 frontier model on this prose would sit well under 6 bits/word. Closing 0.45 bits to a 0.4B model would still leave a larger gap to the models the owner means by "LLM".

## Verdict
- **Not realistic:** matching LLM quality on raw next-word prediction or open reading comprehension with a count-plus-rules substrate on a laptop CPU. The project's own data says the neural piece does the work; the rest is 1990s smoothing and caching, and it has been milked.
- **Realistic but untested:** winning on the two axes the project was actually built for, which no result yet measures:
  - **bits per CPU-second at a small budget** (the "100x efficiency" goal of 2026-10-08). The engine builds its counters in 26-277 s and adapts online; a 0.4B model needs ~1T tokens of pretraining. At a budget of one CPU-hour from scratch the engine may well win. This has never been scored.
  - **honesty-scored answering (+1 / -3 / 0).** The engine's differentiator is calibrated abstention. The model has never been held to the same rule. If the model with a confidence threshold beats +288, the differentiator is gone; if it does not, that is the publishable claim. One afternoon of work.

## Corners not explored (ranked by what they would settle, cheapest first)
1. **The fair neural control.** A small transformer or RWKV trained from scratch on the same 21M tokens for the same CPU minutes as the counters, then scored on the same 50,114 predictions. R24/R25 only ever compared against a pretrained 0.4B model (unfair in both directions). If the from-scratch network beats 7.15, counts are the wrong substrate and the engine should become "small network + online adaptation + copy memory"; if it loses, the data efficiency of counts is a real finding. Nothing in the record runs this.
2. **Cost table (T31) and a matched-compute curve.** Bits/word versus CPU-seconds, ours and the model's, on the same predictions. The only axis where a laptop engine can beat a pretrained model, and the only number the owner's 2026-10-08 goal needs.
3. **The model under the +1 / -3 rule.** Threshold its own answer probability on the 1,110 practice questions, apply once to the 1,800. Cheap; decides whether honesty is a differentiator or a handicap.
4. **A public yardstick.** Every number so far is on this project's own text and questions. LAMBADA (next word that needs the whole passage) and enwik8 bits/char are the standard measures of exactly the two skills in play; one run each gives an external number for the gap.
5. **Mixing context (T12).** T32 shows a per-prediction oracle of 5.70 against the mix's 7.15; a learned gate over "which component to trust here" is the last count-side gain with room. Oracles overstate; expect 0.1-0.2, not 1.4.
6. **Character level for rare words (T15).** Rare words are 23% of the gap and are charged a flat share; a letter model given the group is the standard fix and is unrun.
7. **Learned long-range retrieval (T06, T10).** Copy memories are the only long-range mechanism; a topic vector or entity component is registered and unrun. The topic-as-plan tests (R25-cy, cz) failed on generation, not on prediction, so the prediction form is still open.
8. **Evolved operator programs (T11).** The one idea that is neither an LLM nor a compressor, and the one the R26 brief centres on, has not been run. It is the only test that could change the architecture rather than tune it.
9. **Scaling the piece that works.** The book-scope network has never been scaled beyond what a laptop trains in 3 h (R24 L1/L2 missed bpc gates on throughput). The Colab tunnel exists; the owner's rule is hours-long runs go there. Dynamic evaluation on a 10x larger network is the most likely single gain left on quality.

## Corners exhausted (do not re-enter)
- More count components, shapes, or books into the mix (R25-cn, cv, cw: 0.00-0.02).
- Hand-written state rules; "the rules are not the bottleneck" (R25-ct-t) and emerged rules only tie hand rules (R25-cz-t).
- Practice questions teaching the readers (R25-z, z2): adds wrong answers on new text even with split trust data.
- Route trust tuned on small practice sets: a third of the apparent precision was selection on val_fresh2 (R25-final).
- Readers at ~0.85 precision replacing model answers on B6 (R24-ad..an, R25-i): every added reader lowers the merge.
- Trigger pairs and skip counts in a linear mix (R25-ce, bz); only the square-root mix helps (R25-cs-t).
- Topic vectors as a writing plan (R25-cy, cz) and the rarest-words plan (R25-da).

## Earlier arcs (for completeness)
The rejection-first reasoning engine, the perception rungs and the meta-reasoner (E1-E8, p1-p9, S1-S9) were a different thesis: sound verification with abstention in domains with an exact oracle. They were closed on their own terms (ACTIVE 0/504, 0/2800, 0/3000; rung 1 closed) and dropped in the 2026-10-08 pivot. They never competed with LLMs and were not meant to; their one transferable asset is the abstention discipline, which is corner 3 above.

## Recommendation
Redefine "competitive" as two measurable claims: best bits/word per CPU-second under a one-CPU-hour budget, and best +1 / -3 honesty score against a model held to the same rule. Run corners 1-3 before any more quality tuning; they decide in a day whether the project has a result or a hobby.
