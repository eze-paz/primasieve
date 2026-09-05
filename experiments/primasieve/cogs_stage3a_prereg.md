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

# STAGE 3b PRE-REGISTRATION -- the generator-family control

Written BEFORE the adversary ran. Mirrors Stage 2's part B, which is the test that made Stage 2 a result
rather than a replication.

## Design

A seeded adversary builds 10 COGS-LIKE grammars that randomize the STRUCTURE Stage 3a wrote by hand, with a
synthetic vocabulary so nothing leaks from COGS. Randomized dimensions, each recorded per grammar so that any
failure is attributable to a named assumption:

    np_branch   modifier attaches to the RIGHT of its head noun (COGS) | head-final, to the LEFT
    np_head     a modified NP exports the HEAD noun's variable (COGS) | the DEPENDENT's
    mod_pred    modifier predicate splices the HEAD's lemma (COGS) | the DEPENDENT's | no lemma at all
    mod_args    modifier conjunct arguments (head, dep) (COGS) | (dep, head)
    mid         the constant middle segments: ('nmod',) (COGS) | two segments | none
    det_pos     determiner BEFORE the noun (COGS) | after it
    verb_pos    verb before its post-arguments (COGS) | clause-final
    cl_head     a clause exports the EVENT variable (COGS) | its SUBJECT's variable
    def_style   definiteness as the `*` prefix list (COGS) | an inline marker predicate
    roles / role order per frame, marker words, and the whole lexicon are randomized as well

Train/test is a DEPTH split, as in Stage 2's length split: train has modifier and embedding depth <= 1 and
never a modifier on the subject; test is (a) modifier depth 2-6, (b) embedding depth 2-6, (c) a modifier on the
SUBJECT -- a configuration absent from train. That is the analogue of pp_recursion / cp_recursion /
obj_pp_to_subj_pp. Test items are filtered to vocabulary seen in train, so no result is an OOV artefact.

## Gates

