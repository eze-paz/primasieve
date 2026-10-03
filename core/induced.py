"""INDUCED -- the table's operators as searched TERMS over the primitives, not an authored inventory (induced_prereg.md;
EMERGENCE_PLAN.md S2). Zero LLM. Holds no word of any language and no operator.

The structural SKELETON is the table world's and is authored (filters select rows, a column is read, a second group or a
target column may take part): that is stated, not hidden. What this module removes is the CONTENT -- SUM, MEAN, MAX,
MIN, COUNT, DIFF, LOOKUP, ARGMAX as nine given functions. Here an operator word is bound by SEARCH to the smallest term
over core.primitives (plus the sum atom this prereg forced) that maps the selected column sequence A -- and, when the
readings afford them, the second group's sequence B or the target column T -- to the confirmed answer on every pair the
word occurs in. core.exec's enumeration shape: bottom-up by size, observational equivalence over the examples' inputs.
Rivals at the minimal size are kept as several bindings; the loop reports them as READINGS."""
from fractions import Fraction

from . import primitives as P
from .generate import SignatureBank
from .table import TableWorld, Records, select, symbols, _isnum, _same

LEAVES = ("A", "B", "T")
CONSTS = ()               # a table operator is a function of the data: no constant leaves (run 1 bound a one-example word to the constant 2)


def _ev(tree, env):
    if isinstance(tree, str): return env.get(tree)
    if isinstance(tree, int): return tree
    args = [_ev(k, env) for k in tree[1:]]
    if any(a is None for a in args): return None
    try: return P.apply(tree[0], *args)
    except (P.IllTyped, ZeroDivisionError, ValueError, OverflowError, TypeError, IndexError, KeyError): return None


def _size(t): return 1 if not isinstance(t, tuple) else 1 + sum(_size(k) for k in t[1:])


def ops(exclude=()):
    unary = [p for p in P.pids() if len(P.signature(p)[0]) == 1 and p not in exclude]
    binary = [p for p in P.pids() if len(P.signature(p)[0]) == 2 and p not in exclude]
    return unary, binary


def search(examples, max_size=7, cap=60000, exclude=()):
    """examples: [(env, gold)] -> the minimal-size terms (distinct on the examples) reproducing every gold; [] if none."""
    unary, binary = ops(exclude)
    bank = SignatureBank(budget=cap * 4); by = bank.by_size; n = 0; found = []
    leaves = [l for l in LEAVES if all(env.get(l) is not None for env, _ in examples)] + list(CONSTS)

    def add(size, tree):
        nonlocal n
        n += 1
        vals = tuple(_ev(tree, env) for env, _ in examples)
        if all(v is None for v in vals): return
        sig = tuple(repr(v) for v in vals)
        if not bank.add(tree, sig, size=size, payload=None): return
        if all(v is not None and _same(v, g) for v, (_, g) in zip(vals, examples)): found.append(tree)

    for leaf in leaves: add(1, leaf)
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
        if found: return found
    return found


