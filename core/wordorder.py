"""WORDORDER -- order of relation and argument around a link, learned from answered questions (wordorder_prereg.md,
FLUENCY H10). Zero LLM; holds no word of any language.

A reading of a relation kind (property, column, operator) is a RELATION; an entity, filter value or number is an
ARGUMENT. Between a
relation span and an argument span standing one closed-class symbol apart, that symbol is a LINK, and the order is
counted. A link whose observations agree (>= `least`, one order) has a learned order; a reading that reverses it is out of
order."""
import collections

from .reason import _spans

REL, ARG = "relation-first", "argument-first"
RELATION_KINDS = {"P", "C", "O"}         # the worlds' reading codes (core.kg, core.table, core.exec), not words
ARGUMENT_KINDS = {"E", "F", "N"}


def pairs(fr, closed):
    """-> [(link symbol, order)] for the top answer's structure of a frame"""
    syms = fr["syms"]; n = len(syms)
    if not fr.get("answers"): return []
    w, st = fr["answer_worlds"][0], fr["answers"][0][4]
    used = {(i, j) for i, j in _spans(w, st) if j <= n}
    roles = {}
    for r, rw in zip(fr.get("readings", []), fr.get("reading_worlds", [])):
        if (r[0], r[1]) not in used: continue
        # run 2: the engine's own reading codes -- a property, a column, an operator read a FUNCTION of what follows or
        # precedes; an entity, a filter value, a number are its argument (run 1 used content_kinds, which are the kinds an
        # answer OWES, and called a filter value a relation)
        if r[2] in RELATION_KINDS: roles[(r[0], r[1])] = "R"
        elif r[2] in ARGUMENT_KINDS: roles.setdefault((r[0], r[1]), "A")
    return [(link, order) for link, order, rel in attachments(syms, roles, closed)]


def attachments(syms, roles, closed, chains=False, width=1):
    """-> [(link, order, relation span)] for spans that touch (link "") or stand a run of closed symbols apart (at most
    `width`). Without `chains` a relation attaches only to an argument (H10, H10b); with it (H10c) to any span, and a
    relation-relation link is recorded with the order of the first span's role"""
    out = []
    spans = sorted(roles)
    for a in spans:
        for b in spans:
            if b[0] < a[1] or (roles[a] == roles[b] and not (chains and roles[a] == "R")): continue
            gap = syms[a[1]:b[0]]
            if len(gap) > width or any(t not in closed for t in gap): continue
            link = " ".join(gap)
            if roles[a] == roles[b]: out.append((link, "chain", a)); out.append((link, "chain", b)); continue
            rel = a if roles[a] == "R" else b
            out.append((link, REL if roles[a] == "R" else ARG, rel))
    return out


def kinds_of(fr):
    """C7: span -> the reading code that gives it its role (a relation's code wins)"""
    syms = fr["syms"]; n = len(syms)
    if not fr.get("answers"): return {}
    w, st = fr["answer_worlds"][0], fr["answers"][0][4]
    used = {(i, j) for i, j in _spans(w, st) if j <= n}; out = {}
    for r in fr.get("readings", []):
        if (r[0], r[1]) not in used: continue
        if r[2] in RELATION_KINDS: out[(r[0], r[1])] = r[2]
        elif r[2] in ARGUMENT_KINDS: out.setdefault((r[0], r[1]), r[2])
    return out


def typed_attachments(fr, closed, ordered=True, width=3):
    """C7: -> [(link, order, relation span)]; relation-relation attachments carry 'chain:K1>K2' (ordered) or 'chain'"""
    syms = fr["syms"]; kinds = kinds_of(fr); out = []
    spans = sorted(kinds)
    for a in spans:
        for b in spans:
            if b[0] < a[1]: continue
            gap = syms[a[1]:b[0]]
            if len(gap) > width or any(t not in closed for t in gap): continue
            link = " ".join(gap); ra = kinds[a] in RELATION_KINDS; rb = kinds[b] in RELATION_KINDS
            if ra and rb:
                lab = f"chain:{kinds[a]}>{kinds[b]}" if ordered else "chain"
                out.append((link, lab, a))                 # run 2: a chain licenses only its first relation
            elif ra != rb:
                out.append((link, REL if ra else ARG, a if ra else b))
    return out


def roles_of(fr):
    syms = fr["syms"]; n = len(syms)
    if not fr.get("answers"): return {}
    w, st = fr["answer_worlds"][0], fr["answers"][0][4]
    used = {(i, j) for i, j in _spans(w, st) if j <= n}
    roles = {}
    for r in fr.get("readings", []):
        if (r[0], r[1]) not in used: continue
        if r[2] in RELATION_KINDS: roles[(r[0], r[1])] = "R"
        elif r[2] in ARGUMENT_KINDS: roles.setdefault((r[0], r[1]), "A")
    return roles


class WordOrder:
    def __init__(self, closed, least=3):
        self.closed = set(closed); self.least = least; self.seen = collections.defaultdict(collections.Counter); self.order = {}
        self.wide = collections.Counter()

    def observe(self, fr):
        for link, o in pairs(fr, self.closed): self.seen[link][o] += 1

    def settle(self):
        self.order = {l: next(iter(c)) for l, c in self.seen.items() if len(c) == 1 and sum(c.values()) >= self.least}
        return dict(self.order)

    def observe_wide(self, fr):
        """H10c: attachments with closed runs up to 3 wide, chains included"""
        for l, o, rel in attachments(fr["syms"], roles_of(fr), self.closed, chains=True, width=3): self.wide[(l, o)] += 1

    def observe_typed(self, fr, ordered=True):
        if not hasattr(self, "typed"): self.typed = collections.Counter()
        for l, o, rel in typed_attachments(fr, self.closed, ordered): self.typed[(l, o)] += 1

    def licensed_typed(self, fr, least=2, ordered=True):
        """C7: every relation span licensed by an attested attachment (to an argument, or an ordered chain)"""
        seen = {k for k, n in getattr(self, "typed", {}).items() if n >= least}
        att = typed_attachments(fr, self.closed, ordered)
        rels = [sp for sp, k in kinds_of(fr).items() if k in RELATION_KINDS]
        return [sp for sp in rels if not any(rel == sp and (l, o) in seen for l, o, rel in att)]

    def licensed(self, fr, least=2, wide=False):
        """H10b: every relation span attached to an argument by a (link, order) seen >= `least` times -> [] ; else the
        unlicensed relation spans. wide (H10c): runs of up to 3 closed symbols, chains included"""
        if wide: seen = {k for k, n in self.wide.items() if n >= least}
        else: seen = {(l, o) for l, c in self.seen.items() for o, k in c.items() if k >= least}
        roles = roles_of(fr); att = attachments(fr["syms"], roles, self.closed, chains=wide, width=3 if wide else 1)
        rels = [sp for sp, r in roles.items() if r == "R"]
        return [sp for sp in rels if not any(rel == sp and (l, o) in seen for l, o, rel in att)]

    def violations(self, fr):
        return [(l, o) for l, o in pairs(fr, self.closed) if l in self.order and self.order[l] != o]
