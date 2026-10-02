# Pre-registration -- TURNS BIND OVER LONGER DIALOGUES (`turns.py`; mechanism in `core/reason.py`, `core/exec.py`, `core/table.py`)

Registered 2026-10-02. **Declared up front:** the dialogues below were first run as a diagnostic probe against main
(fe0f26f2) BEFORE this file was written, the four defects it exposed were fixed from the probe, and the gates were
then fixed here. So the session-arm numbers are confirmations of a probe, not blind predictions; what the gates add is
the failure-on-main arm, the controls, the knockout and the round trip, none of which the probe ran. The probe's
pre-fix readings are recorded in section 2 so the attribution is checkable.

## 1. What W4 established and what it left open

`general_prereg.md` W4: six dialogues of three turns over four worlds; 12/12 dependent turns correct at CONFAB 0; a
READINGS choice binds a shape. LOOP.md F4 left "multi-turn binding" open. Three turns never put an antecedent in
competition with another, never asked for a property whose entity was two turns back, never crossed from a computed
value back into a name, and never ran long enough for the context itself to become a cost. The first turn of every W4
dialogue was unscored.

## 2. What the probe found on main (2026-10-02, the same worlds as `worlds_general.py`)

| | main (fe0f26f2) | cause |
|---|---|---|
| "what is the capital of japan" as the SECOND turn after "capital of france" | **CONFAB: Japan** (Tokyo alone) | the three-symbol name reading "capital of Japan" plus the previous turn's property word outranked the text's own LOOKUP by coverage; the explicit property word was there and unused |
| "minus 4" after 3 times 4, plus 5, times 2 | **READINGS {-30, 30}**, **219-638 s**, 5.0 million exec evaluations | both operand orders for a context number; thousands of context-only trees survived and every one was pipe-expanded; the same substitution re-passed 721 times |
| "what is the difference" after the salaries of alice and bob | **CRASH** (`ValueError: 'employee' is not in list`) | DIFF over two same-header filters ranged over every collection, including one without that header |
| "times 2" (third turn) | 25-77 s | as above |
| everything else in section 4 | correct | -- |

Four changes, each world-free and word-free:
1. `core/reason.py`: a survivor that reads nothing of the text is dropped (context alone answers nothing of the text);
   one pipe pass per DISTINCT substitution.
2. `core/reason.py`: **context fills what the text leaves open** -- a survivor using a context reading of kind K is
   dropped when the same world has a context-free survivor using an explicit reading of kind K that it does not use.
3. `core/exec.py`: with one explicit operand, a context number takes the operator's OTHER side (the side is read off the
   text); two context numbers keep both orders; trees built from context alone are not emitted.
4. `core/table.py`: DIFF is emitted only for a collection holding the filters' header.

## 3. Mechanism claims (what the gates test)

- **Recency** settles competing antecedents of one kind without a rule naming it: context items are offered most recent
  first and the loop's last rank key is recency.
