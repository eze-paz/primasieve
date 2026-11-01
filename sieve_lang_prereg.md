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
