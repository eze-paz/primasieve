# W6 PRE-REGISTRATION -- critical thinking: contradictory claims and the record of a source

Written BEFORE the code ran (2026-09-22). Owner: "an important skill we must inbuild is critical thinking. it
must be able to weigh contradictory claims, know how to evaluate the quality of sources." Standing rules unchanged:
zero LLM, no hardcoded paradigm, CONFAB 0, 5-minute cap, nulls reported, every gate shown to FAIL on main first,
"a contest is never settled by vote" (multi-source agreement is corroboration, not an oracle).

## The diagnosis

Today two sources disagreeing is indistinguishable from one source being ambiguous: both end as READINGS. Every
certificate is checked verbatim, so nothing is misattributed, but a source that has been wrong before is quoted
with the same standing as one that has never been wrong. There is no record of outcomes anywhere in the engine.

## Mechanism (core/ledger.py, core/reason.py, core/session.py, frames.py)

LEDGER. Per source name, COUNTS of certificate outcomes -- `confirmed` and `contradicted` -- plus the list of
retracted claims. Counts, never probabilities, never a score. An outcome is written ONLY by an oracle:
  * the confirmation channel: `Session.teach(question, gold)` finds the turn that asked that question; every
    option whose value equals gold has its sources confirmed, every option whose value differs has its sources
    contradicted and its claim recorded as retracted;
  * an attached world with `attributed = False` (the user's own data, an executable primitive) whose value for the
    same structure differs from a quoted claim contradicts that claim's source (the same rule, applied inside the
    loop when both survive at the top).
Agreement between quoted sources writes NOTHING (corroboration is printed, not counted).

CONTEST. In reason(): when the top survivors carry several values from quoted (attributed) sources, the result
lists every option with its sources' records. The verdict:
  * no option's sources have a strictly better record  -> READINGS (ask), exactly as today, with the records shown;
  * exactly one option's sources have a strictly better record -> CONJECTURED (core.verdict's fourth state: a guess
    with a correction channel): that value, both claims cited, both records printed, retractable by teach.
"Strictly better" = fewer contradictions; on a tie of contradictions, more confirmations; otherwise not better.
A record is a property of a SOURCE NAME, never of a claim's content: shuffling the source names shuffles the
verdicts identically (permutation criterion).
A CONJECTURED value is never rendered as ANSWER: a sixth frame, CONJECTURE, realized as "Probably X (per A; record
c confirmed, d contradicted) rather than Y (per B; ...). Correct me if wrong." with an exact inverse.

## The test bed (offline, no Wikidata: two or three LOCAL quoted sources over the same facts)

`core/triples.py`: a generic source adapter over a JSON file {entity: {property: [values]}} exposing the same
interface as the Wikidata source (entities / properties / claims / claims_text / label / consulted), so KGWorld is
reused unchanged. `worlds/almanac.json` (source A), `worlds/gazetteer.json` (source B), `worlds/atlas.json`
(source C): five countries, capital / official language / currency. Seeded disagreements, fixed here:
  A says capital of spain = barcelona (B: madrid)          A wrong
  B says official language of france = occitan (A: french) B wrong
  B and C say currency of italy = lira (A: euro)           B and C wrong, and they AGREE with each other
Everything else agrees.

