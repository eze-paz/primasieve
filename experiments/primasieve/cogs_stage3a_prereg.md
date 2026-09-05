# STAGE 3a PRE-REGISTRATION -- head-passing synchronous grammar on COGS

Written BEFORE the engine ran. Gates fixed here; results go in the commit message whatever they say.

## The structural claim being tested

Stage 2's SCAN engine composes **opaque strings** (PREPEND / APPEND / REPEAT / CONCAT). COGS recursion emits
`prev_head . nmod . prep ( x_prev , x_new )` -- a predicate that references the **head variable of a sibling
constituent**. No string combinator can reference another constituent's head, so the Stage 2 inventory is dead at
depth 1, not merely at depth 12. Stage 3a replaces the output side with constituents that export a HEAD:

    PRIM(lemma)              a word denotes an entity/event/relation, head = its own token index
    EMIT(pred_tpl, args)     a conjunct whose predicate may splice a CHILD'S HEAD LEMMA and whose arguments are
                             CHILD HEAD VARIABLES  -- the combinator SCAN structurally lacked
    UNION(order)             conjunct lists concatenated in a rule-determined order
    HEAD(k)                  head-select: which child's head this constituent exports

Inventory is frozen and carries no COGS-specific token, role name, count or ordering fact: the lexicon, the
relation templates, the frame->role table and the two conjunct-ORDER policies are all INDUCED and then
SOUND-GATED (the grammar must reproduce every training pair exactly).

## Pre-registered gates

G1 (SOUNDNESS, hard). The induced grammar reproduces >= 0.99 of non-primitive train rows exactly (EM). A grammar
   that cannot regenerate its own training data has no standing to be scored on gen. FAIL => Stage 3a is a null.

G2 (IN-DISTRIBUTION, hard). EM >= 0.95 on COGS `test`. FAIL => the parser is broken, not the generalization.

G3 (THE REAL TEST, decisive). EM >= 0.90 on each of the three structural categories that substitution cannot
   solve: `pp_recursion`, `cp_recursion`, `obj_pp_to_subj_pp`. These are the whole point -- depth beyond anything
   in train, and a PP on a subject NP, a configuration that never occurs in train.
   FAIL => head-passing is NOT sufficient and the diagnosis in c5c942d was incomplete. PASS => the output-side
   diagnosis was right and the fix is the head.

G4 (KILL GATE, substitution categories). EM >= 0.90 averaged over the other 18 gen categories. These are
   substitution-solvable, so they are a floor, not a result. Notably `unacc_to_transitive`,
   `active_to_passive`, `passive_to_active`, `do_dative_to_pp_dative`, `pp_dative_to_do_dative` are free ONLY IF
   the frame->role table is keyed on the SYNTACTIC FRAME rather than on the verb; a verb-conditioned table fails
   them. So G4 doubles as a test that role assignment generalized rather than memorized.

G5 (BASELINE CONTRAST, already measured in c5c942d). Nearest-neighbour analogy -- the knockout that killed
   Stage 1 at 0.951 EM on inflection -- scores 0.000 EM / 0.000 EM_alpha on all 21000 gen items and 0.000 on
   every structural category. Any nonzero engine score is therefore not copying.

G6 (BOOKKEEPING vs SEMANTICS). Report EM and EM_alpha side by side. Variable indices ARE 0-based token
   positions, so for a symbolic engine that bookkeeping is free: a large EM_alpha - EM gap would be a serializer
   bug, not a semantic result, and must be fixed rather than reported as a score.

## Declared non-goals

- No morphology. COGS gen reuses train surface forms; a surface->lemma lexicon read off the alignment is enough.
  If gen contains an unseen surface form the engine ABSTAINS, and the abstain count is reported.
- The 143 `primitive` train rows are LEXICON ENTRIES (`LAMBDA a . ball ( a )`), not sentences. They are consumed
  as lexicon and excluded from the G1 reproduction gate; that exclusion is reported explicitly.
- COMMIT/ABSTAIN is kept from Stages 1-2: no probabilistic output. Coverage is reported alongside EM.

## What would make this a KILL rather than a pass

If G3 fails while G4 passes, the honest reading is that COGS gen is 18/21 substitution and the engine solved the
easy 18 -- i.e. the same hollowness Stage 1 was killed for, one level up. That reading is pre-committed here.

## MEASURED LIMITATION (added after the run, before the commit)

All six gates pass, and 0 of 21000 gen items fail for any reason other than two word types (`monastery`,
`gardner`) that occur nowhere in train -- the engine correctly ABSTAINS on those rather than guessing.

What that does NOT establish: the constituent SCHEMAS are authored, not induced. `NP -> [Det] (N|Name) [Rel NP]`
(right-branching, head = the leftmost noun) and `CLAUSE -> [NP] [marker] EVENT slot*` (head = the event token)
are written into the parser. Induced from data are: the word classes, the lemma map, the determiner/definiteness
effect, the sentence terminator, the clause markers, the relation templates, the frame->role table with its
coarsest-consistent-key preference, and both conjunct-order policies. So the strong reading -- "these combinators
are generic" -- is NOT yet earned; the weak reading -- "the missing piece was head-passing, and adding it closes
COGS" -- is.

STAGE 3b is therefore the decisive control, exactly as Stage 2's generator-family test was: a seeded adversary
must build COGS-LIKE grammars with DIFFERENT structure (left-branching modifiers, head-final clauses, modifier
predicates naming the DEPENDENT's lemma instead of the head's, other conjunct orders, other definiteness
marking) and the same engine must run unchanged. Passing COGS but failing those would mean this engine
re-derived COGS's own generator -- the same hollowness Stage 1 was killed for, one level up.
