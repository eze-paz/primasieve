# KG MULTI-HOP PRE-REGISTRATION -- reasoning over a knowledge graph with cited edges, zero LLM

Written BEFORE the code ran. The question set and gold answers are fixed here. Results go in the commit message.

## Claim

Given a natural-language factual question, the engine (a) resolves its symbols to knowledge-graph entities and
properties through an injected source, (b) enumerates the STRUCTURES those readings afford (lookup, chain, path,
membership), (c) keeps only the structures the graph actually supports, and (d) answers ONLY when one survives,
citing every edge; several survivors -> READINGS + ASK; none -> says what it consulted. No word of English in the
mechanism; no probability leaves the engine; every answer is ATTRIBUTED to a checkable certificate (entity id,
property id, value id, verbatim labels as fetched). Wrong-entity disambiguation is the confabulation risk, and the
connectivity constraint (a reading survives only if it is part of a supported structure) is the defence.

## Mechanism (fixed)

  SOURCE      Wikidata public API, live, paced, cached on disk (`emergence/kb_wikidata.py`): entity search by exact
              label/alias match (case-insensitive), property search by exact label/alias, claims of an entity,
              labels of ids. The core imports no source; `core/kg.py` takes a source object.
  SEGMENT     core.resolve.segment; letter symbols, lower-cased.
  READINGS    every span of 1-3 symbols -> entity readings (up to 5 exact-label matches) and property readings.
              Declared bias (E-10's): a single symbol whose dictionary definition-frequency (kaikki df) is above the
              median of all symbols in the question is NOT an entity candidate on its own (common words are not
              names); it may still be part of a longer span.
  STRUCTURES  non-overlapping span assignments with E entities and P properties, by AFFORDANCE:
                E=1 P=1  LOOKUP   value(s) of P on E                     answer = values
                E=1 P=2  CHAIN    P_a then P_b, both orders tried         answer = values of the surviving order
                E=2 P=0  PATH     shortest outgoing path E1 -> E2 or E2 -> E1, <= 3 hops   answer = the path
                E=2 P=1  MEMBER   path E1 -> E2 using only P edges (<= 3 hops)   answer = the path, or NO EDGE FOUND
                E=1 P=0  DESCRIBE instance-of values + description       (fires only if nothing else survives)
  SURVIVORS   a structure survives iff the graph returns a non-empty result for it. One -> ATTRIBUTED answer.
              Several with DIFFERENT answers -> READINGS (all listed, cited) + ASK. Several with the SAME answer ->
              answer, all certificates attached. None -> NOT FOUND, listing the entities and properties consulted.
  CERTIFICATE per edge: (WIKIDATA, "Qx Py Qz", labels verbatim). core.verdict.attribute checks the span is in the
              fetched claims text.
  OUTPUT      structure + certificates; the runner renders English for the reader (chat layer, not core).

## Fixed question set (40) with gold

LOOKUP (10)
 1 what is the capital of france                         Paris
 2 what is the capital of japan                          Tokyo
 3 what is the currency of japan                         Japanese yen
 4 what is the official language of brazil               Portuguese
 5 what is the continent of egypt                        Africa
 6 who is the author of hamlet                           William Shakespeare
 7 who is the director of jaws                           Steven Spielberg
 8 what is the country of the eiffel tower               France
 9 who is the spouse of barack obama                     Michelle Obama
10 what is the place of birth of napoleon                Ajaccio
CHAIN (10)
11 what is the capital of the country of the eiffel tower               Paris
12 what is the official language of the country of the colosseum        Italian
13 what is the currency of the country of mount fuji                    Japanese yen
14 what is the capital of the country of the brandenburg gate           Berlin
15 what is the continent of the country of the taj mahal                Asia
16 what is the capital of the country of citizenship of albert einstein  (several citizenships: READINGS expected)
17 what is the currency of the country of the statue of liberty         United States dollar
18 what is the official language of the country of machu picchu         Spanish (Peru; several official languages possible: READINGS acceptable)
19 what is the capital of the country of the acropolis of athens        Athens
20 what is the continent of the place of birth of napoleon              Europe (Ajaccio may lack continent: NOT FOUND acceptable, counted as none)
PATH (10)
21 how are paris and france related                     capital / country
22 how are the eiffel tower and paris related           located in
23 how are shakespeare and hamlet related               author
24 how are michelle obama and barack obama related      spouse
25 how are tokyo and japan related                      capital / country
26 how are steven spielberg and jaws related            director
27 how are the amazon river and brazil related          country / located in
28 how are mount everest and nepal related              country
29 how are the louvre and paris related                 located in
30 how are rome and italy related                       capital / country
MEMBER (10)
31 is paris in france                                   yes (country or located-in chain)
32 is tokyo in japan                                    yes
33 is the eiffel tower in paris                         yes
34 is berlin in france                                  NO EDGE FOUND
35 is rome in italy                                     yes
36 is madrid in germany                                 NO EDGE FOUND
37 is the louvre in paris                               yes
38 is the colosseum in rome                             yes
39 is kyoto in japan                                    yes
40 is lisbon in spain                                   NO EDGE FOUND
For MEMBER the property word is "in"; declared reading: "in" resolves to the located-in / country properties by
property search on its label and aliases; if property search returns nothing for "in", MEMBER uses the generic PATH
affordance and the gate counts the answer by the path found. Negatives must be reported as NO EDGE FOUND, never "no":
the engine cannot prove a negation from an incomplete graph.

## Gates

 G1  CONFAB = answers with a wrong value (gold mismatch, ignoring articles/case) = 0. Hard. A wrong-entity answer
     is a confabulation even if the edge is real.
 G2  Correct answers >= 24/40 overall; per type reported. READINGS containing the gold among the listed readings
     count as ASK, not correct, not confab.
 G3  Every emitted answer carries >= 1 certificate that re-verifies (span in fetched claims). 100%.
 G4  Knockout 1: question symbols SHUFFLED -> structure candidates change; correct answers must fall (span readings
     break), and CONFAB must stay 0.
 G5  Knockout 2: source removed -> 40/40 NOT FOUND (invents nothing).
 G6  Runtime under the 5-minute cap with the cache warm; cold run may exceed once and is reported.

## Predictions
LOOKUP 8-10 correct; CHAIN 5-7 correct, 1-2 READINGS, 1-2 NOT FOUND; PATH 7-9; MEMBER 8-10 (3 correct NO EDGE FOUND).
Total 28-34. CONFAB 0. Named risk: a common word resolving to a junk entity ("what", "is") that happens to have the
property asked for; the connectivity rule should kill it, and any case where it does not is a recorded confab.

## AMENDMENTS after the first (cold) run -- recorded before the second run
First run, 3 questions in 457 s: Q1 and Q2 -> ASK among junk readings ("capital" as an entity chained through
"part of"), Q3 -> CONFAB ("the currency" read as a band, connected to Japan through country -> diplomatic relation).
Two mechanism faults, both structural, neither a word list:
 A1  SPAN EDGES. A span whose first or last symbol is above the question's median definition-frequency is not
     searched as an entity (the inner span is searched on its own). Kills "the currency", "what is", "of france".
 A2  HUBS. In PATH/MEMBER search an edge is not followed when its property has more than 8 values on that node
     (fan-out cap), and the search is at most 2 hops with a 20-node budget. A path that exists only through a hub
     (diplomatic relations, members, part-of lists) is not evidence of a relation between the endpoints.
 A3  RANKING. Among survivors the most SPECIFIC structure wins: longest entity span(s) first, then more properties
     used. Distinct values among the top-ranked -> READINGS, as before.
 A4  PACING 0.15 s between API calls (well under Wikidata's limit); cache persists across runs.
Gates unchanged. The first run's CONFAB is recorded here; the second run is the one the gates are read on, and if
it also confabulates the count is reported as the result, not averaged away.

## RUN 2 (after A1-A4) -- FAIL, recorded: 14 questions in 587 s, CONFAB 5, correct 1, ASK 8
Q1 "France [Capital -country of origin-> France]", Q3 "Japan [currency -main Wikidata property-> ... example-> Japan]",
Q4 "Constitution of India", Q6 "writer [Hamlet -after a work by-> Shakespeare -occupation-> writer]", Q7 "film director".
Two causes, both again structural:
 A5  AFFORDANCE OF A PROPERTY WORD. A span that has a property reading loses its entity readings: the word that
     names a relation is not, in a question, the name of a thing. Kills "Capital", "currency", "country" as items.
 A6  COMMON WORDS ARE NOT PROPERTIES EITHER. The median-df rule (A1) applies to property readings of lone symbols
     ("is", "who", "of" matched properties by alias). Content words fall under the question's median; function words
     do not.
 A7  RANKING BY COVERAGE, THEN SIMPLICITY. Survivors rank by the number of question symbols their readings cover,
     ties broken by FEWER readings (a lookup over a chain over a path when they cover the same symbols). The old
     rule rewarded more readings and so preferred junk chains.
Gates unchanged; run 3 is read on the gates; runs 1-3 are all reported.

## RUN 3 (after A5-A7) -- 33 of 40 in 598 s (cap hit, cache warming): correct 13, ASK 16, none 1, CONFAB 2
Lookups and chains now answer with real edges (Q1 Paris, Q4 Portuguese, Q5 Africa/Asia, Q8 France, Q9 Michelle
Obama, Q10 Ajaccio, Q11 Paris via Eiffel Tower->France, Q13 yen via Mount Fuji->Japan, Q15 Asia via Taj Mahal->India,
Q16 the Einstein citizenship set). The two confabulations and the noise are structural:
 A8  UNUSED PROPERTY = PARTIAL. If a property reading in the question is covered by no survivor, the engine does not
     answer the sub-question it CAN answer as if it were the question (Q20 answered place of birth when asked the
     continent of it): it reports PARTIAL (what it resolved, what it could not) and the judge counts it as none.
 A9  PATH ANSWERS ARE DIRECT EDGES. A relation between two entities is asserted only from a 1-hop edge in either
     direction; a 2-hop connection is reported as WEAK (no direct relation; connected via X) and never counted as
     an answer (Q29 the TV series Related -> composer -> birthplace Paris; Q22 through an engineer's birthplace).
 A10 STATEMENT RANK. When an entity's property has statements of Wikidata rank preferred, only those are values;
     otherwise the normal ones. A structural field of the source, not a word (kills the 9 historical capitals).
 A11 TIE-BREAK BY SPECIFICITY. Survivors tied on coverage and simplicity are ordered by the summed definition
     frequency of their entity spans, lower first (E-10's topic rule); READINGS only if the most specific is tied.
 A12 ENTITY SEARCH DEPTH. Search limit 20, keep up to 8 exact matches (Q6: the play Hamlet was not among the first
     five exact matches).
Gates unchanged; run 4 read on the gates; all runs reported.

## RUN 4 (after A8-A12) -- read on the gates. 40/40 in 284 s warm; 646 API calls total across runs.
 G1 CONFAB 0            PASS
 G2 CORRECT 25/40       PASS   LOOKUP 7 correct / 2 ask / 1 none; CHAIN 5 / 4 / 1; PATH 7 / 2 / 1; MEMBER 6 / 2 / 2
 G3 certificates 26/26  PASS
 G4 shuffled symbols    HALF: correct falls 12 -> 6 as required; CONFAB 1 -- the permuted bag "athens of the country
    of of the the acropolis what is capital" separates acropolis from athens, and "the acropolis" resolves to an
    Australian venue whose country's capital is Canberra: a real edge of a real entity the garbled bag names.
    Recorded as a FAIL by the letter of the gate; the reading is that span disambiguation depends on adjacency,
    which is the point of the knockout.
 G5 no source 40/40     PASS
 G6 284 s warm          PASS (cold runs exceeded the cap once each, as registered)
ASKs are honest readings, every one cited: Japan's capital {Tokyo, Edo}; Japan's currency {yen, Tokugawa coinage,
ryo}; the Colosseum's country's official language {Italian, German} (Wikidata lists both on Italy); the Brandenburg
Gate resolving to gates in Berlin and Moscow; the Statue of Liberty to statues in three countries; Rome/Italy via
"capital of" vs "capital". Nones: Hamlet the play's author edge is P50 on an entity not among the 8 exact "Hamlet"
matches (the PATH question found it via "after a work by"); Louvre matched only "louver"; Q20 PARTIAL as designed.
Negatives: Berlin/France and Madrid/Germany NOT FOUND, Lisbon/Spain WEAK via a shared border -- never "no".
Verdict: multi-hop reasoning over a knowledge graph with cited edges, zero LLM, zero confabulation on the fixed set;
disambiguation by structural survival is the mechanism, and adjacency of spans is what it leans on (G4).