## Gates

  W6-a  FAILS ON MAIN: HEAD's loop over A and B on "what is the capital of spain" -> READINGS with no record
        anywhere (no ledger exists; the frame carries no counts); shown by running HEAD's core/reason.py from git.
  W6-b  CONTEST SURFACED, NEVER A VOTE: fresh ledger, "capital of spain" over A+B -> READINGS, both options carry
        (source, 0 confirmed, 0 contradicted). "currency of italy" over A+B+C -> READINGS although two sources agree
        on lira: corroboration printed, verdict unchanged.
  W6-c  THE ORACLE WRITES THE RECORD: teach("capital of spain", madrid) -> ledger A contradicted 1, B confirmed 1;
        A's barcelona claim listed as retracted. Then "official language of france" (A french vs B occitan) ->
        CONJECTURED occitan via B (B's record is better at that moment) -- the conjecture is WRONG and says so it
        can be corrected; teach(french) -> B contradicted 1 / confirmed 1, A confirmed 1 / contradicted 1.
        Then "currency of italy" (A euro vs B+C lira) -> CONJECTURED euro via A? NO: A and B tie on record and C is
        0/0 -> the lira option's sources {B, C} have 1 contradiction, A has 1 -> tie -> READINGS. Teach(euro) ->
        B contradicted 2, C contradicted 1, A confirmed 2. A fourth contest, "capital of portugal" (A lisbon vs
        B porto, seeded here as the fourth disagreement) -> CONJECTURED lisbon via A (A: 2 confirmed 1 contradicted
        vs B: 1 confirmed 2 contradicted).
  W6-d  CONFAB 0: no CONJECTURED value is ever emitted as ANSWER; the wrong conjecture in W6-c is counted as a
        conjecture (its own column, as E-9 did), never as a confabulation; every CONJECTURE frame round-trips.
  W6-e  PERMUTATION: rename the sources (A<->B<->C) and rerun the whole script: the sequence of verdict KINDS is
        identical (the record follows the name, the mechanism prefers no name).
  W6-f  runtime < 300 s offline; core_selftest C3 zero islands; no authored English in core/ledger.py.

Predictions. W6-a READINGS with no counts. W6-b two READINGS. W6-c the four verdicts as written (READINGS,
CONJECTURED-wrong, READINGS, CONJECTURED-right). W6-d 0 confab, 1 wrong conjecture, corrected. W6-e identical kinds.

Declared limits. A record is per source, not per source-and-domain (a source good at capitals and bad at currencies
is one count); the oracle is the user or an attached executable/data world, never another quoted source; nothing
here estimates how likely a claim is -- it counts what happened.

## RESULT (2026-09-22) -- `python critical.py`: W6 CRITICAL THINKING: PASS, CONFAB 0, 0.1 s offline

W6-a  Main (23714f0) did WORSE than predicted: the two sources' identical structure was merged into ONE multi-valued
      claim, and "barcelona ; madrid" was asserted as an ATTRIBUTED set. The prediction (READINGS without a record)
      was wrong; the failure is sharper. Fix: a claim's identity is the structure AND the world that made it
      (core/reason.py _key); two sources asserting the same structure with different values are two claims in contest.
W6-b  Fresh ledger: "capital of spain" -> READINGS with (almanac 0/0) vs (gazetteer 0/0). "currency of italy" with
      the gazetteer and the atlas agreeing on lira against the almanac's euro -> READINGS: two against one settles
      nothing. Corroboration is printed in the option ("atlas+gazetteer"), never counted.
W6-c  Amendment (a vote in disguise, caught before the gate was kept): the prereg summed records over an option's
      sources, which grows with the number of agreeing sources. An option's record is now its BEST source's record
      (core/ledger.py of). Under that rule the script gives READINGS, READINGS, CONJECTURED lira (wrong: the atlas had
      a clean record at that moment), CONJECTURED lisbon (right); the prereg's walk-through had forgotten the atlas.
      Final ledger almanac 2 confirmed / 1 contradicted, gazetteer 1/2, atlas 2/1; retracted: almanac barcelona,
      gazetteer occitan, atlas lira, gazetteer lira.
W6-d  CONFAB 0; the wrong conjecture is a conjecture (its own column) and is corrected by teach; every CONJECTURE
      frame round-trips (12/12): "Probably lira (per atlas+gazetteer; record 2 confirmed, 0 contradicted) rather
      than euro (per almanac; record 1 confirmed, 1 contradicted). Say so if that is wrong."
W6-e  Renaming the sources gives the identical verdict sequence and the same counts under the other names.
W6-f  No authored English in core/ledger.py; 0.1 s.

What the engine now does that it did not: it keeps a record of every source that spoke on a question the user
later settled; when quoted sources contradict each other it names the contest and each side's record; it commits to
nothing on a contest, but it will CONJECTURE the side backed by the source with the better record, say so, and
retract on correction; agreement among sources never decides. What it still does not do: a record is per source,
not per source-and-topic; the only oracles are the user and attached executable/data worlds; nothing estimates a
likelihood -- it counts.