G7 (WIN gate, as Stage 2's): the UNCHANGED Stage 3a engine reaches EM >= 0.95 on the held-out depth split for
   >= 9 of 10 grammars.

G8 (SOUNDNESS, per grammar): the induced grammar reproduces >= 0.99 of that grammar's train rows.

G9 (NO COGS REGRESSION): whatever is changed to satisfy G7 must leave the Stage 3a COGS numbers intact --
   train reproduction 1.0000, gen EM 0.9990, and the three structural categories at 0.985 / 1.000 / 1.000.

## Pre-committed reading of the outcome

I expect the unchanged engine to FAIL G7, because Stage 3a's own limitation note says the constituent schemas
are authored: `parse_np` requires a pre-nominal determiner and a right-attaching modifier, `parse_clause`
requires the verb before its post-arguments, `ev_np` splices the HEAD's lemma and exports the HEAD's variable,
and `ev_cl` exports the EVENT. Each of those is a dimension above. That failure is the RESULT, not a bug: it
measures how much of Stage 3a's COGS score came from authored structure.

The fix, if it is attempted, must be the mechanism Stage 3a ALREADY uses for the two conjunct-order policies --
search a small generic space and keep what measurably reproduces train -- extended to the schema dimensions,
NOT a per-dimension special case. Reaching G7 by adding COGS-specific or adversary-specific branches would be
cheating and is pre-committed as a FAIL here. Both numbers get reported: before generalization and after.

## STAGE 3b MEASURED RESULT (added after the runs)

The pre-committed expectation was right: the UNCHANGED Stage 3a engine FAILED the control. Then the fix was
made the pre-registered way -- extend the existing search-a-small-space-and-keep-what-reproduces mechanism to
the structural dimensions -- and the control passes. Both numbers, as promised:

                                        BEFORE (authored schemas)   AFTER (schemas searched)
  part 0  sanity, COGS structure                  1.000                     1.000
  part A  single-dimension knockouts survived      1/11                     11/11
  part B  G7 win gate, 10 random grammars          0/10                     10/10
          G8 per-grammar soundness >= 0.99         0/10                     10/10
  G9      COGS unchanged                             --      train 1.0000, test 0.9997, gen 0.9990,
                                                            pp/cp/obj_pp 0.985/1.000/1.000, 18-cat 0.9996

Before generalization the knockout ladder named ten authored assumptions the COGS score had been resting on:
cl_head=subject, def_style=inline, det_pos=post, mid=(), mod_args=dep_head, mod_pred=dep_lemma,
mod_pred=bare, np_branch=left, np_head=dep, verb_pos=final. Only mid=('rel','of') survived, confirming that
the relation-template segments really were induced in Stage 3a while the rest were written in.

Two facts moved from AUTHORED to DIRECTLY OBSERVED rather than into the search, because the data determines
them outright: the determiner set with its SIDE relative to the noun, and each determiner's DEFINITENESS
REALIZATION (`*` prefix list / an inline marker predicate / none). The distinguishing signal is that a
determiner controls its noun's conjunct realization CONSISTENTLY while an argument marker leaves it untouched.

Three bugs the control found, none of which COGS alone could have exposed:
  1. classifying a two-segment binary predicate as a verb frame BEFORE testing for a modifier misread a
     lemma-less modifier predicate (`nmod . p1 ( x_10 , x_7 )`) as a verb. A modifier's predicate ends in a
     token lying BETWEEN its two arguments; a role predicate never does. Test relator first.
  2. COORDINATE DESCENT over the schema space is NOT sufficient: on random grammar 2 it stranded at 248/350
     because np_branch, np_head, mod_args and np_order must move together (a mirror-image local optimum).
     The space is only 576 wide and just np_branch/verb_pos affect the PARSE, so derivations are computed
     once per parse-config and reused across the 144 read-outs -- exhaustive search, no local optima.
  3. materializing slot alternatives into a list enumerated every parse of every embedded clause before
     returning any, which is exponential in embedding depth; it cost 564/1000 cp_recursion items to a parse
     budget wall. Lazy generators restored cp_recursion to 1.000.

## WHAT IS STILL NOT EARNED (part C, measured)

COGS numbers variables by TOKEN POSITION, which hands the induction its token<->predicate alignment for free.
Renumbering the gold variables by ORDER OF FIRST APPEARANCE, changing nothing else, takes the same grammar
from EM 1.000 to EM 0.000 (and EM_alpha 0.000 -- the induction breaks, not just the serializer). So
positional variables are a load-bearing INPUT to this engine. Recovering the alignment under an order-based
convention is the honest open item after Stage 3b.

# STAGE 3c PRE-REGISTRATION -- earning the alignment instead of being handed it

Written BEFORE the aligner ran. Stage 3b part C measured the one dependency left: COGS numbers logical-form
variables by TOKEN POSITION, which hands the induction its token <-> predicate alignment for free. Renumber
the gold variables by order of first appearance and the SAME grammar goes EM 1.000 -> 0.000, EM_alpha 0.000
too, so the induction breaks and not merely the serializer.

## The claim to test

The alignment is RECOVERABLE from co-occurrence alone, with no positional crutch and no new hand-written
structure. A predicate atom that names a word occurs in a sentence exactly when that word does; an atom that
names a role or a template constant does not. That is a rejection-first test (exact set equality, not a
similarity score), so it fits the engine's existing discipline:

    anchor(atom) = { word : every occurrence of that word co-occurs with the atom }
                   kept only if those words' sentences COVER every occurrence of the atom
    a variable is then constrained to the positions of the words anchoring its own predicate, and the
    per-sentence assignment must be INJECTIVE and consistent across all of that variable's conjuncts

If that recovers positions, the entire Stage 3a/3b engine runs downstream UNCHANGED, and the variable
convention becomes one more searched dimension (`position` | `first_appearance`) rather than an assumption.

## Gates

G10 (the frontier gate). On the COGS-structure adversary grammar with variables renumbered by first
    appearance -- the exact configuration that scored EM 0.000 in Stage 3b part C -- EM >= 0.95.

G11 (it must generalize, not patch one case). Under first-appearance numbering, the whole Stage 3b suite:
    single-dimension knockouts >= 10/11 and the 10-random-grammar win gate >= 9/10.

G12 (NO REGRESSION, both earlier stages). COGS itself, positional, unchanged: train reproduction 1.0000,
    test 0.9997, gen 0.9990, structural 0.985 / 1.000 / 1.000, 18-category mean 0.9996. And Stage 3b
    positional still 10/10 with 11/11 knockouts.

G13 (report the alignment itself, not just the downstream score). Measure and print, separately:
    (a) the fraction of training rows whose variables were aligned to a unique consistent position,
    (b) the fraction aligned CORRECTLY against the oracle -- available because the adversary generated the
        true positions, and the identity for COGS,
    (c) how many predicate atoms were classified lexical vs constant, and any ties.
    An engine that scores well downstream while aligning badly would be exploiting something else, and G13
    is what would expose that.

## Pre-committed reading

If G10 passes but G11 fails, the aligner is a COGS-shaped patch and the honest verdict is a null: report it
as such. If the co-occurrence test cannot separate lexical atoms from role names at all, that is a clean
negative about this signal being insufficient, and it gets reported rather than rescued with positions.
The aligner may NOT consult token positions to decide what a variable means -- it may only use positions as
the candidate SET a variable is assigned from. Using order-of-appearance as a tie-break is allowed and must
be reported as a tie-break, with the count of rows it decided.

## STAGE 3c MEASURED RESULT (added after the runs)

The frontier is closed. The alignment IS recoverable from co-occurrence, with no positional crutch.

  G10  the exact configuration that scored EM 0.000 in Stage 3b part C          EM 1.000   PASS
  G10  strongest form -- REAL COGS, all gold variables renumbered by first
       appearance: train reproduction 1.0000, gen EM 0.9990 / EM_alpha 0.9990,
       structural 0.9850 / 1.0000 / 1.0000, 18-category mean 0.9996
       -- IDENTICAL to positional COGS                                                     PASS
  G11  single-dimension knockouts, all renumbered                                   11/11  PASS
  G11  win gate, 10 random grammars, all renumbered                                 10/10  PASS
  G12  no regression: COGS positional unchanged (train 1.0000, test 0.9997, gen 0.9990,
       structural 0.9850/1.0000/1.0000, 18-cat 0.9996); Stage 3b positional 10/10 + 11/11  PASS
  G13  alignment report over 22 grammars: rows aligned unambiguously mean 0.8544 (min 0.8423);
       ORACLE accuracy of those mean 1.0000, min 1.0000; alignment failures 0;
       12628 tie-broken rows DROPPED rather than guessed; 866 lexical atoms / 66 constants  PASS

On real COGS the aligner reaches 0.9971 unambiguous with 0 failures and discovers the multi-surface lemmas by
itself (`eat` <- ate / eat / eaten, `freeze` <- froze / frozen, `give` <- gave / given), which is the part no
adversary grammar tested -- the synthetic lexicons are one-to-one.

TWO GENERIC REJECTION RULES carry the association, and both were forced by measurement, not chosen a priori:
  PARSIMONY. Necessity alone is far too weak: on an 8000-row COGS slice the atom `nmod` is "necessary" for
    ~170 location nouns, because each of them happens to occur only inside a modifier, and their union does
    cover every `nmod` occurrence. Requiring the MINIMAL necessary set that exactly accounts for the atom
    (at most 3 surface forms) collapses `dog` from {bicycle, dog, notebook, plaque} to {dog}.
  NON-DECOMPOSABILITY. `nmod`'s minimal cover can still come out as {in, on, beside} -- exactly the union of
    three OTHER atoms' covers. A lemma's cover is not built out of other atoms' covers, so an atom whose
    cover decomposes that way is demoted to a constant. After both rules: roll -> {rolled}, agent -> {},
    nmod -> {}, dog -> {dog}.

DISCIPLINE POINTS worth keeping. (a) Induction uses ONLY the unambiguously aligned rows; a row whose
alignment was settled by a tie-break is dropped, because learning from it would be learning from a guess --
and 85% of rows suffice on the adversary, 99.7% on COGS. (b) The variable convention is chosen the same way
every other fact is: try reading variables as positions, keep it if it reproduces train, otherwise recover
the alignment -- so COGS still takes the direct path and there is no branch on dataset identity. (c) The
oracle accuracy is reported SEPARATELY from the downstream score, because an engine scoring well downstream
while aligning badly would be exploiting something else, and only G13 would have caught that.

## WHAT IS STILL NOT EARNED, after 3c

- Tie-broken rows are dropped, not resolved. A word repeated inside one sentence leaves its variable
  ambiguous; ~14% of adversary rows and 0.3% of COGS rows are discarded. Enough survive that nothing is lost
  here, but the engine cannot yet learn from a sentence it cannot align uniquely.
- The alignment signal is sentence-level CO-OCCURRENCE, which needs a corpus where a lemma and its surface
  forms co-vary cleanly. It says nothing about a lemma whose token never appears without another (perfectly
  confounded vocabulary), and that case is untested.
- Everything here still assumes the logical form is a flat set of conjuncts over definites, and that a
  training pair is exactly (one sentence, one logical form). Neither Stage 3b nor 3c varied that.
