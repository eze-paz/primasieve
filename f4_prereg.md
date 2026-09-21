# UNIFICATION + F4 PRE-REGISTRATION -- one reasoning loop, replies realized from epistemic frames

Written BEFORE the code ran.

## Part 1 -- UNIFY: one loop under three worlds

Claim. core/kg.py, core/table.py and core/resolve.py implement the same loop with different worlds:
    SEGMENT -> READINGS (spans -> what a source affords) -> STRUCTURES (by affordance of the reading counts)
    -> SURVIVORS (structures the world actually supports) -> RANK (coverage, simplicity, specificity)
    -> VERDICT: unique -> answer with certificates | several values -> READINGS | a content reading unused by every
       top survivor -> PARTIAL | only a weak connection -> WEAK | nothing -> NOT FOUND with what was consulted.
`core/reason.py` holds that loop ONCE. A World supplies: readings(syms), structures(readings), evaluate(structure)
-> (value, support, certificates) or None, plus which reading kinds are "content" (their non-use makes PARTIAL) and
which survivors are "weak". Worlds: KGWorld (Wikidata), TableWorld (a table + induced lexicon), GlossWorld (the
E-10 dictionary resolver: DESCRIBE affordance, gloss verbatim as certificate).
Gates.
  U1  kg_multihop reproduces run 4 on the warm cache: CONFAB 0, correct 25/40, certificates 26/26 (registry needles).
  U2  tables_numbers reproduces run 6: PASS, CONFAB 0, 30/30.
  U3  core_selftest C3 zero islands; core/reason.py imported by kg, table and the F4 runner.
  U4  GlossWorld answers "what is a dog" with a cited gloss (E-10's acceptance case) through reason(), and refuses
      with no source. em_resolve's own registered claim is untouched (core/resolve.py is not modified).

## Part 2 -- F4: replies from epistemic frames (LOOP.md terminal criterion)

Claim. Every reply the engine gives is the realization of ONE of five frames, and the realization round-trips:
  ANSWER    one value, its support (edges / cells), its provenance (source ids)
  READINGS  the surviving readings with their values and supports, and the question that splits them
  PARTIAL   what was resolved and computed, and which reading could not be applied
  FOUND     claims quoted from sources with certificates when no computation applies (gloss / description)
  PROPOSE   nothing found: what was consulted, and the one action that would resolve it (name the entity, supply
            a table, confirm a reading)
Realization lives in the chat layer (`frames.py`), not in core: templates per frame with RNG over
meaning-preserving variants (connective phrasing, ordering of support, synonyms of "per"/"according to"), the Stage 8
rule. `parse(text)` inverts the realization back to (frame kind, slots). No probability is emitted; the RNG only
chooses among verified-equivalent surfaces.
Prompts: the 40 KG questions + the 30 table questions + 5 gloss prompts ("what is a dog", "what does lofty mean",
"dog?", "what is a xyzzyq" (unknown), "define pomegranate") = 75.
Gates.
  F4-a  ROUND TRIP: parse(realize(frame)) == frame for all 75 replies and for 5 RNG variants each (375). 100%.
  F4-b  BARE ABSTAIN = 0: no reply is empty, "I don't know", or a frame without a next step; every PROPOSE names
        what was consulted and one resolving action; every READINGS names the split.
  F4-c  VARIETY: mean distinct surfaces per frame over 5 samples >= 1.5 (Stage 8's bar).
  F4-d  THE INVARIANT CAN FAIL: corrupt 200 realized replies (swap a value or drop a support) -> parse recovers a
        DIFFERENT frame or fails in >= 0.95 (a round trip that cannot fail proves nothing).
  F4-e  distribution of frames over the 75 prompts printed; ANSWER + READINGS + PARTIAL + FOUND >= 60 (the engine
        speaks to the content in at least 80% of prompts; PROPOSE is the research trigger, not the default).
  F4-f  no LLM, no probability, no authored English in core/ (string-literal check on core/reason.py as in E-10 R4).
Predictions. U1-U4 pass (refactor). F4-a 375/375 by construction of the inverse templates; F4-b 0; F4-c 2.0-3.0;
F4-d >= 0.98; F4-e ~65/75 (10 PROPOSE: KG NOT FOUND/WEAK cases and the unknown gloss word).
Declared limit. This is single-turn: the READINGS split question and the PROPOSE action are asked, not yet bound
to a follow-up turn; multi-turn binding is the next pre-registration.
