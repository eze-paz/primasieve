"""TABLE -- the table WORLD for core.reason (tables_numbers_prereg.md; unified in f4_prereg.md Part 1). Zero LLM.

Holds no word of any language. Knows: how to read a span as a COLUMN (header), a FILTER (cell value), a NUMBER
(literal), an OPERATOR (through an INDUCED lexicon passed in); an unnamed inventory of exact operators over
Fractions; the structures those readings afford; that a structure is computable or not; that a committed answer
cites the cells it used. `induce_lexicon` learns word -> operator from (question, confirmed answer) pairs:
intersection of survivor sets (B1), minimal cover ranked by purity then coverage (B5/B6), DIFF order (B4).
Ranking and verdicts live in core.reason (PARTIAL on an unused column/filter reading = B8)."""
import collections
import itertools
from fractions import Fraction

from .reason import reason, symbols as _symbols, READINGS, PARTIAL, NOT_FOUND

SUM, MEAN, MAX, MIN, COUNT, ARGMAX, ARGMIN, DIFF, LOOKUP = range(9)
AGG = (SUM, MEAN, MAX, MIN)


class Table:
    def __init__(self, headers, rows):
        self.headers = [h.lower() for h in headers]
        self.rows = [list(r) for r in rows]
        self.numeric = {h for i, h in enumerate(self.headers) if all(_isnum(r[i]) for r in self.rows)}
        self.values = collections.defaultdict(set)
        for r in self.rows:
            for i, h in enumerate(self.headers):
                if h not in self.numeric: self.values[h].add(str(r[i]).lower())

    def col(self, h): return self.headers.index(h)


def _isnum(x):
    try: Fraction(str(x)); return True
    except Exception: return False


def symbols(text): return _symbols(text, "LN")


def select(table, filters):
    rows = list(range(len(table.rows)))
    for h, v in filters:
        c = table.col(h); rows = [r for r in rows if str(table.rows[r][c]).lower() == v]
    return rows


def compute(table, op, col, rows, target=None, rows_b=None):
    """-> (value, cells) or None. cells = [(row, column header, cell value)] actually used."""
    if op == COUNT:
        return Fraction(len(rows)), [(r, table.headers[0], table.rows[r][0]) for r in rows]
    if not rows or col is None or col not in table.numeric: return None
    c = table.col(col)
    vals = [(r, Fraction(str(table.rows[r][c]))) for r in rows]
    cells = [(r, col, table.rows[r][c]) for r, _ in vals]
    if op == SUM: return sum(v for _, v in vals), cells
    if op == MEAN: return sum(v for _, v in vals) / len(vals), cells
    if op == MAX: return max(v for _, v in vals), cells
    if op == MIN: return min(v for _, v in vals), cells
    if op in (ARGMAX, ARGMIN):
        if target is None or target == col: return None
        r, v = (max if op == ARGMAX else min)(vals, key=lambda x: x[1])
        if len([rr for rr, vv in vals if vv == v]) > 1: return None       # a tie is not a unique answer
        t = table.col(target)
        return str(table.rows[r][t]).lower(), cells + [(r, target, table.rows[r][t])]
    if op == DIFF:
        if rows_b is None: return None
        a = compute(table, SUM, col, rows); b = compute(table, SUM, col, rows_b)
        if a is None or b is None: return None
        return a[0] - b[0], a[1] + b[1]
    if op == LOOKUP:
        if len(rows) != 1: return None
        r = rows[0]; v = table.rows[r][c] if col in table.numeric else str(table.rows[r][c]).lower()
        return (Fraction(str(v)) if col in table.numeric else v), [(r, col, table.rows[r][c])]
    return None


