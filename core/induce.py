"""INDUCE -- word -> operator from (question, confirmed answer) pairs, by ELIMINATION (tables_numbers_prereg.md
B1/B4/B5/B6; shared by core.table and core.exec since general_prereg.md W3).

A word is bound to an operator only if, in EVERY teaching question containing the word, that operator reproduces
the confirmed answer, and no other operator does (intersection of survivor sets). Words that are not the operator
(fillers, the question's own words) are eliminated the same way: they occur with several operators, so their
intersection is empty or contested. A minimal cover ranked by purity then coverage keeps the lexicon to the words
that explain the teaching. Nothing here knows a word; `survivors(question, gold)` is the world's own probe."""
import collections


def induce(teaching, survivors, order_of=None, negatives=(), df=None, prior=None):
    """teaching: [(question, gold)]; survivors(question, gold) -> (free words, set of operators that reproduce gold,
    extra) where `extra` is a list of order votes (or []). -> (lexicon word -> op, contested words, order or None).
    negatives: [(question, forbidden value)] -- a denial of the engine's own answer (negative_prereg.md, S6): the
    operators that PRODUCE the forbidden value on that question are subtracted from the survivor set of every free word
    of the question. Sound by the same argument as the positive step: had the true binding produced that value, the
    denial was false. A denial never adds; a word no positive example mentions has nothing to subtract from."""
    inter = {}; seen = collections.Counter(); order_votes = collections.Counter(); questions = []
    for q, gold in teaching:
        if gold is None: continue
        free, ops, votes = survivors(q, gold)
        for v in votes: order_votes[v] += 1
        # a question NO known operator explains still eliminates: its words cannot name a known operator
        if ops: questions.append((set(free), set(ops)))
        for w in free:
            seen[w] += 1
            inter[w] = set(ops) & inter[w] if w in inter else set(ops)
    for q, bad in negatives:
        free, ops, _ = survivors(q, bad)
        for w in free:
            if w in inter: inter[w] -= set(ops)
    cands, contested = {}, []
    for w, ops in inter.items():
        if len(ops) == 1: cands[w] = next(iter(ops))
        elif len(ops) > 1 and seen[w] >= 2: contested.append(w)
    lexicon = {}
    uncovered = [(free, ops) for free, ops in questions if any(w in cands and cands[w] in ops for w in free)]
    while uncovered:
        def purity(w): return sum(1 for free, ops in questions if w in free and ops == {cands[w]}) / max(seen[w], 1)
        def covers(w): return sum(1 for free, ops in uncovered if w in free and cands[w] in ops)
        live = [w for w in cands if covers(w) > 0]          # only a word that still explains something is a candidate
        if not live: break
        # STABILITY (together_prereg.md): among pure words, one already bound to this operator keeps its place; a new pair
        # must not flip a working lexicon without a contradiction (a confirmed swapped question made a preposition cover
        # one more difference question than the difference word, and the preposition took the operator)
        held = lambda w: 1 if (prior or {}).get(w) == cands[w] else 0
        # a word that already appears in COVERED questions was a filler there; the operator of a new question is the word
        # that is new to the cover (the preposition of the difference questions must not take a confirmed synonym's place)
        covered = lambda w: sum(1 for free, ops in questions if w in free and (free, ops) not in uncovered)
        key = lambda w: (purity(w), held(w), covers(w), -covered(w), seen[w])
        best = max(live, key=key)
        # words that ALWAYS CO-OCCUR (the same questions, the same operator) cannot be told apart by the pairs: an operator
        # word and the preposition it always comes with. The tie-break is DECLARED (transfer_prereg.md, run 2): the loop's specificity
        # bias -- the rarest word by definition frequency -- when a `df` is given; otherwise the word that comes first in
        # the teaching text, which is what the insertion order of `inter` had been choosing silently all along.
        qset = lambda w: frozenset(i for i, (free, ops) in enumerate(questions) if w in free)
        tied = [w for w in live if key(w) == key(best) and cands[w] == cands[best] and qset(w) == qset(best)]
        if len(tied) > 1:
            first = list(inter)
            best = min(tied, key=lambda w: ((df(w) if df is not None else 0), first.index(w)))
        lexicon[best] = cands[best]
        uncovered = [(free, ops) for free, ops in uncovered if not (best in free and cands[best] in ops)]
    order = "first" if order_votes and set(order_votes) == {"first"} else None
    return lexicon, contested, order