class TermWorld(TableWorld):
    """the table world's readings and skeleton; the operators are searched terms."""

    def __init__(self, table, name=None, df=None, exclude=()):
        TableWorld.__init__(self, table, {}, None, name or "terms", df)
        self.terms = {}                 # word -> {shape key: [term, ...]} (several = rivals at the minimal size)
        self.default = {}               # shape key -> [term, ...]: the operator when NO operator word is read (induced too)
        self.exclude = tuple(exclude); self.searched = []

    # ---- readings: the table's, with operator words read from `terms` ---------------------------------------------
    def readings(self, syms):
        out = [r for r in TableWorld.readings(self, syms) if r[2] != "O"]
        for i, s in enumerate(syms):
            if s in self.terms: out.append((i, i + 1, "O", s, s))
        return out

    # ---- the skeleton (authored, stated): filters -> rows; a column -> A; a target column -> T; a second group -> B
    def _shapes(self, rd):
        recs = self.recs
        cols = [r for r in rd if r[2] == "C"]; fils = [r for r in rd if r[2] == "F"]
        named = {r[3] for r in rd if r[2] == "T"}                       # a collection named in the text: read that one
        def disjoint(rs):
            iv = sorted((r[0], r[1]) for r in rs)
            return all(iv[k][1] <= iv[k + 1][0] for k in range(len(iv) - 1))
        import itertools
        out = []
        fsets = [()] + [(f,) for f in fils] + [tuple(p) for k in (2, 3) for p in itertools.combinations(fils, k) if len({f[3][0] for f in p}) == k]
        for fs in fsets:
            if not disjoint(list(fs)): continue
            filters = [f[3] for f in fs]
            tables = recs.holding([h for h, _ in filters]) if filters else list(recs.tables.values())
            if named: tables = [t for t in tables if t.name in named] or tables
            for A_t in tables:
                rows = select(A_t, filters)
                if not rows: continue
                out.append((A_t, rows, None, None, fs, None, None))                           # no column: A = the keys
                for c in cols:
                    if c[3] not in A_t.headers or not disjoint(list(fs) + [c]): continue
                    if not any(h == c[3] for h, _ in filters): out.append((A_t, rows, c, None, fs, None, None))
                    for tg in cols:
                        if tg is not c and tg[3] in A_t.headers and tg[3] not in A_t.numeric and c[3] in A_t.numeric and disjoint(list(fs) + [c, tg]):
                            out.append((A_t, rows, c, tg, fs, None, None))
                # a second group: two filters on one header
                for fa, fb in itertools.permutations(fils, 2):
                    if fa[3][0] == fb[3][0] and fa[3][0] in A_t.headers and fa[0] < fb[0]:
                        for c in cols:
                            if c[3] in A_t.headers and c[3] in A_t.numeric and disjoint([fa, fb, c]):
                                out.append((A_t, select(A_t, [fa[3]]), c, None, (fa,), fb, select(A_t, [fb[3]])))
        return out

    @staticmethod
    def _seq(table, rows, col):
        c = table.col(col) if col is not None else 0
        vals = tuple(table.rows[r][c] for r in rows)
        return tuple(int(v) if isinstance(v, (int, Fraction)) and Fraction(v).denominator == 1 else (str(v) if not isinstance(v, (int, Fraction)) else v) for v in vals)

    def _env(self, shape):
        A_t, rows, c, tg, fs, fb, rows_b = shape
        env = {"A": self._seq(A_t, rows, c[3] if c else None)}
        if tg is not None: env["T"] = self._seq(A_t, rows, tg[3])
        if fb is not None: env["B"] = self._seq(A_t, rows_b, c[3])
        return env

    @staticmethod
    def shape_key(env): return tuple(sorted(k for k in env if env.get(k) is not None))

    def structures(self, rd):
        """one structure per operator word, shape and term of that word for the shape's key (several terms = rivals)"""
        ows = [r for r in rd if r[2] == "O"]
        out = []
        for shape in self._shapes(rd):
            spans = [(r[0], r[1]) for r in shape[4] + tuple(x for x in (shape[2], shape[3], shape[5]) if x is not None)]
            sk = self.shape_key(self._env(shape))
            for o in ows:
                if any(a < o[1] and o[0] < b for a, b in spans): continue
                for k in range(len(self.terms.get(o[3], {}).get(sk, []))): out.append(("TERM", o, shape, k))
            if not ows:                                                  # no operator word: the induced default
                for k in range(len(self.default.get(sk, []))): out.append(("TERM", None, shape, k))
        return out

    def spans_of(self, st):
        o, shape = st[1], st[2]
        return ([(o[0], o[1])] if o else []) + [(r[0], r[1]) for r in shape[4] + tuple(x for x in (shape[2], shape[3], shape[5]) if x is not None)]

    def key(self, st):
        o, shape = st[1], st[2]
        return ("TERM", o[3] if o else None, st[3], tuple(f[3] for f in shape[4]), shape[2][3] if shape[2] else None, shape[3][3] if shape[3] else None, shape[5][3] if shape[5] else None, shape[0].name)

    def shape(self, st): return ("TERM", st[1][3] if st[1] else None)

    def rank_key(self, st): return 0

    def conjectured(self, st):
        """conjectured_prereg.md: a term that has not predicted an example it was not fitted to"""
        o, shape = st[1], st[2]; word = o[3] if o else None
        return (word, self.shape_key(self._env(shape))) not in self.predicted

    def evaluate(self, st):
        o, shape, k = st[1], st[2], st[3]; word = o[3] if o else None
        env = self._env(shape); term = (self.terms[word][self.shape_key(env)] if word else self.default[self.shape_key(env)])[k]
        v = _ev(term, env)
        if v is None: return None
        A_t, rows, c, tg, fs, fb, rows_b = shape
        cells = [(r, (c[3] if c else A_t.headers[0]), A_t.rows[r][A_t.col(c[3]) if c else 0]) for r in rows]
        return (Fraction(v) if isinstance(v, (int, Fraction)) and not isinstance(v, bool) else v), cells, {("TERM", word or "", repr(term))} | {("TABLE", A_t.name, r, h, str(x)) for r, h, x in cells}

    # ---- induction: a word's term from the pairs it occurs in --------------------------------------------------------
    def induce_lexicon(self, teaching, max_size=7):
        self.pairs = list(teaching); self.terms = {}; self.default = {}; self.searched = []; self.predicted = set()

        def mark(word, sk, exs, found):
            """COMMIT only if the fit on all examples but the newest reproduces the newest (conjectured_prereg.md)"""
            if len(exs) < 2: return
            prior = search([(env, g) for env, g, q in exs[:-1]], max_size=max_size, exclude=self.exclude)
            env, g, q = exs[-1]
            if prior and all(_same(_ev(t, env), g) for t in prior if _ev(t, env) is not None) and any(_ev(t, env) is not None for t in prior):
                self.predicted.add((word, sk))
        explained = set()
        for _ in range(12):
            open_qs = [(q, g) for q, g in self.pairs if g is not None and q not in explained]
            if not open_qs: break
            by_word = {}
            for q, g in open_qs:
                syms = symbols(q); rd = [r for r in TableWorld.readings(self, syms) if r[2] != "O"]
                read = {p for r in rd for p in range(r[0], r[1])}
                shapes = self._shapes(rd)
                if not shapes: continue
                best = max(shapes, key=lambda s: len(s[4]) + (s[2] is not None) + (s[3] is not None) + (s[5] is not None))
                for k, w in enumerate(syms):
                    if k in read or _isnum(w) or w in self.terms: continue
                    by_word.setdefault(w, []).append((q, g, best))
            def purity(w): return len(by_word[w]) / max(sum(1 for q, g in self.pairs if w in symbols(q)), 1)
            cands = sorted(by_word, key=lambda w: (-purity(w), -len(by_word[w]), w))
            if not cands: break
            bound = False
            if not any(purity(w) == 1.0 for w in cands):
                # every remaining word also occurs in explained questions: these questions carry NO operator word, and
                # their operator is the DEFAULT -- searched from their shapes like any word's (run 2 bound a filler to min here)
                groups = {}
                for q, g in open_qs:
                    syms = symbols(q); rd = [r for r in TableWorld.readings(self, syms) if r[2] != "O"]
                    shapes = self._shapes(rd)
                    if not shapes: continue
                    best = max(shapes, key=lambda s: len(s[4]) + (s[2] is not None) + (s[3] is not None) + (s[5] is not None))
                    env = self._env(best); groups.setdefault(self.shape_key(env), []).append((env, g, q))
                for sk, exs in groups.items():
                    found = search([(env, g) for env, g, q in exs], max_size=max_size, exclude=self.exclude)
                    self.searched.append(("", sk, len(found), len(exs)))
                    if found:
                        self.default[sk] = found; bound = True; mark(None, sk, exs, found)
                        for env, g, q in exs: explained.add(q)
                if not bound: break
                continue
            for w in cands:
                if purity(w) < 1.0: continue
                groups = {}
                for q, g, shape in by_word[w]:
                    env = self._env(shape); groups.setdefault(self.shape_key(env), []).append((env, g, q))
                per = {}
                for sk, exs in groups.items():
                    found = search([(env, g) for env, g, q in exs], max_size=max_size, exclude=self.exclude)
                    self.searched.append((w, sk, len(found), len(exs)))
                    if found: per[sk] = found
                if per and len(per) == len(groups):           # every shape the word occurs in has a term: the word is explained
                    self.terms[w] = per; bound = True
                    for sk, exs in groups.items(): mark(w, sk, exs, per[sk])
                    for q, g, shape in by_word[w]: explained.add(q)
                    break
            if not bound: break
        return dict(bound={w: t for w, t in self.terms.items()}, default=dict(self.default), contested=[], order=None, searched=self.searched)

    def consulted(self): return [(self.name, tuple(self.recs.tables), "terms", len(self.terms))]
