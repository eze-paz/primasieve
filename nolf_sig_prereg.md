# Pre-registration -- A COMPOSITIONAL OBSERVATIONAL SIGNATURE for the nolf enumerator (`nolf_sig.py`; option in `nolf_learn.Enumerator`)

Registered 2026-10-02 before the first measurement.

## 1. The measured problem

`nolf_rebuild_prereg.md` section 6: at `max_ops=4` on records, an incrementally extended table differs from a full build
by 11 and 2 of ~15,000 level-4 signatures. Diagnosis from the code: `Enumerator._sig` evaluates a term on five hole
environments, and the value a hole receives is `envs[kind][(j + q) % len]` where `q` is the hole's index IN THE WHOLE
TERM. Two terms with equal signatures agree as stand-alone terms; embedded as sub-terms their holes sit at other offsets
and receive other values, so two "equivalent" sub-terms can give a composition two different signatures. The signature
is not compositional, and which representative of an equivalence class survives (arrival order) changes the table.

It is also the dedupe the whole learner stands on: a merge the signature gets wrong loses a construction (ARCHITECTURE,
Phase 3: "the hole KINDS are part of the signature, or not(_b) and 0<_i merge and negation is lost (measured)").

## 2. The mechanism

A signature that IS compositional: observational equivalence as functional equivalence on a PRODUCT DOMAIN. Each hole
kind gets a fixed small domain (declared: INT {0, 1}, ELEM the first two elements, RELATION the first two relation
atoms, SELECTOR the first two selectors, BOOL {True, False}); a term's signature is its value on EVERY combination of
hole values from those domains, on every probe situation (and bound variable for `lam` tables). If two terms agree on
every combination, any composition over them agrees on every combination too, because the sub-term only ever sees
values from the same domains. `Enumerator(sig_mode="product")`; the shipped rotation signature stays the default
(`sig_mode="rotation"`) until the gates below say otherwise.

Cost, predicted before measuring: 2^k combinations for k holes against 5 environments today -- for the 4- and 5-hole
terms that dominate the upper levels this is 3-6x more evaluations per term.

## 3. Gates

| gate | claim | bar |
|---|---|---|
| **S1** | with `sig_mode="product"`, extend(base -> L) and extend(L1 -> L2) are EQUIVALENT to a full build at records `max_ops=4` (the case that differed) and at `max_ops=2` on both worlds | identical signature sets at every (lam, level, type) |
| **S2** | the product signature loses no construction the rotation signature keeps: a 240 s fit on each world with `sig_mode="product"` adopts a superset of the rotation fit's construction keys, CONFAB 0 | superset; confab 0 |
| **S3** | cost: strings base table at `max_ops=4` (today 41-69 s) under the product signature | reported; **the default flips to product only if <= 2x** |
| **S4** | table size: distinct signatures per level, product vs rotation (fewer = merges rotation kept apart; more = splits rotation wrongly merged) | reported, with the terms that moved |

## 4. Predictions

- **P1** S1 passes: compositionality is a theorem for the product signature, so the only way S1 fails is a bug.
- **P2** S2 holds on records (1.000 already) and on strings the same six constructions land; the risk is the table time
  eating the 240 s budget (S3), not the dedupe.
- **P3** S3 misses the 2x bar on strings at max_ops=4 (prediction: 3-5x), so the product signature does NOT become the
  default; it is kept as the exact option for incremental growth, and the rotation signature's non-compositionality
  is recorded as a known, bounded approximation (11 of 15,000 at level 4).
- **P4** S4: product splits a few classes rotation merged (more signatures at level 3-4), and merges none.

## 5. What a PASS would and would not establish

Would: an exact equivalence notion for the enumerator, so incremental library growth is bit-equivalent to a rebuild at
any depth. Would not: anything about reach -- the same terms are enumerated; only their grouping changes.

## 6. MEASURED (2026-10-02) -- `python nolf_sig.py`: EQUIVALENT at depth 2; unaffordable at depth 4; rotation stays the default

| gate | measured | |
|---|---|---|
| **S1** | product signature: extend(base -> L) and extend(L1 -> L2) EQUIVALENT to a full build at max_ops=2 on both worlds (records 521 signatures, strings 5,244). **Records max_ops=4 NOT RUN**: the three product builds had not finished after 45 min (rotation: ~100 s each) and the run was stopped | PASS at 2; the depth-4 case the gate named could not be measured |
| **S2** | not run: a depth-4 product base table exceeds the 240 s fit budget by itself, so the fit would adopt nothing -- determined by S3, not measured | NOT RUN |
| **S3** | depth-4 cost **> 9x** rotation (bound from the stopped run; bar 2x). At depth 2 the product signature is CHEAPER (0.5-0.6x: terms there have <= 2 holes, so <= 4 combinations against 5 environments) | the default does NOT flip |
| **S4** | per level, product vs rotation: records level 2 **-7** (204 -> 197), strings level 2 **-15** (310 -> 295), lam level 1 **+1** on both. The product signature with a two-value domain MERGES classes rotation keeps apart (INT holes compared against values >= 2 are indistinguishable on {0, 1}) and splits one | reported |

### Prediction ledger
- **P1 HIT** (where measurable): equivalence is exact at depth 2.
- **P2 not testable**; **P3 HIT, harder than predicted**: > 9x rather than 3-5x, from the 2^k combinations of the 4- and
  5-hole terms that dominate depth 4.
- **P4 MISS**: the product signature merges MORE (-7, -15 at level 2), not fewer -- a domain of two values per kind is
  coarser than five rotated environments over six values. A larger per-kind domain would restore the distinctions and
  multiply the cost again (3^k).

### Disposition
A recorded null with one exact fact: compositionality costs exponential-in-holes evaluations here, and the cheap
rotation signature's non-compositionality is a bounded approximation (11 of ~15,000 level-4 signatures) that the
learner's library pass (depth 2) never meets. `Enumerator(sig_mode="product")` stays as the exact option; nothing is
registered; the default is unchanged.
