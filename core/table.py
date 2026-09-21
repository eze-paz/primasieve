"""TABLE -- exact reasoning over a table with traceable cells (tables_numbers_prereg.md). Zero LLM.

Holds no word of any language. Knows: how to read a span as a COLUMN (header), a FILTER (cell value), a NUMBER
(literal); an unnamed inventory of exact operators over Fractions; the structures those readings afford; that a
structure survives iff it is computable; that a unique survivor commits with the cells it used as certificate.
The OPERATOR LEXICON (word -> operator) is not here: `induce_lexicon` learns it from (question, confirmed answer)
pairs by elimination, and `answer` receives it as an argument."""
import collections
import itertools
import unicodedata
from fractions import Fraction

from .resolve import segment

SUM, MEAN, MAX, MIN, COUNT, ARGMAX, ARGMIN, DIFF, LOOKUP = range(9)
AGG = (SUM, MEAN, MAX, MIN)


class Table:
    def __init__(self, headers, rows):
        self.headers = [h.lower() for h in headers]
        self.rows = [list(r) for r in rows]
        self.numeric = {h for i, h in enumerate(self.headers) if all(_isnum(r[i]) for r in self.rows)}
        self.values = collections.defaultdict(set)              # categorical column -> set of values (lower)
        for r in self.rows:
            for i, h in enumerate(self.headers):
                if h not in self.numeric: self.values[h].add(str(r[i]).lower())

    def col(self, h): return self.headers.index(h)


def _isnum(x):
    try: Fraction(str(x)); return True
    except Exception: return False


def symbols(text):
    return [s.lower() for s in segment(text) if unicodedata.category(s[0])[0] in "LN"]


def readings(syms, table, lexicon=None):
    """-> list of (i, j, kind, payload). kinds: C column, F (column, value), N number, O operator (via lexicon)."""
    out = []
    for i in range(len(syms)):
        for L in (3, 2, 1):
            if i + L > len(syms): continue
            text = " ".join(syms[i:i + L])
            if text in table.headers: out.append((i, i + L, "C", text))
            for h, vals in table.values.items():
                if text in vals: out.append((i, i + L, "F", (h, text)))
            if L == 1 and _isnum(text): out.append((i, i + 1, "N", Fraction(text)))
            if lexicon and text in lexicon: out.append((i, i + L, "O", lexicon[text]))
    return out


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
        ties = [rr for rr, vv in vals if vv == v]
        if len(ties) > 1: return None                            # a tie is not a unique answer
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


def structures(rd, table, order=None):
    """-> list of (op, col, filters, target, filters_b) affordances from the readings (non-overlapping spans)."""
    cols = [r for r in rd if r[2] == "C"]; fils = [r for r in rd if r[2] == "F"]; ops = [r for r in rd if r[2] == "O"]
    out = []

    def disjoint(rs):
        iv = sorted((r[0], r[1]) for r in rs)
        return all(iv[k][1] <= iv[k + 1][0] for k in range(len(iv) - 1))

    fsets = [()] + [(f,) for f in fils]
    for k in (2, 3):                                                # B3: up to three filters on distinct columns
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
                if op in (MAX, MIN):                              # ARG variant = MAX/MIN with a categorical TARGET column present
                    for t in cols:
                        if t is not c and t[3] not in table.numeric and disjoint(list(fs) + [c, t] + owords):
                            out.append((ARGMAX if op == MAX else ARGMIN, c[3], filters, t[3], None, fs + (c, t), owords))
                if op == DIFF:
                    for fa, fb in itertools.permutations(fils, 2):
                        if fa[3][0] == fb[3][0] and disjoint([fa, fb, c] + owords):
                            if order == "first" and fa[0] > fb[0]: continue      # B4: learned order, first-mentioned minus second
                            out.append((op, c[3], [fa[3]], None, [fb[3]], (fa, fb, c), owords))
    return out


def evaluate(table, st):
    op, col, filters, target, filters_b = st[:5]
    rows = select(table, filters); rows_b = select(table, filters_b) if filters_b is not None else None
    return compute(table, op, col, rows, target, rows_b)


