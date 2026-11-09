# Symbolic understanding and text: the theory (notes, 2026-11-09)

Why this matters for primasieve: our generators choose words with no representation of *who is in the scene and what is happening*, which is why every system so far drifts in topic from sentence to sentence (raters' coherence gap to human text is larger than the grammar gap). Five NN-free judges (5-gram counts, harmonic reservoir, spectral recurrence, count denoiser, treebank parser) all saw local form, none saw meaning. The theory below is about getting meaning from text and text from meaning with symbols.

## From text to meaning
- **Compositional semantics (Montague, 1970s).** The meaning of a sentence is built from the meanings of its parts by rules that follow its syntax: the parse tree is the recipe for the logical form ("every dog barks" -> forall x. dog(x) -> bark(x)). Consequence: with a grammar and word meanings, meaning comes for free.
- **Discourse Representation Theory (Kamp 1981; Heim 1982).** Extends composition across sentences: a growing *discourse representation structure* of referents (x, y, ...) and conditions (farmer(x), donkey(y), owns(x, y)); pronouns and definite descriptions are resolved to existing referents ("he" -> x). This is exactly the entity/event tracking our generators lack.
- **Centering theory (Grosz, Joshi & Weinstein 1995).** A theory of local coherence on top of DRT-like referents: each utterance has a backward-looking center (the entity it continues) and ranked forward-looking centers (subject > object > other). Transitions are ranked CONTINUE (same center, still most salient) > RETAIN > SMOOTH SHIFT > ROUGH SHIFT; texts with more CONTINUE transitions read as more coherent. The entity grid (Barzilay & Lapata 2008) is the count-based measurement of this.
- **Frames and scripts (Fillmore's frame semantics; Schank & Abelson 1977).** Meaning comes from stereotyped situations (a restaurant script: enter, order, eat, pay, leave). A text is coherent when it moves through a frame plausibly; a reader fills unstated steps from the script.
- **Wide-coverage practice (hybrids).** Boxer (Bos 2008) produced DRT representations for open text from a statistical CCG parser; semantic parsing with CCG (Zettlemoyer & Collins 2005; Steedman) learned sentence -> logical form; AMR (Banarescu et al. 2013) is a sentence-level meaning graph bank. All working systems used statistics to parse and disambiguate, symbols to represent.

## From meaning to text: the NLG pipeline (Reiter & Dale 2000)
1. **Content determination / document planning:** decide what to say and in what order (a plan of messages: entities and events).
2. **Microplanning:** aggregate messages into sentences, choose referring expressions (first mention "the doctor", later "he": the Centering rules), choose words.
3. **Surface realisation:** turn each sentence plan into a grammatical word string (template, grammar, or corpus-based realiser).
These pipelines produced fluent, coherent text in narrow domains (weather forecasts, medical summaries) with no neural network, because coherence was designed into the plan, not hoped for from the word sampler.

## Why symbolic understanding never scaled to open text
1. **Knowledge acquisition bottleneck.** Understanding needs vast world knowledge; Cyc spent decades hand-coding it without reaching open coverage.
2. **Ambiguity.** Every sentence has many parses and readings; choosing needs statistics (hence the hybrids).
3. **Symbol grounding (Harnad 1990).** Symbols get meaning only from their connection to perception or use; a closed symbol system cannot learn what its symbols refer to.

## What it suggests for us
A hybrid in the spirit of the NLG pipeline: a small symbolic discourse state (DRT-lite referents from our NN-free tagger and parser, Centering salience), a planner that decides what each next sentence is about (keep the center, refer to it properly, stay within the prompt's referents), and our corpus collage as the surface realiser, constrained to carry out the plan. The plan supplies coherence; the collage supplies fluent wording. Preregistered as SYM in sieve_lang_prereg.md.
