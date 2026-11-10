# Primary research target: SYM — symbolic understanding for fluent, coherent text (set 2026-11-09)

**SYM is the leading, primary research target of primasieve and the most promising direction we have.** SYM = an NN-free hybrid in the shape of the classic NLG pipeline (Reiter & Dale 2000): a symbolic *reader* builds a discourse state (DRT-lite referents with Centering salience, from our count-trained tagger and dependency parser), a *planner* decides what each next sentence is about (Centering transitions), and the corpus collage (JX3S1) is the *surface realiser*, constrained to carry out the plan. Theory: `sieve_theory_symbolic.md`. Preregistrations and results: `sieve_lang_prereg.md` (sections SYM, SYM2). Code: `sieve_g1b_kernel.py` (options `sym`, `ptr`), `sieve_parse.py` (reader), `sieve_symcont.py`, `sieve_symtrans.py`.

## Current best: SYM3C — milestone PASSED (2026-11-09)

**SYM3C is the default decoder.** It plans each sentence's subject (Centering CONTINUE, prompt referents weighted 3, no expletive "it") and its verb (narrative event chains, Chambers & Jurafsky 2008, counted from the books), and the collage realises the plan as a hard constraint. 80 fresh prompts, two independent blind raters, against JX3S1:
- coherence pooled **0.775 [0.6875, 0.85]**; fluency pooled **0.6188 [0.5188, 0.7188]**;
- grammatical share 0.625 vs 0.597 (paired [-0.032, 0.087]); 5-gram copy share 0.6139 vs 0.7296; human text 0.923 grammatical.
It is the first NN-free change to pass an 80-prompt two-rater milestone. It was found by step-by-step tracing: the earlier SYM2H milestone failed because its plan almost never acted (weak boost, vetoes), which batch scores could not show. Preregistration and results: `sieve_lang_prereg.md` (sections SYM3, SY3, SY3M80). Run options: `sym` "pfhv", `pw` 3.0 (`sieve_g1b_kernel.py`; `G1_TRACE` for step traces).

**Update 2026-11-10: default is SYM3N** (SYM3C without the harmonic tie-breaker): at 80 prompts with two raters removing it is level (coherence 0.475 [0.375, 0.581], grammar 0.674 vs 0.653) and generation is about 8x faster; the junction veto and power 6 were tested and kept (removing them rated 0.20 and 0.35 on coherence). The phasor (FHRR) state holds the scene as well as the symbolic state (Test A) but has no job in decoding yet. **Open line, not closed:** the harmonic/phasor state was only ever tested as a tie-breaker among 4-word-match candidates; that use may be the wrong one (owner, 2026-11-10). All harmonic code stays switchable (beta/svd/fhrr options), and new mechanisms must stay compatible with it so it can return where it contributes (candidate: searching book passages by situation). Options: `sym` "pfhv", `pw` 3.0, `eps` 0.03, `pow` 6.

## Justification

1. **It is the only NN-free change that blind raters preferred on coherence across the board.** SYM round (20 prompts, one rater, local bench MT 27M):
   - Preferred over JX3S1: SYM fluency 0.70, coherence 0.70; SYMP (plan only) fluency 0.70, coherence 0.70.
   - Grammatical share: SYMP 0.735, JX3S1 0.663, human text 0.933.
   - Sentences whose subject is a prompt referent: SYM 0.4516, SYMP 0.3163, JX3S1 0.1939, human 0.3167.
   - 5-gram copy share: SYM 0.6728, JX3S1 0.7043 (it does not copy more).
2. **Every other NN-free line tested on 2026-11-09 hit a ceiling, and each failure points at the same missing piece: a representation of who is in the scene and what happens.**
   - Judges of form plateau: 5-gram critic, harmonic reservoir critic (human vs generated AUC 0.8980, but grammar AUC 0.8608 against 0.8352 for length alone), treebank parser (0.8476), entity grid (coherence pair accuracy 0.5679 against 0.5218 baseline).
   - Spectral learning of the recurrence: 9.5690 bits per word alone.
   - Revision is capped by its judge: checked Gibbs is preferred on 16 of 22 changed texts but moves grammar only +0.02; critic-guided revision fools the critic and raters reject it 0 of 20; count diffusion is rejected (fluency 0.05); annealing's edits read better in 4 of 13 blind cases.
3. **Theory says coherence is designed into a plan, not sampled into words.** DRT (Kamp 1981) and Centering (Grosz, Joshi & Weinstein 1995) model discourse as tracked referents and their transitions; the NLG pipeline produced coherent text without neural networks by planning content first. SYM's result fits: the plan alone (SYMP) carried the coherence gain; boosting entity words alone (SYME) raised continuity numbers but not rated coherence (0.55).
4. **It has a clear, theory-backed path to grow, with no neural network and no extra compute:**
   - sampled Centering transitions with human frequencies (SYM2H: coherence 0.7368 [0.526, 0.895] over JX3S1, round SY2; plan fallback never triggered);
   - event planning: who does what next, from verb-subject and verb-object counts over parsed books;
   - dictionary-derived world knowledge: IS-A taxonomy from definition genus terms (Amsler 1980), animacy and gender for pronouns, selectional preferences over classes (Resnik 1997).
5. **It keeps the strengths we already have:** the collage's fluency and the count veto. SYM adds the content-planning layer the system lacked.

## Caveats (honest status)

- **Milestone failed (2026-11-09, SYM2M80):** SYM2H vs JX3S1 on 80 fresh prompts with two blind raters: coherence pooled 0.4562 [0.35, 0.5563], fluency 0.475, grammar 0.656 vs 0.644. The 20-prompt wins below were within noise. The current SYM plans only which referent opens the next sentence; that is too thin. The target designation stands by the owner's decision; the evidence for it is now the theory and the failure of the alternatives, not a measured gain. Next: plan more of each sentence (events).

- The SYM result is 20 prompts with one rater: intervals [0.50, 0.90] touch 0.5. A milestone on more prompts with two raters is required before adoption as the default decoder.
- Always-CONTINUE planning (SYMP) did not replicate on fresh prompts (coherence 0.70 in round SY, 0.4737 in round SY2; pooled 23 of 39 = 0.59). The current best variant is SYM2H (human-frequency transitions: coherence 0.7368, interval [0.526, 0.895]); its milestone is the next step.
- Its components are crude: tag-only parser (attachment accuracy 0.6152), coreference by pronoun groups, no gender for nouns.
- The neural MW (HSSM writes, counts veto) also beat JX3S1 (0.80 / 0.80), but it is an NN. SYM is the leading **NN-free** direction and the primary target by the owner's decision of 2026-11-09.