def answer(text, table, lexicon, order=None):
    syms = symbols(text)
    rd = readings(syms, table, lexicon)
    surv = []
    for st in structures(rd, table, order):
        res = evaluate(table, st)
        if res is not None: surv.append((st, res))
    if not surv: return dict(state="NOT FOUND", readings=rd, answers=[])
    def cover(s): return sum(r[1] - r[0] for r in s[0][5] + tuple(s[0][6]))
    top = max(cover(s) for s in surv); best = [s for s in surv if cover(s) == top]
    vals = collections.OrderedDict()
    for st, (v, cells) in best: vals.setdefault(v, []).append((st, cells))
    # B8: a column or filter reading no top survivor uses (and no used span overlaps) -> PARTIAL, never a commit
    used_spans = [(r[0], r[1]) for st, _ in best for r in st[5]]
    unused = [r for r in rd if r[2] in ("C", "F") and not any(a < r[1] and r[0] < b for a, b in used_spans)]
    if unused:
        return dict(state="PARTIAL", readings=rd, answers=[(v, lst[0][0][:5]) for v, lst in vals.items()],
                    missing=[r[3] for r in unused])
    if len(vals) == 1:
        v = next(iter(vals)); st, cells = vals[v][0]
        return dict(state="COMMIT", value=v, cells=cells, structure=st[:5], readings=rd, answers=[(v, st[:5])])
    return dict(state="READINGS", readings=rd, answers=[(v, lst[0][0][:5]) for v, lst in vals.items()])


def induce_lexicon(teaching, table):
    """(question, confirmed answer) pairs -> (word -> operator, contested words, diff order).
    B1 INTERSECTION: for each pair the SURVIVOR ops are those with a structure over the question's column/filter
    readings reproducing the confirmed answer. A free symbol (not read as column/filter/number) is bound to op X iff
    X is in the survivor set of EVERY teaching question containing it that has a non-empty survivor set, and that
    intersection is exactly one op. Words present in questions of different operators intersect to nothing and stay
    unbound. B4: the DIFF order is 'first' (first-mentioned minus second) iff every DIFF teaching pair confirms it."""
    inter = {}; seen = collections.Counter(); order_votes = collections.Counter(); questions = []
    for q, gold in teaching:
        if gold is None: continue                                   # a teacher confirms an answer that exists
        syms = symbols(q); rd = readings(syms, table)
        surv_ops = set()
        for op in (SUM, MEAN, MAX, MIN, COUNT, DIFF, LOOKUP):
            fake = rd + [(len(syms), len(syms) + 1, "O", op)]      # a virtual operator word outside the span
            for st in structures(fake, table):
                res = evaluate(table, st)
                if res is not None and _same(res[0], gold):
                    surv_ops.add(op)
                    if st[0] == DIFF:
                        fa, fb = st[5][0], st[5][1]
                        order_votes["first" if fa[0] < fb[0] else "second"] += 1
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
    # B5 MINIMAL LEXICON: greedy set cover -- the fewest bindings such that every teaching question contains a bound
    # word whose operator is among its survivors. Redundant co-varying words ("which", "rows", "and") never enter.
    lexicon = {}
    uncovered = [(free, ops) for free, ops in questions if any(w in cands and cands[w] in ops for w in free)]
    while uncovered:
        def purity(w): return sum(1 for free, ops in questions if w in free and ops == {cands[w]}) / max(seen[w], 1)
        best = max(cands, key=lambda w: (purity(w), sum(1 for free, ops in uncovered if w in free and cands[w] in ops), seen[w]))   # B6
        gain = sum(1 for free, ops in uncovered if best in free and cands[best] in ops)
        if gain == 0: break
        lexicon[best] = cands[best]
        uncovered = [(free, ops) for free, ops in uncovered if not (best in free and cands[best] in ops)]
    order = "first" if order_votes and set(order_votes) == {"first"} else None
    return lexicon, contested, order


def _same(a, b):
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        try: return Fraction(str(a)) == Fraction(str(b))
        except Exception: return False
    return str(a).lower() == str(b).lower()