class TableWorld:
    content_kinds = {"C", "F"}
    attributed = False           # a computed answer over the user's own table is COMMIT, not a quoted source

    def __init__(self, table, lexicon=None, order=None):
        self.table, self.lexicon, self.order = table, lexicon or {}, order

    def readings(self, syms):
        t = self.table; out = []
        for i in range(len(syms)):
            for L in (3, 2, 1):
                if i + L > len(syms): continue
                text = " ".join(syms[i:i + L])
                if text in t.headers: out.append((i, i + L, "C", text, text))
                for h, vals in t.values.items():
                    if text in vals: out.append((i, i + L, "F", (h, text), text))
                if L == 1 and _isnum(text): out.append((i, i + 1, "N", Fraction(text), text))
                if text in self.lexicon: out.append((i, i + L, "O", self.lexicon[text], text))
        return out

    def structures(self, rd):
        t = self.table
        cols = [r for r in rd if r[2] == "C"]; fils = [r for r in rd if r[2] == "F"]; ops = [r for r in rd if r[2] == "O"]
        out = []

        def disjoint(rs):
            iv = sorted((r[0], r[1]) for r in rs)
            return all(iv[k][1] <= iv[k + 1][0] for k in range(len(iv) - 1))

        fsets = [()] + [(f,) for f in fils]
        for k in (2, 3):
            fsets += [tuple(p) for p in itertools.combinations(fils, k) if len({f[3][0] for f in p}) == k]
        opset = sorted({o[3] for o in ops}) or [LOOKUP]
        for fs in fsets:
            if not disjoint(list(fs)): continue
            filters = [f[3] for f in fs]
            for op in opset:
                owords = [o for o in ops if o[3] == op]
                if op == COUNT:
                    if all(disjoint(list(fs) + [o]) for o in owords): out.append((op, None, filters, None, None, fs, owords))
                    continue
                for c in cols:
                    if not disjoint(list(fs) + [c] + owords): continue
                    if op in AGG or op == LOOKUP: out.append((op, c[3], filters, None, None, fs + (c,), owords))
                    if op in (MAX, MIN):
                        for tg in cols:
                            if tg is not c and tg[3] not in t.numeric and disjoint(list(fs) + [c, tg] + owords):
                                out.append((ARGMAX if op == MAX else ARGMIN, c[3], filters, tg[3], None, fs + (c, tg), owords))
                    if op == DIFF:
                        for fa, fb in itertools.permutations(fils, 2):
                            if fa[3][0] == fb[3][0] and disjoint([fa, fb, c] + owords):
                                if self.order == "first" and fa[0] > fb[0]: continue
                                out.append((op, c[3], [fa[3]], None, [fb[3]], (fa, fb, c), owords))
        return out

    def spans_of(self, st): return [(r[0], r[1]) for r in tuple(st[5]) + tuple(st[6])]

    def key(self, st): return (st[0], st[1], tuple(st[2]), st[3], tuple(st[4]) if st[4] is not None else None)

    def evaluate(self, st):
        op, col, filters, target, filters_b = st[:5]
        rows = select(self.table, filters); rows_b = select(self.table, filters_b) if filters_b is not None else None
        res = compute(self.table, op, col, rows, target, rows_b)
        if res is None: return None
        value, cells = res
        return value, cells, {("TABLE", r, h, str(v)) for r, h, v in cells}

    def label(self, v): return str(v)


def structures(rd, table, order=None): return TableWorld(table, {}, order).structures(rd)


def readings(syms, table, lexicon=None): return TableWorld(table, lexicon).readings(syms)


def evaluate(table, st): return TableWorld(table).evaluate(st)


def answer(text, table, lexicon, order=None):
    """pre-unification result shape (tables_numbers.py reads it)."""
    world = TableWorld(table, lexicon, order)
    fr = reason(text, world, None, cats="LN")
    rd = fr["readings"]
    if fr["kind"] == NOT_FOUND: return dict(state="NOT FOUND", readings=rd, answers=[])
    answers = [(v, st[:5]) for v, lab, sups, certs, st in fr["answers"]]
    if fr["kind"] == PARTIAL: return dict(state="PARTIAL", readings=rd, answers=answers, missing=fr["missing"])
    if fr["kind"] == READINGS: return dict(state="READINGS", readings=rd, answers=answers)
    v, lab, sups, certs, st = fr["answers"][0]
    return dict(state="COMMIT", value=v, cells=sups[0], structure=st[:5], readings=rd, answers=answers)


def induce_lexicon(teaching, table):
    """(question, confirmed answer) pairs -> (word -> operator, contested, diff order). B1 intersection, B5/B6
    minimal cover by purity then coverage, B4 order."""
    inter = {}; seen = collections.Counter(); order_votes = collections.Counter(); questions = []
    for q, gold in teaching:
        if gold is None: continue
        syms = symbols(q); rd = readings(syms, table)
        surv_ops = set()
        for op in (SUM, MEAN, MAX, MIN, COUNT, DIFF, LOOKUP):
            fake = rd + [(len(syms), len(syms) + 1, "O", op, "")]
            for st in structures(fake, table):
                res = evaluate(table, st)
                if res is not None and _same(res[0], gold):
                    surv_ops.add(op)
                    if st[0] == DIFF:
                        fa, fb = st[5][0], st[5][1]; order_votes["first" if fa[0] < fb[0] else "second"] += 1
        if not surv_ops: continue
        read_pos = {k for r in rd for k in range(r[0], r[1])}
        free = [w for k, w in enumerate(syms) if k not in read_pos]
        questions.append((set(free), surv_ops))
        for w in free:
            seen[w] += 1
            inter[w] = surv_ops & inter[w] if w in inter else set(surv_ops)
    cands, contested = {}, []
    for w, ops in inter.items():
        if len(ops) == 1: cands[w] = next(iter(ops))
        elif len(ops) > 1 and seen[w] >= 2: contested.append(w)
    lexicon = {}
    uncovered = [(free, ops) for free, ops in questions if any(w in cands and cands[w] in ops for w in free)]
    while uncovered:
        def purity(w): return sum(1 for free, ops in questions if w in free and ops == {cands[w]}) / max(seen[w], 1)
        best = max(cands, key=lambda w: (purity(w), sum(1 for free, ops in uncovered if w in free and cands[w] in ops), seen[w]))
        if sum(1 for free, ops in uncovered if best in free and cands[best] in ops) == 0: break
        lexicon[best] = cands[best]
        uncovered = [(free, ops) for free, ops in uncovered if not (best in free and cands[best] in ops)]
    order = "first" if order_votes and set(order_votes) == {"first"} else None
    return lexicon, contested, order


def _same(a, b):
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        try: return Fraction(str(a)) == Fraction(str(b))
        except Exception: return False
    return str(a).lower() == str(b).lower()
