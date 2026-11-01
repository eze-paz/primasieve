# Sieve on language (registered 2026-11-01, before any run)

Model names (ARCHITECTURE.md): **Sieve** = the original deterministic operator deriver. Everything in
`learned/lx/` (LX..NC) was Stack/Counter work; this is the first time Sieve itself runs on language.

## Sieve's interface, as the code has it
Sieve is not one function; it is a loop pattern each experiment instantiates with its own object grammar, using the
shared mechanisms in `core/`:
- **object grammar**: the programs that may explain an artifact (E4 `grammar()`: rules coeff = g(exp)).
- **GENERATE**: enumerate programs simplest-first, deduplicated by observable behaviour
  (`core.generate.SignatureBank`).
- **REJECT**: a program survives only if it reproduces every observed point exactly (`core.search`: score =
  exact reproduction); the channel must be sound (E1: an unsound channel breaks discovery).
- **COMPRESS** (SLEEP): the fragment recurring across solutions becomes a library operator
  (`core.generate.compress_recurring`, plurality, cost-ordered adoption).
- **Invention from residuals (E5)**: artifacts the library cannot explain are abstained; when the SAME residual
  recurs, a DEEPER hypothesis space is searched and the simplest program fitting the recurring residual is
  crystallized as a new primitive, then must explain held-out artifacts. Knockouts: DECOY (mixed rules -> nothing),
  OUTSIDE (unreachable -> nothing), THIN (under-determined -> nothing).
- **COLLECT**: choose the probe that splits the survivors most (`core.collect.best_split`), reject the disagreeing.
- **COMMIT/ABSTAIN**: never a probability; commit only on a single survivor; report confabulation first
  (`core.verdict.score_two_mode`).
Inputs: artifacts (observed points), an object grammar, a rejection channel. Outputs: a library of verified
operators, and per query a committed answer or an abstention.

## Mapping language into those inputs
Points come from text only (training books' vocabulary, `learned/lx/lx_vocab.json`; library of 358 training + 400
extra books for attestation). The rejection channel is attestation in text -- a SUBSET channel: what is attested is
real, what is absent may still be real (E1: sound but incomplete, which should degrade into abstention, not
confabulation).

## S1/S2 morphology (sieve_morph.py)
Points: pairs (x, y) of attested words (>= 3 uses each, letters only, len(x) >= 3), y longer than x by <= 4 letters,
sharing all but the last <= 2 letters of x, with y's last two letters among the 10 most frequent such endings
(frequency only, no authored list). Base object grammar: y = drop_k(x) + c, k in {0,1,2}, c a constant.
Deeper space (searched only on recurring residual, as E5): y = drop_k(x) + f(x) + c, f in {last letter,
second-last letter, first letter}. COMPRESS: repeatedly adopt the most recurring program covering >= 50 still
unexplained pairs (base first); the pairs left are the residual; then the deeper space over the residual, same rule.
Commit/abstain query (S2): given a held-out lemma and the slot (the last two letters of the wanted form), the
library programs producing that slot are filtered by an exceptionless guard learned on training -- the shape of x
(consonant/vowel pattern of its last 3 letters + its last letter): commit only if exactly one program was ever used
for that (shape, slot) in training; else abstain. Rows: the 900 novel forms of lx_gold.items (forms attested >= 3
times in the 400 extra books, never in training). Baseline (core.gates Analogy-style): always commit the most
frequent program for the slot.
Knockouts: DECOY -- every doubled letter in training outputs replaced by a different random consonant; SHUFFLE --
outputs shuffled among pairs with the same ending.
Bars: S1 -- a last-letter (doubling) program is crystallized from the residual, and neither knockout crystallizes
one. S2 -- Sieve's confabulation on the 900 rows <= 0.05, it commits on >= 1 row explained only by an invented
program, and the baseline's confabulation is reported beside it.

