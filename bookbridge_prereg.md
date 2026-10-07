# Pre-registration -- NOVEL LOOP ITERATION 5 (B4): THE BRIDGE TO THE REAL WORLD, WITH EVIDENCE; THREE NON-FICTION ERRORS (`core/bookworld.py`, `emergence/kb_bookworld.py`, `book_battery.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. The owner's ruling: a source's claims stay in its own context "unless
we know we are talking about the real world". Iterations 1-4 kept every book proposition book-local. The non-fiction
books (a biography of Bunyan, letters on literature, lectures on medicine) name real people and places; a book name
should be tied to a world-store entity only with EVIDENCE, and even then the claim stays the book's.

## Mechanism
1. **The bridge.** For each book name (its full text, e.g. "Oliver Cromwell", and its key), the store's label index
   gives candidate items. EVIDENCE: the store relates a candidate (any property, either direction) to a candidate of
   ANOTHER name of the same book, and the two names occur in one sentence of the book. A name is bridged when exactly
   one of its candidates has such evidence; the item is chosen, the evidence pair kept. Names of one symbol that are
   among the commonest 1,000 symbols are never looked up (diagnosis: "yes", "felt" resolved to songs).
2. **What a bridge changes -- and does not.** A proposition whose doer is bridged carries `ref` (the item) and
   `ref_evidence`; it is still said "according to <book>" (the claim is the book's, not the store's); the item is
   shown so a reader knows which real person the book means. No proposition becomes a world fact (`real` stays False).
3. **Precision fixes from iteration 4.** (a) A capitalised closed symbol right before "." and a name joins the name's
   run, so the preposition test sees what precedes "Mr."; (b) a pronoun resolves only when no OTHER person-like name in
   the three-sentence window has the same pronoun (God / Bunyan); (c) an auxiliary's chain crosses one non-skippable
   symbol when a participle follows ("has never wholly abandoned").

## Gates
| gate | claim | bar |
|---|---|---|
| **G1** | precision, builder-judged fresh sample of 100 (50 novels, 50 others; seed 5) | **>= 0.90** |
| **G2** | bridges: names bridged per group printed; builder-judged precision of (up to 40) bridges -- is the book's name that item? | **>= 0.90** |
| **G3** | honesty: book propositions said without "according to", or marked `real` | **0** |
| **G4** | B4-book, real novels | **>= 9.5 %** (hold) |

## Prediction
G1 ~0.90; bridges: ~20-40 in the non-fiction (Bunyan, Cromwell, Keats, Fielding, Galen ...), few in the novels
(Poussin and Porbus are real painters in Balzac's story: a bridge there is right); G2 ~0.85; G4 held.
Frozen B4 3/4,605.

## Run (2026-10-07): G1 PASS, G3 PASS, G4 PASS (held), G2 MISS
| gate | result |
|---|---|
| G1 precision, fresh judged sample (tests/bookworld_judged_it5.json) | **91/100 = 0.91 PASS** (novels **50/50**; others 41/50 = 0.82) |
| G2 bridges | novels 2 (August, September -- months), others 23; judged **20/25 = 0.80 MISS** |
| G3 honesty | 0 of 263 said without context; 10 propositions carry a bridged item; none marked real |
| G4 B4-book real novels | **163/1,709 = 9.5 %** held (others 87/3,000 = 2.9 %; all 250/4,709 = 5.3 %) |
Pronoun/narrator precision (not a gate here): 22/27 = 0.81 -- the uniqueness rule (b) did not remove "he" = Bunyan read
as God (Bunyan's own pronoun is unknown, so he does not count as a rival). Frozen B4: 3/4,605 (unchanged).
**Reading.** First pass of the precision bar on the owner's metric. The bridge is right for places, ancient authors and
books of scripture (Pavia, Padua, Alexandria, Plato, Empedocles, Henry Fielding, the Bible) and wrong for single given
names in a biography ("Mary", "Elizabeth" -- Bunyan's daughter and wife -- tied to the Virgin Mary and a queen through
each other), for a lookup that returned a different museum, and for a name run that swallowed a stray ". Burne"
(-> Tom Jones). A display glitch (". Vanborough") comes from fix (a): the trimmed title leaves its "." -- the referent is
right.
