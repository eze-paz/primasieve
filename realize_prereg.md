# Pre-registration -- AN ATTESTED REGISTER FOR REPLIES, WITH THE LOOP AS THE INVERSE (`realize.py`)

Registered 2026-10-02 before the first run. Owner's question: how to get replies that are not rigid without hardcoding an
opinionated structure. Answer under test: the register is DATA mined by distant supervision, the form is INDUCED from it,
and the constraint on a reply is SEMANTIC (the engine must read its own sentence back to the frame it meant), not
syntactic (a regular expression it must match).

## 1. The measured problem

Every reply today is one of a few templates with an exact regex inverse (`frames.py`); fluency was never their goal
(LOOP.md: F3 closed at the novelty/typicality frontier, F4 met only as "every reply is a rendered frame"). The chat plan's
phase C names an authored seed set as the fallback register. Authoring is what this file tries to make unnecessary for
the ANSWER frame, the one frame with an attested counterpart in encyclopedic text.

## 2. The mechanism (one file, imports core/ + the offline sources)

1. **Register by distant supervision.** For every fully labelled triple (s, p, o) in the offline Wikidata cache
   (measured before registration: 1,895 triples, 509 labels), the Wiktionary entry (kaikki index, offline) of s and of o
   is read; a definition or example sentence that mentions the OTHER label verbatim (word-boundary, case-insensitive) is a
   PAIR (triple, side, text). Measured before registration: 1,508 such texts (972 definitions, 536 examples). Nothing is
   written by hand; the alignment is checked the way a certificate is (the span is verbatim in the source).
