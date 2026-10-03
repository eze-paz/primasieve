"""TABLE / RECORDS -- the data WORLD for core.reason (tables_numbers_prereg.md; unified in f4_prereg.md Part 1;
generalized to RECORDS in general_prereg.md W1). Zero LLM.

Holds no word of any language. A world here is DATA: one or more named collections of records (a Table each), and
nothing declared about them. A field whose every value is the key (first column) of a record in some collection
is a REFERENCE field -- induced from the data, never declared (Records.refs). The flat table is the special case of
one collection with no references, and reproduces tables_numbers unchanged.

Knows: how to read a span as a COLUMN (header), a FILTER (cell value), a NUMBER (literal), an OPERATOR (through an
INDUCED lexicon passed in); an unnamed inventory of exact operators over Fractions; the structures those readings
afford -- including CHAINS: a column reading that is a reference field is a HOP to the referenced collection, and a
column that lives in a collection referencing the current one is reached by the reverse hop; that a structure is
computable or not; that a committed answer cites the cells it used. Both hop orders of the column readings are
enumerated (nothing here knows which way a language nests "X of Y"); the data eliminates the wrong one, and if both
compute to different values the loop reports READINGS.
`induce_lexicon` learns word -> operator from (question, confirmed answer) pairs: intersection of survivor sets
(B1), minimal cover ranked by purity then coverage (B5/B6), DIFF order (B4). Ranking and verdicts live in
core.reason (PARTIAL on an unused column/filter reading = B8)."""
import collections
import itertools
from fractions import Fraction

from .reason import reason, symbols as _symbols, READINGS, PARTIAL, NOT_FOUND
from .induce import induce

SUM, MEAN, MAX, MIN, COUNT, ARGMAX, ARGMIN, DIFF, LOOKUP = range(9)
AGG = (SUM, MEAN, MAX, MIN)
ALL_OPS = (SUM, MEAN, MAX, MIN, COUNT, DIFF, LOOKUP)


class Table:
    def __init__(self, headers, rows, name=None):
        self.name = name
        self.headers = [h.lower() for h in headers]
        self.rows = [list(r) for r in rows]
        self.numeric = {h for i, h in enumerate(self.headers) if all(_isnum(r[i]) for r in self.rows)}
        self.values = collections.defaultdict(set)
        for r in self.rows:
            for i, h in enumerate(self.headers):
                if h not in self.numeric: self.values[h].add(str(r[i]).lower())
        self.keys = {str(r[0]).lower() for r in self.rows}

    def col(self, h): return self.headers.index(h)


class Records:
    """named collections + induced references. refs[(collection name, field)] = referenced collection name."""

    def __init__(self, tables):
        self.tables = {}
        for i, t in enumerate(tables):
            t.name = t.name or str(i); self.tables[t.name] = t
        self.refs = {}
        for a in self.tables.values():
            for h in a.headers[1:]:
                if h in a.numeric or not a.values[h]: continue
                for b in self.tables.values():
                    if a.values[h] <= b.keys: self.refs[(a.name, h)] = b.name; break
        self.headers = sorted({h for t in self.tables.values() for h in t.headers})
        self.values = collections.defaultdict(set)
        for t in self.tables.values():
            for h, vs in t.values.items(): self.values[h] |= vs
        self.numeric = {h for h in self.headers if all(h in t.numeric for t in self.tables.values() if h in t.headers)}

    @classmethod
    def of(cls, x): return x if isinstance(x, cls) else cls([x])

    def holding(self, headers):
        """collections whose header set contains every given header."""
        return [t for t in self.tables.values() if all(h in t.headers for h in headers)]

    def refs_of(self, name): return {h for (a, h) in self.refs if a == name}

    def back(self, cur, col):
        """the reverse hop: collections b with a reference field into `cur` and holding `col`. -> [(b, field)]"""
        return [(self.tables[a], h) for (a, h), b in self.refs.items() if b == cur.name and col in self.tables[a].headers]


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
    if not rows or col is None or col not in table.headers: return None
    if col not in table.numeric and op != LOOKUP: return None
    c = table.col(col)
    if op == LOOKUP:
        if len(rows) != 1: return None
        r = rows[0]; v = table.rows[r][c] if col in table.numeric else str(table.rows[r][c]).lower()
        return (Fraction(str(v)) if col in table.numeric else v), [(r, col, table.rows[r][c])]
    vals = [(r, Fraction(str(table.rows[r][c]))) for r in rows]
    cells = [(r, col, table.rows[r][c]) for r, _ in vals]
    if op == SUM: return sum(v for _, v in vals), cells
    if op == MEAN: return sum(v for _, v in vals) / len(vals), cells
    if op == MAX: return max(v for _, v in vals), cells
    if op == MIN: return min(v for _, v in vals), cells
    if op in (ARGMAX, ARGMIN):
        if target is None or target == col or target not in table.headers: return None
        r, v = (max if op == ARGMAX else min)(vals, key=lambda x: x[1])
        if len([rr for rr, vv in vals if vv == v]) > 1: return None       # a tie is not a unique answer
        t = table.col(target)
        return str(table.rows[r][t]).lower(), cells + [(r, target, table.rows[r][t])]
    if op == DIFF:
        if rows_b is None: return None
        a = compute(table, SUM, col, rows); b = compute(table, SUM, col, rows_b)
        if a is None or b is None: return None
        return a[0] - b[0], a[1] + b[1]
    return None