## S3 word order (sieve_order.py)
The same held-out sentences as NC2 (5-8 known words; 467 scored / 737 dev). GENERATE: every order of the bag that
uses only attested adjacent pairs, starts with a word attested sentence-initially, ends with one attested
sentence-finally (depth-first, survivors kept). REJECT/COLLECT: probes are the trigrams, then 4-grams, inside the
survivors, taken in best-split order (`core.collect.best_split`); a survivor containing an unattested probe is
rejected. COMMIT the single survivor, else ABSTAIN. Reported: confabulation, abstention, exact order, precision
(score_two_mode), lookups used, and how often the channel rejected the true order. Counter's beam (NC2, always
commits) is the baseline: exact 0.206 / 0.267, so confabulation 0.794 / 0.733.
Bar: Sieve confabulation <= 0.05 on both folds, with commits > 0.

## Results (2026-11-01), absolute numbers
Logs: sieve_morph_run.txt (registered), sieve_morph_b_run.txt (post hoc variant), sieve_order_run.txt.
Fixes before reading results: compression counts kept incrementally (same plurality rule) after the first run
overran 5 minutes; the order oracle cached; above 200 survivors every probe is looked up at once.

**S1 morphology, as registered -- FAIL.** 483,306 pairs; 2,142 operators adopted (2,133 base); base residual 155,437
pairs; invented 9, none a last-letter (doubling) operator -- the base grammar already covered doubled forms with one
constant per letter ("+pped", "+cked", ...), so doubling never reached the residual that triggers E5; the 9 inventions
are junk from short-word pairs (blot -> bloomed). DECOY and SHUFFLE invent no last-letter operator.
**S2 as registered:** Sieve CONFAB 0.0000, abstain 1.0000, EM 0.0000 (unanimous guard never holds); baseline
(always commit the most used operator) CONFAB 0.4122, abstain 0.2344, EM 0.3533. FAIL (no commit).
**Post hoc variant (--b, disclosed):** pairs need len(x) >= 4 and a shared stem >= 3 letters (156,931 pairs); ONE
compression over base and deeper programs together (the SLEEP step of emergence.py rather than E5's residual
trigger); guard detail chosen by leave-one-out search on training (last 3 letters + consonant/vowel shape; training
LOO EM 0.0231, confabulation 0.0437). Invented "x + last(x) + 'ed'" (209 pairs: abet -> abetted, admit -> admitted,
annul -> annulled) and "x + last(x) + 'ing'" (180); DECOY: 0 last-letter operators (but the decoy only rewrote pairs
whose output starts with the whole input, so "drop 1 + second-last(x) + 'ed'" (admits -> admitted) survives it).
S2: Sieve CONFAB 0.0144, abstain 0.9478, EM 0.0378, precision 0.7234; baseline CONFAB 0.3944, abstain 0.2344, EM
0.3711, precision 0.4848; 20 rows only an invented operator explains, Sieve committed correctly on 1.

**S3 word order -- FAIL.** True order survives the attested-pair channel in 254 / 467 (scored), 462 / 737 (dev).
| channel | CONFAB | abstain | EM | precision |
|---|---|---|---|---|
| pairs only (scored) | 0.0128 | 0.9872 | 0.0000 | 0.0000 |
| pairs + trigrams (scored) | 0.3790 | 0.6039 | 0.0171 | 0.0432 |
| pairs + trigrams + 4-grams, registered (scored) | 0.5589 | 0.3790 | 0.0621 | 0.1000 |
| pairs + trigrams + 4-grams, registered (dev) | 0.5224 | 0.4003 | 0.0773 | 0.1290 |
Counter's beam (NC2, always commits): exact 0.206 / 0.267.

Reading: Sieve runs on language and, given a grammar where the operator is not already expressible by constants, it
invents doubling itself and keeps confabulation at 0.0144 where an always-commit rule confabulates 0.3944 -- by
abstaining on 0.9478. The wall is Sieve's own first limit (E1): its REJECT needs a sound channel, and text
attestation is sound only where it is uninformative (pairs: 0.0128 confabulation, 0.0000 exact); every longer
n-gram channel is informative but unsound (absence of a phrase is not evidence it is wrong), and confabulation jumps
to 0.3790-0.5589. Language gives Sieve positive evidence only; a sound rejection channel for language is the open
problem.

