"""KG -- the knowledge-graph WORLD for core.reason (kg_multihop_prereg.md; unified in f4_prereg.md Part 1).

Holds no word of any language, no entity, no property. Supplies to the one loop:
  READINGS    every 1-3 symbol span -> entity readings and property readings from the injected source. A1: a span
              edged by a symbol above the question's median definition-frequency is not a name; A5: a span that
              names a PROPERTY is not an entity; A6: a lone common word is no property either.
  STRUCTURES  by AFFORDANCE of the reading counts: LOOKUP (1 entity, 1 property), CHAIN (1, 2), PATH (2, 0),
              MEMBER (2, 1). A9: a relation is asserted only from a DIRECT edge; a 2-hop connection is WEAK.
  EVALUATE    the graph supports the structure or not; every edge carries a certificate checked verbatim against
              the fetched claims (core.verdict.attribute). A2: hub edges (fan-out > 8) are never followed.
Ranking and verdicts (coverage, simplicity, specificity; READINGS / PARTIAL / WEAK / NOT FOUND) live in core.reason."""
import itertools

from .reason import reason, symbols as _symbols, READINGS, PARTIAL, WEAK, NOT_FOUND
from .verdict import attribute, ATTRIBUTED

LOOKUP, CHAIN, PATH, MEMBER, DESCRIBE = "LOOKUP", "CHAIN", "PATH", "MEMBER", "DESCRIBE"


def symbols(text): return _symbols(text, "L")


def spans(syms, maxlen=3):
    for i in range(len(syms)):
        for L in range(1, maxlen + 1):
            if i + L <= len(syms): yield i, i + L, " ".join(syms[i:i + L])


def edge_certificate(source, s, p, o):
    text = source.claims_text(s)
    span = f'"{o}"'
    claim, state, prov = attribute(span, "KG", text, span if (span in text and p in text) else "", lambda x: x)
    return state == ATTRIBUTED, {(f"{s} {p} {o}", source.label(s), source.label(p), source.label(o))}


def lookup(source, e, p):
    return [(v, [(e, p, v)]) for v in source.claims(e).get(p, [])]


def chain(source, e, p1, p2):
    return [(v2, ed1 + ed2) for v1, ed1 in lookup(source, e, p1) for v2, ed2 in lookup(source, v1, p2)]


def path(source, a, b, max_hops=2, only=None, budget=20, fanout=8):
    frontier = [(a, [])]; seen = {a}; expanded = 0
    for hop in range(max_hops):
        nxt = []
        for node, edges in frontier:
            if expanded >= budget: return None
            expanded += 1
            for p, vals in source.claims(node).items():
                if only is not None and p not in only: continue
                if len(vals) > fanout: continue
                for v in vals:
                    if v == b: return edges + [(node, p, v)]
                    if v not in seen and hop + 1 < max_hops:
                        seen.add(v); nxt.append((v, edges + [(node, p, v)]))
        frontier = nxt[:budget]
    return None