def hop(recs, cur, rows, field):
    """follow reference `field` of collection `cur` from `rows` -> (referenced collection, its rows) or None."""
    b = recs.refs.get((cur.name, field))
    if b is None: return None
    c = cur.col(field); keys = {str(cur.rows[r][c]).lower() for r in rows}
    t = recs.tables[b]
    return t, [i for i, row in enumerate(t.rows) if str(row[0]).lower() in keys]


def hop_back(recs, cur, rows, col=None, to=None):
    """reach the collection holding `col` (or the collection named `to`) through its reference INTO `cur`
    (unique or nothing)."""
    ways = recs.back(cur, col) if to is None else [(recs.tables[a], h) for (a, h), b in recs.refs.items() if b == cur.name and a == to]
    if len(ways) != 1: return None
    t, field = ways[0]; keys = {str(cur.rows[r][0]).lower() for r in rows}; c = t.col(field)
    return t, [i for i, row in enumerate(t.rows) if str(row[c]).lower() in keys]


class TableWorld:
    content_kinds = {"C", "F"}
    attributed = False           # a computed answer over the user's own data is COMMIT, not a quoted source

    def __init__(self, table, lexicon=None, order=None, name=None, df=None):
        self.recs = Records.of(table); self.table = table; self.lexicon, self.order = lexicon or {}, order
        self.name = name or "records"; self.log = []; self.negatives = []; self.pairs = []; self.df = df; self.contested = []
        self.borrowed = {}; self.refused = set()            # transfer (transfer_prereg.md): see core/transfer.py

    def deny(self, question, value):
        """negative evidence (negative_prereg.md): the engine's own answer to `question` was wrong. Recorded and
        applied at the next induction; the operators producing `value` on the question leave its words' survivors.
        A BORROWED word that produced the value is refused for good."""
        if (question, value) not in self.negatives: self.negatives.append((question, value))
        syms = symbols(question)
        for w in [w for w in self.borrowed if w in syms]:
            rd = self.readings(syms)
            if any(_same(r[0], value) for r in (self.evaluate(st) for st in self.structures(rd)) if r is not None):
                del self.borrowed[w]; self.refused.add(w)

    # ---- transfer: an operator's TWO-ARGUMENT restriction is its behaviour on the scalar probes (core/transfer.py) ----
    def operators(self): return list(ALL_OPS)

    def fingerprint(self, op):
        from .primitives import PROBES, RAT
        f = {DIFF: lambda a, b: a - b, SUM: lambda a, b: a + b, MAX: max, MIN: min, MEAN: lambda a, b: (a + b) / 2}.get(op)
        if f is None: return None                      # COUNT and LOOKUP have no scalar behaviour
        grid = PROBES[RAT]
        return (2,) + tuple(str(Fraction(f(Fraction(a), Fraction(b)))) for a in grid for b in grid)

    def borrow(self, word, op, source, order=None):
        """`order`: the source word's argument order ("forward" = the first-named group first); DIFF reads it as "first"."""
        if word in self.lexicon or word in self.refused or word in self.borrowed: return False
        self.borrowed[word] = (op, source, order); return True

    def conjectured(self, st): return any(len(o) > 4 and o[4] in self.borrowed for o in st[6])

    def readings(self, syms):
        t = self.recs; out = []
        for i in range(len(syms)):
            for L in (3, 2, 1):
                if i + L > len(syms): continue
                text = " ".join(syms[i:i + L])
                if text in t.headers: out.append((i, i + L, "C", text, text))
                if text in t.tables: out.append((i, i + L, "T", text, text))
                for h, vals in t.values.items():
                    if text in vals: out.append((i, i + L, "F", (h, text), text))
                if L == 1 and _isnum(text): out.append((i, i + 1, "N", Fraction(text), text))
                if text in self.lexicon: out.append((i, i + L, "O", self.lexicon[text], text))
                elif text in self.borrowed: out.append((i, i + L, "O", self.borrowed[text][0], text))
        self.log.append((self.name, " ".join(syms)))
        return out

    def structures(self, rd):
        recs = self.recs
        cols = [r for r in rd if r[2] == "C"]; fils = [r for r in rd if r[2] == "F"]; ops = [r for r in rd if r[2] == "O"]
        tabs = [r for r in rd if r[2] == "T"]
        out = []

        def disjoint(rs):
            iv = sorted((r[0], r[1]) for r in rs)
            return all(iv[k][1] <= iv[k + 1][0] for k in range(len(iv) - 1))

        fsets = [()] + [(f,) for f in fils]
        for k in (2, 3):
            fsets += [tuple(p) for p in itertools.combinations(fils, k) if len({f[3][0] for f in p}) == k]
        # an operator word IN THE TEXT replaces the default lookup; an operator offered by the session's context (a 6th
        # element marks it) is one more option beside it, never a replacement (chat_acts_prereg.md run 2: an earlier
        # "how many" lingering in context removed LOOKUP from "what is the city of marketing")
        explicit_ops = sorted({o[3] for o in ops if len(o) <= 5})
        # one structure per operator READING, not per operator (depth_prereg.md): a question naming the same operator
        # word twice (an aggregate of one group plus the same aggregate of another) must yield two inners whose
        # spans are disjoint; attaching every reading of the word to each structure made them overlap
        opitems = [(o[3], [o]) for o in ops if len(o) <= 5] or [(LOOKUP, [])]
        opitems += [(o[3], [o]) for o in ops if len(o) > 5 and o[3] not in set(explicit_ops or [LOOKUP])]
        # column subsets: a final column plus 0-2 hop columns, in BOTH nesting orders
        colsets = [(c, ()) for c in cols]
        for c in cols:
            others = [x for x in cols if x is not c]
            for k in (1, 2):
                for hs in itertools.permutations(others, k):
                    colsets.append((c, tuple(hs)))
        for fs in fsets:
            if not disjoint(list(fs)): continue
            filters = [f[3] for f in fs]
            for A in (recs.holding([h for h, _ in filters]) if filters else list(recs.tables.values())):
                for tsp in [()] + [(t,) for t in tabs]:            # a collection-name reading: the collection to end in
                    for op, owords in opitems:
                        if op == COUNT:
                            if not disjoint(list(fs) + list(tsp)) or not all(disjoint(list(fs) + list(tsp) + [o]) for o in owords): continue
                            out.append((op, None, filters, None, None, fs, owords, (), A.name, tsp))
                            for c, hs in colsets:            # count after hops: every column reading is a hop
                                path = (c,) + hs
                                if disjoint(list(fs) + list(path) + list(tsp) + owords):
                                    out.append((op, None, filters, None, None, fs, owords, path, A.name, tsp))
                            continue
                        for c, hs in colsets:
                            if not disjoint(list(fs) + [c] + list(hs) + list(tsp) + owords): continue
                            # a column selected on ITSELF and read back without a hop computes nothing: the value is the
                            # filter (chat_prereg.md run 1: a city name in context was looked up as its own city)
                            if not hs and any(h == c[3] for h, _ in filters): continue
                            if op in AGG or op == LOOKUP: out.append((op, c[3], filters, None, None, fs + (c,), owords, hs, A.name, tsp))
                            if op in (MAX, MIN):
                                for tg in cols:
                                    if tg is not c and tg not in hs and tg[3] not in recs.numeric and disjoint(list(fs) + [c, tg] + list(hs) + list(tsp) + owords):
                                        out.append((ARGMAX if op == MAX else ARGMIN, c[3], filters, tg[3], None, fs + (c, tg), owords, hs, A.name, tsp))
                            if op == DIFF and not hs:
                                for fa, fb in itertools.permutations(fils, 2):
                                    # the two filters share a header, so they are not in `fs` and A ranges over EVERY
                                    # collection: a collection without that header cannot be selected on it (a
                                    # session's context offered ('employee', bob) and ('employee', alice) against the
                                    # departments collection and select() crashed -- found by the turns gate)
                                    if fa[3][0] not in A.headers: continue
                                    if fa[3][0] == fb[3][0] and disjoint([fa, fb, c] + list(tsp) + owords):
                                        order = self.order or ("first" if any(len(o) > 4 and o[4] in self.borrowed and self.borrowed[o[4]][2] == "forward" for o in owords) else None)
                                        if order == "first" and fa[0] > fb[0]: continue
                                        out.append((op, c[3], [fa[3]], None, [fb[3]], (fa, fb, c), owords, (), A.name, tsp))
        return out

    def spans_of(self, st): return [(r[0], r[1]) for r in tuple(st[5]) + tuple(st[6]) + tuple(st[7]) + tuple(st[9])]

    def key(self, st):
        return (st[0], st[1], tuple(st[2]), st[3], tuple(st[4]) if st[4] is not None else None, tuple(h[3] for h in st[7]), st[8], tuple(t[3] for t in st[9]))

    def shape(self, st):        # the structure with its filter VALUES abstracted (headers, hops and operator stay)
        return (st[0], st[1], tuple(h for h, _ in st[2]), st[3], tuple(h for h, _ in st[4]) if st[4] is not None else None, tuple(h[3] for h in st[7]), st[8], tuple(t[3] for t in st[9]))

    def walk(self, start, rows, hops, tsp, col):
        """follow the hops, then the named collection, then the column's own collection -> (collection, rows) | None"""
        recs = self.recs; cur = start
        for h in hops:
            step = hop(recs, cur, rows, h[3])
            if step is None or not step[1]: return None
            cur, rows = step
        if tsp and tsp[0][3] != cur.name:                    # the named collection is reached through its reference into the current one
            step = hop_back(recs, cur, rows, to=tsp[0][3])
            if step is None or not step[1]: return None
            cur, rows = step
        if col is not None and col not in cur.headers:
            step = hop_back(recs, cur, rows, col)
            if step is None or not step[1]: return None
            cur, rows = step
        return cur, rows

    def rank_key(self, st):
        """a filter on a KEY column names a record; the same value in a reference column names the records pointing
        at it. Both are enumerated; at equal coverage the record's own identity ranks first (a fact of the data:
        keys are unique)."""
        recs = self.recs
        return sum(1 for h, _ in st[2] if any(t.headers[0] == h for t in recs.tables.values()))

    def evaluate(self, st):
        op, col, filters, target, filters_b, fs, owords, hops, coll, tsp = st
        recs = self.recs; A = recs.tables[coll]
        w = self.walk(A, select(A, filters), hops, tsp, col)
        if w is None: return None
        cur, rows = w; rows_b = None
        if filters_b is not None:
            wb = self.walk(A, select(A, filters_b), hops, tsp, col)
            if wb is None or wb[0] is not cur: return None
            rows_b = wb[1]
        if target is not None and target not in cur.headers: return None
        res = compute(cur, op, col, rows, target, rows_b)
        if res is None: return None
        value, cells = res
        certs = {("TABLE", cur.name, r, h, str(v)) for r, h, v in cells}
        certs |= {("TRANSFER", o[4], self.borrowed[o[4]][1]) for o in owords if len(o) > 4 and o[4] in self.borrowed}      # (op, source, order); a probe's fake reading has no word
        return value, cells, certs

    def label(self, v): return str(v)

    def owns(self, r): return r[2] in ("C", "F", "N", "O", "T")

    def consulted(self): return [(self.name, tuple(self.recs.tables))]

    def induce_lexicon(self, teaching):
        """the session's confirmation channel: re-induce this world's operator lexicon from all pairs (and the denials)."""
        self.pairs = list(teaching)                 # the session hands every pair each time; the world keeps the last set
        self.lexicon, contested, self.order = induce_lexicon(list(self.pairs), self.recs, negatives=self.negatives, df=self.df)
        for w in [w for w in self.borrowed if w in self.lexicon]: del self.borrowed[w]      # a binding of this world's own supersedes a borrowing
        self.contested = sorted(contested)
        return dict(bound=dict(self.lexicon), contested=self.contested, order=self.order)

    def contested_words(self):
        """the residue (core/goals.py), computed on demand: words the teaching leaves with several operators -- those
        `contested` by core.induce, and a word seen once whose survivor set is still several (a one-row filter)."""
        return sorted(set(self.contested) | {w for q, g in self.pairs for w in symbols(q) if w not in self.lexicon
                                              and not _isnum(w) and self._pure(w) and len(self.survivors_of(w)) > 1})

    def _pure(self, word):
        """a candidate operator word: every question it occurs in is one no bound word explains"""
        return all(not any(s in self.lexicon for s in symbols(q)) for q, g in self.pairs if word in symbols(q))

    # ---- the residue's probes (core/goals.py): other values of a filter's header, and an operator's value on a question
    def alternatives(self, sym):
        for h, vals in self.recs.values.items():
            if sym in vals: return sorted(v for v in vals if v != sym and " " not in v)
        return []

    def value_with(self, word, op, question):
        """the value the question takes with `word` read as `op` (the probe's outcome), or None."""
        syms = symbols(question); rd = [r for r in readings(syms, self.recs) if not (r[2] == "O" and r[4] == word)]
        rd += [(k, k + 1, "O", op, word) for k, s in enumerate(syms) if s == word]
        # the outcome is what the question's FULL reading computes: only the structures of greatest coverage count (a
        # structure ignoring the filter would make a one-row group look splittable by the whole table's aggregate)
        best = {}
        for st in structures(rd, self.recs, self.order):
            res = evaluate(self.recs, st)
            if res is None: continue
            cov = len({p for i, j in TableWorld.spans_of(self, st) for p in range(i, j)})
            best.setdefault(cov, set()).add(str(res[0]))
        return tuple(sorted(best[max(best)])) if best else None

    # ---- persistence (core/store.py): the pairs and the denials are the evidence; the lexicon is re-induced -----------
    def evidence(self):
        return dict(pairs=[[q, str(g)] for q, g in self.pairs], negatives=[[q, str(v)] for q, v in self.negatives])

    def absorb(self, ev):
        def num(s):
            try: return Fraction(str(s))
            except Exception: return s
        self.negatives = [(q, num(v)) for q, v in ev.get("negatives", [])]
        r = self.induce_lexicon([(q, num(g)) for q, g in ev.get("pairs", [])])
        return dict(bound=sorted(self.lexicon), contested=r["contested"])

    def survivors_of(self, word):
        """the operators still possible for `word` under every positive pair and denial so far (a diagnostic)."""
        return induce_lexicon(list(self.pairs), self.recs, negatives=self.negatives, word=word)


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