## SC -- does Sieve derive counting? (registered 2026-11-01, before any SC run)
Owner's question: Sieve should derive counting (and probabilities) as a method from its ability to learn; if it does
not, the engine is not emergent enough and we must find why, with engine changes as domain-agnostic as possible.
**Environment.** A token stream (words mapped to the 2,000 most frequent + one unknown id, a boundary token between
sentences). Task at each scored position t: the next token. History = the previous 50,000 tokens (a fixed memory
bound of the environment, not tuned). Training stream = first 300,000 training-book tokens, 3,000 scored positions
sampled from its second half; held-out = 3,000 positions of the scored held-out text, history continuing from the
training stream.
**What Sieve is given (generic, typed primitives; no count model):** a context matcher (positions j < t whose k
previous tokens equal t's, k in {0,1,2} -- equality + position lookup), the follower map j -> token[j], the distance
d = t - j, a weight-term grammar over {1, d} with + * / (terms of size <= 5, deduplicated by normalised behaviour
with core.generate.SignatureBank), aggregators over the matched followers -- last, first, set (uniform over distinct
followers), group-sum of a weight term per distinct follower (normalised), argmax of that group-sum -- combinators
orelse (next component only if the previous matched nothing) and mix(lambda in {.5,.7,.9}), and an escape to the
uniform token (rate from {.5,.3,.2,.1,.05,.02,.01}). Counting = group-sum with weight term 1; it is one composition
among recency-weighted sums (1/d, 1/(1+d), ...), sets, last/first occurrence and their argmaxes. Nothing ranks it.
**Selection (agnostic, Sieve's COMPRESS):** minimum description length -- bits to encode the scored training tokens
under the program (-log2 P(token)) + the program's own bits (log2 of the choices at each node). Search: chains of up
to 3 components, beam 30, simplest first.
**Sanity control first (core.gates rule 1):** a stream from a random 2nd-order Markov chain (200 tokens, each context
with a random Dirichlet(0.3) follower distribution) -- the MDL-best program must use group-sum with weight 1 at
k = 2. If this fails, the harness is broken and nothing else is read.
**Bars on real text.** SC1 counting derived: the MDL-best program's weighted components use weight term 1, and on
held-out text it beats the best program without any count component (absolute bits/word both reported). SC2 context:
the MDL-best program uses k >= 1. SC3 decoy, shuffled real text: the MDL-best program uses no k >= 1 component. SC4
decoy, deterministic generator (next token a fixed function of the previous two, 200 tokens): the MDL-best program
uses no group-sum/argmax component (a simpler exact one suffices). SC5 COMPRESS: the plurality fragment across the
top 20 programs (core.generate.compress_recurring) is a weight-1 group-sum. Reference: Witten-Bell trigram on the same
streams (absolute bits/word).
If SC1 fails, the next step is a diagnosis of which engine limit blocked it, and any engine change must be
domain-agnostic.

## SC6 -- counting without a group-sum primitive (registered 2026-11-01, after SC1-SC5, before SC6 runs)
SC1-SC5 gave Sieve "group-sum of a weight term per distinct follower" as one aggregator node, so counting was one
constant away. SC6 removes that: a candidate's score is a TERM over the matched list M (pairs follower, distance) and
the candidate y, built from generic nodes -- lists M and filter(M, follower == y); numbers 1, len(L), sum(L, w) for a
weight term w of the SC grammar, exists(L), [latest follower == y], [earliest follower == y]; and + * / between
numbers; at most 5 nodes, deduplicated by behaviour (SignatureBank). Scores are normalised over all tokens (absent
tokens take the term's value on an empty filter) -- the coding step of the channel, not a learned method. Program
bits = log2 of the choices at each node. Same chains, combinators, escape, beam, 1,000 scored positions.
Counting = len(filter(M, follower == y)) (3 nodes), one term among add-one counts, recency sums, set membership,
last/first occurrence, ratios.
Bars: SC6a sanity (Markov stream): the MDL-best k = 2 component's term behaves as counting. SC6b real text: the
MDL-best program's k >= 1 components behave as counting (or a count-equivalent behaviour); held-out bits/token
reported beside SC's 6.5839 and Witten-Bell's 6.5137.

## SC results (2026-11-01), absolute numbers
Logs: sieve_count_run.txt (SC1-SC5), sieve_count2_run.txt (SC6).
Harness fixes, disclosed (each before the affected result was read): the generators first used 200 token types --
40,000 contexts against a 50,000-token memory, so the sanity control learned nothing (7.6228 bits/token vs uniform
7.64); changed to 20. Program bits first charged every weight term a flat log2(15) bits; changed to the registered
"log2 of the choices at each node", which makes "1" cheaper than "d/(1+d)" (they tied in data bits). The
deterministic decoy first restarted every 20 tokens (restart positions are random) and then was scored on rule-only
positions (block ends still jump to the boundary token); the final decoy is one uninterrupted run of the rule.
**SC (group-sum given as one aggregator):**
- Sanity (Markov, 20 types): MDL-best "k=2 group-sum[1]" -- counting -- 3.0554 bits/token, 8.7 program bits; k=2
  set 3.7576, k=2 last 4.5971, k=0 count 4.3195. COMPRESS: "k=2 sum[1]" in 20 of the top 20. PASS.
- SC1 real text -- FAIL as registered. MDL-best: k=0 group-sum[1/(1+d)] MIX0.5 k=1 group-sum[1] MIX0.9 k=2
  group-sum[1], training 6.4905 bits/token: counting for both context components, a RECENCY-weighted sum for the
  context-free one (the book-recency register, found by Sieve). The bar demanded weight 1 everywhere. Held-out:
  MDL-best 6.5839; best with no weight-1 component (uses 1 + 1/d, near-constant) 6.5803; best without context
  7.1822; Witten-Bell trigram reference 6.5137 bits/token.
- SC2 context: uses k >= 1. PASS. SC3 shuffled: MDL-best "k=0 group-sum[1]" only (7.2164). PASS.
- SC4 deterministic (final, uninterrupted): MDL-best "k=2 last" (0.0138 bits/token, 6.7 program bits), no counting.
  PASS (post hoc generator). SC5 COMPRESS on real text: plurality fragment "k=0 sum[1/(1+d)]" (20 of 20) -- FAIL
  as registered (the recurring fragment is the recency sum, not a weight-1 count).
**SC6 (no group-sum: terms from list / filter / len / sum / exists / latest / earliest / + * /):** 3,924 terms, 310
(Markov) / 336 (real) distinct behaviours.
- SC6a sanity: MDL-best "k=2 len(filter(M, f==y))" -- counting composed from generic nodes -- 2.9615 bits/token,
  8.6 program bits. PASS.
- SC6b real text: MDL-best k=1 len(filter(M, f==y)) MIX0.5 k=0 sum(filter(M, f==y), 1/(1+d)) MIX0.9 k=2
  len(filter(M, f==y)), training 6.5973 bits/token; both context components are counting. PASS. Held-out 6.8795
  bits/token on the first 1,000 held-out positions (a different sample from SC's 3,000 -- not comparable to 6.5839).
Reading: Sieve derives counting. Given generic list operations it composes len(filter(M, follower == y)) and selects
it by compression wherever the context is informative, keeps plain counting out of deterministic text (last
occurrence suffices) and out of shuffled text's context components, and on real text prefers a recency-weighted sum
over plain counts for the context-free part. Still GIVEN, not derived: the context matcher (which past positions
count as "the same situation": k previous tokens equal), the normalisation of scores into a code, and MDL itself.
The next emergence question is the matcher: whether Sieve can derive which positions are alike (word groups,
topics, the book) the way it derived counting.