2. **Skeletons by abstraction.** In each pair's text the two labels are replaced by slots `{S}` and `{O}`; the result is a
   skeleton keyed by (property, side). A skeleton is ADMITTED when it recurs across at least two distinct triples
   (E-8's two-source rule applied to form); singletons are held as weak and used only when nothing admitted fits. Two
   shapes arise from the data and both are kept, counted separately: (a) texts on the SUBJECT's entry that name the value
   ("Capital and largest city: {O}"), filled directly; (b) definitions on the VALUE's entry that describe it in terms of the
   subject ("The capital and largest city of {S}."), realized in the dictionary's own headword convention,
   `<headword>: <gloss>`. The only joins in the file are that colon and the provenance tail " (per <sources>)". Both are
   declared here; no other English literal takes part in selection.
3. **The loop as the inverse.** A candidate reply is ADMISSIBLE iff (i) it contains the frame's value label, and (ii)
   `core.reason(reply, [kg world])` returns a unique value equal to the frame's value. A candidate that reads back to
   another value is a MISREPORT and is dropped; one that reads back to several or none is REJECTED (counted, not emitted).
   No regex is consulted.
4. **Selection with a temperature on the form side.** Among admissible candidates, weight = attestation count (how many
   distinct triples the skeleton recurs over); the reply is sampled from softmax(log weight / T). T = 0 is the most
   attested surface; T = 1 is proportional. The frame is fixed before any of this runs, so T can change the sentence and
   never the claim. The template fallback (`frames.realize`, or a one-line stand-in if that module is mid-change) is used
   when no candidate is admissible, and the number of fallbacks is the printed number.

Declared biases: two-triple admission; the colon and the provenance tail; T in {0, 1} reported. No property, entity or
word is named in the code.

## 3. Evaluation set
LOOKUP questions "what is the <property> of <subject>" for every cached triple whose property is among the eight most
frequent in the register and whose question the engine answers ATTRIBUTED with the unique value o (so the frame is the
engine's own, not a constructed one). Fixed by the data; the count is printed.

## 4. Gates

| gate | claim | bar |
|---|---|---|
| **R1** | the register is data: pairs and admitted skeletons printed; skeleton count grows with the data (half the triples admit fewer skeletons than all) and no code names a property | monotone; structural |
| **R2** | round trip through the loop on every EMITTED reply | 100 % (by construction; the rejection rate of candidates is printed) |
| **R3** | MISREPORT (a candidate reading back to a different value) | 0 emitted; the count among candidates printed |
| **R4** | coverage: evaluation frames realized by an attested skeleton rather than the fallback | **>= 50 %**; the fallback count printed |
| **R5** | variety: distinct admissible surfaces per covered frame at T = 1 over 20 samples | mean >= 2 |
| **R6** | novelty: covered replies that are not the template's surface | 100 % of covered (they come from a different source) |
| **R7** | KNOCKOUT: shuffle texts across triples before abstraction | admitted skeletons < 25 % of the main run's, coverage < 10 % |
| **R8** | hygiene: no string literal in the selection path shares a token with an emitted reply except the two declared joins; imports core/ and the offline sources only | structural |

## 5. Predictions
- **P1** ~150-300 admitted skeletons; most under `country`, `capital`, `capital of`, `continent`, `official language`.
- **P2** R4 lands between 50 and 70 %: definitions that mention other entities too read back as READINGS and are rejected.
- **P3** R3: a handful of candidates misreport (a definition mentioning a different capital, e.g. a former one) and all are
  dropped; the inverse is what makes distant supervision safe.
- **P4** R7 collapses: shuffled texts almost never recur across two triples once abstracted.
- **P5** variety is modest (2-4 surfaces) because most properties have one or two dominant definition shapes.

## 6. What a PASS would and would not establish
Would: ANSWER replies drawn from attested text, varied by a temperature, with the engine's own reading as the only
constraint, and zero authored sentences. Would not: fluency for READINGS / PARTIAL / PROPOSE / CONJECTURE (no attested
counterpart; they stay on the fallback and are counted), discourse across turns, or a judge of English beyond the round
trip. The join (`<headword>: <gloss>`) is a dictionary convention, not prose; replacing it with an attested copula frame
learned from example sentences is the named next step.

## 7. MEASURED (2026-10-02) -- `python realize.py`: NOT PASSED. The register exists; the inverse is the wall.

| gate | measured | |
|---|---|---|
| **R1** | 1,895 triples -> 1,508 pairs (972 definitions, 536 examples) -> **14 admitted skeletons** (1,139 weak); half the triples admit 5 | PASS (grows with data; no code names a property) |
| **R2** | round trip by construction; 16,183 candidates checked: 15,047 "edge not read", 827 unverified name, 211 unverified relation, 50 conflicting | PASS on emitted replies |
| **R3** | 50 candidates would have misreported (a different value for the same edge: former capitals, other "Tokyo"s); 0 emitted | PASS |
| **R4** | coverage **37/116 = 0.32** under the lenient inverse; **0/116** under the strict one (every content symbol inside a verified span) | **FAIL** |
| **R5** | variety 1.30 surfaces per covered frame | **FAIL** |
| **R6** | 37/37 novel vs the template | PASS |
| **R7** | shuffled texts: 2 admitted skeletons (main 14), coverage 0.00 | PASS |
| **R8** | no selection-path literal shares a token with an emitted reply (joins excluded) | PASS |

### What the 37 "admissible" replies look like, and why that is the finding
`Paris: A federal city, the capital and largest city of France.` is right. `Germany: A former Germany and country that
existed between 1871 and 1918. Capital: Brandenburg.` is admissible too -- and false. It came from the German Empire's
definition ("A former empire and country ... Capital: Berlin") aligned to (Berlin, country, Germany), abstracted with
the labels in the wrong roles, filled for (Brandenburg, country, Germany), and ACCEPTED by the inverse: the carrier
LOOKUP(Brandenburg, country) = Germany is a verified edge, the frame's own names are used, and the world reads nothing
else in the sentence -- "former", "existed", "1871", "Capital:" are not names or relations to it (the definition-frequency
filter that tells names from words in a short question drops them in a long one). So the lenient inverse (R2) keeps
the engine from misreporting the EDGE and cannot keep it from saying things the frame does not support. The strict
inverse (R2') -- every content symbol must sit inside a span some verified survivor used -- is the right criterion and
licenses **nothing**: no attested definition is made only of two names and a relation word.

### Four amendments, made in order and recorded
1. Admission counts distinct dictionary ENTRIES, not triples (two Wikidata items labelled "Tokyo" share one text).
2. The carrier must SAY the relation (a structure using a property reading); a bare PATH between the two names is a
   co-mention -- the first run accepted a defence-policy example sentence that happened to mention both ends.
3. The frame's own two names count as used wherever they stand (the value's mention was being flagged as unverified).
4. A capitalized, non-initial token outside every used span is an unverified name (orthography, declared) -- the world
   reads few names in long text; this caught 827 candidates the world had not.

### Prediction ledger
- **P1 MISS**: 14 admitted skeletons, not 150-300. Distant supervision over 509 labels yields few texts that recur in
  the same shape across two entries; the long tail (1,139 weak) is one-off.
- **P2 MISS**: 0.32 lenient / 0.00 strict, not 0.50-0.70.
- **P3 HIT**: 50 misreporting candidates, all dropped by the edge check.
- **P4 HIT**: the knockout collapses (14 -> 2, coverage 0).
- **P5 MISS**: variety 1.30.

### Disposition and the one thing it shows
Not registered; nothing in core/. The register mechanism is sound and data-only; the inverse is where fluency without
authoring stands or falls, and today's engine reads a declarative as two names and a relation word. A reply whose every
word the engine can account for is the standard; meeting it needs the engine to read noun-phrase structure (modifier vs
relation, apposition, dates) -- the grammar-induction side of the project (COGS, nolf) applied to English glosses, which
nothing does yet. That, not the register, is what item 1 of the fluency list reduces to.
