# Pre-registration -- SELF-GENERATED GOALS: the engine asks what would settle most of its own residue (`core/goals.py`, `goals.py`; EMERGENCE_PLAN.md S9)

Registered 2026-10-02 before any code. Zero LLM. Offline.

## 1. The shortcoming

Every task the engine works on is given: a question typed in, a gate's list, a prereg's targets. It never proposes
anything. Yet a session leaves a RESIDUE the engine can see: symbols no world read (UNKNOWN readings), words whose
operator is contested (several survivors, none bound), words bound by search with rivals of the same size,
borrowed words held CONJECTURED, denials that eliminated without settling, READINGS the user never chose, and
single-source claims. Each of those is a question the engine could ask -- and `core/collect.py` already holds the
mechanism for choosing which: the probe that splits the surviving hypotheses most.

## 2. The claim

A goal is a question whose answer would shrink a survivor set the engine currently holds. `core/goals.py` gathers the
session's residue into candidate goals, each with its survivor set and the probe (a question to the user, or to a
world) that splits it; the next goal is `core.collect.best_split` over them -- the one whose answer rules out most --
and a residue nothing can split is reported as irreducible, not asked about. ACTIVE (split-ordered) asks settle the
residue in fewer turns than RANDOM order; a session with no residue proposes nothing. The engine never acts on a goal
by itself: it OFFERS the question, and the user's answer enters through the existing channels (teach / deny / choice).

## 3. What is built

- `core/goals.py`: `residue(session)` -> [Goal(kind, key, survivors, probe)] from: contested words per world
  (`survivors_of` where a world has it), borrowed words (`borrowed`), the session's unresolved READINGS frames (options
  as survivors), UNKNOWN symbols (the dictionary's U readings: survivors = the worlds that could learn them, probe = ask
  for a definition or an example), and the ledger's contested sources. `next_goal(goals)` -> the goal with the largest
  split (`core.collect.best_split` with outcome = the survivor the answer would leave), ties by recency; None when
  nothing splits (irreducible) or there is no residue. `realize(goal)` -> a question in the user's own words (the
  frames layer's PROPOSE/READINGS shapes; no new English).
- `core/session.py`: `Session.goals()` wraps `residue`; `Session.propose()` returns the next goal's question, or None.
- `chat.py`: a turn consisting of the word the chat layer maps to a proposal request (data, like the META fields)
  answers with `propose()`; off the gate's path unless invoked.

## 4. Gates

- **Q1 the residue is found.** A scripted session (worlds_general's worlds): one contested word (`peak` after a one-row
  teaching, negative_prereg.md N3), one borrowed word (transfer on), one unanswered READINGS (the twiddle question), two
  unknown symbols ("what is a flurb", "the gronk of 3"), one unresolved denial. `residue` returns exactly these six
  kinds with the right survivor sets (printed), and nothing else; a fresh session returns [].
- **Q2 the probe is the split** (amended before any code: as first written, every goal took exactly one ask, so the
  order of goals could not matter and the bar was vacuous). Two claims instead. (a) WITHIN a goal, the question the
  engine chooses is the one whose answer splits the survivors most: for `peak` (5 survivors) the candidates are the
  taught question with every other filter value of the same header; the one-row filter splits nothing and is never
  asked; the chosen question's answer leaves ONE survivor, so one ask settles the word (a random candidate: median >= 2
  asks over 20 seeds, because one-row and two-row filters leave several). For a searched word with rivals, the
  candidates are the word over 1..10 and the chosen input separates every rival. (b) ACROSS goals, with a budget of two
  asks, ACTIVE (largest split first) removes more survivors than the RANDOM order's median over 20 seeds.
- **Q3 irreducibility is honest.** A residue whose survivors no probe can split (the `huge`/`square` shape from the
  architecture: two hypotheses that agree on every observable) is reported as irreducible and never asked about twice.
- **Q4 nothing is invented.** The six goals' questions, realized, round-trip through the frames layer; no goal names a
  value the session has not seen; CONFAB 0 on everything the oracle confirms; a session with no residue proposes None.
- **Q5 knockout.** `next_goal` with the split replaced by a constant -> order = recency = the RANDOM arm's median or
  worse.
- **Q6 the registered numbers** unchanged (the proposal path is opt-in).

PASS = Q1-Q6.

## 5. Predictions

PASS on Q1, Q3-Q6; Q2 at risk because the pool is small (six goals): the bar is +1 ask over RANDOM's median, and if the
ACTIVE/RANDOM gap is 0 the claim is NULL and recorded.

## 6. Not claimed

Goals that require the engine to act in a world (every goal here is a question); goals ranked by anything but the
split (no curiosity score, no novelty bonus: E-5's lesson); persistence of goals across sessions (the residue is
recomputed from the stored evidence on load, S8).

## 7. Runs (2026-10-02): SOUND

Q1 the residue of the scripted session: one contested goal (`peak`, with `of` folded into it: the same question settles
both), four borrowed words, one unanswered READINGS, one unknown symbol; a fresh session has none. Q2a the chosen probe
("the peak salary of engineering") splits all five survivors and one ask binds `peak` to MAX; the random bar did not
discriminate on this data (every other department has several rows, so every candidate splits all five) -- recorded, not
counted. Q2b with a budget of two asks ACTIVE removes 6 survivors against a RANDOM median of 2.5. Q3 a table whose groups
are all one row: no candidate splits, the goal is irreducible, `propose` returns None (run 1 had a toy table whose row
count equalled a taught price, so COUNT over the table survived by accident; the data was fixed). Q4 every probe is a
seen question with one symbol changed or a seen symbol; after the oracle's answer "the peak salary of research" -> COMMIT
300. Q5 the recency knockout removed 3 against the random median 2.5: on a pool of seven the knockout does not
discriminate -- FAIL as registered. Q6 unchanged (358 s). Registered (goals.py): "S9 GOALS: SOUND".
