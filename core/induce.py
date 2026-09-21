"""INDUCE -- word -> operator from (question, confirmed answer) pairs, by ELIMINATION (tables_numbers_prereg.md
B1/B4/B5/B6; shared by core.table and core.exec since general_prereg.md W3).

A word is bound to an operator only if, in EVERY teaching question containing the word, that operator reproduces
the confirmed answer, and no other operator does (intersection of survivor sets). Words that are not the operator
(fillers, the question's own words) are eliminated the same way: they occur with several operators, so their
intersection is empty or contested. A minimal cover ranked by purity then coverage keeps the lexicon to the words
that explain the teaching. Nothing here knows a word; `survivors(question, gold)` is the world's own probe."""
import collections


def induce(teaching, survivors, order_of=None):
    """teaching: [(question, gold)]; survivors(question, gold) -> (free words, set of operators that reproduce gold,
    extra) where `extra` is a list of order votes (or []). -> (lexicon word -> op, contested words, order or None)."""
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
        best = max(live, key=lambda w: (purity(w), covers(w), seen[w]))
        lexicon[best] = cands[best]
        uncovered = [(free, ops) for free, ops in uncovered if not (best in free and cands[best] in ops)]
    order = "first" if order_votes and set(order_votes) == {"first"} else None
    return lexicon, contested, order
