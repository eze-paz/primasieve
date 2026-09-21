"""KG -- multi-hop reasoning over an injected knowledge graph with cited edges (kg_multihop_prereg.md).

Holds no word of any language, no entity, no property. Knows five things:
  SEGMENT     symbols (core.resolve.segment), lower-cased letters.
  READINGS    every 1-3 symbol span -> entity readings and property readings from the source; a lone symbol whose
              definition-frequency is above the question's median is not an entity on its own (E-10's bias).
  STRUCTURES  by AFFORDANCE of the reading counts: LOOKUP (1 entity, 1 property), CHAIN (1, 2), PATH (2, 0),
              MEMBER (2, 1), DESCRIBE (1, 0; only if nothing else survives).
  SURVIVORS   a structure survives iff the graph supports it (non-empty result). One -> ATTRIBUTED answer; several
              with different answers -> READINGS + ASK; none -> NOT FOUND with what was consulted.
  CERTIFICATE every edge (subject, property, object) is checked verbatim against the fetched claims text through
              core.verdict.attribute; an edge that fails is refused.
No probability leaves the module."""
import collections
import itertools
import unicodedata

from .resolve import segment
from .verdict import attribute, ATTRIBUTED, ABSTAIN

LOOKUP, CHAIN, PATH, MEMBER, DESCRIBE = "LOOKUP", "CHAIN", "PATH", "MEMBER", "DESCRIBE"


def symbols(text):
    return [s.lower() for s in segment(text) if unicodedata.category(s[0])[0] == "L"]


def spans(syms, maxlen=3):
    for i in range(len(syms)):
        for L in range(1, maxlen + 1):
            if i + L <= len(syms): yield i, i + L, " ".join(syms[i:i + L])


