# WORD SEGMENTATION PRE-REGISTRATION — can the engine LEARN language structure from raw text (MDL + entropy)?

Committed BEFORE the segmenter code. Tests the owner's "one missing piece": a self-supervised COMPRESSION oracle
over raw text turns the engine's search+COMPRESS+emergence loop into a bottom-up language learner. First rung =
unsupervised WORD SEGMENTATION (space-stripped character stream -> word boundaries) -- the canonical first step of
language acquisition, the one language task with a fully deterministic lossless-compression (MDL) oracle. Entropy
is the "smart entropy system": it PROPOSES candidate boundaries; MDL (sound) accepts/rejects. fable-scoped (a335fc3).

## Committed corpus (SHA-pinned)
Project Gutenberg "Alice's Adventures in Wonderland" `alice.txt`, SHA256
`a3a27f8edbf7fcd9b8ba8435494440e24952deaa3e2f2d65192d4cb7ca403754` (26543 words). NOTE (honest): the standard
benchmark is Bernstein-Ratner br-phono (published Brent/Goldwater/Zhikov numbers); it wasn't fetchable offline, so
we use Alice -- a valid, arguably HARDER (English orthography) segmentation test, but published-number comparability
is LOST; internal controls carry the honesty instead. Preprocess: lowercase, keep [a-z] + spaces, sentence-split
into "utterances"; INPUT = utterances with intra-utterance spaces REMOVED (utterance breaks kept). GOLD spaces
stored separately, read ONLY by the scorer. 80/20 utterance split by seeded hash; lexicon learned on TRAIN, F1 on
TEST only. Gold boundaries NEVER touch training (leakage rule).

## MDL objective (SOUND, deterministic)
total bits = LEXICON [ Σ_types (len(w)·log2|Σ| + Elias-gamma(count)) ] + CORPUS [ Σ_tokens −log2 P(w) ], P = MLE
unigram (count/total). A candidate segmentation is ACCEPTED only if total bits STRICTLY decrease (same
sound-rejection discipline as every prior experiment); else REJECTED.

## Entropy (proposal only — never touches the score)
Forward + backward branching entropy at each stream position from n-gram stats (order 2-4): H(next char | preceding
k). Positions where H SPIKES above a local mean become candidate split sites, ranked, fed to the MDL accept/reject
loop. Entropy proposes; MDL decides.

## Controls / knockouts
- (a) SHUFFLE-characters: permute the char stream -> structure destroyed -> bits-gain ~0 and F1 ~ chance.
- (b) NO-ENTROPY: same MDL, RANDOM-position proposals at equal budget -> is entropy load-bearing?
- (c) Baselines: all-boundaries (every char a word) F1; MDL-only.

## Metric (the only non-riggable number)
Held-out **token F1** vs gold boundaries (compression ratio is riggable; F1 cannot be, since gold never enters
training). KILL: F1 < 0.60, OR entropy-knockout costs < 5 points (entropy not shown to matter). WIN: F1 >= 0.75.
Between 0.60-0.75 = "MDL works, entropy contribution unproven" -- reported as such, not spun. (Ceiling on br-phono
is ~0.87; on Alice/English unknown -- report the number honestly against the internal baselines.)
