# Pre-registration -- TWO FETCHED SOURCES: corroborated, contested, never voted (`emergence/kb_osm.py`, `crosscheck.py`; 2026-10-03)

Registered 2026-10-03 before the gate ran (the OpenStreetMap module was written and probed once first). Zero LLM.

## 1. Why a second source, and what it may and may not do

Research by itself (research_prereg.md) fetches from one structured source. With one source the engine can never notice
that a fetched claim is wrong. A second, independent source lets it: when both say the same, the answer carries both
citations (CORROBORATION, printed, never counted -- W6's rule); when they differ, the contest between quoted values goes
the W6 way: each option with its sources and their ledger record, CONJECTURED when exactly one source's record is
strictly better, READINGS otherwise; the user's "correct"/"wrong" writes the record; the next contest is settled by it.
What a second QUOTING source cannot do is confirm a guess by itself (selfconfirm_prereg.md needs a computing route):
two quotes agreeing is a vote, and the engine does not vote. That stays as it is and is measured as 0.

## 2. The second source

OpenStreetMap's Nominatim, through a module of the same shape as the Wikidata one: a place name -> the top matches with
their address fields (country, state, county, city, type) as claims; paced at one request per second; its own cache
file; a recorded pass replayed offline by the gate. The engine knows it only as a fetcher.

## 3. Gates (replaying recorded caches; NOT RUN without them)

- **X1 both attach.** research_prereg.md's ten questions, two fetchers: both sources attach for at least 7 of the 10
  names; the answers' `sources` name both where both carry the country.
- **X2 corroboration is printed, not counted.** For a question both answer alike, ONE value with two sources, kind
  ATTRIBUTED; the ledger unchanged (no confirmation written by agreement); self-confirmations 0.
- **X3 a contest, settled the W6 way.** One recorded OpenStreetMap entry planted with a different country for one place
  (labelled): the question -> READINGS over the two values naming each source (no record yet); the user says "correct"
  to the Wikidata value -> the ledger records; a second planted disagreement on another place -> CONJECTURED, the
  source with the better record first, "Correct me if wrong"; never a lone wrong value.
- **X4 the knockout.** The OpenStreetMap entries shuffled across names -> every question is a contest or an abstention,
  never a lone wrong COMMIT/ATTRIBUTED.
- **X5 the live chat.** `chat.py --serve --online` builds its door with the store, transfer and both fetchers (code read
  by the gate), and the proposal word answers with a question or with "nothing open".
- **X6 registered numbers** unchanged (chat, research, together).

PASS = X1-X6.

## 4. Runs (2026-10-03): PASS

X1 both sources attach for 10/10 names. X2 six answers carry one value with both citations; the ledger is untouched by
agreement; self-confirmations 0 (two quotes are a vote, and the engine does not vote). X3 the planted France for
stonehenge -> READINGS over {United Kingdom, France} naming each source; the user's choice and "correct" write the record
(Wikidata 1 confirmed, OpenStreetMap 1 contradicted -- the unchosen option is now recorded against its source, which it
was not before); the planted Thailand for angkor wat -> "Probably Cambodia (per wikidata-research; record 1 confirmed, 0
contradicted) rather than Thailand (per osm-research ...)". X4 with the geocoder's entries shuffled across names: three
contests, no lone wrong value where both sources speak; one wrong value from a SOLE source (the mountain, whose Wikidata
entity carries no country) is recorded as the limit a second source cannot reach. X5 the live door wires the store,
transfer and both fetchers; the proposal word answers with the engine's question. X6 unchanged; core_selftest green.

Found on the way, each fixed with its rule: the researcher's attempt budget (40) ran out after seven names and the
context rule then answered two rivers with the previous turn's entity -- the budget is 400 and spans whose every symbol
sits above the question's median definition frequency are not fetched; the context rule itself let a turn borrow when its
unread symbol was absent from the dictionary (absent counted as the rarest, so nothing could be rarer): a symbol no
dictionary knows is a name candidate and the turn has a topic of its own (turns and chat gates unchanged by it); the
geocoder's second and third hits were namesakes (its top match is taken); fetched worlds were named per entity, so a
source's record never carried to its next entity (named by source now). Registered (crosscheck.py): "CROSSCHECK: PASS".