def readings(syms, source, df=None, max_ent=5):
    """-> list of (start, end, kind, id, label). df(symbol) -> definition frequency (or None: bias off)."""
    med = None
    if df is not None:
        vals = sorted(df(s) for s in syms)
        med = vals[len(vals) // 2] if vals else None
    out = []
    for i, j, text in spans(syms):
        hi = lambda k: med is not None and df(syms[k]) > med
        edged = med is not None and (hi(i) or hi(j - 1))
        props = [] if (edged and j - i == 1) else list(source.properties(text))    # A6: a lone common word is no property
        for pid, lab, *_ in props: out.append((i, j, "P", pid, lab))
        if edged or props:
            continue                                              # A1 / A5: edged by a common word, or names a relation
        for qid, lab, desc in source.entities(text)[:max_ent]: out.append((i, j, "E", qid, lab))
    return out


def edge_certificate(source, s, p, o):
    """(WIKIDATA-style) certificate: the object id must appear verbatim in the subject's fetched claims text under
    the property; checked through core.verdict.attribute with reads = identity on the span."""
    text = source.claims_text(s)
    span = f'"{o}"'
    claim, state, prov = attribute(span, "KG", text, span if (span in text and p in text) else "", lambda x: x)
    return state == ATTRIBUTED, {(f"{s} {p} {o}", source.label(s), source.label(p), source.label(o))}


def lookup(source, e, p):
    vals = source.claims(e).get(p, [])
    return [(v, [(e, p, v)]) for v in vals]


def chain(source, e, p1, p2):
    out = []
    for v1, ed1 in lookup(source, e, p1):
        for v2, ed2 in lookup(source, v1, p2):
            out.append((v2, ed1 + ed2))
    return out


def path(source, a, b, max_hops=2, only=None, budget=20, fanout=8):
    """shortest outgoing path a -> b (edges restricted to `only` properties if given). BFS with a node budget.
    A2: an edge whose property has more than `fanout` values on the node is a HUB and is not followed."""
    frontier = [(a, [])]; seen = {a}; expanded = 0
    for hop in range(max_hops):
        nxt = []
        for node, edges in frontier:
            if expanded >= budget: return None
            expanded += 1
            cl = source.claims(node)
            for p, vals in cl.items():
                if only is not None and p not in only: continue
                if len(vals) > fanout: continue
                for v in vals:
                    if v == b: return edges + [(node, p, v)]
                    if v not in seen and hop + 1 < max_hops:
                        seen.add(v); nxt.append((v, edges + [(node, p, v)]))
        frontier = nxt[:budget]
    return None


def structures(rd):
    """non-overlapping assignments of readings -> list of (kind, entities, properties) with their spans."""
    ents = [r for r in rd if r[2] == "E"]; props = [r for r in rd if r[2] == "P"]
    out = []

    def disjoint(rs):
        iv = sorted((r[0], r[1]) for r in rs)
        return all(iv[k][1] <= iv[k + 1][0] for k in range(len(iv) - 1))

    for e in ents:
        out.append((DESCRIBE, [e], []))
        for p in props:
            if disjoint([e, p]): out.append((LOOKUP, [e], [p]))
        for p1, p2 in itertools.permutations(props, 2):
            if disjoint([e, p1, p2]): out.append((CHAIN, [e], [p1, p2]))
    for e1, e2 in itertools.combinations(ents, 2):
        if not disjoint([e1, e2]): continue
        out.append((PATH, [e1, e2], []))
        for p in props:
            if disjoint([e1, e2, p]): out.append((MEMBER, [e1, e2], [p]))
    return out


def answer(text, source, df=None, log=None):
    """-> dict(state, kind, answers: [(value_id, label, edges, certs)], readings, consulted, ask)"""
    syms = symbols(text)
    rd = readings(syms, source, df)
    cands = structures(rd)
    survivors = []; weaks = []
    for kind, es, ps in cands:
        if kind == DESCRIBE: continue
        e = es[0][3]
        if kind == LOOKUP: res = lookup(source, e, ps[0][3])
        elif kind == CHAIN: res = chain(source, e, ps[0][3], ps[1][3])
        elif kind == PATH:
            pth = path(source, es[0][3], es[1][3], max_hops=1) or path(source, es[1][3], es[0][3], max_hops=1)
            if pth is None:
                weak = path(source, es[0][3], es[1][3]) or path(source, es[1][3], es[0][3])
                if weak: weaks.append((es, weak))
            res = [(pth[-1][2], pth)] if pth else []
        elif kind == MEMBER:
            pth = path(source, es[0][3], es[1][3], only={ps[0][3]}, max_hops=1) or path(source, es[0][3], es[1][3], max_hops=1)
            if pth is None:
                weak = path(source, es[0][3], es[1][3], only={ps[0][3]}) or path(source, es[0][3], es[1][3])
                if weak: weaks.append((es, weak))
            res = [(pth[-1][2], pth)] if pth else []
        else: res = []
        for value, edges in res:
            ok, certs = True, set()
            for s, p, o in edges:
                good, c = edge_certificate(source, s, p, o); ok = ok and good; certs |= c
            if ok: survivors.append((kind, es, ps, value, edges, certs))
    if not survivors:
        if weaks:
            es, w = weaks[0]
            return dict(state="WEAK", kind=PATH, answers=[], readings=rd, consulted=source.consulted(), ask=None, weak=w)
        return dict(state="NOT FOUND", kind=None, answers=[], readings=rd, consulted=source.consulted(), ask=None)
    # A7 coverage then simplicity; A11 tie-break by specificity (lower summed df of entity spans first)
    def spec(sv): return sum((df(syms[r[0]]) if df else 0) for r in sv[1])
    def used(sv): return (sum(r[1] - r[0] for r in sv[1] + sv[2]), -(len(sv[1]) + len(sv[2])), -spec(sv))
    top = max(used(sv) for sv in survivors)
    best = [sv for sv in survivors if used(sv) == top]
    # A8: a property reading no top survivor uses, not overlapping a used span -> PARTIAL
    used_spans = [(r[0], r[1]) for sv in best for r in sv[1] + sv[2]]
    unused = [r for r in rd if r[2] == "P" and not any(a < r[1] and r[0] < b for a, b in used_spans)]
    if unused:
        return dict(state="PARTIAL", kind=best[0][0], answers=[(sv[3], source.label(sv[3]), [sv[4]], sv[5], [sv[0]]) for sv in best[:3]],
                    readings=rd, consulted=source.consulted(), ask=None, missing=sorted({lab for _, _, _, _, lab in unused}))
    values = collections.OrderedDict()
    for kind, es, ps, value, edges, certs in best:
        values.setdefault(value, []).append((kind, es, ps, edges, certs))
    answers = [(v, source.label(v), [x[3] for x in lst], set().union(*[x[4] for x in lst]), [x[0] for x in lst]) for v, lst in values.items()]
    if len(values) == 1:
        return dict(state=ATTRIBUTED, kind=answers[0][4][0], answers=answers, readings=rd, consulted=source.consulted(), ask=None)
    # several distinct values: if they all come from ONE structure (a multi-valued property), that is one answer SET
    kinds = {(x[0], tuple(r[3] for r in x[1]), tuple(r[3] for r in x[2])) for lst in values.values() for x in lst}
    if len(kinds) == 1:
        return dict(state=ATTRIBUTED, kind=answers[0][4][0], answers=answers, readings=rd, consulted=source.consulted(), ask=None, multi=True)
    return dict(state="READINGS", kind=None, answers=answers, readings=rd, consulted=source.consulted(),
                ask="which reading: " + " | ".join(f"{lab} via {' -> '.join(source.label(p) for _, p, _ in ed[0])}" for _, lab, ed, _, _ in answers))
