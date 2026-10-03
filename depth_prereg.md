# Pre-registration -- COMPOSITION DEPTH AND ORDER ACROSS WORLDS (`depth.py`; EMERGENCE_PLAN.md S3)

Registered 2026-10-02 before the mechanism code, after a measurement of the live loop. Zero LLM. Offline.

## 1. The shortcoming, measured (worlds_general's four worlds, its exec teaching, no context)

The pipe runs ONCE: one inner survivor's label is substituted and the other worlds get one more pass. Eight questions
that need more than that, on today's loop:

| question | gold | today |
|---|---|---|
| the salary of alice plus the salary of bob | 270 | PARTIAL (120) |
| the salary of alice plus the floor of engineering | 123 | PARTIAL (120) |
| the total salary of engineering plus the total salary of sales | 600 | PARTIAL (220) |
| the salary of the manager of alice minus the salary of alice | 30 | PARTIAL (150) |
| the double of the salary of the manager of alice | 300 | **COMMIT 240** |
| the capital of the country of the city of research | berlin | **ATTRIBUTED Germany** |
| the double of the floor of the department of alice | 6 | COMMIT 6 |
| the twiddle of the salary of alice plus 1 | 242 | READINGS {243, 242, 123} |

Four two-argument compositions abstain honestly (PARTIAL: the second argument's readings are left unused). Two are
CONFABULATIONS on main, and neither is about depth:
- **240**: the inner "salary ... alice" (120) was substituted over the region "salary of the manager of alice", which
  swallowed the unused `manager` reading; the outer doubled it. The standing rule "an unused reading is PARTIAL, never
  a sub-answer" was not applied inside the substituted region.
- **Germany**: after "city of research" -> berlin, the graph read `capital`, `capital of` (a real property, P1376) and
  `country`; CHAIN enumerates both property orders; the text-order chain capital(country(berlin)) = Berlin covers three
  positions, the reversed chain country(capital-of(berlin)) = Germany covers four (`capital of` is two symbols), and
  coverage decided. The graph has no evidence about nesting; the exec world now has (order_prereg.md).
(An earlier probe showed six confabulations; four were the probe's own doing -- its exec teaching never separated `the`
from `double`, so `the` was bound to doubling -- and are recorded in transfer_prereg.md, not here.)

## 2. The claim

Three mechanisms, each world-free:
1. **The region rule** (`core/reason.py`): an inner is substitutable only if the region it replaces holds no explicit
   content reading of its own world that it leaves unused. Removes the 240 and nothing else.
2. **Several inners at once** (`core/reason.py`): the pipe also substitutes every pair of DISJOINT, labelled inner
   survivors in one pass (one pass per distinct substituted text, as now), so an outer with two arguments can read both.
   A composite then carries a list of inners; spans map back through each region in turn; certificates and supports
   are the union. Turns the four PARTIALs into COMMITs (270, 123, 600, 30) when the outer is unique.
3. **Nesting as evidence in the graph** (`core/kg.py`): `KGWorld.induce_lexicon(pairs)` induces a nesting preference
   from confirmed pairs exactly as the exec world does (a CHAIN whose text-first property is outer reproduces the gold:
   first-outer; the reverse: first-inner; unanimous -> that order only, like the records' DIFF order; contradicted or no
   evidence -> both, as today). The session's `teach` already calls every world that has `induce_lexicon`.

## 3. Gates

- **D1 the table above**: CONFAB 0; the four two-argument questions COMMIT their gold; 300 and 6; the capital question
  -> berlin once the graph has been taught two first-outer pairs from kg_multihop's own gold ("the continent of the
  country of berlin" -> Europe style), ATTRIBUTED Germany -> PARTIAL or READINGS before teaching (never a lone wrong
  COMMIT); the twiddle question stays READINGS (the nesting of a unary over a binary is genuinely ambiguous without
  exec nesting evidence, and the exec world here has none).
- **D2 main arm**: `core/` of HEAD before this prereg (loaded from git, as turns.py does) on the same eight questions
  reproduces the table: 2 confabulations, 4 PARTIAL. FAILS ON MAIN.
- **D3 cost**: p95 time per question over the eight and over worlds_general's W2/W4 sets < 2 s; the number of pipe
  passes printed.
- **D4 controls**: "the salary of alice plus the salary of nobody" (no second argument) -> PARTIAL/NOT FOUND, never a
  value; "the capital of the country of berlin" with a CONTRADICTED nesting (one first-inner pair taught) -> READINGS.
- **D5 the registered numbers**: worlds_general, turns, chat, chat_prose, kg_multihop, critical, negative, persist,
  order, transfer unchanged.

PASS = D1-D5, CONFAB 0.

## 4. Predictions

PASS on 1 and 2; 3 at risk: kg_multihop's teaching gold may contain both nestings for different properties (then the
preference is "mixed" and the capital question stays an honest READINGS/PARTIAL, recorded). Pairs of inners may cost
time on long questions; D3 is the bar.

## 5. Not claimed

Three or more inners in one outer; recursion beyond pairs of inners plus the existing one-world chains; nesting
evidence for the records world (its hops are already resolved by the data).

## 6. Runs (2026-10-02): PASS

D1 the eight: the four two-argument questions COMMIT 270, 123, 600, 30 (PARTIAL on main); 300 (240 on main: the region rule);
the capital question -> ATTRIBUTED Berlin once the graph has two first-outer pairs (ATTRIBUTED Germany on main); 6; the
twiddle question stays READINGS (a unary over a binary, no exec nesting evidence here). CONFAB 0. D2 main (HEAD's core/
from git): 2 confabulations, 4 PARTIAL -- FAILS ON MAIN. D3 p95 0.09 s. D4 no second argument -> PARTIAL; a contradicted
nesting (one unnatural first-inner pair) -> mixed -> READINGS {Germany, Berlin}, never a lone value. D5 eleven registered
gates unchanged (772 s). Found on the way: the repeated-operator question needed one structure per operator READING in
the table world (every reading of the word had been attached to each structure, making the two inners overlap); the
mixed-nesting case needed the ranking to count CONTENT positions (a symbol above the question's median definition
frequency earns nothing, the graph's own A1 criterion) and to prefer fewer unused content readings before fewer spans
-- both in core/reason.py, both world-free. Registered (depth.py): "S3 DEPTH: PASS", "CONFAB: 0".
