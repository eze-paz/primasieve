# Pre-registration -- LOOP ITERATION 15 (B2, honesty of guesses): A LOOKED-UP WORLD SPEAKS ONLY WHILE ITS NAME IS IN THE CONVERSATION (`core/session.py`, `core/research.py`; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Two of B2's remaining misses are wrong labelled guesses that appear only
late in the 498-question session: "the capital of the country of the acropolis of athens is what" -> "Probably Greece",
"what's the currency of the country of the statue of liberty" -> "Probably yen". In a fresh door both are answered
correctly from the fixture (Athens; United States dollar). By question 349 the session holds **45 store worlds**, fetched
for earlier questions; a guessed (transfer) composite route through one of them covers the turn and outcompetes the
fixture. The fetched worlds never leave: this is the "long-session fetched-world accumulation" noted since iteration 7.

## Mechanism
Each world attached by the researcher remembers the name it was fetched for. In a turn, a fetched world takes part only
when that name occurs in the turn itself or in the last 3 turns (the same window the conversation context uses);
otherwise it sits out (kept, and back the moment its name is used again). Worlds the session started with are unchanged.

## Gates
| gate | claim | bar |
|---|---|---|
| **K1** | wrong labelled guesses in B2 (CONJECTURED replies missing the gold) | **< 5** (from 5) and the two above answered |
| **K2** | B1 | 0 (counted; inspected) |
| **K3** | B2 not lower; B9, B10, B6 not lower by more than 2 points | held |

## Prediction
B2 +2 to +4 items; B9 unchanged ("and of bob" follows within the window); B10 unchanged (each question names its thing).

## Amendment before the battery run (2026-10-07)
With scoping alone, B2 misses 54 -> 51 and wrong labelled guesses 5 -> 3: "Probably yen" is gone, but "Probably Greece"
stays. Cause: a typo ("acroplois") sent "athens" to the store; the fetched Athens world's property "capital of" (Athens
IS the capital of Greece) composes into a guessed reading of "the capital of the country of ... athens" that OUTRANKS the
fixture's plain answer (Athens) outright -- the reasoner's ranking (core/reason.py `rank`) never looks at whether a route
is a guess. Added: at equal content coverage, a route that is not a guess outranks one that is (after coverage, before
the quoting criterion). Gate added: **K4** core_selftest.py unchanged.
Second amendment (same day, before the battery run): honest coverage alone made the right reading of "the country of the
city of the department of alice" (records -> Wikidata: France) TIE with a junk Wikidata reading (Manhattan) that leaves
"alice" unread and earns a point for "the" (a symbol AT the median definition frequency counts as content), and lose on
the span-count tiebreak. Added, right after coverage: fewer content readings of ANY non-quoting world left untouched by
the structure's readings. Both probes then read right (Athens; France).

## Run (2026-10-07, battery15 + core_selftest): PASS (K1-K4)
**K1: wrong labelled guesses in B2 5 -> 1** ("Probably yen" and "Probably Greece" both answered right; the one left is the
guesser's labelled guess for a typo'd chain, "ciitzenship"). **B2 449/498 = 90.2 %** (from 89.2 %). K2 B1 counted 1 (the
"jurisdiction" item: the store's own claim against an unlabelled Q-id gold). K3: B9 18/20, B10 398/500, B6 43, B5 +11.6,
B4 3/4,605; B3 dictionary 97.65/0.59, conversational true 86.4 -> **87.5 %** / 0 %; B7 15/18 at 0 %. Disclosed: B10's
"quoted answers missing the gold" rose 7 -> 11 (B10's count unchanged; not traced in this run). K4 core_selftest PASS --
a first run under load reported crosscheck as MOVED (0.0000): its subprocess hit the self-test's 3,600 s limit while the
battery and the novel loop shared the machine; crosscheck alone passed (1,500 s), and the self-test re-run on a quiet
machine passed whole.
