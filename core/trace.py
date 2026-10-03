"""TRACE -- a world with TIME: situations in sequence, transitions as evidence, prediction by search (dynamics_prereg.md;
EMERGENCE_PLAN.md S7). Zero LLM. Holds no word of any language: the time words are DATA the chat layer hands in, the
fields are the trace's own.

A trace is a sequence of flat records. A DYNAMICS for a field is the smallest term over core.primitives (leaves: the
current situation's fields and the structural constants 1, 2) that maps every observed situation to the next value of
that field. The search is core.exec.synth's shape: bottom-up by size, observational equivalence over the PROBE inputs
-- the observed situations AND the last one, whose successor is the question -- so two programs that agree on every
transition but differ on the next step stay two hypotheses (the dedupe signature holds every input the verdict depends
on: the lesson of negative_prereg.md and nolf, met a third time). The world PREDICTS only when the transitions are a
FUNCTION (no situation observed with two different successors) and reports several minimal programs as several
structures, which the loop renders as READINGS over futures, never a COMMIT.

Structures: AT(field, t), CHANGE(field, t1, t2), NEXT(field, k) -- the last one per minimal program. Certificates: the
situations read, and for NEXT the transitions that forced the program."""
from fractions import Fraction

from . import primitives as P
from .generate import SignatureBank
from .reason import symbols as _symbols

CONSTS = (1, 2)
AT, CHANGE, NEXT = "AT", "CHANGE", "NEXT"


def _norm(v):
    if isinstance(v, Fraction) and v.denominator == 1: return int(v)
    return v


def _apply(op, args):
    try: return _norm(P.apply(op, *args))
    except (P.IllTyped, ZeroDivisionError, ValueError, OverflowError, TypeError): return None


def _ev(tree, sit):
    """a term over field names / constants / (op, kids) evaluated on one situation -> value or None"""
    if isinstance(tree, str): return sit.get(tree)
    if isinstance(tree, int): return tree
    args = [_ev(k, sit) for k in tree[1:]]
    if any(a is None for a in args): return None
    return _apply(tree[0], args)


def ops_for(exclude=()):
    unary = [p for p in P.pids() if P.signature(p) in (((P.RAT,), P.RAT), ((P.INT,), P.INT)) and p not in exclude]
    binary = [p for p in P.pids() if P.signature(p) in (((P.RAT, P.RAT), P.RAT), ((P.INT, P.INT), P.INT)) and p not in exclude]
    return unary, binary


def _size(t): return 1 if not isinstance(t, tuple) else 1 + sum(_size(k) for k in t[1:])


class Trace:
    def __init__(self, records):
        self.records = [dict(r) for r in records]
        self.fields = sorted({f for r in self.records for f in r})

    def __len__(self): return len(self.records)

    def transitions(self): return list(zip(self.records[:-1], self.records[1:]))

    def functional(self):
        """no situation observed with two different successors"""
        seen = {}
        for a, b in self.transitions():
            key = tuple(sorted(a.items())); nxt = tuple(sorted(b.items()))
            if seen.setdefault(key, nxt) != nxt: return False
        return True


def induce(trace, field, max_size=9, cap=50000, exclude=()):
    """-> list of the minimal-size programs (distinct on the probe inputs) reproducing every transition of `field`;
    [] when none within the bound. The probe inputs are every observed situation (the last included)."""
    trans = trace.transitions()
    if not trans: return []
    probe = [a for a, b in trans] + [trace.records[-1]]
    target = tuple(b[field] for a, b in trans); m = len(trans)
    unary, binary = ops_for(exclude)
    bank = SignatureBank(budget=cap * 4); by = bank.by_size; n = 0; found = []

    def add(size, tree):
        nonlocal n
        n += 1
        vals = tuple(_ev(tree, s) for s in probe)
        if any(v is None for v in vals[:m]): return
        if not bank.add(tree, vals, size=size, payload=None): return
        if vals[:m] == target: found.append(tree)

    for leaf in list(trace.fields) + list(CONSTS): add(1, leaf)
    if found: return found
    for size in range(2, max_size + 1):
        for u in unary:
            for ctree, _, _ in list(by[size - 1]):
                if n >= cap: return found
                add(size, (u, ctree))
        for ls in range(1, size - 1):
            rs = size - 1 - ls
            for ltree, _, _ in list(by[ls]):
                for rtree, _, _ in list(by[rs]):
                    for b in binary:
                        if n >= cap: return found
                        add(size, (b, ltree, rtree))
        if found: return found                                 # the smallest size that fits: every program of that size
    return found


