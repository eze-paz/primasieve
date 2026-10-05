# Pre-registration -- H6 (+H9): ANSWER IN THE PERSON'S OWN WORDS, CHECKED BY RE-READING (`chat.py` aligned replies, `align.py`; 2026-10-05)

Registered 2026-10-05 before the first run. Zero LLM. FLUENCY_HYPOTHESES.md H6 (dialogue partners align: they reuse
each other's words and structures -- Pickering & Garrod) with part of H9 (say what the listener needs; the evidence
moves behind "why"). speak_prereg.md found the person's own question, re-ordered around the value, the most reliable
fluent wording (13/18 read back) -- with no corpus.

## 1. Mechanism (chat layer; English stays out of core/)
- **An answer is its question with the question word filled.** For an answered question (COMMIT / ATTRIBUTED, one value,
  not a quoted gloss) whose first symbol is NOT used by the answer's structure (the question word) and whose second is
  not used either (the person's own link -- no list), the reply sentence is the person's own text with the first word
  replaced by the value, in the person's casing, capitalised, ending in a full stop: "who is the spouse of barack obama"
  -> "Michelle Obama is the spouse of barack obama."
- **The monitor (H7):** the rest of the question (after the link) is read again by the engine over its worlds, without
  context, and must give one value equal to the answer, with every open-class symbol used (H3's rule, the text model's
  commonest-100 cut). Otherwise the ordinary frame reply is given.
- **Brevity (H9):** the aligned reply carries only its source name in brackets; the evidence stays in the transcript
  record, where "why" already finds it.
- **Opt-in** (`Door(fluent=...)`): the live chat turns it on; the chat gate keeps its frames and its exact round trip.

## 2. Gates
On the chat gate's 200 utterances, one session, fluent on vs off.

| gate | claim | bar |
|---|---|---|
| **A1** | coverage: correct non-quoted value answers that receive an aligned sentence | **>= 60 %** |
| **A2** | alignment: share of the question's content (open-class) symbols reused in the reply, aligned vs frame replies | aligned **>= 0.9** and **>** frame |
| **A3** | truth: aligned sentences emitted whose re-read value differs from the answer | **0**; and the knockout (no re-read) would emit **> 0** such sentences or **0** is reported as "monitor never needed" |
| **A4** | brevity: mean reply length, aligned vs frame, on the same turns | aligned **<= 60 %** |
| **A5** | "why" after an aligned reply returns the evidence | **>= 90 %** of probes |
| **A6** | registered numbers unchanged (chat.py with the default) | unchanged |

PASS = A1, A2, A4-A6 and A3's first clause.

## 3. Predictions
P1 A1 ~65 % (questions without a question word -- "total quantity for doohickey" -- get none). P2 A2 ~1.0 vs ~0.8.
P3 A3 0; the knockout emits a few (questions whose rest reads differently out of context). P4 A4 ~35 %. P5 A5 ~100 %.

## 4. Run 1 (2026-10-05): NOT PASSED (A1 56/96 = 58 % vs 60 %; A2-A6 pass) -- one defect found and fixed
Examples: "who is the spouse of barack obama" -> "Michelle Obama is the spouse of barack obama. (Wikidata)"; "what is the
capital of the country of the brandenburg gate" -> "Berlin is the capital of the country of the brandenburg gate.
(Wikidata)"; "what is 6 times 7" -> "42 is 6 times 7. (exec)". The frame reply for the first example was "The country
of the city of the department of alice: France (according to Wikidata ; records; evidence: row 0 city=paris ...".
A2 content words reused 1.00 (frame 0.99). A3 0 by construction; the monitor refused 18 wordings a knockout would have
emitted. A4 53 vs 124 characters (43 %). A5 "why" returned the evidence 20/20 ("the support was Eiffel Tower -country->
France"). A6 chat.py unchanged.

Defect: a yes/no question ("is the eiffel tower in paris") has an unused first AND second symbol, so it produced "Paris
the eiffel tower in paris." -- the monitor passed it because the rest reads Paris. Fixed with its rule: when the value is
already named in the question, it is a check, not a lookup, and the frame reply is kept. A1 after the fix is printed
below; the registered verdict stays run 1's.
A1  aligned sentences for 54/96 correct value answers   [>= 60 % -> FAIL]

Not registered (A1). The live chat turns aligned replies on.
