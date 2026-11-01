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

## SM -- does Sieve derive the context matcher? (registered 2026-11-01, before any SM run)
Until now "which past positions count as the same situation" was given: the k previous tokens are equal. SM gives
Sieve a matcher GRAMMAR instead: a matcher = a set of <= 2 equality atoms + a distance bound. Atom = attr(token at
t - a) == attr(token at j - a), a in {1, 2}, attr in {identity, most frequent follower, most frequent predecessor}
-- the two derived attributes are Sieve's own counting (SC6) applied to each word over the training stream, so
equality of them is an induced word class nobody listed. Distance bound: j within the 50,000-token memory, or within
1,000 tokens. 22 atom sets x 2 bounds = 44 matchers; each with 4 terms from SC6's selected behaviours (count
len(filter), recency sum(filter, 1/(1+d)), latest, exists); chains as before, MDL, beam 30. Same real stream and
1,000 scored positions as SC6; held-out = the first 1,000 held-out positions.
Bars: SM1 the MDL-best program uses a matcher outside plain token equality (a derived-attribute atom or the 1,000-token
bound) AND has lower held-out bits/token than the best program restricted to plain token-equality matchers (SC6's
matcher space) on the same positions. SM2 decoy, shuffled text: the MDL-best uses no derived-attribute atom. Reported
beside them: Witten-Bell trigram on the same held-out positions, and examples of the induced classes.

## SM results (2026-11-01), absolute numbers -- log sieve_match_run.txt
**SM1 -- PASS.** MDL-best on real text: [token(t-1)] count MIX0.5 [mff(t-1)] count MIX0.9 [mff(t-2) & mfp(t-1)]
recency, training 6.5261 bits/token (program 29.2 bits). Best with plain token-equality matchers only: [any position]
recency MIX0.5 [token(t-1)] count MIX0.9 [token(t-1) & token(t-2)] count, training 6.5973. Held-out, same 1,000
positions: derived matchers 6.8362, plain matchers 6.8795, Witten-Bell trigram 6.6939 bits/token. The 1,000-token
bound was not selected. Induced classes (equal most-frequent-follower): prepositions of/in/with/for/at/on/by/from/
into (-> "the"); come/go/came/back/got/seemed/going/want (-> "to"); sentence-final him/me/said/them/now/here/us (->
sentence end); the 450 words whose most frequent follower is a rare (unknown) word (the/and/to/a/he/that/was) form
one coarse class.
**SM2 -- PASS.** Shuffled text: MDL-best [any position] count (7.3087), no derived-attribute atom.
Reading: Sieve derives a context matcher -- word classes from its own counting -- and prefers it by compression over
exact-word context, generalising better (6.8362 vs 6.8795 held-out); still behind Witten-Bell (6.6939), whose
smoothing over all history Sieve's chains approximate only with fixed mixing weights. Still given: the atom grammar
(equality, two derived attributes, offsets 1-2), normalisation, MDL.

## SN -- adaptive trust, full scale, wider matchers, checked probabilities (registered 2026-11-01, before any SN run)
**SN1 adaptive trust (sieve_trust.py).** SM's components (44 matchers x 4 terms, same 1,000 positions). New
combinator mix(term): the weight on the earlier component is a TERM over that component's own evidence at the
position -- n (matched positions), T (distinct followers) and 1, with + * / (size <= 5, values in [0,1] on every
position, deduplicated by behaviour) -- beside orelse and the fixed 0.5/0.7/0.9. Program bits: log2 of the choices
at each node. Bars: the MDL-best program uses a mix(term), and its held-out bits/token on SM's 1,000 positions is
<= 6.7439 (Witten-Bell 6.6939 + 0.05; SM's best was 6.8362). Decoy: on the deterministic stream the MDL-best still
needs no mixing.
**SN2 full scale (sieve_full.py).** Sieve's SN1-best program, run unchanged on the full vocabulary (every training
word + one unknown id, the ids Counter uses) with count terms over all 13M training tokens + the held-out prefix
(recency terms keep the 50,000-token memory they were derived with), scored on the same 50,114 positions as Counter
(8.9368), Stack (8.1507) and the LM (6.026). Descriptive; derived attributes recomputed by counting on the full text.
**SN3 wider matchers (sieve_wide.py).** SM's grammar plus: offsets up to 3 (longer contexts); a bound "same book"
(the book memory / copy register = token(t-1) within the book); and a LIBRARY source -- matches counted in the first
2,000,000 tokens of the 400 extra books (the library lookup). Same 1,000 positions as SM. Bar: the MDL-best uses at
least one of the new atoms or sources and has lower held-out bits/token than SN1's best on the same positions.
**SN4 probabilities as checked claims (sieve_claims.py).** On the 1,000 held-out positions, the SN1-best program
states its top 3 tokens with probabilities. Claims are grouped by stated probability (10 bins), aggregated first
(core/tolerance: denoise, then one bound), and each bin's claim "these occur at the stated mean rate" is checked
with a Hoeffding bound eps = sqrt(ln(2/0.01) / (2 n)) -- an upper bound, not an estimate. Verdict per bin: standing
(within eps) or REFUTED. Bar: no bin with >= 30 claims is refuted; reported beside: the same for the local
Witten-Bell trigram.

