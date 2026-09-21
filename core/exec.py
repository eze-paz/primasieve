"""EXEC -- the executable WORLD for core.reason (general_prereg.md W3): numbers, operator WORDS bound by teaching,
and a LIBRARY of learned compositions that the search itself uses. Zero LLM. Holds no word of any language.

Readings: a numeric symbol is a NUMBER ("N"); a word in the induced lexicon is an OPERATOR ("O") whose payload is an
opaque id: a primitive of core.primitives or a library entry. Structures: expression trees over the read numbers
with at most two operator applications (both nesting orders; the data eliminates the wrong one). Evaluate: exact
rational arithmetic through core.primitives.apply; the certificate is the expression over opaque ids together with
the teaching examples that bound each operator word -- an answer is only ever as good as the examples that named
its operators, and it cites them.

Binding (WAKE). `induce_lexicon(teaching)`: a word is bound by ELIMINATION (core.induce) over every primitive and
library entry of a fitting shape; a word that no existing operator explains is bound by SEARCH: the smallest
expression tree over primitives and library entries (leaves: the argument and the structural constants 1, 2) that
reproduces every confirmed example, within an evaluation cap, with observational-equivalence pruning
(core.generate.SignatureBank). A found tree is crystallised into the library under an opaque id.
SLEEP. `sleep()`: the sub-tree recurring across the library's entries (core.generate.compress_recurring) becomes a
library entry of its own, so later searches reach deeper targets at the same cap: that is the emergence claim of
emergence/em_loop.py, now inside the loop every question goes through.
Retraction. A binding that fails a later confirmed example is dropped (and re-searched); nothing wrong is kept."""
import hashlib
from fractions import Fraction

from . import primitives as P
from .generate import SignatureBank, compress_recurring
from .induce import induce
from .reason import symbols as _symbols

X = "x"                    # the argument leaf of a unary tree
CONSTS = (1, 2)            # structural constants, not content (em_loop's consts)


def symbols(text): return _symbols(text, "LN")


def _isnum(x):
    try: Fraction(str(x)); return True
    except Exception: return False


class Library:
    """opaque id -> unary tree over primitive ids / library ids / leaves. Ids hash the tree, never a name."""

    def __init__(self): self.entries = {}; self.forced = {}

    def add(self, tree, forced_by):
        lid = "L#" + hashlib.sha1(repr(tree).encode()).hexdigest()[:8]
        if lid not in self.entries: self.entries[lid] = tree; self.forced[lid] = forced_by
        return lid

    def __len__(self): return len(self.entries)

    def __contains__(self, k): return k in self.entries


def arity(op, lib):
    if op in lib: return 1
    return len(P.signature(op)[0])


def ev(tree, x, lib, budget=None):
    """evaluate a unary tree at x -> Fraction or None (domain error / ill-typed)."""
    if tree == X: return x
    if isinstance(tree, int): return Fraction(tree)
    op = tree[0]
    args = [ev(t, x, lib) for t in tree[1:]]
    if any(a is None for a in args): return None
    return apply_op(op, args, lib)


def apply_op(op, args, lib):
    if op in lib:
        if len(args) != 1: return None
        return ev(lib.entries[op], args[0], lib)
    try:
        r = P.apply(op, *[Fraction(a) for a in args])
        return Fraction(r)
    except (P.IllTyped, ZeroDivisionError, ValueError, OverflowError):
        return None


def synth(examples, lib, max_size=9, cap=50000, use_library=True):
    """smallest unary tree reproducing every (x, y) example -> (tree, evaluations) or (None, evaluations).
    Bottom-up by size, observational equivalence on the example inputs (core.generate.SignatureBank)."""
    xs = [Fraction(str(a)) for a, _ in examples]; target = tuple(Fraction(str(b)) for _, b in examples)
    unary = [p for p in P.pids() if P.signature(p) == ((P.RAT,), P.RAT)] + (sorted(lib.entries) if use_library else [])
    binary = [p for p in P.pids() if P.signature(p) == ((P.RAT, P.RAT), P.RAT)]
    bank = SignatureBank(budget=cap * 4); by = bank.by_size; n = [0]

    def add(size, tree):
        n[0] += 1
        vals = tuple(ev(tree, x, lib) for x in xs)
        if any(v is None for v in vals): return None
        if not bank.add(tree, vals, size=size, payload=None): return None
        return tree if vals == target else None

    for leaf in (X,) + CONSTS:
        r = add(1, leaf)
        if r is not None: return r, n[0]
    for size in range(2, max_size + 1):
        for u in unary:
            for ctree, _, _ in list(by[size - 1]):
                if n[0] >= cap: return None, n[0]
                r = add(size, (u, ctree))
                if r is not None: return r, n[0]
        for ls in range(1, size - 1):
            rs = size - 1 - ls
            for ltree, _, _ in list(by[ls]):
                for rtree, _, _ in list(by[rs]):
                    for b in binary:
                        if n[0] >= cap: return None, n[0]
                        r = add(size, (b, ltree, rtree))
                        if r is not None: return r, n[0]
    return None, n[0]


