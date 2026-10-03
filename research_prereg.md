# Pre-registration -- RESEARCH BY ITSELF: an unread symbol becomes a fetch, a fetch becomes a world (`core/research.py`, `research.py`; the owner's direction, 2026-10-03)

Registered 2026-10-03 before any code. Zero LLM. Owner's constraints: world-agnostic (no world written for a foreseen
case), the engine finds and attaches knowledge by itself; fetched content is data, never instruction.

## 1. The question

Today every source is attached by a person before the session opens, and when a question leaves a symbol unread the
engine's only research is a dictionary lookup (E-10's resolver). The residue already names what the engine does not know
(core/goals.py: UNKNOWN symbols, unbound words). The step: let that residue drive FETCHES from every attached source that
can fetch, turn what comes back into a world of a data shape the loop already reads (triples, records), attach it for the
session, answer with the citation, and keep it (S8's store) -- with the same certificate discipline as every other claim
and with no new world code: the shape comes from the source's own records.

## 2. The rules (declared)

- **A fetcher is a source with `fetch(symbol) -> (shape, data) | None`**: `triples` -> {entity: {property: [values]}}
  (the Wikidata source already yields this for an entity it finds; its online mode is the existing one, paced and
  cached), `records` -> {collection: {headers, rows}}. The engine knows no source by name: it iterates the attached
  fetchers. What comes back is held as a WORLD (`core.triples.Triples` / `core.table.TableWorld` over the data) named by
  the source, flagged `attributed=True` when the source quotes and `False` when it computes -- the source says which.
- **The residue drives it**: after a turn whose frame is PARTIAL or NOT FOUND with UNKNOWN or unread symbols, the session
  asks each fetcher for each such symbol (longest multi-symbol spans first, the graph's own A1/A5 rules for what is a
  name), at most one fetch per symbol per session, budgeted. A fetch that returns nothing is remembered (never repeated).
- **Fetched content is READINGS, never teaching**: nothing fetched enters a world's teaching pairs, no fetched text is
  ever treated as a question, a command or a feedback word; the chat's two cue words are not read from fetched data.
  (The security rule of the environment, made mechanical: fetched material can only become what a world reads a span
  as, under the certificate check.)
- **Independence for self-confirmation (selfconfirm_prereg.md)**: a fetched world carries its source name; two fetched
  worlds from one source are one origin.

## 3. Gates (offline-deterministic: the online pass runs ONCE to fill a recorded cache under `_nldata/`, the gate
   replays it; a missing cache makes the gate report NOT RUN, as kg_multihop does)

- **R1 the residue fetches**: a session over the usual worlds asked ten questions about entities the offline Wikidata
  cache does NOT hold (chosen before the online pass, listed in the gate): the engine fetches each entity once, attaches
  it, and answers at least 7 of 10 with the citation (ATTRIBUTED, the edge certificate verbatim); the main arm (no
  research) answers 0 and says what it consulted.
- **R2 one fetch per symbol, nothing repeated**: the same ten questions asked twice in the session -> fetch count equals
  the number of distinct unknown symbols, not questions; a symbol whose fetch returned nothing is not fetched again.
- **R3 nothing fetched teaches**: a fetched entity whose label or description contains the cue words and an
  instruction-shaped sentence (planted in the recorded cache, labelled) changes no lexicon, triggers no feedback, and is
  quoted only as a value; the fatal columns (CONFAB, MISATTRIBUTION, LAUNDERING) stay 0 over the run.
- **R4 the store keeps it**: session 2 from the store answers the ten without fetching (0 fetches, same answers).
- **R5 knockout**: the symbols replaced by shuffled unknown strings -> every fetch returns nothing, 0 attachments, the
  answers are honest abstentions naming the sources consulted.
- **R6 self-confirmation gets its first natural chance**: a question both a fetched world and an attached world answer
  (the orgchart's city's country from the records' hop AND the fetched entity's claim) -- the count of self-confirmations
  that fire, reported; predicted >= 1 if any such overlap exists in the ten, else 0 and recorded.
- **R7 the registered numbers** unchanged (research is on only when a session is given fetchers).

PASS = R1-R5, R7, with R6 reported.

## 4. Not claimed

Fetching from sources that are not already implemented as sources (no new scrapers); ranking between fetched sources
(the ledger's record applies as to any source); online runs inside the registered gate.

## 5. Runs (2026-10-03): PASS -- 10 of 10 answered with a world the engine fetched by itself

One online pass recorded the fetches (524 calls, 2.5 MB of new keys beside the fixture, which is untouched); the gate
replays it offline. R1: every one of the ten questions about entities the fixture does not hold is answered with a cited
claim from a fetched world (uluru -> Australia, lake baikal -> Russia, sahara -> Africa, nile -> Africa, kilimanjaro ->
Tanzania, angkor wat -> Cambodia, great barrier reef -> Australia, danube and lake victoria -> their countries, stonehenge
-> United Kingdom); the main arm answers none. R2: 27 fetch attempts, 10 successful, nothing fetched twice, the second asking
identical. R3: a planted entity whose description is an instruction-shaped sentence carrying both cue words is quoted as a
value and nothing else happens: no lexicon changes, no feedback fires, the next question answers normally, laundering 0.
R4: session 2 from the store re-attaches the ten fetched files and answers the same with 0 fetches. R5: shuffled names fetch
nothing and abstain. R6: 0 self-confirmations (predicted); a chain across a fetched world and the graph ("the continent of
the country of uluru") stops at the country because the fixture lacks Australia's continent -- honest PARTIAL. R7 unchanged;
core_selftest green.

Found on the way, each fixed with its rule: research fired only on an abstention, so a context-built wrong answer ("the
country of great barrier reef" -> the previous turn's Cambodia) never triggered it -- it fires whenever a span is unread,
whatever the verdict, and the fetched reading then outranks the context by coverage; the fetcher took the first search hit
(an album for "kilimanjaro") -- it now carries every top hit under the asked name and the question's property decides,
the graph world's own rule; a fetched value could not feed the next hop because the triples adapter names nothing -- a
fetched value is a label by construction; a word inside a found name ("tower" in "tokyo tower") was fetched as a thing of
its own -- a span inside a name that attached is that name's part. Test-design slips recorded: tokyo tower was answerable
through the fixture's Tokyo (swapped for uluru); two rivers have countries but no continent claim (asked for the country).
Registered (research.py): "RESEARCH BY ITSELF: PASS", "CONFAB: 0".