## SN results (2026-11-01), absolute numbers
Logs: sieve_trust_run.txt, sieve_full_run.txt, sieve_wide_run.txt, sieve_claims_run.txt.
**SN1 adaptive trust -- the trust term is derived, the bits bar FAILS.** 20 trust terms valid in [0,1]. MDL-best:
[token(t-1) & mfp(t-1)] count MIX[n/(n+T)] [mff(t-1)] count MIX0.9 [mff(t-2) & mfp(t-1)] recency, training 6.4803
bits/token -- n/(n+T) is Witten-Bell's own weight (matched count over matched count + distinct followers), selected
by compression from 20 candidates. Held-out (SM's 1,000 positions): 6.7892 (without a trust term 6.8362;
Witten-Bell 6.6939; bar 6.7439 -- missed). Decoy (deterministic): one component, no mixing (0.0138). PASS.
**SN2 full scale (descriptive).** The SN1 program, unchanged, on the full vocabulary (94,503 ids) and all 13.85M
tokens, the 50,114 positions: Sieve 8.7941 bits/word (first component alone 9.4995, two 8.9926). Same positions:
Counter 8.9368, Stack 8.1507, LM 6.026.
**SN3 wider matchers -- PASS.** 183 matchers x 2 terms. MDL-best: [token(t-1) & mff(t-1), in the library] count
MIX0.7 [mff(t-1) & mff(t-2)] count MIX0.7 [token(t-1) & token(t-2), in the library] count, training 6.1288; held-out
6.1871 bits/token (best without the new sources 6.9103; SN1 6.7892; Witten-Bell without library 6.6939). The library
source was selected; "same book" and offset-3 atoms were not. Latest/exists terms were dropped for time (disclosed).
**SN4 checked probabilities -- PASS.** Sieve's top-3 claims on 1,000 held-out positions: no bin with >= 30 claims
refuted (bins 0-0.1: stated 0.060 / observed 0.057; 0.1-0.2: 0.133 / 0.157; 0.2-0.3: 0.240 / 0.264; 0.3-0.4: 0.336
/ 0.390); top-3 holds the truth 0.340 vs stated 0.322. Witten-Bell: 1 bin refuted (0.5-0.6: stated 0.530, observed
0.167, 66 claims, bound 0.200); top-3 holds the truth 0.364 vs stated 0.457. Bins with few claims have wide bounds
and test little.

## SN5 -- SN3's program at full scale (registered 2026-11-01, before the run)
SN3's MDL-best program (library + class matchers; trust terms were available in that search and not chosen), run
unchanged at full scale: full vocabulary, count terms over all 13.85M training tokens + the held-out prefix, the
LIBRARY = all 17.7M tokens of the 400 extra books (SN3 used the first 2M), scored on the 50,114 positions.
Descriptive, absolute bits/word beside Counter 8.9368, Stack 8.1507 (its best used the same library by lookup), LM
6.026, and SN2's 8.7941.

