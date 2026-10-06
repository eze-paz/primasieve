# Pre-registration -- C7: ORDER-AWARE CHAINS IN THE MONITOR (`core/wordorder.py` typed chains, `chains.py`; 2026-10-06)

Registered 2026-10-06 before the first run. Zero LLM. Rung C7 of COMPREHENSION_PLAN.md, REDEFINED by a diagnosis made
before this file: the plan said "harvest copular constructions from the corpus", but listing the 8 messages H10b's
licensing leaves uncovered shows none fails for lack of copular exposure. Six carry a TWO-WORD relation -- an operator
before a column ("total quantity", "maximum price", "mean price", "largest revenue", "average quantity", "average
salary") -- and H10b licenses a relation only by an attachment to an ARGUMENT; two fail at message building (three open
runs). H10c licensed relation-relation adjacency without ORDER, and reversals came back (34 %).

## 1. Mechanism
Attachments between two RELATION spans are recorded with the ordered pair of their reading codes (e.g. operator ->
column, "O>C") and their link (the closed run between, 0-3 symbols). A relation is licensed by an attested (link, order)
attachment to an argument (H10b) OR by an attested (link, "chain:K1>K2") attachment to another relation in that order.
Learned from the answered questions, as H10b; attested = seen at least twice.

## 2. Gates (SPEAK's 18 messages)
| gate | claim | bar |
|---|---|---|
| **K1** | accepted wordings reversing the question's order | **<= 10 %** |
| **K2** | messages with an accepted wording | **>= 60 %** (H10b: 10/18) |
| **K3** | held-out half: correctly answered questions left unlicensed | **<= 2 %** (H10b: 32/54) |
| **K4** | KNOCKOUT: chains recorded without order (H10c's rule) | K1 not met |

PASS = K1-K4.

## 3. Predictions
P1 ~2 %. P2 14/18 (the six two-word relations licensed). P3 ~5 % (questions whose chains are not attested twice in half
A). P4 the unordered knockout lets reversals back.

## 4. Run 1 (2026-10-06): FAIL K1, K3
Attested chains include ('', chain:O>C) 20, (of the, chain:P>P) 8. K2 coverage **16/18**, but K1 reversed **355/984
(36 %)** and K3 4/54 unlicensed; K4 unordered 37 %. Defect of the rule as implemented: a chain attachment licensed BOTH of
its relations, so the head relation ("price" in "maximum price") never had to attach to its argument in an attested
order, and "the doohickey of maximum price" passed.

## Amendment, run 2 (declared after run 1)
A chain licenses only its FIRST relation (the modifier: "maximum" before "price"); every relation that is not the first
of an attested chain must attach to an argument by an attested (link, order).

## Run 2 (2026-10-06): NOT PASSED (K3 11/54; K4 the knockout also holds) -- and the monitor's wall is mostly lifted
K1 reversed **0/276**; K2 coverage **15/18** (H10b: 10/18). New wordings: "79 4 is the average quantity of the widget",
"1410 is the largest revenue of february", "217 12 is the mean price of east" (the fraction's bar is lost in the
tokens), alongside "120 is the salary of alice", "michelle obama is the spouse of barack obama". Still wrong in form:
"40 are a maximum price of doohickey", "18 is double in 9", "any of double of the 50 of which are 100". K3: 11/54 held-out
questions unlicensed (licence learned from half of 96 questions). K4: the UNORDERED knockout also gives 0 % reversed --
so the order of the chain pair is not what keeps the order; the rule that a chain licenses only its first relation (the
head must still attach to its argument in an attested order) is. Recorded as the finding; the hypothesis "ordered chain
codes" is not supported over "first-only chains".
