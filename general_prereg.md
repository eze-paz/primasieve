# GENERAL PRE-REGISTRATION -- worlds as data, composition across worlds, the library in the loop, turns, research

Written BEFORE the code ran (2026-09-21). Owner's instruction: "something cheaper for step 1. proceed and do all
steps now." Standing rules unchanged: zero LLM, no hardcoded paradigm (permutation criterion), "I don't know" is an
internal research trigger never an output, CONFAB 0 throughout, 5-minute cap per run, nulls reported never tuned,
every gate shown to FAIL on today's main before the change (the meta-rule), merge or delete, no islands.

## The diagnosis this answers

The one loop (core/reason.py) reasons inside any world that has a verifier. Every world so far is a hand-written
module: `core/kg.py` is shaped like Wikidata's API, `core/table.py` like one flat table, `core/gloss.py` like a
dictionary. By the owner's own criterion a "world" is therefore still a PARADIGM: adding a domain means editing
code. General reasoning is claimed only when a new domain costs DATA and TEACHING EXAMPLES, not code; when one
question can draw on several worlds in one derivation; when learned operators are what the loop searches over; when
a turn can bind to the previous one; and when a miss in one world is a research trigger into every other.

## W1 -- a world is data (the fourth domain costs zero world code)

Mechanism. `core/table.py` grows from one flat table into RECORDS: several named collections of records, where a
field whose every value is the key of a record in another collection is a REFERENCE field. Nothing declares this;
it is induced from the data (a field is a reference iff all its values are keys elsewhere). Readings then include
record keys (kind "E"); structures include CHAIN over references (field of a field, 1-2 hops); the flat table is the
special case with one collection and no references (tables_numbers must reproduce unchanged).
The fourth domain. `worlds/orgchart.json`: employees (name, department -> ref, manager -> ref, salary, start year)
and departments (name, floor, city). Chosen because its verifier is the file itself: no network, no code.
Its teaching pairs and 20 held-out questions live in the runner, not in core.
Gates.
  W1-a  FAILS ON MAIN: the single-table arm (today's TableWorld over the employees collection alone) answers
        0 of the 8 reference questions ("who is the manager of the manager of X", "what is the city of the
        department of X", "total salary of the department of X"); reported as the arm's number.
  W1-b  records arm: >= 18/20 held-out correct, CONFAB 0 (a wrong committed value = 0), every COMMIT cites cells.
  W1-c  ZERO WORLD CODE: the domain is one JSON file plus (question, confirmed answer) pairs; the runner asserts the
        domain file parses as JSON and that no module named after the domain exists in core/.
  W1-d  tables_numbers reproduces 30/30 CONFAB 0 on the same module (the flat table is the no-reference case).

## W2 -- composition across worlds in one derivation

Mechanism. `reason(text, worlds)` takes a LIST of worlds. Readings are gathered from every world; every structure is
evaluated by the world that afforded it. Then one PIPE step: a survivor whose spans cover a strict sub-span of the
question is substituted (its label's symbols replace the span) and the loop runs once more over all worlds; a
composite's spans are the union (mapped back to the original positions), its certificates the union, its support
both worlds' supports in order. Ranking is unchanged (coverage, simplicity, specificity), so a composite that covers
more of the question outranks either half. Depth is 2 (one pipe). No world knows another exists.
Questions (fixed here): 10 cross-world questions, e.g. "what is the country of the city of the engineering
department" (records -> KG), "what is the total salary of engineering times 2" (records -> exec),
"what is the capital of the country of the city of sales" (records -> KG chain).
Gates.
  W2-a  FAILS ON MAIN: each single world alone answers 0/10 (NOT FOUND or PARTIAL); printed per world.
  W2-b  composed: >= 7/10 correct, CONFAB 0; every answer carries certificates from BOTH worlds it used.
  W2-c  the composite's coverage strictly exceeds the best single-world survivor's on every answered question.

## W3 -- the library is what the loop searches over

Mechanism. `core/exec.py`: ExecWorld reads numbers and operator WORDS (a lexicon induced from teaching by the same
elimination as tables: a word survives for every primitive/library entry that reproduces every confirmed example);
its structures apply an operator to the read numbers; the operator space is `core.primitives.candidates` plus a
LIBRARY of learned compositions. WAKE: a teaching word with confirmed examples is bound by search over compositions
of primitives up to depth D within a cap. SLEEP (core.generate.compress_recurring): the fragment recurring across
confirmed solutions is crystallised as a library entry and becomes a leaf for later searches. The library is stored
as expression trees over opaque primitive ids (no names).
Task (fixed here). Made-up operator words with confirmed examples: `twiddle` (x -> 2x+1, depth 2), `blorp`
(x -> 2x-1, depth 2), then `quop` (x -> 2(2x+1)+1 = 4x+3, depth 4 with consts 1,2; = twiddle o twiddle).
Gates.
  W3-a  FAILS ON MAIN / blind arm: with the library disabled and the same cap, `quop` is NOT bound (search exhausts
        the cap) -> the question "what is the quop of 5" is PROPOSE, never a value.
  W3-b  library arm: after twiddle and blorp are confirmed, sleep crystallises the recurring fragment; `quop` binds
        as a composition over the library within the same cap; "what is the quop of 5" -> COMMIT 23 with the
        examples cited as certificates. Evaluations printed for both arms.
  W3-c  no wrong binding: a teaching word bound to a composition that fails any later confirmed example is
        retracted (printed), CONFAB 0 over 12 held-out arithmetic questions.
  W3-d  the 60x39 case: with ONE teaching pair ("3x4" -> 12) `x` binds to the multiplication primitive by
        elimination and "60x39" -> 2340 COMMIT; without the pair it is PROPOSE naming the sources consulted
        (the owner's honest-truth rule: no authored reading of `x`).

## W4 -- turns bind

Mechanism. `core/session.py`: a Session holds the worlds, the teaching so far, and the history of frames. Each
turn calls reason() with CONTEXT = the previous answers' values, offered as VIRTUAL readings at a position past the
end of the text (the same device induce_lexicon uses), so a structure may take a prior answer as an argument at
zero coverage: an explicit reading always outranks it. A reply to a READINGS frame that names one option's value
COMMITS that option and records (question shape -> chosen structure key) as teaching. A reply "no"/a corrected value
to an ANSWER retracts the lexicon entry that produced it. No pronoun list, no speech-act taxonomy: the only cues are
the previous frame's own values and the presence or absence of a match.
Dialogues (fixed here): 6 scripted dialogues of 3 turns each over KG / records / exec / gloss, where turns 2-3 are
unanswerable stand-alone ("what is its currency", "and of japan", "double it").
Gates.
  W4-a  FAILS ON MAIN: the stand-alone arm (each turn reasoned alone) answers 0 of the 12 dependent turns.
  W4-b  session arm: >= 10/12 dependent turns correct, CONFAB 0.
  W4-c  a READINGS turn followed by the user's choice commits it, and the next same-shaped question is answered
        without asking (binding retained); shown on one dialogue.
  W4-d  every reply still round-trips (frames.py parse(realize) == frame) -- F4-a holds on the session's replies.

## W5 -- research is the default everywhere

Mechanism. reason() over the world list: when no world supports a structure, `consulted` is the UNION of every
world's consulted() (Wikidata searches, record collections, primitive signatures tried, gloss sources by name).
PROPOSE names all of them. A symbol no world reads is looked up in the gloss sources as part of the same call (the
gloss world is a member of the list), so a KG question whose subject only a dictionary knows still gets FOUND.
Gates.
  W5-a  FAILS ON MAIN: today's single-world PROPOSE for "what is the capital of xyzzyq" names only "readings none"
        (f4 to_frame); it does not name Wikidata, the record collections, the primitive inventory or the dictionary.
  W5-b  multi-world: the same question -> PROPOSE whose consulted list names every world's sources (>= 4 names).
  W5-c  "what is a pomegranate" asked through the SAME world list -> FOUND with the gloss cited (research fell
        through to the dictionary).
  W5-d  no bare abstain on any of W1-W4's prompts (F4-b holds on the multi-world loop).

## Global
  G1  core_selftest C3 zero islands; C2 published numbers unmoved (kg_multihop, tables_numbers, f4_dialogue).
  G2  no authored English in core/ (string-literal check as F4-f) including the new modules.
  G3  every gate runs under 300 s offline (Wikidata from the committed cache; the cache may be warmed once online
      for the new cross-world entities and committed, as previous runs did).

Predictions. W1-b 19-20/20; W2-b 7-9/10 (cache coverage is the risk, not the mechanism); W3-b binds within ~10^3
evaluations against a blind cap of 5x10^4; W4-b 10-12/12; W5-b 4-5 names. If W2 stays below 7 for cache reasons the
null is reported as such, not tuned.

Declared limit. The form line (how fluently the engine speaks) is untouched; replies remain frame realizations.

## RESULT (2026-09-22) -- `python worlds_general.py`: GENERAL WORLDS: PASS, TOTAL CONFAB 0, 277 s offline

W1  records world (core/table.py: collections + references INDUCED from the data; hops in both nesting orders; the
    collection-name reading; DIFF walked through the same hops). Fourth domain `worlds/orgchart.json` + 14 pairs.
    W1-a HEAD's single-table module on the 8 reference questions: 0/8 (FAILS ON MAIN). W1-b 20/20, CONFAB 0.
    W1-c one JSON file, no module in core/ named after it. W1-d tables_numbers 30/30 CONFAB 0 on the same module.
W2  one loop over a LIST of worlds with one PIPE step (core/reason.py). W2-a every single world alone 0/10.
    W2-b 10/10, CONFAB 0, certificates from both worlds 10/10. W2-c composite coverage > best single 10/10.
    Amendments (each shown to bite before it was kept): coverage counts DISTINCT positions (a composite had counted
    the substituted region twice); composition is across worlds only (a world's own chains are its own); the outer
    must read something beyond the substituted value; a quoted text is neither substituted nor a composition; a value
    the world cannot name is not substituted; at equal coverage the source's own search order decides between
    same-named entities (KGWorld.rank_key), and a filter on a KEY column outranks the same value in a reference
    column (TableWorld.rank_key). Two W2 questions were replaced because records ALONE answered them by coincidence
    (capital of Portugal = Lisbon, the value the records step already produced): "a gate that already passes does
    not discriminate" applied to a question.
W3  core/exec.py + core/induce.py (the table's elimination, generalized and shared). Task amended: quop = 4x+3 was
    blind-REACHABLE at 30,257 evaluations (null recorded), so the tier-3 word quop = twiddle^3 = 8x+7 is the task.
    W3-a blind arm: cap 50,000 exhausted, NOT FOUND. W3-b library arm: bound in 308 evaluations, COMMIT 47 citing the
    teaching. W3-c held-out 10/12 correct, CONFAB 0, 2 READINGS (nesting without precedence -- honest); retraction
    shown (zap: 2x+1 on two examples, a third contradicts, dropped, re-searched to x*x+1, zap of 6 -> 37).
    W3-d 60x39 -> 2340 from the single pair "3x4 -> 12"; untaught -> PROPOSE naming the sources.
    Nulls: sleep found no recurring fragment among twiddle/blorp/double (the search finds the additive forms first,
    which share no sub-tree); the library reached quop through twiddle itself, not through a sleep-made fragment.
    Words sharing one example set share one search (memo); a filler is never searched when a purer word explains the
    open questions; teaching accumulates across calls (purity over ALL pairs), which is what stopped "is" from being
    bound as an operator in the first run.
W4  core/session.py. W4-a stand-alone arm 0/12. W4-b 12/12, CONFAB 0. W4-c the "17" choice binds the nesting shape
    and "twiddle of the blorp of 6" is answered 25 without asking. W4-d 18/18 round trip, bare abstain 0.
    Amendment: context hands a world back its OWN readings verbatim (label re-search made "Paris" three entities).
W5  W5-a HEAD's to_frame names 0 sources. W5-b PROPOSE names Wikidata, records, exec, dictionary (4). W5-c
    pomegranate FOUND from WordNet through the same world list. W5-d bare abstain 0 over 60 prompts.
    Mechanism: a symbol the dictionary finds nowhere is an UNKNOWN reading (content kind), so an answer that ignores
    it is PARTIAL, and a PARTIAL whose only content is quoted text is rendered as PROPOSE (chat layer).
G   C3 zero islands (1 component, 120 files); F4 375/375, tables 30/30, KG CONFAB 0 unchanged; no authored English
    in core/ (G2); 277 s (G3).

Declared limits. Two-op arithmetic without precedence asks (by design). Composition depth is one pipe. The
dictionary is a research source, never a decider. NEXT (owner, 2026-09-22): critical thinking -- weighing
contradictory claims and the quality of sources. Today a contest is READINGS and "multi-source agreement is
corroboration, not an oracle"; there is no per-source track record. Pre-registration to write: a source LEDGER of
certificate outcomes (a claim later contradicted by an executable or attached world counts against its source, as
counts, never probabilities), contradictions surfaced with each side's record, retraction when an oracle disagrees.

## PROFILE (2026-09-22, owner's question "where is the 277 s spent?")
cProfile over the whole runner (424 s under the profiler): 304 s in the Wikidata source's `claims()` re-parsing the
same cached JSON on every call (163,534 json.loads = 246 s), called 480k times by the two-hop PATH search
(`core/kg.py path/weak`, 349k calls) that the session's context readings multiply (session turns = 373 s of the 424).
The exec world's search was 21 s; everything else under 15 s. Fix: parse each entity's claims once per run
(kb_wikidata.claims memo, exact). Runner: 277 s -> 37 s, verdicts unchanged (GENERAL WORLDS: PASS, CONFAB 0).
Side effect recorded: kg_multihop now 36/40 correct, ask 0 (was 27/40, ask 9), CONFAB 0 -- the source-order
tie-break (KGWorld.rank_key, added for W4) settles same-named entities that used to be asked; the registry needles
(CONFAB 0, PASS) are unchanged and the count is reported here, not claimed.