def induce_lexicon(teaching, table, ops=ALL_OPS, negatives=(), word=None, df=None):
    """(question, confirmed answer) pairs -> (word -> operator, contested, diff order): core.induce by elimination
    with this world's own probe (a fake operator reading past the end of the text, B1/B4). `negatives`: denials
    (question, forbidden value), see core.induce. `word`: return that word's surviving operator set instead."""
    def survivors(q, gold):
        syms = symbols(q); rd = readings(syms, table); surv, votes = set(), []
        for op in ops:
            fake = rd + [(len(syms), len(syms) + 1, "O", op, "")]
            for st in structures(fake, table):
                res = evaluate(table, st)
                if res is not None and _same(res[0], gold):
                    surv.add(op)
                    if st[0] == DIFF:
                        fa, fb = st[5][0], st[5][1]; votes.append("first" if fa[0] < fb[0] else "second")
        read_pos = {k for r in rd for k in range(r[0], r[1])}
        return [w for k, w in enumerate(syms) if k not in read_pos], surv, votes
    if word is not None:                     # (the unpacked names must not shadow `ops`, which the probe iterates)
        inter = None
        for q, gold in teaching:
            free, sv, _ = survivors(q, gold)
            if word in free: inter = set(sv) if inter is None else inter & set(sv)
        for q, bad in negatives:
            free, sv, _ = survivors(q, bad)
            if word in free and inter is not None: inter -= set(sv)
        return inter or set()
    return induce(teaching, survivors, negatives=negatives, df=df)


def _same(a, b):
    if isinstance(a, Fraction) or isinstance(b, Fraction):
        try: return Fraction(str(a)) == Fraction(str(b))
        except Exception: return False
    return str(a).lower() == str(b).lower()