def fragments(tree):
    """proper sub-trees of size >= 2 that contain the argument (the parts worth naming)."""
    out = []
    def walk(t, top):
        if t == X or isinstance(t, int): return False
        has = any(walk(c, False) for c in t[1:]) or any(c == X for c in t[1:])
        if has and not top: out.append(t)
        return has
    walk(tree, True)
    return out


class ExecWorld:
    content_kinds = {"O"}      # an operator word the answer did not use -> PARTIAL
    attributed = False

    def __init__(self, lexicon=None, library=None, teaching=None, name=None):
        self.lexicon = dict(lexicon or {}); self.lib = library or Library(); self.teach = dict(teaching or {})
        self.name = name or "exec"; self.log = []; self.pairs = []

    # ---- the world contract ------------------------------------------------------------------------------
    def readings(self, syms):
        out = []
        for i, s in enumerate(syms):
            if _isnum(s): out.append((i, i + 1, "N", Fraction(s), s))
            if s in self.lexicon: out.append((i, i + 1, "O", self.lexicon[s], s))
        self.log.append((self.name, " ".join(syms)))
        return out

    def structures(self, rd):
        """expression trees over the read numbers: one or two operator applications, the operator words in either
        nesting order (nothing here knows how a language nests), the NUMBER leaves in textual order (an argument
        order is a fact about the text; permuting it would manufacture readings the text does not carry). A
        CONTEXT number (a previous turn's value, marked by the loop) has no textual position: both orders."""
        nums = sorted((r for r in rd if r[2] == "N"), key=lambda r: r[0]); ops = [r for r in rd if r[2] == "O"]
        virt = lambda r: len(r) > 5
        def pairs():
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    yield nums[i], nums[j]
                    if virt(nums[i]) or virt(nums[j]): yield nums[j], nums[i]
        out = []
        for o in ops:
            k = arity(o[3], self.lib)
            if k == 1: out += [((o, a),) for a in nums]
            elif k == 2: out += [((o, a, b),) for a, b in pairs()]
        for o1 in ops:
            for o2 in ops:
                if o1 is o2: continue
                k1, k2 = arity(o1[3], self.lib), arity(o2[3], self.lib)
                if k2 == 1: inner = [(o2, a) for a in nums]
                elif k2 == 2: inner = [(o2, a, b) for a, b in pairs()]
                else: inner = []
                for inn in inner:
                    if k1 == 1: out.append(((o1, inn),)); continue
                    if k1 != 2: continue
                    used = [a for a in inn[1:]]; lo, hi = min(a[0] for a in used), max(a[0] for a in used)
                    for c in nums:
                        if c in used: continue
                        if c[0] > hi or virt(c): out.append(((o1, inn, c),))
                        if c[0] < lo or virt(c): out.append(((o1, c, inn),))
        return out

    def _tree(self, node):
        """structure node -> (tree over ids, spans)"""
        if not isinstance(node[0], tuple): return node[3], [(node[0], node[1])]        # a number reading
        op = node[0]; kids = [self._tree(k) for k in node[1:]]
        return (op[3],) + tuple(k[0] for k in kids), [(op[0], op[1])] + [s for k in kids for s in k[1]]

    def spans_of(self, st): return self._tree(st[0])[1]

    def key(self, st): return ("EXEC", repr(self._tree(st[0])[0]))

    def shape(self, st):
        """the tree with its numbers abstracted to explicit/context leaves (what a user's choice generalizes over)."""
        def ab(node):
            if not isinstance(node[0], tuple): return "ctx" if len(node) > 5 else "n"
            return (node[0][3],) + tuple(ab(k) for k in node[1:])
        return ("EXEC", ab(st[0]))

    def evaluate(self, st):
        tree, spans = self._tree(st[0])
        v = _ev_ground(tree, self.lib)
        if v is None: return None
        words = self._words(st[0]); certs = {("EXEC", repr(tree), str(v))}
        for w in words:
            for q, g in self.teach.get(w, []): certs.add(("TEACH", w, q, str(g)))
        return v, [(repr(tree), sorted(words))], certs

    def _words(self, node):
        if not isinstance(node[0], tuple): return []
        return [node[0][4]] + [w for k in node[1:] for w in self._words(k)]

    def label(self, v): return str(v)

    def owns(self, r): return r[2] in ("N", "O")

    def consulted(self):
        return [(self.name, "primitives", len(P.pids()), "library", len(self.lib), "lexicon", len(self.lexicon))] + list(self.log)

    # ---- binding: wake and sleep -----------------------------------------------------------------------------
    def induce_lexicon(self, teaching, cap=50000, max_size=9, use_library=True, say=lambda *a, **k: None):
        """(question, confirmed answer) pairs -> binds words by elimination over known operators, then by search
        for the words no known operator explains. -> dict(bound, contested, searched [(word, tree|None, evals)])."""
        for pr in teaching:
            if pr not in self.pairs: self.pairs.append(pr)
        teaching = list(self.pairs)                     # every confirmed pair so far: purity and retraction see all of them
        known = [p for p in P.pids() if P.signature(p) in (((P.RAT,), P.RAT), ((P.RAT, P.RAT), P.RAT))] + sorted(self.lib.entries)
        # retraction FIRST: a bound word must reproduce every confirmed example that contains it; a contradicted
        # binding is dropped here so that the elimination and the search below re-bind it from all the evidence
        dropped = []
        for w in list(self.lexicon):
            for q, g in teaching:
                if w not in symbols(q): continue
                syms = symbols(q); rd = self.readings(syms)
                ok = any(_same(self.evaluate(st)[0], g) for st in self.structures(rd) if self.evaluate(st) is not None)
                if not ok: dropped.append((w, q, g)); del self.lexicon[w]; break

        def survivors(q, gold):
            syms = symbols(q); rd = self.readings_plain(syms); surv = set()
            for op in known:
                fake = rd + [(len(syms), len(syms) + 1, "O", op, "")]
                for st in self.structures(fake):
                    t, _ = self._tree(st[0]); v = _ev_ground(t, self.lib)
                    if v is not None and _same(v, gold): surv.add(op)
            read = {k for r in rd for k in range(r[0], r[1])}
            return [w for k, w in enumerate(syms) if k not in read], surv, []

        lex, contested, _ = induce(teaching, survivors)
        for w, op in lex.items():
            self.lexicon[w] = op
            self.teach.setdefault(w, []).extend((q, g) for q, g in teaching if w in symbols(q))
        # words no known operator explains: SEARCH, in order of purity (a word occurring only in questions that
        # nothing explains yet comes first); a found binding explains its questions, so the fillers they share
        # with explained questions are never searched (the minimal-cover rule of core.induce, applied to search)
        searched = []; memo = {}
        def explained(q, g):
            syms = symbols(q); rd = self.readings(syms)
            return any(r is not None and _same(r[0], g) for r in (self.evaluate(st) for st in self.structures(rd)))
        while True:
            open_qs = [(q, g) for q, g in teaching if g is not None and not explained(q, g)]
            if not open_qs: break
            by_word = {}
            for q, g in open_qs:
                syms = symbols(q); nums = [s for s in syms if _isnum(s)]
                for w in set(syms):
                    if _isnum(w) or w in self.lexicon: continue
                    by_word.setdefault(w, []).append((q, nums, g))
            def purity(w):
                total = sum(1 for q, g in teaching if w in symbols(q))
                return len(by_word[w]) / max(total, 1), len(by_word[w])
            def functional(items):      # a name for an operator is a FUNCTION of its argument
                seen = {}
                for _, nums, g in items:
                    if seen.setdefault(nums[0], g) != g: return False
                return True
            cands = [w for w, items in by_word.items() if len(items) >= 2 and all(len(nums) == 1 for _, nums, _ in items)
                     and functional(items) and w not in {s for s, _, _ in searched}]
            if not cands: break
            w = max(cands, key=purity); items = by_word[w]
            ex = [(nums[0], g) for _, nums, g in items]
            key = (tuple(ex), use_library, len(self.lib))
            if key not in memo: memo[key] = synth(ex, self.lib, max_size=max_size, cap=cap, use_library=use_library)
            tree, n = memo[key]                      # words sharing the same examples share the same search
            searched.append((w, tree, n))
            if tree is None: continue
            lid = self.lib.add(tree, forced_by=(w, ex))
            self.lexicon[w] = lid; self.teach.setdefault(w, []).extend((q, g) for q, _, g in items)
        return dict(bound=dict(lex), contested=contested, searched=searched, dropped=dropped)

    def readings_plain(self, syms):
        return [(i, i + 1, "N", Fraction(s), s) for i, s in enumerate(syms) if _isnum(s)]

    def sleep(self, min_count=2):
        """crystallise the fragment recurring across library entries -> new library id or None."""
        top, n = compress_recurring(list(self.lib.entries.values()), fragments, min_count=min_count)
        if top is None: return None, n
        return self.lib.add(top, forced_by=("sleep", n)), n


def _ev_ground(tree, lib):
    """a ground tree (Fraction leaves) -> value or None."""
    if isinstance(tree, Fraction): return tree
    if isinstance(tree, int): return Fraction(tree)
    op = tree[0]; args = [_ev_ground(t, lib) for t in tree[1:]]
    if any(a is None for a in args): return None
    return apply_op(op, args, lib)


def _same(a, b):
    try: return Fraction(str(a)) == Fraction(str(b))
    except Exception: return str(a).lower() == str(b).lower()
