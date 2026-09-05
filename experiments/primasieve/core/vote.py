"""Corpus voting WITH REJECTION -- one implementation of the decision every induction thread makes.

Every thread that learns a lexicon, a class map, a role table or a segmentation has to answer the same
question: the corpus votes for several readings, do I commit to the winner or decline? Three tests were
implemented separately across threads, and Stage 3d MEASURED which is right where. That measurement is the
reason this module exists rather than each thread picking one by feel.

    plurality(cc)              take the winner, always. Cheapest, and the source of every confabulation
                               observed in Stage 3d: a rare noun in a mispaired row had `tomb` read as the
                               lemma `like` and `cobra` as `boy`, and the engine committed a wrong form.
    decisive_purity(cc, eps)   commit only if the winner holds >= 1-eps of the votes.
    decisive_margin(cc, eps)   commit only if the winner beats the RUNNER-UP by more than eps of the total.

MEASURED, and this is the part that must travel with the code: on the COGS lexicon BOTH decisive tests are
far WORSE than plurality -- exact match falls to 0.04-0.23 at 5% corruption, because rejecting a word's entry
makes every sentence containing it abstain, and that cost exceeds the confabulation it prevents. On the
frame -> role table the opposite holds: `settled` at eps = 0 (unanimity) is correct and is what Stage 3a
shipped. So the choice is per-DECISION, not per-engine, and the discriminator is how expensive an abstention
is: cheap to abstain -> be decisive; catastrophic to abstain -> take the plurality and MEASURE the
confabulation it costs.

The open problem, recorded here because it blocks three threads at once (Stage 3c's tie-broken rows, Stage
3d's two plurality guesses): none of these separates a NOISE-induced minority from a GENUINE ambiguity.
A 39%-support runner-up on the COGS intransitive frame is real linguistic ambiguity; a 5% runner-up under
mispairing is noise. Sentence-level counts alone cannot tell them apart."""


def plurality(cc):
    """The winner, unconditionally. Use when abstaining is more expensive than being wrong -- and then
    MEASURE the confabulation, as cogs_stage3d.py does, instead of assuming it is small."""
    if not cc:
        return None
    return cc.most_common(1)[0][0]


def decisive_purity(cc, eps=0.0):
    """Commit only if the winner holds at least (1 - eps) of the votes. At eps = 0 this is UNANIMITY, which
    is what Stage 3a's frame table used (`len(cc) == 1`) and what Stage 3d generalized."""
    tot = sum(cc.values())
    if not tot:
        return None
    top, n = cc.most_common(1)[0]
    return top if n >= (1 - eps) * tot else None


def decisive_margin(cc, eps=0.0):
    """Commit only if the winner beats the runner-up by more than eps of the total. Scale-free in the number
    of competing readings, where purity is not: purity discards a noun seen 50 times with 3 stray votes."""
    tot = sum(cc.values())
    if not tot:
        return None
    ranked = cc.most_common(2)
    top, n = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    return top if (n - second) > eps * tot else None


def contested(cc, eps=0.0, test=decisive_purity):
    """The eps-consistent SET of readings -- Phase 6's output shape. Empty-or-many means abstain."""
    if test(cc, eps) is not None:
        return {test(cc, eps)}
    tot = sum(cc.values()) or 1
    return {k for k, v in cc.items() if v >= eps * tot} or set(cc)
