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


def synth(examples, lib, max_size=9, cap=50000, use_library=True, guided=False, score="lookahead", forbidden=()):
    """smallest unary tree reproducing every (x, y) example -> (tree, evaluations) or (None, evaluations).
    Bottom-up by size, observational equivalence on the example inputs (core.generate.SignatureBank).
    guided: True = core.guide.best_first from the leaves; an int = BLIND through that size, then best-first seeded with
    the blind bank (graded_prereg.md S1b/S1c). score: "lookahead" (charged per candidate) or "match" (free). With
    guided the second number is primitive APPLICATIONS (the score's cost included) and the cap bounds those. The
    verdict is the same exact reproduction either way; only the order of enumeration differs."""
    xs = [Fraction(str(a)) for a, _ in examples]; target = tuple(Fraction(str(b)) for _, b in examples)
    unary = [p for p in P.pids() if P.signature(p) == ((P.RAT,), P.RAT)] + (sorted(lib.entries) if use_library else [])
    binary = [p for p in P.pids() if P.signature(p) == ((P.RAT, P.RAT), P.RAT)]
    # negative evidence (negative_prereg.md): a tree that yields a forbidden (x, y) is refused at the door and the
    # search goes on. A denial removes; it never admits. The forbidden inputs are PROBED like the examples, so that
    # two trees equal on the examples but different on a denied input stay two hypotheses (the first run of
    # negative.py lost x*x+1 as an observational duplicate of 2x+1 on {0, 2} and found nothing after the denial).
    bad = [(Fraction(str(a)), Fraction(str(b))) for a, b in forbidden]
    m = len(xs); probe = xs + [a for a, _ in bad]; bads = tuple(b for _, b in bad)
    def hit(vals): return vals[:m] == target and all(v != b for v, b in zip(vals[m:], bads))
    allowed = (lambda t: not any(ev(t, a, lib) == b for a, b in bad)) if bad else (lambda t: True)

    def blind(msize, ncap):
        bank = SignatureBank(budget=ncap * 4); by = bank.by_size; n = [0]

        def add(size, tree):
            n[0] += 1
            vals = tuple(ev(tree, x, lib) for x in probe)
            if any(v is None for v in vals[:m]): return None
            if not bank.add(tree, vals, size=size, payload=None): return None
            return tree if hit(vals) else None

        for leaf in (X,) + CONSTS:
            r = add(1, leaf)
            if r is not None: return r, n[0], bank
        for size in range(2, msize + 1):
            for u in unary:
                for ctree, _, _ in list(by[size - 1]):
                    if n[0] >= ncap: return None, n[0], bank
                    r = add(size, (u, ctree))
                    if r is not None: return r, n[0], bank
            for ls in range(1, size - 1):
                rs = size - 1 - ls
                for ltree, _, _ in list(by[ls]):
                    for rtree, _, _ in list(by[rs]):
                        for b in binary:
                            if n[0] >= ncap: return None, n[0], bank
                            r = add(size, (b, ltree, rtree))
                            if r is not None: return r, n[0], bank
        return None, n[0], bank

    if not guided:
        tree, n, _ = blind(max_size, cap)
        return tree, n
    from .guide import best_first, match_count
    spent = 0; seeds = None; min_size = 1
    if guided is not True:              # an int: the cheap layers blind, their bank seeding the queue, deeper sizes guided
        tree, nev, bank = blind(min(max_size, int(guided)), max(cap // len(xs), 1))
        spent = nev * len(xs)
        if tree is not None or spent >= cap: return tree, spent
        seeds = [(t, list(sig)) for t, sig in bank.order]; min_size = int(guided) + 1
    leaves = [(X, [x for x in probe])] + [(c, [Fraction(c)] * len(probe)) for c in CONSTS]
    sc = (lambda v: match_count(v[:m], target)) if score == "match" else None
    tree, apps = best_first(probe, target, leaves, unary, binary, list(CONSTS), lambda op, *a: apply_op(op, list(a), lib),
                            cap=cap - spent, max_size=max_size, score=sc, seeds=seeds, min_size=min_size, accept=allowed if bad else None)
    apps += spent
    if tree is not None and (tuple(ev(tree, x, lib) for x in xs) != target or not allowed(tree)): return None, apps      # the door
    return tree, apps


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
    content_kinds = {"O", "X"}      # an operator word the answer did not use -> PARTIAL; "X" = a refused word, never usable, always owed
    attributed = False
    PROBE_BOTH = True          # the elimination probe tries both argument orders (order_prereg.md); False = textual only

    def __init__(self, lexicon=None, library=None, teaching=None, name=None, df=None):
        self.lexicon = dict(lexicon or {}); self.lib = library or Library(); self.teach = dict(teaching or {})
        self.df = df                       # optional: a symbol's definition frequency (the loop's specificity bias), to break a co-occurrence tie
        self.name = name or "exec"; self.log = []; self.pairs = []; self.negatives = []
        # order as induced evidence (order_prereg.md, S5): per binary word, which argument order the confirmed pairs
        # support ('forward' = textual, 'reverse', 'both'); per world, which nesting of two operator words
        # ('first-outer' | 'first-inner' | 'mixed' | None). Re-induced from the pairs at every induce_lexicon.
        self.arg_order = {}; self.nesting = None; self._probe_both = False
        # transfer (transfer_prereg.md, S4): words borrowed from another world by behaviour, read but held CONJECTURED;
        # a denial refuses the word for good, a confirmed pair supersedes the borrowing with a binding of this world's own
        self.borrowed = {}; self.refused = set()
        self.searched_words = set()        # words whose binding came from SEARCH (kept across inductions; elimination's are recomputed)
        self.unconfirmed = set()           # search-bound words whose tree has not predicted an unfitted example (conjectured_prereg.md)

    # ---- transfer: the behaviour of an operator, and borrowing by it (core/transfer.py) ------------------------------
    def operators(self):
        return [p for p in P.pids() if P.signature(p) in (((P.RAT,), P.RAT), ((P.RAT, P.RAT), P.RAT))] + sorted(self.lib.entries)

    def fingerprint(self, op):
        grid = P.PROBES[P.RAT]; k = arity(op, self.lib)
        if k == 1: return (1,) + tuple(str(apply_op(op, [Fraction(a)], self.lib)) for a in grid)
        return (2,) + tuple(str(apply_op(op, [Fraction(a), Fraction(b)], self.lib)) for a in grid for b in grid)

    def borrow(self, word, op, source, order=None):
        if word in self.lexicon or word in self.refused or word in self.borrowed: return False
        self.borrowed[word] = (op, source)
        if order in ("forward", "reverse", "both"): self.arg_order[word] = order
        return True

    def conjectured(self, st):
        """a borrowed word, or a search-bound word that has not yet predicted an example it was not fitted to"""
        return any(w in self.borrowed or w in self.unconfirmed for w in self._words(st[0]))

    # ---- the residue's probes (core/goals.py): the numerals 1..10, and an operator's value on a question
    def alternatives(self, sym): return [str(k) for k in range(1, 11) if str(k) != sym] if _isnum(sym) else []

    def survivors_of(self, word):
        known = [p for p in P.pids() if P.signature(p) in (((P.RAT,), P.RAT), ((P.RAT, P.RAT), P.RAT))] + sorted(self.lib.entries)
        inter = None
        for q, g in self.pairs:
            if word not in symbols(q): continue
            surv = {op for op in known if self.value_with(word, op, q) is not None and any(_same(v, g) for v in self.value_with(word, op, q))}
            inter = surv if inter is None else inter & surv
        for q, bad in self.negatives:
            if word in symbols(q) and inter is not None:
                inter -= {op for op in known if self.value_with(word, op, q) is not None and any(_same(v, bad) for v in self.value_with(word, op, q))}
        return inter or set()

    def value_with(self, word, op, question):
        syms = symbols(question); rd = [r for r in self.readings(syms) if not (r[2] == "O" and r[4] == word)]
        rd += [(k, k + 1, "O", op, word) for k, s in enumerate(syms) if s == word]
        best = {}
        for st in self.structures(rd):
            t, spans = self._tree(st[0]); v = _ev_ground(t, self.lib)
            if v is not None: best.setdefault(len({p for i, j in spans for p in range(i, j)}), set()).add(str(v))
        return tuple(sorted(best[max(best)])) if best else None          # the structures of greatest coverage only

    def deny(self, question, value):
        """negative evidence (negative_prereg.md): the engine's own answer to `question` was wrong. Applied at the next
        induction: a binding producing it is dropped, elimination subtracts the operators producing it, and the search
        for the word refuses any tree that yields it. A BORROWED word that produced the value is refused for good."""
        if (question, value) not in self.negatives: self.negatives.append((question, value))
        syms = symbols(question)
        for w in [w for w in self.borrowed if w in syms]:
            rd = self.readings(syms)
            if any(_same(r[0], value) for r in (self.evaluate(st) for st in self.structures(rd)) if r is not None):
                del self.borrowed[w]; self.refused.add(w)

    # ---- the world contract ------------------------------------------------------------------------------
    def readings(self, syms):
        out = []
        for i, s in enumerate(syms):
            if _isnum(s): out.append((i, i + 1, "N", Fraction(s), s))
            if s in self.lexicon: out.append((i, i + 1, "O", self.lexicon[s], s))
            elif s in self.borrowed: out.append((i, i + 1, "O", self.borrowed[s][0], s))
            elif s in self.refused: out.append((i, i + 1, "X", None, s))     # an operator word whose reading the user denied: still a predicate, unresolved
        self.log.append((self.name, " ".join(syms)))
        return out

    def structures(self, rd):
        """expression trees over the read numbers: one or two operator applications, the operator words in either
        nesting order (nothing here knows how a language nests), the NUMBER leaves in textual order (an argument
        order is a fact about the text; permuting it would manufacture readings the text does not carry). A
        CONTEXT number (a previous turn's value, marked by the loop) has no textual position. With ONE explicit operand
        it takes the operator's other side ("minus 4" after 34 -> 34 minus 4; "5 minus it" -> 5 minus it): the side
        is read off the text, not off a word. Two context numbers under one operator keep both orders (nothing in the
        text orders them). Measured before this rule: "minus 4" gave READINGS {-30, 30}, an ask where the text was
        not ambiguous (turns prereg, T-b)."""
        nums = sorted((r for r in rd if r[2] == "N"), key=lambda r: r[0]); ops = [r for r in rd if r[2] == "O"]
        virt = lambda r: len(r) > 5
        def pairs(o):
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    a, b = nums[i], nums[j]                           # a precedes b; context numbers sit past the text
                    if virt(a) and virt(b): yield a, b; yield b, a
                    elif virt(b): yield (a, b) if a[0] < o[0] else (b, a)
                    else:
                        # the word's INDUCED argument order (order_prereg.md): textual unless its confirmed pairs say
                        # reverse; a word with mixed evidence yields both (the loop reports READINGS); the elimination
                        # probe tries both so that a reverse word can be bound at all
                        ordw = "both" if self._probe_both else self.arg_order.get(o[4], "forward")
                        if ordw != "reverse": yield a, b
                        if ordw != "forward": yield b, a
        out = []
        for o in ops:
            k = arity(o[3], self.lib)
            if k == 1: out += [((o, a),) for a in nums]
            elif k == 2: out += [((o, a, b),) for a, b in pairs(o)]
        for o1 in ops:
            for o2 in ops:
                if o1 is o2: continue
                k1, k2 = arity(o1[3], self.lib), arity(o2[3], self.lib)
                if k2 == 1: inner = [(o2, a) for a in nums]
                elif k2 == 2: inner = [(o2, a, b) for a, b in pairs(o2)]
                else: inner = []
                for inn in inner:
                    if k1 == 1: out.append(((o1, inn),)); continue
                    if k1 != 2: continue
                    used = [a for a in inn[1:]]; lo, hi = min(a[0] for a in used), max(a[0] for a in used)
                    for c in nums:
                        if c in used: continue
                        if c[0] > hi or virt(c): out.append(((o1, inn, c),))
                        if c[0] < lo or virt(c): out.append(((o1, c, inn),))
        # a tree built from context alone reads nothing of the text: with three turns of numbers and operator words in
        # context, such trees were most of the thousands evaluated per turn (turns prereg, runtime)
        def explicit(node):
            if not isinstance(node[0], tuple): return not virt(node)
            return not virt(node[0]) or any(explicit(k) for k in node[1:])
        return [st for st in out if explicit(st[0])]

    def _tree(self, node):
        """structure node -> (tree over ids, spans)"""
        if not isinstance(node[0], tuple): return node[3], [(node[0], node[1])]        # a number reading
        op = node[0]; kids = [self._tree(k) for k in node[1:]]
        return (op[3],) + tuple(k[0] for k in kids), [(op[0], op[1])] + [s for k in kids for s in k[1]]

    def spans_of(self, st): return self._tree(st[0])[1]

    def key(self, st): return ("EXEC", repr(self._tree(st[0])[0]))

    def rank_key(self, st):
        """the induced NESTING preference (order_prereg.md): 1 when a two-operator tree nests the way the confirmed pairs
        did (the operator word that comes first in the text outermost, or innermost), else 0. A rank key, never a filter:
        the other nesting stays a survivor, and with no preference (or a mixed one) every tree ranks 0."""
        node = st[0]
        if self.nesting not in ("first-outer", "first-inner") or not isinstance(node[0], tuple): return 0
        inner = [k for k in node[1:] if isinstance(k[0], tuple)]
        if not inner: return 0
        outer_first = node[0][0] < inner[0][0][0]
        return 1 if (outer_first == (self.nesting == "first-outer")) else 0

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
            if w in self.borrowed: certs.add(("TRANSFER", w, self.borrowed[w][1]))
        return v, [(repr(tree), sorted(words))], certs

    def _words(self, node):
        if not isinstance(node[0], tuple): return []
        return [node[0][4]] + [w for k in node[1:] for w in self._words(k)]

    def label(self, v): return str(v)

    def owns(self, r): return r[2] in ("N", "O")

    def consulted(self):
        return [(self.name, "primitives", len(P.pids()), "library", len(self.lib), "lexicon", len(self.lexicon))] + list(self.log)

    # ---- binding: wake and sleep -----------------------------------------------------------------------------
    def induce_lexicon(self, teaching, cap=50000, max_size=9, use_library=True, say=lambda *a, **k: None, guided=False, score="lookahead"):
        """(question, confirmed answer) pairs -> binds words by elimination over known operators, then by search
        for the words no known operator explains. -> dict(bound, contested, searched [(word, tree|None, evals)])."""
        for pr in teaching:
            if pr not in self.pairs: self.pairs.append(pr)
        teaching = list(self.pairs)                     # every confirmed pair so far: purity and retraction see all of them
        known = [p for p in P.pids() if P.signature(p) in (((P.RAT,), P.RAT), ((P.RAT, P.RAT), P.RAT))] + sorted(self.lib.entries)
        # ELIMINATION IS TOTAL over all the pairs, so its bindings are recomputed from scratch every time; only a word
        # bound by SEARCH carries over (subject to the retraction below). Before this (transfer_prereg.md, run 1), a
        # session teaching one pair at a time kept the binding the FIRST pair alone forced (a question word bound to
        # multiplication by the first product question), because a stale binding is dropped only when a pair contradicts it and some other
        # structure always reproduced the gold.
        previous = dict(self.lexicon); prior = dict(self.lexicon)
        for w in [w for w in self.lexicon if w not in self.searched_words]: del self.lexicon[w]
        # retraction FIRST: a bound word must reproduce every confirmed example that contains it; a contradicted
        # binding is dropped here so that the elimination and the search below re-bind it from all the evidence
        dropped = []
        for w in list(self.lexicon):
            for q, g in teaching:
                if w not in symbols(q): continue
                syms = symbols(q); rd = self.readings(syms)
                ok = any(_same(self.evaluate(st)[0], g) for st in self.structures(rd) if self.evaluate(st) is not None)
                if not ok: dropped.append((w, q, g)); del self.lexicon[w]; self.searched_words.discard(w); self.unconfirmed.discard(w); break
            if w not in self.lexicon: continue
            for q, bad in self.negatives:               # a binding that yields a DENIED value on its question is dropped too
                if w not in symbols(q): continue
                syms = symbols(q); rd = self.readings(syms)
                hit = any(_same(self.evaluate(st)[0], bad) for st in self.structures(rd) if self.evaluate(st) is not None)
                if hit: dropped.append((w, q, ("not", bad))); del self.lexicon[w]; self.searched_words.discard(w); break

        def survivors(q, gold):
            syms = symbols(q); rd = self.readings_plain(syms); surv = set()
            self._probe_both = self.PROBE_BOTH           # both argument orders: the data, not the text, decides the word's order
            try:
                for op in known:
                    fake = rd + [(len(syms), len(syms) + 1, "O", op, "")]
                    for st in self.structures(fake):
                        t, _ = self._tree(st[0]); v = _ev_ground(t, self.lib)
                        if v is not None and _same(v, gold): surv.add(op)
            finally: self._probe_both = False
            read = {k for r in rd for k in range(r[0], r[1])}
            return [w for k, w in enumerate(syms) if k not in read], surv, []

        lex, contested, _ = induce(teaching, survivors, negatives=self.negatives, df=self.df, prior=prior)
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
            # SIMPLEST QUESTIONS FIRST (order_prereg.md, run 1): a question's weight is its number of unexplained symbols --
            # not a number, not bound, not seen in any explained question. Examples for a word are taken only from the
            # lightest open stratum that yields a candidate: a nested pair (one operator word applied to another's result) must
            # not enter twiddle's or double's examples, where it made both words non-functional and bound neither.
            fillers = {s for q, g in teaching if g is not None and explained(q, g) for s in symbols(q) if not _isnum(s)}
            def weight(q): return sum(1 for s in set(symbols(q)) if not _isnum(s) and s not in self.lexicon and s not in fillers)
            strata = sorted({weight(q) for q, g in open_qs})
            by_word = {}
            for level in strata:
                by_word = {}
                for q, g in open_qs:
                    if weight(q) != level: continue
                    syms = symbols(q); nums = [s for s in syms if _isnum(s)]
                    if any(s in self.lexicon for s in set(syms) if not _isnum(s)): continue      # a question with a BOUND operator word is not a plain example of another
                    for w in set(syms):
                        if _isnum(w) or w in self.lexicon: continue
                        by_word.setdefault(w, []).append((q, nums, g))
                def _functional(items):
                    seen = {}
                    for _, nums, g in items:
                        if len(nums) != 1 or seen.setdefault(nums[0], g) != g: return False
                    return True
                if any(len(items) >= 2 and _functional(items) and w not in {s for s, _, _ in searched} for w, items in by_word.items()): break
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
            w = max(cands, key=purity)
            # WORDS THAT ALWAYS CO-OCCUR cannot be told apart by the pairs (an article, a preposition and the operator word
            # over three questions of one shape): binding one of them is a guess. The declared tie-break is the loop's specificity bias
            # (the rarest by definition frequency, when a df is given); without one the tie is held CONTESTED and
            # nothing is bound until a differently shaped question separates them (transfer_prereg.md, run 2).
            tied = [t for t in cands if purity(t) == purity(w) and [q for q, _, _ in by_word[t]] == [q for q, _, _ in by_word[w]]]
            if len(tied) > 1:
                # the declared tie-break: rarest by definition frequency when a df is given; else first in the teaching text
                # (deterministic -- before this the iteration order of a set decided, which differs between processes)
                def first_pos(t): return min(symbols(q).index(t) for q, _, _ in by_word[t])
                w = min(tied, key=lambda t: ((self.df(t) if self.df is not None else 0), first_pos(t), t))
            items = by_word[w]
            ex = [(nums[0], g) for _, nums, g in items]
            forbid = [(nn[0], bad) for q, bad in self.negatives if w in symbols(q) for nn in [[s for s in symbols(q) if _isnum(s)]] if len(nn) == 1]
            key = (tuple(ex), tuple(forbid), use_library, len(self.lib), guided, score)
            if key not in memo: memo[key] = synth(ex, self.lib, max_size=max_size, cap=cap, use_library=use_library, guided=guided, score=score, forbidden=forbid)
            tree, n = memo[key]                      # words sharing the same examples share the same search
            searched.append((w, tree, n))
            if tree is None: continue
            lid = self.lib.add(tree, forced_by=(w, ex))
            self.lexicon[w] = lid; self.searched_words.add(w); self.teach.setdefault(w, []).extend((q, g) for q, _, g in items)
            # CONJECTURED until it has PREDICTED (conjectured_prereg.md): the fit on all examples but the newest must
            # reproduce the newest, or the binding is a guess and the loop says so
            predicted = False
            if len(ex) >= 2:
                k2 = (tuple(ex[:-1]), tuple(forbid), use_library, len(self.lib), guided, score)
                if k2 not in memo: memo[k2] = synth(ex[:-1], self.lib, max_size=max_size, cap=cap, use_library=use_library, guided=guided, score=score, forbidden=forbid)
                t2 = memo[k2][0]
                predicted = t2 is not None and _same(ev(t2, Fraction(str(ex[-1][0])), self.lib), ex[-1][1])
            if predicted: self.unconfirmed.discard(w)
            else: self.unconfirmed.add(w)
        self._induce_order(teaching)
        for w in [w for w in self.borrowed if w in self.lexicon]: del self.borrowed[w]       # a binding of this world's own supersedes a borrowing
        # an elimination-bound word that the recompute no longer binds the same way was retracted by the new evidence too
        for w, op in previous.items():
            if self.lexicon.get(w) != op and not any(d[0] == w for d in dropped): dropped.append((w, None, ("re-eliminated", op)))
        self.contested = sorted(set(contested))                     # the residue (core/goals.py)
        return dict(bound=dict(lex), contested=contested, searched=searched, dropped=dropped, arg_order=dict(self.arg_order), nesting=self.nesting)

    def _induce_order(self, teaching):
        """order as evidence (order_prereg.md): per bound binary word, the argument order its confirmed pairs support;
        per world, the nesting its two-operator pairs support. Unanimous -> that order; contradicted -> both/mixed;
        no evidence -> textual / None."""
        votes = {}; nest = set()
        for q, g in teaching:
            if g is None: continue
            syms = symbols(q); nums = [Fraction(s) for s in syms if _isnum(s)]
            ops = [(k, s) for k, s in enumerate(syms) if s in self.lexicon and not _isnum(s)]
            if len(ops) == 1 and len(nums) == 2 and arity(self.lexicon[ops[0][1]], self.lib) == 2:
                op = self.lexicon[ops[0][1]]; a, b = nums
                f = apply_op(op, [a, b], self.lib); r = apply_op(op, [b, a], self.lib)
                fo = f is not None and _same(f, g); ro = r is not None and _same(r, g)
                if fo != ro: votes.setdefault(ops[0][1], set()).add("forward" if fo else "reverse")
            if len(ops) == 2 and len(nums) == 1:
                (k1, w1), (k2, w2) = ops; o1, o2 = self.lexicon[w1], self.lexicon[w2]
                if arity(o1, self.lib) == 1 and arity(o2, self.lib) == 1:
                    x = nums[0]
                    v_first_outer = apply_op(o1, [apply_op(o2, [x], self.lib)], self.lib) if apply_op(o2, [x], self.lib) is not None else None
                    v_first_inner = apply_op(o2, [apply_op(o1, [x], self.lib)], self.lib) if apply_op(o1, [x], self.lib) is not None else None
                    fo = v_first_outer is not None and _same(v_first_outer, g); fi = v_first_inner is not None and _same(v_first_inner, g)
                    if fo != fi: nest.add("first-outer" if fo else "first-inner")
        self.arg_order = {w: (next(iter(v)) if len(v) == 1 else "both") for w, v in votes.items()}
        self.nesting = None if not nest else (next(iter(nest)) if len(nest) == 1 else "mixed")

    def readings_plain(self, syms):
        return [(i, i + 1, "N", Fraction(s), s) for i, s in enumerate(syms) if _isnum(s)]

    # ---- persistence: evidence out, evidence in (core/store.py, persist_prereg.md) --------------------------------
    def evidence(self):
        """pairs, denials, and the library as a cache: each tree with the record that forced it."""
        return dict(pairs=[[q, str(g)] for q, g in self.pairs], negatives=[[q, str(v)] for q, v in self.negatives], refused=sorted(self.refused),
                    library=[[lid, _json_tree(self.lib.entries[lid]), _json_forced(self.lib.forced.get(lid))] for lid in sorted(self.lib.entries)])

    def absorb(self, ev):
        """re-add each cached tree only if it still reproduces the examples that forced it; re-induce every binding from
        the pairs and denials; then consolidate. -> report."""
        self.pairs = [(q, _num(g)) for q, g in ev.get("pairs", [])]
        self.negatives = [(q, _num(v)) for q, v in ev.get("negatives", [])]
        self.refused = set(ev.get("refused", []))          # a denied borrowing stays denied across sessions
        for w in [w for w in self.borrowed if w in self.refused]: del self.borrowed[w]
        self.lib = Library(); self.lexicon = {}; self.teach = {}; self.searched_words = set(); self.unconfirmed = set()
        pending = [(lid, _tuple_tree(t), _tuple_forced(f)) for lid, t, f in ev.get("library", [])]
        kept, dropped = [], []
        while pending:
            progress = False
            for item in list(pending):
                lid, tree, forced = item
                if not all(r in self.lib for r in _refs(tree)): continue
                pending.remove(item); progress = True
                ok = True
                if forced and forced[0] != "sleep":
                    try: ok = all(ev_(tree, a, self.lib) == b for a, b in forced[1])
                    except Exception: ok = False
                if ok: kept.append(self.lib.add(tree, forced))
                else: dropped.append((lid, tree))
            if not progress: break
        dropped += [(lid, t) for lid, t, f in pending]                   # a tree whose part was dropped goes with it
        r = self.induce_lexicon(list(self.pairs))
        c = self.consolidate()
        return dict(kept=len(kept), dropped=[d[0] for d in dropped], searched=[(w, n) for w, t, n in r["searched"]],
                    bound=sorted(self.lexicon), **c)

    def consolidate(self):
        """sleep once, then prune every library entry no binding and no other entry reaches. -> report."""
        slept, n = self.sleep()
        live = set(); stack = [v for v in self.lexicon.values() if v in self.lib]
        while stack:
            k = stack.pop()
            if k in live: continue
            live.add(k); stack.extend(r for r in _refs(self.lib.entries[k]) if r in self.lib)
        pruned = [k for k in self.lib.entries if k not in live]
        for k in pruned: del self.lib.entries[k]; self.lib.forced.pop(k, None)
        return dict(slept=slept, pruned=len(pruned), library=len(self.lib))

    def sleep(self, min_count=2):
        """crystallise the fragment recurring across library entries -> new library id or None."""
        top, n = compress_recurring(list(self.lib.entries.values()), fragments, min_count=min_count)
        if top is None: return None, n
        return self.lib.add(top, forced_by=("sleep", n)), n


def _num(s):
    try: return Fraction(str(s))
    except Exception: return s


def _json_tree(t): return t if not isinstance(t, tuple) else [_json_tree(c) for c in t]


def _tuple_tree(t): return tuple(_tuple_tree(c) for c in t) if isinstance(t, list) else t


def _json_forced(f):
    if f is None: return None
    if f[0] == "sleep": return ["sleep", f[1]]
    return [f[0], [[str(a), str(b)] for a, b in f[1]]]


def _tuple_forced(f):
    if f is None: return None
    if f[0] == "sleep": return ("sleep", f[1])
    return (f[0], [(_num(a), _num(b)) for a, b in f[1]])


def _refs(tree):
    """the library ids a tree refers to."""
    if not isinstance(tree, tuple): return []
    return ([tree[0]] if isinstance(tree[0], str) and tree[0].startswith("L#") else []) + [r for c in tree[1:] for r in _refs(c)]


ev_ = ev


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
