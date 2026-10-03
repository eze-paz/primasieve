"""TRANSFER -- a word bound in one world offered to another by BEHAVIOUR, held as a conjecture (transfer_prereg.md;
EMERGENCE_PLAN.md S4). Zero LLM; holds no word, no operator, no world.

Two operators in two worlds are the same operator when they behave the same on the same probes. A world that takes
part exposes `lexicon` (word -> op), `operators()`, `fingerprint(op)` (a hashable behaviour on core.primitives'
canonical probes, or None when the operator has no scalar behaviour), and `borrow(word, op, source) -> bool`. A word
bound in A and unbound in B is offered to B iff EXACTLY ONE of B's operators has A's operator's fingerprint: the survivor
set of B's operators under that behaviour must be a singleton, because no simplicity key is supplied here (the
CONJECTURED admission rule of core.verdict). What B does with a borrowed word is B's: it reads it, answers through it,
marks the answer CONJECTURED, and drops it on a denial or supersedes it on a confirmation (its own elimination)."""


def bridge(worlds):
    """-> [(word, from world name, to world name, operator)] of the borrowings made in this call."""
    ws = [w for w in worlds if all(hasattr(w, a) for a in ("lexicon", "operators", "fingerprint", "borrow"))]
    prints = {id(B): {op: B.fingerprint(op) for op in B.operators()} for B in ws}
    out = []
    # a borrowing lives only while its source does: revoke one whose word is no longer bound in the source world to an
    # operator of that behaviour (run 1: a binding one pair alone had forced in the records leaked into exec and stayed)
    by_name = {getattr(w, "name", "?"): w for w in ws}
    for B in ws:
        for word, entry in list(getattr(B, "borrowed", {}).items()):
            op, src = entry[0], entry[1]
            A = by_name.get(src)
            if A is None or word not in A.lexicon or A.fingerprint(A.lexicon[word]) != prints[id(B)].get(op):
                del B.borrowed[word]
    for A in ws:
        for word, op in list(A.lexicon.items()):
            f = A.fingerprint(op)
            if f is None: continue
            for B in ws:
                if B is A or word in B.lexicon or word in getattr(B, "borrowed", {}): continue
                matches = [ob for ob, fb in prints[id(B)].items() if fb is not None and fb == f]
                # the word's ARGUMENT ORDER travels with it (order_prereg.md): a world states it as "forward"/"reverse"/
                # "both" per word (exec) or as its DIFF order "first" (records); the receiving world reads what it can
                order = getattr(A, "arg_order", {}).get(word) or ("forward" if getattr(A, "order", None) == "first" else None)
                if len(matches) == 1 and B.borrow(word, matches[0], getattr(A, "name", "?"), order=order):
                    out.append((word, getattr(A, "name", "?"), getattr(B, "name", "?"), matches[0]))
    return out