class KGWorld:
    content_kinds = {"P"}          # a property word the answer did not use -> PARTIAL (A8)
    attributed = True

    def __init__(self, source, df=None, max_ent=8, name=None):
        self.source, self.df, self.max_ent = source, df, max_ent; self.name = name or "kg"; self.rank = {}
        self._ent, self._prop = {}, {}                  # per-span memo over the source (the source parses JSON on every call)

    def readings(self, syms):
        df, source = self.df, self.source
        med = None
        if df is not None:
            vals = sorted(df(s) for s in syms); med = vals[len(vals) // 2] if vals else None
        out = []
        for i, j, text in spans(syms):
            hi = lambda k: med is not None and df(syms[k]) > med
            edged = med is not None and (hi(i) or hi(j - 1))
            if text not in self._prop: self._prop[text] = list(source.properties(text))
            props = [] if (edged and j - i == 1) else self._prop[text]
            for pid, lab, *_ in props: out.append((i, j, "P", pid, lab))
            if edged or props: continue
            if text not in self._ent: self._ent[text] = source.entities(text)[:self.max_ent]
            for pos, (qid, lab, desc) in enumerate(self._ent[text]):
                out.append((i, j, "E", qid, lab)); self.rank.setdefault(qid, pos)
        return out

    def rank_key(self, st):
        """at equal coverage, the source's own search order decides between same-named entities (its ordering, not ours)."""
        return -sum(self.rank.get(r[3], 0) for r in st[1])

    def value_reading(self, v):
        return ("E", v) if isinstance(v, str) and v[:1] == "Q" and self.source.label(v) != v else None

    def owns(self, r): return r[2] in ("E", "P")

    def structures(self, rd):
        ents = [r for r in rd if r[2] == "E"]; props = [r for r in rd if r[2] == "P"]
        out = []

        def disjoint(rs):
            iv = sorted((r[0], r[1]) for r in rs)
            return all(iv[k][1] <= iv[k + 1][0] for k in range(len(iv) - 1))

        for e in ents:
            for p in props:
                if disjoint([e, p]): out.append((LOOKUP, (e,), (p,)))
            for p1, p2 in itertools.permutations(props, 2):
                if disjoint([e, p1, p2]): out.append((CHAIN, (e,), (p1, p2)))
        for e1, e2 in itertools.combinations(ents, 2):
            if not disjoint([e1, e2]): continue
            out.append((PATH, (e1, e2), ()))
            for p in props:
                if disjoint([e1, e2, p]): out.append((MEMBER, (e1, e2), (p,)))
        return out

    def spans_of(self, st): return [(r[0], r[1]) for r in st[1] + st[2]]

    def key(self, st): return (st[0], tuple(r[3] for r in st[1]), tuple(r[3] for r in st[2]))

    def shape(self, st): return (st[0], tuple(r[3] for r in st[2]))          # the structure with its entities abstracted

    def _result(self, st):
        kind, es, ps = st; src = self.source; e = es[0][3]
        if kind == LOOKUP: return lookup(src, e, ps[0][3])
        if kind == CHAIN: return chain(src, e, ps[0][3], ps[1][3])
        if kind == PATH:
            pth = path(src, es[0][3], es[1][3], max_hops=1) or path(src, es[1][3], es[0][3], max_hops=1)
            return [(pth[-1][2], pth)] if pth else []
        if kind == MEMBER:
            pth = path(src, es[0][3], es[1][3], only={ps[0][3]}, max_hops=1) or path(src, es[0][3], es[1][3], max_hops=1)
            return [(pth[-1][2], pth)] if pth else []
        return []

    def evaluate(self, st):
        res = self.evaluate_all(st)
        return res[0] if res else None

    def evaluate_all(self, st):
        out = []
        for value, edges in self._result(st):
            ok, certs = True, set()
            for s, p, o in edges:
                good, c = edge_certificate(self.source, s, p, o); ok = ok and good; certs |= c
            if ok: out.append((value, edges, certs))
        return out

    def weak(self, st):
        kind, es, ps = st; src = self.source
        if kind == PATH:
            w = path(src, es[0][3], es[1][3]) or path(src, es[1][3], es[0][3])
        elif kind == MEMBER:
            w = path(src, es[0][3], es[1][3], only={ps[0][3]}) or path(src, es[0][3], es[1][3])
        else: w = None
        return (w[-1][2], w) if w else None

    def label(self, v): return self.source.label(v)

    def labelled(self, v): return self.source.label(v) != v

    def consulted(self): return self.source.consulted()


def answer(text, source, df=None, log=None):
    """the pre-unification result shape (kg_multihop.py reads it). Multi-valued structures are expanded here."""
    world = KGWorld(source, df)
    fr = reason(text, world, df)
    rd = fr["readings"]
    if fr["kind"] == NOT_FOUND:
        return dict(state="NOT FOUND", kind=None, answers=[], readings=rd, consulted=fr["consulted"], ask=None)
    if fr["kind"] == WEAK:
        return dict(state="WEAK", kind=PATH, answers=[], readings=rd, consulted=fr["consulted"], ask=None, weak=fr["weak"][2])
    answers = []; seen = set()
    for v, lab, sups, certs, st in fr["answers"]:
        for value, edges, c in world.evaluate_all(st):
            if value in seen: continue
            seen.add(value); answers.append((value, source.label(value), [edges], c, [st[0]]))
    if fr["kind"] == PARTIAL:
        return dict(state="PARTIAL", kind=fr["answers"][0][4][0], answers=answers[:3], readings=rd, consulted=fr["consulted"], ask=None, missing=fr["missing"])
    if fr["kind"] == READINGS:
        return dict(state="READINGS", kind=None, answers=answers, readings=rd, consulted=fr["consulted"],
                    ask="which reading: " + " | ".join(f"{lab} via {' -> '.join(source.label(p) for _, p, _ in ed[0])}" for _, lab, ed, _, _ in answers))
    return dict(state=ATTRIBUTED, kind=answers[0][4][0], answers=answers, readings=rd, consulted=fr["consulted"], ask=None, multi=len(answers) > 1)