## SN5 result (2026-11-01) -- log sieve_full_run.txt (second block)
SN3's program re-derived on rerun with its first component matching [token(t-1) & mfp(t-1), in the library] (the
first run printed mff(t-1); same held-out 6.1871 -- a tie) and saved to sieve_wide_best.json. At full scale (library =
all 400 books, 18,649,916 tokens with sentence marks): Sieve 8.7812 bits/word on the 50,114 positions (first
component 9.5575, two 8.9464). Beside: SN2 8.7941, Counter 8.9368, Stack 8.1507, LM 6.026.
Reading: the library, decisive at 300k tokens (6.1871 vs 6.7892), adds little once the training text is 13.85M
tokens; and this program has no recency component (SN2's had one) and fixed 0.7 mixing. Programs selected at 300k
tokens with 2,000 words are not the programs full scale wants: the search itself has to run at full scale.

## SP -- SIEVE_LANGUAGE_PLAN.md items (registered 2026-11-01, before any SP run)
**SP0 harness fixes.** Matchers deduplicated by behaviour (simplest kept), program bits per atom, deterministic tie
order. Bar: sieve_wide.py gives the identical program under two different PYTHONHASHSEED values, held-out <= 6.1971.
**SP1 ceiling (descriptive).** (a) Counter-style local model (lr_base.py) trained on the 13.85M training tokens +
the 18.6M library tokens: word bits on the 50,114 positions beside 9.0919 (half) and 8.9368 (all training).
(b) LM vs Stack per position, split by the longest library match of the sentence's last 2-6 words (lr_think_lib):
mean bits each.
**SP2 search at full scale.** Fit positions: the first 3,000 sentence-internal positions of the dev books, history =
all training text + the dev prefix (+ the whole library for library matchers); count terms over all history, recency
over the 50,000-token memory for the two simplest matchers; trust combinators; MDL beam. The selected program is run
on the 50,114 positions. Bar: < 8.7812 bits/word.
**SP3 graded matching (+ SP6 entity atom).** Small scale (SM's 1,000 positions). A graded component: every past
position j in memory scored by agreement of the last 4 tokens with t's, attr in {identity, mff, mfp} per offset,
weights per offset from {0, 1, 2}, follower weight = 2^(agreement) among the top-K agreeing positions (K in 10, 100,
1000); the grid is the grammar, MDL picks. SP6 adds an atom: "the most recent capitalised mid-sentence word (an
entity, <= 30 tokens back) is the same". Both offered beside SP0's components. Bar SP3: MDL selects a graded
component and held-out < the same search without it. SP6: descriptive (selected or not; bits).
**SP4 many cues, log-linear.** The 30 best single components (by MDL) as features of a log-linear model
P(y) ~ prod p_c(y)^beta_c (smoothed), features added greedily while training bits saved exceed 8 bits per weight.
Bar: held-out < SP3's best on the same positions.
**SP5 all of Gutenberg** needs a large download -- asked of the owner, not run.
**SP7 forms.** Words (2,000 most frequent) described by left/right neighbour distributions; agglomerative
average-linkage merging gives a hierarchy; the number of forms is chosen by MDL (class-bigram bits of a fit stream +
k^2 x 8 bits). Outside checks (no labels used to build): nouns in the same form share a WordNet lexicographer file
(noun.person, noun.animal, ...) more often than nouns in different forms, and more than with forms built from
shuffled text; rarer words (5-20 uses, not in the 2,000) placed in the form of their nearest centroid share the
form's majority lexicographer file more often than under shuffled forms. Bar: both checks above the shuffled control.
**SP8 scoreboard**: absolute bits and reliability (calibration bins, confabulation) for every model.

## SP results (2026-11-01), absolute numbers
Logs: sieve_sp0_run.txt, sieve_sp1_run.txt, sieve_sp2_run.txt, sieve_sp3_run.txt, sieve_sp4_run.txt, sieve_sp7_run.txt.
**SP0 -- PASS.** 24 of 183 matchers were behavioural duplicates. Under PYTHONHASHSEED 1 and 2 the identical program:
[token(t-1), in the library] count MIX0.7 [any position] recency MIX0.7 [token(t-1) & token(t-2), in the library]
count; held-out 6.1638 bits/token (bar 6.1971).
**SP1 (descriptive).** (a) Local model word bits on the 50,114 positions: half the training books 9.0919; all
(13.85M tokens) 8.9368; all + library (32.5M tokens) 8.7003. (b) By the longest library match of the sentence's
last words, Stack + lookup / LM mean bits: none 8.484 / 6.167 (10,800 positions); 2 words 8.376 / 5.981; 3 words
8.274 / 6.010; 4 words 8.296 / 5.945; 5 words 8.411 / 6.006; 6 words 8.063 / 5.871 -- the LM's lead is the same
whatever the library holds: it is not missing text.
**SP2 -- FAIL.** Search at full scale (44 components, 36 distinct; fit = first 3,000 dev positions): MDL-best
token(t-1) & token(t-2) count MIX0.9 [mff(t-1), in the library] count MIX0.9 token(t-1) count, fit 6.5543
bits/word; on the 50,114 positions 9.0344 (SN5 8.7812). The fit sample (the start of the dev books) was too narrow
and the selected program has no recency.
**SP3 -- PASS (narrowly).** MDL selected a graded component ([graded identity, offset weights 2,2,1, top 1,000]) in
place of the recency one: held-out 6.1598 vs the same search without graded/entity components 6.1638 bits/token.
**SP6 (descriptive).** The entity atom was offered and not selected.
**SP4 -- FAIL.** Log-linear over 7 greedily selected features (graded + 6 count components): fit 6.1487, held-out
6.2647 bits/token (SP3's chain 6.1598).
**SP5 -- not run** (needs a large download; asked of the owner).
**SP7 -- PASS.** MDL chose 400 forms on real text (14.621 MB; 25 forms on shuffled text). Nouns sharing a WordNet
lexicographer file: within a form 0.327, across forms 0.068 (shuffled: 0.078 / 0.069). Rarer nouns (5-20 uses)
placed by nearest form: majority lexicographer file right 0.271 (shuffled 0.153). Forms include man/men/people/woman
/father/mother/lady/friend/king; power/interest/change/number/strength/force/desire; the/a/his/her/my/this/their;
come/go/came/went/get/got/looked.
**SP8 scoreboard (the 50,114 positions, bits/word):** LM 6.026; Stack 8.1507; Sieve 8.7812 (SN5, small-scale-selected
program); Counter 8.9368; Counter-style + library 8.7003. Small scale (1,000 positions, 2,000 words, bits/token): Sieve
graded chain 6.1598; Sieve SP0 6.1638; Witten-Bell (no library) 6.6939. Reliability (SN4): Sieve 0 of 4 well-filled
calibration bins refuted, Witten-Bell 1 of 6.

## SQ -- second pass of SIEVE_LANGUAGE_PLAN.md (registered 2026-11-01, before any SQ run)
**SQ2 search at full scale, redo.** As SP2, but the 3,000 fit positions are spread evenly over all 7 dev books
(every k-th sentence-internal position of the 231k dev tokens; history = all training text + the dev text before the
position). Bar: the selected program on the 50,114 positions < 8.7812 bits/word.
**SQ3 graded matching widened (items 3 + 7).** SP3's graded component with offsets 1-5 (weights {0,1,2} at offsets
1-3, {0,1} at 4-5), top 1,000, and agreement attribute in {identity, most frequent follower, form (SP7's 400 MDL forms),
identity+form (agreement per offset = same token + same form)}. Offered beside SP3's components; MDL picks. Bar: MDL
selects a graded component that uses offset 4/5 or forms, and held-out < 6.1598 bits/token (SP3, same positions).
**SQ4 mixture of experts.** Cached components as experts: P(y) = sum_c w_c p'_c(y) over the experts that match at the
position (+ uniform), weights renormalised over those present; variant: weights per trust bin (log2 of the expert's
matched count, 4 bins). Experts added greedily while training bits saved exceed the expert's program bits + 8 bits per
weight; weights by EM. Bar: held-out < the best chain of SP3/SQ3 on the same positions.
**SQ9 long-range concepts emerge from residuals (E5).** Fit: the best small-scale program's per-position bits on the
1,000 fit positions. Residuals = the quarter of positions with the most bits. For each generic relation "attr(y)
occurred among the past W tokens" (attr in identity, mff, form; W in 50, 1,000, same book) the fraction of residual
answers for which it holds vs the same fraction for a stand-in answer drawn from the unigram distribution (chance).
The relation with the largest absolute excess is proposed as a primitive and instantiated generically as an
attribute-factored component P(y) = P_window(attr(y)) x P(y | attr(y)) (window term count or recency over the past W;
P(y | attr) by counts); all (attr, W, term) instances are offered to the MDL search beside SP3's components.
Decoy: the same with sentences shuffled across all books (no long-range structure); positive control: sentences
shuffled within each book (topic survives, order does not). Bars: (1) the top residual relation is long-range (W >=
1,000) on real text; (2) MDL selects a long-range factored component (form-level = topic-like); (3) on the decoy the
excess is <= 0.02 and no long-range factored component is selected; (4) held-out < the best chain so far, and at full
scale, SN5's program plus the selected component(s) < 8.7812 bits/word on the 50,114 positions (Stack 8.1507).
**SQ5 more text.** C:\ has 28 GB free; all of Gutenberg (tens of GB) is not downloaded. Instead the data curve is
measured on fractions of the library (Counter-style, lr_base.py --addlib with the first 1/4 and 1/2 of the library
books) and extrapolated to Gutenberg's ~4 billion tokens. Descriptive.

## SQ results (2026-11-01), absolute numbers
Logs: sieve_sq2_run.txt, sieve_sq3_run.txt, sieve_sq4_run.txt, sieve_sq5_run.txt, sieve_sq9_run.txt.
**SQ2 -- PASS.** Fit positions spread over all 7 dev books: MDL-best [token(t-1), in the library] count MIX0.7 [any
position] recency MIX0.7 [token(t-1) & token(t-2)] count (escape 0.02), fit 7.9385 bits/word; on the 50,114 positions
8.3411 bits/word (bar 8.7812; Counter 8.9368, Counter + library 8.7003, Stack 8.1507, LM 6.026). Execution change,
disclosed: [any position] recency at full scale is computed from each word's position list (checked equal to the scan,
max difference 1.8e-16 on 200 positions).
**SQ3 -- FAIL.** 802 components (748 distinct); search budget: the 250 best single components enter the beam
(disclosed; the full beam exceeded five minutes). MDL-best [token(t-1), in the library] count MIX0.5 [graded
identity+form, offset weights 2,2,2,0,0, top 1,000] MIX0.7 [token(t-1) & mfp(t-2), in the library] count: training
6.1167, held-out 6.2461 bits/token (bar 6.1598). Forms were selected (identity+form agreement), offsets 4-5 were not.
Likely cause: SP7's forms were built from all 13.85M training tokens, which include this 300k-token fit stream.
**SQ4 -- FAIL.** Mixture of experts (150 best single experts as candidates): 4 experts selected by MDL (library
token(t-1) count, graded identity+form 2,2,1,0,0, library token(t-1) & mfp(t-2) count, mff(t-1) & mfp(t-1) count), none
with per-trust-bin weights; training 6.0928, held-out 6.2244 bits/token (bar 6.1598).
**SQ5 (descriptive).** Data curve, Counter-style, bits/word on the 50,114 positions: 6.24M tokens 9.0919; 13.04M
8.9368; 17.46M 8.8576; 21.87M 8.7802; 30.71M 8.7003. Extrapolated to Gutenberg's ~4 billion tokens: 7.497
(log-linear) / 7.574 (power law). No sign of flattening within 6-31M tokens. Not downloaded (28 GB free on C:).
**SQ9.** (1) PASS: on real text the top residual relation is long-range -- 'the answer occurred in the past 1,000
tokens': 0.452 of residual answers vs 0.312 for the same answers at a far position. (3) PASS for long-range: on the
decoy (sentences shuffled across books) the long-range excesses are <= 0.016 (id 1,000: 0.440 vs 0.460); the decoy's
top relation is short-range (id in the past 50: 0.112 vs 0.052), which sentence shuffling keeps. Control (shuffled
within books): id in the past 1,000 0.424 vs 0.356 -- long-range survives, as expected. (2) FAIL: MDL selected no
factored component on real text (nor on the decoy); the selected program is SP0's, whose [any position] recency over
the 50,000-token memory (derived in SC) already is the identity-level long-range concept. Form-level (topic-like)
factored components lose: best chain with one 6.1316-6.1344 vs 6.1264 training bits/token. (4) not run (nothing
selected). Diagnosis -- the flexibility gap: Sieve's combinators only ADD distributions (orelse, mix); a topic is a
REWEIGHTING of the local distribution (P(y) ~ P_local(y) x boost(form(y))), which needs a product combinator with
normalisation over the vocabulary -- and the component cache stores only P(answer), not full distributions.

## SR -- ten improvements, all at full scale (registered 2026-11-01, before any SR run)
Everything is selected on the 3,000 fit positions spread over the 7 dev books (SQ2) and scored once on the 50,114
positions; reference SQ2 8.3411 bits/word (Stack 8.1507, LM 6.026). New runner sieve_fs2.py.
**SR2 distributions.** Every component also states its distribution over forms (SP7's 400 forms + 'other' for words
outside the 2,000 + '<s>'): Q[position, form]. Mixes and escapes act on Q as on P. Check: Q sums to 1 (|1 - sum| <=
1e-6) and Q[form of the answer] >= P(answer) at every position.
**SR1 reweight combinator.** A final stage P'(y) = P(y) b(form(y)) / sum_f Q[f] b(f), b(f) = ((Pwin(f) + 1e-4) /
Pglob(f))^beta, Pwin = form shares of the past W tokens (W in 200, 1,000, 5,000), Pglob = training shares, beta in
0.25, 0.5, 1; program bits 1 + log2 3 + log2 3. Bar: MDL selects a reweight stage and the 50,114 score < the same
program without it.
**SR3 forms without leak.** At full scale the fit (dev) and scored (test) text were never seen by the forms (built on
training). Graded components (identity, form, identity+form; offset weights 221, 22200, 22100, 2210; top 1,000) at full
scale are offered. Descriptive: selected or not.
**SR4 full-scale selection** (all of SR runs this way). **SR5 longer chains**: up to 5 components, MDL stops.
**SR6 residual-steered search**: at each extension only the 20 candidates with the most bits saved on the worst quarter
of the beam program's positions are scored. **SR7 residual rounds**: after each search, the residual relation with the
largest excess over chance ("form of the answer in the past W", "the answer follows an earlier occurrence of the last
k >= 3 words in the history / library") names the component family offered next round; rounds stop when a round
adopts nothing (max 3). **SR8 long-match lookup**: longest matching context (k from 8 down to 3) in the training+prefix
history or in the library, count of the answer after it. **SR9 library as history**: count components over training
+ library + prefix. **SR10 calibration filter**: the selected program is the MDL-best one whose form-level claims
(top-3 forms with Q) have no refuted Hoeffding bin (>= 30 claims, 0.01) on the fit positions.
Bar for the whole pass: the selected program < 8.3411 bits/word on the 50,114 positions. Descriptive per idea:
selected or not, and the score without it.

## SR results (2026-11-01), absolute numbers (log: sieve_sr_run.txt; state: sieve_fs2_state_r1.json / sieve_fs2_state.json)
**Whole pass -- PASS.** Selected program (round 1, after the calibration filter): token(t-1) in history + library count
MIX0.5 token(t-1) & token(t-2) in history + library count MIX0.9 any-position recency MIX0.9 graded identity 2,2,1
MIX0.9 mff(t-1) & mff(t-2) in history + library count, escape 0.1, REWEIGHT by form shares of the past 1,000 tokens,
beta 0.25: fit 7.7917, on the 50,114 positions 8.1979 bits/word (bar 8.3411). The MDL-best program before the
calibration filter (same chain, escape 0.02): fit 7.7335, scored 8.1519 (Stack 8.1507, LM 6.026).
**SR1 reweight -- PASS.** Selected by MDL in round 1. Scored with / without the reweight stage: 8.1979 / 8.2275
(selected); 8.1519 / 8.1860 (MDL-best).
**SR2 distributions -- PASS.** Q summed to 1 and Q[form of the answer] >= P(answer) at every matched position of all
79 fit components and 6 scored components (asserted on caching). Counts reproduce SQ2's cache exactly (max |P diff| 0).
**SR3 forms at full scale.** Graded identity/form/identity+form offered; graded identity 2,2,1 selected; no form-level
graded component selected.
**SR4/SR5/SR6.** Selection at full scale; chains grew to the 5-component limit (MDL total 25,669.6 -> 24,486.3 ->
23,556.1 -> 23,413.0 -> 23,304.8 bits; still falling at 5); residual-steered search over 76 components took 26-40 s.
**SR7 residual rounds.** Round 0 top relation: form of the answer in the past 200 tokens, 0.781 vs 0.745 -> reweight
offered and adopted in round 1. Round 1 top relation again form-level (past 5,000: 0.963 vs 0.943; tie at 0.020 with
the history copy relation 0.024 vs 0.004, broken by name) -> stop. Long-match was never named by the rounds.
**SR8 long-match (post hoc round 2, offered by hand).** MDL selected longest match (3-8 words) in the history as a 4th
component: fit 7.6872 (MDL-best) / 7.7560 (calibrated); scored 8.1726 / 8.2072 -- worse than round 1 (8.1519 /
8.1979): it overfits the fit positions.
**SR9 library as history -- selected.** All three count components chosen count over training + library + prefix.
**SR10 calibration filter -- FAIL as a reliability guard.** Round 0: all 210 top programs refuted >= 3 form-claim bins
(fell back to the MDL-best); round 1: a program with escape 0.1 passed on the fit positions, but on the 50,114
positions it refutes 5 bins (MDL-best: 6) and costs bits (8.1979 vs 8.1519).

## ST -- cooking the SR conclusions (registered 2026-11-02, before any ST run)
**ST1 Sieve vs Stack, per position.** Stack's best (stack + lookup everywhere + copy, 8.1507) per-position bits saved
by lr_c12.py; aligned to Sieve's 50,114 positions (answers checked equal). Bootstrap over paragraphs (2,000 resamples,
seed 0): 95% interval of each model's mean bits. "Level" stands only if each model's mean lies inside the other's
interval; otherwise the lower one is ahead. Also per word kind (repeat in book / function / content / unknown) means.
**ST2 decoy for the reweight stage.** Dev sentences shuffled across all dev books (fit stream = training + shuffled
dev); the SR selected chain's components recomputed on it; MDL chooses among no reweight and the 9 reweights. Bar: no
reweight selected on the decoy (on real dev text it was selected).
**ST3 more fit positions, longer chains.** 9,000 fit positions spread over the 7 dev books; all families offered
(count, recency, graded identity, long-match, reweight); chains up to 8, MDL stops; scored once. Bars: (a) scored <
8.1519; (b) if long-match is selected, its scored effect (with vs without) is reported -- the SR8 overfitting claim
stands only if it again hurts.
**ST4 calibration.** Diagnose: per bin stated vs observed form claims of the ST3 (or SR) program on the 50,114
positions (direction of the error). Fix (generic, one parameter): stated form distribution Qc = (1 - a) Q + a PG,
a in {0, 0.05, 0.1, 0.2, 0.3, 0.5}, chosen on the fit positions by the fewest refuted bins, then the least form-claim
log loss. Bar: 0 refuted bins on the 50,114 positions.
**ST3 amendment (2026-11-02, after ST1, before any ST3 run).** ST1 showed Stack ahead on words repeated in the book
(6.711 vs 6.880) and Sieve ahead on content words (14.473 vs 15.220). Stack's edge there is its copy register; Sieve's
full-scale grammar has no same-book source (the small-scale one had). Added to ST3's grammar: count components over
the same book's earlier text (all 21 atom sets). Descriptive: selected or not; repeat-in-book mean bits reported.
**ST4b (registered 2026-11-02, after ST4's diagnosis, before running).** ST4 showed the stated form distribution too
flat (stated 0.445 -> observed 0.520; stated 0.072 -> 0.060), so shrinking toward the prior cannot fix it. Sharpening
instead: Qc ~ Q^g normalised, g in {1, 1.1, 1.2, 1.3, 1.5, 1.75, 2}, chosen on the 9,000 fit positions by fewest
refuted bins, then least form-claim loss. Bar: 0 refuted bins on the 50,114 positions.
**ST4c (registered 2026-11-02, after ST4b, before running).** ST4b (g = 1.1) left 3 refuted bins, all at stated
0.0-0.3 (overstated by 0.010-0.016). Generic fix: histogram binning -- each claim's stated probability is replaced by
the observed rate of its stated-probability bin (10 bins, after g = 1.1) on the 9,000 fit positions; applied unchanged
to the 50,114 positions, rebinned by the new stated values. Bar: 0 refuted bins.

## ST results (2026-11-02), absolute numbers (logs: sieve_st1_run.txt ... sieve_st4_run.txt)
**ST1 Sieve vs Stack.** 95% intervals (paragraph bootstrap) on the 50,114 positions: Stack 8.1507 (8.0842-8.2178);
Sieve SR MDL-best 8.1519 (8.0931-8.2102) -- level; Sieve SR selected 8.1979 (8.1428-8.2536) -- level; Sieve ST3
8.0208 (7.9512-8.0911) -- ahead of Stack (each mean outside the other's interval); LM 6.0261 (5.9471-6.1100). By word
kind (Stack / SR MDL-best / ST3 / LM): repeat in book (40,984) 6.711 / 6.880 / 6.693 / 4.979; function word (447)
7.920 / 7.451 / 7.503 / 6.234; content word (8,373) 15.220 / 14.473 / 14.599 / 10.858; unknown (310) 7.933 / 6.626 /
6.661 / 13.580.
**ST2 decoy -- PASS.** SR chain on real dev text: no reweight 7.7527, best reweight 7.7335 -> MDL chooses reweight
(1,000, 0.25); on dev sentences shuffled across books: no reweight 7.9831, best reweight 7.9849 -> MDL chooses none.
**ST3 -- PASS (a), (b) reverses SR8.** 9,000 fit positions, 91 components, chains up to 8 (MDL total still falling at
8: 77,534.0 -> 73,552.3 -> 70,779.7 -> 70,037.4 -> 69,375.0 -> 69,043.4 -> 68,789.0 -> 68,601.2 bits). Selected (no
program among the top 40 passed the calibration filter -> MDL-best): token(t-1) history+library count MIX0.5 token(t-1)
& token(t-2) history+library count MIX0.9 any-position recency MIX0.9 token(t-1) earlier in this book count MIX0.9
longest match history MIX0.9 token(t-2) count MIX0.9 longest match library MIX0.9 token(t-1) & token(t-2) earlier in
this book count, escape 0.02, reweight (1,000, 0.25); fit 7.5992. Scored on the 50,114 positions: 8.0208 (without
reweight 8.0487); dropping longest match in history 8.0334, in the library 8.0255, token(t-1) earlier in this book
8.0968. With 9,000 fit positions the long-match components help on held-out text (SR8's overfitting was the 3,000-
position sample). Same-book counts (Stack's copy register) were derived and selected; repeat-in-book 6.693 (Stack 6.711).
**ST4 calibration -- FAIL (all three fixes).** Diagnosis on the 50,114 positions: form claims too flat at the top
(stated 0.445 -> observed 0.520; 0.541 -> 0.611) and overstated at the bottom (0.072 -> 0.060): 7 bins refuted.
ST4 shrink toward the prior: chosen a = 0, 7 refuted. ST4b sharpening: chosen g = 1.1, 3 refuted (stated 0.0-0.3,
overstated by 0.010-0.016). ST4c histogram binning learned on the fit positions: 2 refuted (stated 0.365 -> 0.340;
0.688 -> 0.647). The fit (dev books) rates do not transfer to the scored (test) books at bounds of 0.007-0.03.
**ST4 diagnosis, post hoc (2026-11-02).** Histogram binning learned on two test books, checked on the third:
book 0 (6,520 positions) 0 refuted, largest |stated - observed| 0.028; book 1 (26,943) 2 refuted, 0.051;
book 2 (16,651) 1 refuted, 0.061. Calibration of form claims differs from book to book by up to 0.061, so no fixed
correction learned on other books can pass bounds of 0.007-0.03; a correction would have to adapt within each book.
