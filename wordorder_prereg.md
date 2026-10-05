# Pre-registration -- H10: WORD ORDER LEARNED FROM ANSWERED QUESTIONS, ENFORCED BY THE MONITOR (`core/wordorder.py`, `wordorder.py`; 2026-10-05)

Registered 2026-10-05 before the first run. Zero LLM. A new hypothesis, H10, added to FLUENCY_HYPOTHESES.md from
speak_prereg.md's finding: the reader is ORDER-BLIND, so the monitor accepted "the director by which jaws is steven
spielberg" beside "steven spielberg is the director of jaws" -- 1,130 of 2,448 accepted wordings reversed the order of
relation and argument. Every theory of grammar puts order first (constituent order is the cheapest syntactic cue); the
engine has never used it.

## 1. Mechanism
- **Roles by kind, no words:** a reading of one of its world's CONTENT kinds (a property, a column, an operator) is a
  RELATION; any other reading the structure uses (an entity, a filter value, a number) is an ARGUMENT.
- **Observations:** in each correctly answered question, for each relation span and argument span of the answer's
  structure that stand with exactly one closed-class symbol between them (the text model's 100 commonest), the link
  symbol and the order (relation first or argument first) are counted.
- **The rule:** a link whose observations agree (at least 3, all one order) has a learned ORDER. A reading that puts a
  relation and an argument around that link in the other order is out of order.
- **Use:** in the SPEAK monitor, a wording whose re-read is out of order is rejected.

## 2. Gates
| gate | claim | bar |
|---|---|---|
| **W1** | learned links from HALF the chat gate's answered questions (seeded split) | **>= 1** link with an order |
| **W2** | the OTHER half: correctly answered questions the rule calls out of order | **<= 2 %** |
| **W3** | SPEAK rerun with the rule: accepted wordings reversing the question's order (S8) | **<= 10 %** of accepted (from 46 %) |
| **W4** | SPEAK coverage with the rule | **>= 60 %** of messages |
| **W5** | KNOCKOUT: orders learned from questions with their symbols shuffled | W3 not met |
| **W6** | hygiene: core/wordorder.py holds no word of any language | structural |

PASS = W1-W6.

## 3. Predictions
P1 "of" relation-first, from ~60 observations. P2 W2 0 %. P3 W3 ~5 %. P4 coverage ~80 %. P5 the knockout learns no
consistent order.

## 4. Run 1 (2026-10-05): FAIL W1, W3
Observations from half A: of {relation-first 7, argument-first 1}, in {2, 2}, for {argument-first 1}, and {1}: no link
unanimous, nothing learned, SPEAK unchanged (reversed 1,130/2,448). The disagreeing observations were a defect of the
role assignment, not of the data: roles were taken from a world's CONTENT kinds -- the kinds an answer OWES -- which for a
table world include the FILTER VALUE ("gadget", "february") and exclude its operator ("sum"), so "sum of quantity for
gadget" was read argument-first.

## Amendment, run 2 (declared after run 1)
Roles from the engine's reading codes: property, column, operator (P, C, O) are relations; entity, filter value, number
(E, F, N) are arguments. Everything else as registered.

## Run 2 (2026-10-05): NOT PASSED (W3)
Half A: of {relation-first 17}, for {relation-first 4}, in {relation-first 2}: learned of and for, relation-first. W2 0/54
of half B called out of order. But SPEAK's reversed wordings fell only 1,130/2,448 -> 988/2,306 (43 %): most reversed
wordings never put a relation and an argument around ONE link -- "the director BY WHICH jaws", "alice THE salary" -- so a
rule that only forbids reversals around learned links does not see them. W4 16/18, W5 knockout learned only {is}, W6 ok.

## H10b -- LICENSING (declared after run 2, before its run)
Usage-based grammar produces only ATTESTED combinations. Rule: in a re-read, every relation span must be attached to an
argument span by a (link, order) pair -- link = the one closed-class symbol between them, or none when they touch --
seen at least twice in the correctly answered questions. A relation without a licensed attachment rejects the wording.
Gates as W2-W6 (W2 with licensing on half B: <= 2 % of correct questions unlicensed; W3 <= 10 % reversed; W4 >= 60 %
coverage; W5 knockout from shuffled questions fails W3).

## H10b run (2026-10-05): NOT PASSED (W2b 32/54 unlicensed; W4b 10/18) -- and the wordings are right
W3b reversed **0/129** (from 43 %); the chosen wordings read as English for 6 of 8: "120 is the salary of alice", "2012
is the start of judy", "michelle obama is the spouse of barack obama", "africa is the continent of egypt", "william
shakespeare is the author of hamlet" ("18 is double in 9" and "a double of 50 that is 100" remain). W5b knockout
licensing: reversed 54/94. But licensing from 42 questions rejects 32 of 54 correct held-out questions: a "link" was ONE
closed symbol, so "the country OF THE city" attaches nothing, and a chain's outer relation attaches to a RELATION, which
the rule did not allow.

## H10c (declared after H10b, before its run)
A link is the run of 0-3 closed-class symbols between two used spans; a relation is licensed by an attested (link,
order) attachment to ANY used span (an argument, or another relation in a chain). Same gates as H10b.

## H10c run (2026-10-05): NOT PASSED (W2c 2/54 = 3.7 %; W3c 34 % reversed)
Attested attachments (half A) now include ('', chain) 22, (of the, chain) 22, (of, relation-first) 17. Coverage returns
(16/18) and the unlicensed held-out questions fall to 2/54 ("how many employees are in support", "difference in salary
between engineering and sales"), but reversed wordings return to 34 %: a chain attachment carries no order, and
touching relations ('' chain, 22 sightings) license almost any adjacency. W5c knockout 46 %.

### What the three runs establish
| rule | reversed accepted | coverage | correct held-out questions refused |
|---|---|---|---|
| none (SPEAK) | 46 % | 16/18 | -- |
| H10: forbid reversals around learned links | 43 % | 16/18 | 0/54 |
| H10b: license only attested one-symbol attachments | **0 %** | 10/18 | 32/54 |
| H10c: license attested runs and chains | 34 % | 16/18 | 2/54 |

Usage-based licensing is the rule that fixes word order (H10b: 0 % reversed, and its chosen wordings read as English:
"120 is the salary of alice", "2012 is the start of judy"); what it lacks is EXPOSURE -- it learned from 96 questions,
and a child learns its attachments from millions of sentences. The order-carrying version of H10c (a chain attachment
with its order, learned from many more read phrases -- e.g. the noun phrases of definitions the engine can read) is the
next step. Not registered.

## H10d -- EXPOSURE (declared after H10c, before its run)
Claim: H10b's strict licensing fails on coverage for lack of exposure, not for being wrong. Exposure: windows of 3-6
symbols from Wiktionary example sentences and definitions that contain a relation word (the crawl's property labels,
the tables' headers) are read by the engine; a window read as one COMMIT/ATTRIBUTED value from a computing world with
every open-class symbol used is a READ PHRASE, and its attachments (H10b's: one closed symbol or none) are counted
beside the questions'. Up to 20,000 windows tried, seeded. Gates: W2d half B unlicensed <= 2 % (licence from half A +
the read phrases); W3d reversed <= 10 %; W4d coverage >= 60 %; W5d knockout (windows' symbols shuffled before reading)
does not meet W3d and W4d together.

## H10d run (2026-10-05): NOT PASSED -- no exposure was gathered
20,000 windows from Wiktionary sentences, each containing a relation word, were read: **0** read as one value from a
computing world with every open-class symbol used. With no added exposure the licence is H10b's (W3d reversed 0/129, W4d
10/18, W2d 32/54 unlicensed); the knockout is identical for the same reason. The test of "exposure is the bottleneck"
could not run, and its failure is itself the finding: the engine can read NONE of 20,000 phrases of ordinary dictionary
prose as a complete, used reading -- its reader covers the questions it was built for, and real text almost not at all
(the gloss line's 0.34 measures word coverage; this measures whole-phrase readings, and finds zero). Comprehension of
real text is the floor every fluency rung stands on.