- **Ellipsis of either argument**: a turn supplying only a property binds the previous entity; a turn supplying only an
  entity binds the previous property (W4's "and of japan"), including after a turn that itself was elliptical.
- **Cross-world chains**: a records value becomes a Wikidata entity, a count becomes an exec operand, a Wikidata entity's
  property is asked three turns later.
- **No antecedent, wrong-kind antecedent**: nothing is bound; the engine quotes or proposes, never values.
- **Memory is load-bearing**: with the history depth cut to one turn the long-range turn is lost.

## 4. The dialogues (fixed here; turns marked -> depend on a previous turn)

Worlds exactly as `worlds_general.py`: Wikidata offline cache, `worlds/orgchart.json` records with its induced lexicon,
the exec world with the gate's teaching, the dictionary.

```
D1 recency        capital of france -> Paris | capital of japan -> Tokyo | -> its country: Japan | -> its currency: yen | -> its continent: Asia
D2 ellipsis       capital of italy -> Rome | -> and the official language: Italian | -> and the continent: Europe | -> and of spain: Europe | -> and the capital: Madrid
D3 cross-world    city of sales -> rome | -> its country: Italy | -> its official language: Italian | how many employees in sales -> 2 | -> double it: 4
D5 arithmetic     3 times 4 -> 12 | -> plus 5: 17 | -> times 2: 34 | -> minus 4: 30 | -> the double of it: 60 | -> 5 minus it: -55
D7 depth          capital of france -> Paris | 2 plus 2 -> 4 | -> times 3: 12 | -> its country (3 turns back): France
D11 difference    salary of alice -> 120 | -> and of bob: 150 | -> what is the difference: 30
D12 person        manager of alice -> bob | -> his salary: 150 | -> and his manager: carol | -> her department: research
```
22 dependent turns; 29 turns in all. The euro's Wikidata item (Q4916) has no English label in the live data on the
registration date, so "the currency" of italy is not used as a dependent turn (its value would be right and unlabelled).

Controls (fixed here):
```
C1 no antecedent    fresh session: "what is its currency" | "and its capital"
C2 wrong kind       3 times 4 -> 12 | "what is its capital" ;  salary of alice -> 120 | "what is its continent"
```

## 5. Gates

| gate | claim | bar |
|---|---|---|
| **T-a** | FAILS ON MAIN: main's `core/` (loaded from git fe0f26f2) on D1, D11 and D5 up to "times 2" | >= 1 confab, >= 1 crash, and "times 2" >= 5x the session arm's time |
| **T-b** | session arm, dependent turns | **>= 20/22 correct**, CONFAB 0 over ALL 29 turns (first turns included) |
| **T-c** | stand-alone arm (each dependent turn reasoned alone) | 0/22 correct |
| **T-d** | controls C1, C2 | no ANSWER frame on any control turn (FOUND quotes and PROPOSE are the allowed replies); CONFAB 0 |
| **T-e** | depth knockout: D7 with `Session(depth=1)` | the long-range turn is NOT answered; with depth 3 it is |
| **T-f** | round trip: `frames.parse(realize(frame)) == canonical(frame)` on every session reply, 3 realizations each | all; bare abstain 0 |
| **T-g** | runtime: the session arm over all dialogues and controls | **< 120 s**; slowest turn printed |
| **T-h** | hygiene: `core_selftest` C3 zero islands, C4 pass; the four changes name no word of any language | structural |
| **T-i** | no regression: `worlds_general.py` W4 12/12 and its registered needles; `kg_multihop`, `tables_numbers`, `f4_dialogue`, `critical` unchanged | the registry's C2 on these modules |

## 6. Predictions

- **P1** T-b 22/22 (the probe showed 22/22 after the fixes).
- **P2** T-a: confab 1 (Japan), crash 1 (difference), "times 2" >= 5x slower.
- **P3** T-d: the no-antecedent turns are answered with the dictionary's gloss of the property word (FOUND), not a
  value -- the engine's standing behaviour for "what is X"; the wrong-kind turns are FOUND or PARTIAL.
- **P4** T-e: depth 1 loses France on D7 (the antecedent is three turns back).
- **P5** T-g: under 120 s; "minus 4" remains the slowest turn (tens of seconds) -- the remaining cost is in the
  Wikidata world reading the context numbers as items, not in exec; reported, not fixed here.
- **P6** T-i: W4 unchanged; the operator-order rule changes no W4 value (its binary turns were commutative).

## 7. What a PASS would and would not establish

Would: turns bind over longer dialogues with competing antecedents, elliptical arguments on either side, and
cross-world chains, at CONFAB 0, with memory shown load-bearing and controls that cannot be satisfied by grabbing the
nearest value.

Would not: pronoun semantics (no word is read as a pronoun; "its", "his", "her" are simply unread), plural or set
antecedents, antecedents introduced by the user's own statements rather than by answers, or any dialogue outside these
four worlds. Those are the next open items and are named here so they are not claimed by implication.

## 8. MEASURED (2026-10-02) -- `python turns.py`: TURNS BIND: PASS, CONFAB 0

| gate | measured | |
|---|---|---|
| **T-a** FAILS ON MAIN | main (fe0f26f2): confab 1 ("capital of japan" -> Japan), crash 1 ("what is the difference"), "times 2" **29.3 s vs 0.1 s** (446x) | FAILS ON MAIN |
| **T-b** session arm | **22/22** dependent turns correct; CONFAB 0 over all 29 turns | PASS |
| **T-c** stand-alone arm | 0/22 correct (16 FOUND -- the dictionary quoting the property word -- and 6 PROPOSE) | PASS |
| **T-d** controls | 0 of 4 control turns answered with a value: 3 FOUND (gloss of "currency", "capital", "continent"), 1 PROPOSE | PASS |
| **T-e** depth knockout | depth 1 on D7: PARTIAL (the dictionary's readings of "what"), no value; depth 3: France | PASS |
| **T-f** round trip | 32/32 replies, 3 realizations each; bare abstain 0 | PASS |
| **T-g** runtime | session arm + controls **6-7 s**; slowest turn 2.0 s ("what is the double of it") | PASS |
| **T-h** hygiene | core_selftest --map-only: 0 islands, 0 world imports in mechanisms | PASS |
| **T-i** no regression | worlds_general PASS (W4 12/12), tables_numbers 30/30, kg_multihop 36/40 CONFAB 0, f4_dialogue 375/375, critical PASS -- every registered needle reproduced | PASS |

### Prediction ledger
- **P1 HIT** 22/22. **P2 HIT** confab 1, crash 1, 446x. **P3 HIT** FOUND / PROPOSE on every control. **P4 HIT**.
- **P5 MISS, in the good direction.** "minus 4" was predicted to stay the slowest turn at tens of seconds with the cost
  in the Wikidata world. Profiled after the first two fixes it was 46-128 s and the cost was NOT Wikidata: 90 s was the
  domination check itself (quadratic over 2,500 survivors, re-deriving spans) and the rest was 216 pipe passes over
  inner values built from CONTEXT operators applied to the explicit 4 ("12 plus 4", "17 times 4", ...), each
  substituted back and re-passed. Two further changes, both in `core/reason.py`: spans computed once per survivor and
  the context-free survivors' (span, kind) set indexed per world; and a pipe-admission rule -- an inner that borrowed a
  kind-K reading from context while an explicit kind-K reading of the text sits unused is not composed further. The
  turn now takes 0.2 s. The prediction named the wrong world; the profile, not the prediction, is what is recorded.
- **P6 HIT** W4 unchanged.

### What is and is not claimed
Claimed: over four worlds, turns bind across competing antecedents (recency), elliptical arguments on either side,
cross-world chains and a three-turn gap, at CONFAB 0, with the no-antecedent and wrong-kind controls answered by a quote
or a proposal and never by a value, and with memory shown load-bearing by the depth knockout. The four mechanism
changes name no word of any language (the hygiene gate and F4-f's literal check hold).

Not claimed: pronoun semantics -- "its", "his", "her" are unread symbols and the dictionary's reading of "what" is what
surfaces when nothing binds (T-e's PARTIAL lists twelve senses of "what": honest, and not a good reply; the chat layer's
rendering of a PARTIAL whose only content is a function word is the next thing to fix); plural or set antecedents;
antecedents introduced by the user's own statements; the euro, whose Wikidata item carries no English label today.

Registered in `core/registry.py`: `turns: ["TURNS BIND: PASS", "CONFAB: 0"]`.