class TraceWorld:
    content_kinds = {"F"}
    attributed = False

    def __init__(self, trace, words, name=None, exclude=()):
        """`words`: time words as DATA, word -> AT | CHANGE | NEXT (the chat layer's, like the transcript world's fields)"""
        self.trace = trace if isinstance(trace, Trace) else Trace(trace); self.words = dict(words); self.name = name or "trace"
        self.log = []; self.exclude = tuple(exclude); self._programs = {}

    def programs(self, field):
        if field not in self._programs: self._programs[field] = induce(self.trace, field, exclude=self.exclude)
        return self._programs[field]

    # ---- the world contract -------------------------------------------------------------------------------------------
    def readings(self, syms):
        out = []
        for i, s in enumerate(syms):
            if s in self.trace.fields: out.append((i, i + 1, "F", s, s))
            if s in self.words: out.append((i, i + 1, "W", self.words[s], s))
            if s.isdigit(): out.append((i, i + 1, "N", int(s), s))
        self.log.append((self.name, " ".join(syms)))
        return out

    def structures(self, rd):
        fs = [r for r in rd if r[2] == "F"]; ws = [r for r in rd if r[2] == "W"]; ns = [r for r in rd if r[2] == "N"]
        kinds = {w[3] for w in ws} or {AT}
        out = []
        for f in fs:
            for w in (ws or [None]):
                k = w[3] if w else AT
                if k == AT:
                    for t in ns: out.append((AT, f, w, t))
                if k == NEXT:
                    for t in ns:
                        for pi in range(max(1, len(self.programs(f[3])))): out.append((NEXT, f, w, t, pi))
                if k == CHANGE:
                    for a in ns:
                        for b in ns:
                            if a[0] < b[0]: out.append((CHANGE, f, w, a, b))
        return out

    def spans_of(self, st): return [(r[0], r[1]) for r in st[1:] if isinstance(r, tuple)]

    def key(self, st): return (st[0], st[1][3]) + tuple(r[3] for r in st[3:] if isinstance(r, tuple)) + ((st[4],) if st[0] == NEXT else ())

    def shape(self, st): return (st[0], st[1][3])

    def _step(self, sit, choice):
        """one step of the joint dynamics: every field by its chosen program (a field with none keeps its value)"""
        nxt = {}
        for f in self.trace.fields:
            progs = self.programs(f)
            if not progs: return None
            v = _ev(progs[choice.get(f, 0)], sit)
            if v is None: return None
            nxt[f] = v
        return nxt

    def evaluate(self, st):
        kind, f = st[0], st[1][3]; recs = self.trace.records
        if kind == AT:
            t = st[3][3]
            if not 0 <= t < len(recs) or f not in recs[t]: return None
            return recs[t][f], [(t, f)], {("TRACE", t, f, str(recs[t][f]))}
        if kind == CHANGE:
            a, b = st[3][3], st[4][3]
            if not (0 <= a < len(recs) and 0 <= b < len(recs)): return None
            return recs[b][f] - recs[a][f], [(a, f), (b, f)], {("TRACE", a, f, str(recs[a][f])), ("TRACE", b, f, str(recs[b][f]))}
        if kind == NEXT:
            k, pi = st[3][3], st[4]
            if not self.trace.functional() or k < 1: return None                  # not a function at this grain: no prediction
            progs = self.programs(f)
            if not progs or pi >= len(progs): return None
            sit = dict(recs[-1])
            for _ in range(k):
                sit = self._step(sit, {f: pi})
                if sit is None: return None
            certs = {("DYN", f, repr(progs[pi]), len(self.trace.transitions()))} | {("TRACE", t, f, str(r[f])) for t, r in enumerate(recs) if f in r}
            return sit[f], [(len(recs) - 1 + k, f)], certs
        return None

    def label(self, v): return str(v)

    def owns(self, r): return r[2] in ("F", "W", "N")

    def consulted(self): return [(self.name, "situations", len(self.trace), "fields", tuple(self.trace.fields))] + list(self.log)
