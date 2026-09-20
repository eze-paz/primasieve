"""PHASE 3 -- THE LEARNER (nolf_prereg.md). Imports core/ only; never a world.

From (situation, tokens, truth) triples and nothing else -- no logical form, no word classes, no combinator
names -- induce a compositional truth-conditional grammar:

  CLASSES      words are grouped by distributional substitutability: two words share a class when the sets of
               (left neighbour, right neighbour) contexts they occur in agree closely. Classes are numbered.
  SKELETONS    a sentence's class sequence. A class with two or more members is a SLOT (its words denote
               something and the construction takes that something as an argument); a singleton class is part
               of the construction itself. If no term fits with every multi-member class as a slot, slots are
               demoted one at a time (the construction absorbs that word) -- searched, not authored.
  TERMS        for a skeleton, the SMALLEST executable truth condition over core.primitives' structural atoms
               (sequence access, membership, counting, order, equality, the connectives) with typed HOLES for the
               slots: an INT hole, an ELEM hole, a RELATION hole (the word denotes one of the (int,int)->bool
               atoms), a SELECTOR hole (the word denotes how a per-element predicate is turned into a truth
               value: all of them, any of them, the k-th), a BOOL hole (a reduced sub-sentence). Enumerated
               bottom-up by the number of atom applications under observational-equivalence dedupe
               (core.generate.SignatureBank), ties to the smallest (core.search's rule).
  DENOTATIONS  a word's denotation is solved as a CONSTRAINT problem across every sentence it occurs in, with a
               single domain per word shared across skeletons -- the cross-situational elimination of the lexicon
               work, applied to constants. That sharing is what makes a word learned in one construction usable
               in another (the compositional split).
  COMPOSITION  a span whose class sequence is a learned skeleton is reduced to a BOOL slot; negation and
               conjunction are then skeletons over BOOL slots like any other.
  VERDICT      predict only when every word is known, the skeleton is learned, and every surviving denotation
               and every surviving term agree; otherwise ABSTAIN (core.verdict discipline).

Two combinators live here and are declared as such: SELECT (a selector value applied to a sequence and a body
over a bound element) and RELATE (a relation value applied to two integers). Both are l0-style: they take a
word's denotation as the operator. Nothing here names a field, a colour, a character, or a quantifier word."""
import itertools, collections, random, time
from core import primitives as P
from core.generate import SignatureBank

INT, BOOL, SEQ, ELEM = P.INT, P.BOOL, P.SEQ, P.ELEM
HI, HE, HR, HS, HB = "hi", "he", "hr", "hs", "hb"                  # hole kinds
HOLE_TYPE = {HI: INT, HE: ELEM, HB: BOOL}
MAX_OPS, MAX_HOLES, JACCARD, BANK_CAP, MIN_ROWS, GRACE = 4, 5, 0.5, 6000, 40, 10


# ------------------------------------------------------------------------------------------ terms and their closures
def _atoms_by_sig():
    out = collections.defaultdict(list)
    for p in P.pids():
        args, res = P.signature(p)
        if all(t in (INT, BOOL, SEQ, ELEM) for t in args) and res in (INT, BOOL, SEQ, ELEM):
            out[(args, res)].append(p)
    return out


def holes(term):
    """hole kinds in left-to-right order (RELATE and SELECT carry one hole each: the operator word)."""
    tag = term[0]
    if tag == "H": return [term[1]]
    if tag in ("SIT", "VAR", "K"): return []
    if tag == "A": return [h for a in term[2:] for h in holes(a)]
    if tag == "R": return [HR] + holes(term[1]) + holes(term[2])
    if tag == "S": return [HS] + holes(term[1]) + holes(term[2])
    if tag == "SK": return holes(term[2]) + holes(term[3])
    raise ValueError(tag)


def uses_sit(term):
    tag = term[0]
    if tag == "SIT": return True
    if tag in ("H", "VAR", "K"): return False
    return any(uses_sit(a) for a in (term[2:] if tag in ("A", "SK") else term[1:]))


def ops(term):
    tag = term[0]
    if tag in ("H", "SIT", "VAR", "K"): return 0
    if tag == "A": return 1 + sum(ops(a) for a in term[2:])
    if tag == "SK": return 1 + ops(term[2]) + ops(term[3])
    return 1 + ops(term[1]) + ops(term[2])


def result_type(term):
    tag = term[0]
    if tag == "SIT": return SEQ
    if tag == "K": return INT
    if tag == "H": return HOLE_TYPE.get(term[1])
    if tag == "VAR": return None
    if tag == "A": return P.signature(term[1])[1]
    return BOOL


def has_var(term):
    tag = term[0]
    if tag == "VAR": return True
    if tag in ("SIT", "K", "H"): return False
    return any(has_var(a) for a in (term[2:] if tag in ("A", "SK") else term[1:]))


def subterms(term):
    yield term
    tag = term[0]
    if tag in ("SIT", "K", "H", "VAR"): return
    for a in (term[2:] if tag in ("A", "SK") else term[1:]):
        yield from subterms(a)


def fragments(grammar):
    """THE LIBRARY: every sub-term with at least one atom application inside an adopted construction, with its
    result type and whether it mentions the bound variable. The emergence thread's lesson applied to language:
    a construction learned once is a piece of the next one (field-vs-field is the atom's body applied twice)."""
    out = {}
    for alts in grammar.values():
        for term, _ in alts:
            for sub in subterms(term):
                if ops(sub) >= 1 and result_type(sub) is not None:
                    out[sub] = (result_type(sub), has_var(sub))
    return out


def compile_term(term):
    """-> f(sit, env, var) where env is the tuple of hole values in `holes` order; raises on a partial application."""
    counter = [0]

    def build(t):
        tag = t[0]
        if tag == "SIT": return lambda s, e, v: s
        if tag == "VAR": return lambda s, e, v: v
        if tag == "K":
            k = t[1]; return lambda s, e, v: k
        if tag == "H":
            i = counter[0]; counter[0] += 1
            return lambda s, e, v, i=i: e[i]
        if tag == "A":
            fn = P.unchecked(t[1]); argt, rest = P.signature(t[1]); chk = [P.CHECK[a] for a in argt]; rchk = P.CHECK[rest]
            subs = [build(a) for a in t[2:]]
            def f(s, e, v, fn=fn, subs=subs, chk=chk, rchk=rchk):
                vals = [g(s, e, v) for g in subs]
                for val, c in zip(vals, chk):
                    if not c(val): raise TypeError
                out = fn(*vals)
                if not rchk(out): raise TypeError
                return out
            return f
        if tag == "R":
            i = counter[0]; counter[0] += 1
            a, b = build(t[1]), build(t[2])
            def f(s, e, v, i=i, a=a, b=b):
                x, y = a(s, e, v), b(s, e, v)
                if not (P.CHECK[INT](x) and P.CHECK[INT](y)): raise TypeError
                return P.unchecked(e[i])(x, y)
            return f
        if tag == "SK":
            sel = t[1]; sq, body = build(t[2]), build(t[3])
            def f(s, e, v, sel=sel, sq=sq, body=body):
                seq = sq(s, e, v)
                if not P.CHECK[SEQ](seq): raise TypeError
                outs = []
                for x in seq:
                    o = body(s, e, x)
                    if not isinstance(o, bool): raise TypeError
                    outs.append(o)
                return all(outs) if sel == "all" else any(outs)
            return f
        if tag == "S":
            i = counter[0]; counter[0] += 1
            sq, body = build(t[1]), build(t[2])
            def f(s, e, v, i=i, sq=sq, body=body):
                seq = sq(s, e, v)
                if not P.CHECK[SEQ](seq): raise TypeError
                sel = e[i]
                if sel[0] == "idx":
                    k = sel[1]
                    if not -len(seq) <= k < len(seq): raise IndexError
                    out = body(s, e, seq[k])
                    if not isinstance(out, bool): raise TypeError
                    return out
                outs = []
                for x in seq:
                    o = body(s, e, x)
                    if not isinstance(o, bool): raise TypeError
                    outs.append(o)
                return all(outs) if sel[0] == "all" else any(outs)
            return f
        raise ValueError(tag)
    return build(term)


def show(term):
    tag = term[0]
    if tag == "SIT": return "S"
    if tag == "VAR": return "x"
    if tag == "K": return str(term[1])
    if tag == "H": return "_" + term[1][1]
    if tag == "A": return f"{P.signature(term[1])[1][0]}{term[1][:3]}(" + ", ".join(show(a) for a in term[2:]) + ")"
    if tag == "R": return f"REL_r({show(term[1])}, {show(term[2])})"
    if tag == "S": return f"SEL_s({show(term[1])}, x. {show(term[2])})"
    if tag == "SK": return f"{term[1].upper()}({show(term[2])}, x. {show(term[3])})"


# ------------------------------------------------------------------------------------------------- enumeration
class Enumerator:
    """BOOL terms with typed holes, by number of atom applications, deduped by observational signature on probe
    situations. `lam=True` tables also contain the bound variable (bodies for SELECT)."""

    def __init__(self, probes, elems, rels, sels, library=None, max_ops=None):
        self.library = library or {}                      # fragment term -> (type, has_var): extra LEAVES
        self.max_ops = max_ops if max_ops is not None else MAX_OPS
        self.atoms = _atoms_by_sig()
        self.probes = probes; self.elems = sorted(elems, key=repr); self.rels = rels; self.sels = sels
        rng = random.Random(0)
        self.envs = {HI: [0, 1, 3, 2, 5, 4], HE: (self.elems * 3)[:6], HR: (rels * 2)[:6], HS: (sels * 2)[:6], HB: [True, True, False, False, True, False]}
        self.vars = []
        for s in probes[:2]:
            for x in list(s)[:3]: self.vars.append(x)
        self.tables = {}                                          # (lam) -> {ops: {type: [terms]}}

    def _sig(self, term, lam):
        """observational signature. The hole KINDS are part of it: not(_b) and 0 < _i agree on every probe value
        and are different terms -- the first version merged them and lost negation."""
        f = compile_term(term); hs = holes(term)
        out = [tuple(hs)]
        for j in range(5):
            env = tuple(self.envs[h][(j + q) % len(self.envs[h])] for q, h in enumerate(hs))   # distinct per hole
            for s in self.probes:
                vs = self.vars if lam else [None]
                for v in vs:
                    try: out.append(repr(f(s, env, v)))
                    except Exception: out.append("!")
        return tuple(out)

    def table(self, lam):
        if lam in self.tables: return self.tables[lam]
        banks = collections.defaultdict(lambda: SignatureBank(cap=BANK_CAP))
        T = collections.defaultdict(lambda: collections.defaultdict(list))
        # an ELEM hole is a distinct kind only when the situations hold elements that are not integers; where every
        # element is an integer (records) it duplicates the INT hole and doubles the table for nothing -- data decides
        elem_hole = [("H", HE)] if any(not P.CHECK[INT](e) for e in self.elems) else []
        leaves = [("SIT",), ("H", HI), ("K", 0), ("K", -1)] + elem_hole + ([("VAR",)] if lam else [("H", HB)])
        types_of = {"SIT": [SEQ], "K": [INT], "VAR": [SEQ, ELEM]}
        for lf in leaves:
            ts = [HOLE_TYPE[lf[1]]] if lf[0] == "H" else types_of[lf[0]]
            for ty in ts:
                if banks[ty].add(lf, ("leaf", lf, ty)): T[0][ty].append(lf)
        for frag, (ty, hv) in self.library.items():                  # library fragments are leaves: depth for free
            if hv and not lam: continue
            if len(holes(frag)) > MAX_HOLES: continue
            if banks[ty].add(frag, self._sig(frag, lam)): T[0][ty].append(frag)
        for k in range(1, self.max_ops + 1):
            new = []
            for (args, res), pids in self.atoms.items():
                for split in _splits(k - 1, len(args)):
                    pools = [T[n][t] for n, t in zip(split, args)]
                    for combo in itertools.product(*pools):
                        for p in pids:
                            new.append((res, ("A", p) + combo))
            for split in _splits(k - 1, 2):                                             # RELATE
                for a in T[split[0]][INT]:
                    for b in T[split[1]][INT]:
                        new.append((BOOL, ("R", a, b)))
            if lam and k == self.max_ops: break                                            # a body sits under SELECT
            if not lam:                                                                    # SELECT (no nesting)
                L = self.table(True)
                for split in _splits(k - 1, 2):
                    for sq in T[split[0]][SEQ]:
                        for body in L[split[1]][BOOL]:
                            new.append((BOOL, ("S", sq, body)))
                            new.append((BOOL, ("SK", "all", sq, body)))
                            new.append((BOOL, ("SK", "any", sq, body)))
            for res, term in new:
                if len(holes(term)) > MAX_HOLES: continue
                if banks[res].add(term, self._sig(term, lam)): T[k][res].append(term)
        self.tables[lam] = T
        return T

    def candidates(self, max_ops=None):
        T = self.table(False)
        for k in range(0, (max_ops if max_ops is not None else self.max_ops) + 1):
            for t in T[k][BOOL]: yield t


def _splits(n, parts):
    if parts == 1: yield (n,); return
    for i in range(n + 1):
        for rest in _splits(n - i, parts - 1): yield (i,) + rest


# ------------------------------------------------------------------------------------------------- the learner
class Learner:
    """dom: (word, hole kind) -> set of denotations. A word may carry one denotation PER KIND (an ordinal is a
    position when a construction wants an integer and a selector when it wants one); within a kind it is shared
    by every construction, and that sharing is what carries a word into a construction it was never seen in."""

    def __init__(self, time_budget=240, max_ops=MAX_OPS, verbose=False):
        self.budget = time_budget; self.max_ops = max_ops; self.verbose = verbose
        self.dom = {}                 # (word, kind) -> set of values
        self.grammar = {}             # skeleton key -> list of (term, perm)
        self.rows_of = {}             # skeleton key -> the rows it was learned from
        self.cls = {}                 # word -> class id
        self.members = collections.Counter()

    # ---- classes -------------------------------------------------------------------------------------------
    def _classes(self, train):
        ctx = collections.defaultdict(set)
        for _, toks, _ in train:
            for i, w in enumerate(toks):
                ctx[w].add((toks[i - 1] if i else "<", toks[i + 1] if i + 1 < len(toks) else ">"))
        words = sorted(ctx); parent = {w: w for w in words}
        def find(w):
            while parent[w] != w: parent[w] = parent[parent[w]]; w = parent[w]
            return w
        for a, b in itertools.combinations(words, 2):
            j = len(ctx[a] & ctx[b]) / len(ctx[a] | ctx[b])
            if j >= JACCARD: parent[find(a)] = find(b)
        roots = sorted({find(w) for w in words})
        ids = {r: i for i, r in enumerate(roots)}
        self.cls = {w: ids[find(w)] for w in words}
        self.members = collections.Counter(self.cls.values())

    # ---- reduction of learned spans to BOOL slots -------------------------------------------------------
    def _span_key(self, span):
        """the learned construction a span instantiates, if any: with every multi-member class as a slot, or with
        one of them demoted (a construction learned around one of its words)."""
        saved = set(self.demoted)
        try:
            key, fill = self._key(span)
            if key in self.grammar: return key, fill
            for c in sorted({it[1] for it in span if it[0] != "B"}):
                self.demoted = saved | {c}
                key, fill = self._key(span)
                if key in self.grammar: return key, fill
        finally:
            self.demoted = saved
        return None, None

    def _reduce(self, toks):
        items = [("c", self.cls[w], w) for w in toks]
        changed = True
        while changed:
            changed = False
            for L in range(len(items) - 1, 1, -1):
                for i in range(0, len(items) - L + 1):
                    key, fill = self._span_key(items[i:i + L])
                    if key is not None:
                        items[i:i + L] = [("B", key, fill)]
                        changed = True; break
                if changed: break
        return items

    def _key(self, items):
        key, fill = [], []
        for it in items:
            if it[0] == "B":
                key.append("B"); fill.append(it)
            else:
                _, c, w = it
                if self.members[c] >= 2 and c not in self.demoted:
                    key.append(("C", c)); fill.append(w)
                else:
                    key.append(("W", w))
        return tuple(key), fill

    # ---- the truth values a reduced sub-sentence can take -----------------------------------------------------
    def _sub_values(self, it, sit):
        _, key, fill = it
        outs = set()
        for term, perm in self.grammar[key]:
            f = compile_term(term); hs = holes(term)
            pools = []
            for j, h in enumerate(hs):
                x = fill[perm[j]]
                if isinstance(x, str):
                    d = self.dom.get((x, h))
                    if not d: pools = None; break
                    pools.append(sorted(d, key=repr))
                else:
                    vs = self._sub_values(x, sit)
                    if not vs: pools = None; break
                    pools.append(sorted(vs))
            if pools is None: continue                                   # this alternative types a word otherwise
            for env in itertools.islice(itertools.product(*pools), 64):
                o = self._top(f, sit, env)
                if o is not None: outs.add(o)
        return outs

    # ---- domains and pools ------------------------------------------------------------------------------------
    def _initial_domains(self, rows, hs, perm):
        doms = {}
        for j, h in enumerate(hs):
            for sit, fill, tv in rows:
                it = fill[perm[j]]
                if isinstance(it, str):
                    if h not in self.universe: return None            # a word never denotes a truth value
                    k = (it, h)
                    if k not in doms: doms[k] = set(self.dom.get(k, self.universe[h]))
                elif h != HB: return None                                # a sub-sentence is a truth value
        return doms

    def _env_pool(self, fill, hs, perm, doms, sit):
        pools = []
        for j, h in enumerate(hs):
            it = fill[perm[j]]
            if isinstance(it, str): pools.append(sorted(doms[(it, h)], key=repr))
            else:
                vs = self._sub_values(it, sit)
                if not vs: return None
                pools.append(sorted(vs))
        return pools

    @staticmethod
    def _mentions(row, keys):
        words = {k[0] for k in keys}
        return any(w in words for w in row[1] if isinstance(w, str))

    # ---- solving -------------------------------------------------------------------------------------------------
    def _solve(self, key, rows, enum):
        nslots = len(rows[0][1]); found = []; best_ops = None
        # satisfiability probes: the rows whose words are already pinned by earlier constructions -- a wrong
        # candidate dies there in milliseconds, where wide domains would let it survive for seconds
        def pinned(row):
            return sum(1 for w in row[1] if isinstance(w, str) and any(k[0] == w and len(v) == 1 for k, v in self.dom.items()))
        probe_rows = sorted(rows, key=lambda r: -pinned(r))[:12]
        seen_tv = {}; collide = False
        for sit, fill, tv in rows:
            k = tuple(w if isinstance(w, str) else "B" for w in fill)
            if seen_tv.setdefault(k, tv) != tv: collide = True; break
        words = [w for w in rows[0][1] if isinstance(w, str)]
        first_hit = None
        typed = {}                                                # word -> kinds it already has
        for (w, h) in self.dom: typed.setdefault(w, set()).add(h)
        def min_novelty(term):
            hs_ = holes(term)
            if len(hs_) != nslots: return 99
            best = 99
            for perm in itertools.permutations(range(nslots)):
                n = sum(1 for j, h in enumerate(hs_) if isinstance(rows[0][1][perm[j]], str)
                        and rows[0][1][perm[j]] in typed and h not in typed[rows[0][1][perm[j]]])
                best = min(best, n)
                if best == 0: break
            return best
        lib = fragments(self.grammar)
        def reuse(term):
            return -sum(1 for sub in subterms(term) if sub in lib)
        def ordered():
            """size level by size level; inside a level, terms whose holes can be filled without giving any word a
            new kind come first (measured: element-holed terms consumed a level's budget), and among those, terms
            that REUSE fragments of adopted constructions (the library) come before terms that reuse nothing"""
            level, buf = None, []
            for t in enum.candidates(enum.max_ops):
                if ops(t) != level:
                    for x in sorted(buf, key=lambda x: (min_novelty(x), reuse(x))): yield x
                    level, buf = ops(t), []
                buf.append(t)
            for x in sorted(buf, key=lambda x: (min_novelty(x), reuse(x))): yield x
        for term in ordered():
            if time.time() > self.deadline: break
            # after the first accepted analysis, alternatives at the same size get a short grace period; the
            # held-out fifth (evidence gate) is what protects against a wrong first analysis, not exhaustion
            if first_hit is not None and time.time() > first_hit + GRACE: break
            hs = holes(term)
            if len(hs) != nslots: continue
            if best_ops is not None and ops(term) > best_ops: break
            # a sentence's truth depends on the situation: a term over word slots that never reads it can only be right
            # by memorising (measured: 'b12a(_i, 0)' on 23-34 rows passed the evidence gate by luck and confabulated)
            if not uses_sit(term) and HB not in hs: continue
            f = compile_term(term)
            # a word keeps the kind it already has unless nothing else fits: mappings that give a typed word a NEW
            # kind are tried after those that do not, and once a level succeeds the noisier levels are skipped
            def novelty(perm):
                nov = sum(1 for j, h in enumerate(hs) if isinstance(rows[0][1][perm[j]], str)
                          and any(k[0] == rows[0][1][perm[j]] for k in self.dom) and (rows[0][1][perm[j]], h) not in self.dom)
                # mutual exclusivity (the child's bias, used as an ORDER not a rule): different words of one class
                # want different denotations, so a class with more members than a kind has values is tried in that
                # kind last -- ten numerals cannot all be one of three relations
                crowd = sum(1 for j, h in enumerate(hs) if isinstance(rows[0][1][perm[j]], str) and h in self.universe
                            and self.members.get(self.cls.get(rows[0][1][perm[j]]), 1) > len(self.universe[h]))
                return nov + 2 * crowd
            perms = sorted(itertools.permutations(range(nslots)), key=novelty)
            best_nov = None
            for perm in perms:
                if time.time() > self.deadline: break
                if best_nov is not None and novelty(perm) > best_nov: break
                doms = self._initial_domains(rows, hs, perm)
                if doms is None: continue
                if not self._satisfiable(f, probe_rows, hs, perm, doms): continue
                doms = self._fit_candidate(f, rows, hs, perm, doms)
                if doms is None: continue
                found.append((term, perm, doms)); best_ops = ops(term); best_nov = novelty(perm)
                first_hit = first_hit or time.time()
        return found

    def _satisfiable(self, f, rows, hs, perm, doms):
        for sit, fill, tv in rows:
            pools = self._env_pool(fill, hs, perm, doms, sit)
            if pools is None: return False
            ok = False
            for env in itertools.product(*pools):
                if self._top(f, sit, env) is tv: ok = True; break
            if not ok: return False
            if time.time() > self.deadline: return False
        return True

    @staticmethod
    def _top(f, sit, env):
        """the truth value of a whole sentence. An ABSENT element (KeyError from the position atoms) is a false
        presupposition: the sentence is false. An IMPOSSIBLE position (IndexError: the fifth record of four, the
        fourth field of three) is not a sentence about this situation at all: undefined, and a candidate that
        needs it for a row is inconsistent with that row. Letting impossible positions count as false kept ten
        index values alive per word where the situations support three or four, and multiplied the search."""
        try: out = f(sit, env, None)
        except Exception: return False                 # measured: treating impossible positions as undefined was slower
        return out if isinstance(out, bool) else None

    def _ev(self, f, rid, sit, env, cache):
        k = (rid, env)
        if k in cache: return cache[k]
        out = self._top(f, sit, env)
        cache[k] = out
        return out

    def _csp(self, f, rows, hs, perm, doms, cache, only=None):
        """arc consistency over rows; `only` restricts the first pass to rows mentioning those variables."""
        doms = {k: set(v) for k, v in doms.items()}
        queue = list(range(len(rows))) if only is None else [i for i, r in enumerate(rows) if self._mentions(r, only)]
        while queue:
            if time.time() > self.deadline: return None
            i = queue.pop(0)
            sit, fill, tv = rows[i]
            pools = self._env_pool(fill, hs, perm, doms, sit)
            if pools is None: return None
            size = 1
            for pl in pools: size *= len(pl)
            if size > 30000: continue
            seen = [set() for _ in hs]
            for env in itertools.product(*pools):
                if self._ev(f, i, sit, env, cache) is tv:
                    for j, v in enumerate(env): seen[j].add(v)
            if not any(seen): return None
            changed = set()
            for j, h in enumerate(hs):
                it = fill[perm[j]]
                if isinstance(it, str) and seen[j] != doms[(it, h)]:
                    doms[(it, h)] &= seen[j]; changed.add((it, h))
                    if not doms[(it, h)]: return None
            if changed:
                for k2, r2 in enumerate(rows):
                    if k2 != i and self._mentions(r2, changed) and k2 not in queue: queue.append(k2)
        return doms

    LIMIT = object()          # the assignment search ran out of nodes: not enough evidence in this sample, not a refutation

    def _global(self, f, rows, hs, perm, doms, cache, nodes=None, limit=60):
        """ONE denotation per word: depth-first assignment with propagation after every choice. A small node
        budget: a wrong candidate that propagation alone does not kill dies here cheaply, and a right one that
        needs more than this many choices is under-determined by the sample -- LIMIT tells the caller to widen."""
        nodes = nodes if nodes is not None else [0]
        free = [k for k, d in doms.items() if len(d) > 1]
        if not free: return doms
        if nodes[0] > limit: return self.LIMIT
        if time.time() > self.deadline: return None
        k = min(free, key=lambda x: len(doms[x]))
        for v in sorted(doms[k], key=repr):
            nodes[0] += 1
            trial = {x: set(d) for x, d in doms.items()}; trial[k] = {v}
            trial = self._csp(f, rows, hs, perm, trial, cache, only={k})
            if trial is None: continue
            out = self._global(f, rows, hs, perm, trial, cache, nodes, limit)
            if out is self.LIMIT: return self.LIMIT
            if out is not None: return out
        return None

    def _verify(self, f, rows, hs, perm, doms):
        """-> (ok, unpinned, first failing row index)"""
        unpinned = set()
        for i, (sit, fill, tv) in enumerate(rows):
            pools = self._env_pool(fill, hs, perm, doms, sit)
            if pools is None: return False, unpinned, i
            if any(len(pl) != 1 for pl in pools):
                unpinned |= {(fill[perm[j]], hs[j]) for j, pl in enumerate(pools) if len(pl) != 1 and isinstance(fill[perm[j]], str)}
                continue
            if self._top(f, sit, tuple(pl[0] for pl in pools)) is not tv: return False, unpinned, i
        return True, unpinned, None

    def _fit_candidate(self, f, rows, hs, perm, doms):
        """subsample -> propagate -> assign -> verify on everything; a failed verification widens the sample (the
        failing row first) and re-solves; only a failure on the whole set rejects. Then the EVIDENCE gate: the
        construction, fitted on four fifths of the skeleton's rows, must predict the held-out fifth exactly --
        a lexicon that merely memorises its rows fails here, and a skeleton with too few rows cannot pass."""
        rows = list(rows)
        if len(rows) < MIN_ROWS: return None
        check = rows[4::5]; rows = [r for i, r in enumerate(rows) if i % 5 != 4]
        d = self._fit_rows(f, rows, hs, perm, doms)
        if d is None: return None
        ok, unpinned, _ = self._verify(f, check, hs, perm, d)
        return d if ok and not unpinned else None

    def _fit_rows(self, f, rows, hs, perm, doms):
        cache = {}; n = 12; rows = list(rows); widened = False
        while True:
            sub = rows[:n]
            d = self._csp(f, sub, hs, perm, doms, cache)
            if d is None: return None
            d = self._global(f, sub, hs, perm, d, cache)
            if d is None: return None
            if d is self.LIMIT: return None                     # measured: widening on the limit cost more than it saved
            ok, unpinned, bad = self._verify(f, rows, hs, perm, d)
            if ok and not unpinned: return d
            if n >= len(rows): return None
            if bad is not None and bad >= n:
                rows.insert(n, rows.pop(bad)); cache = {}
            n = min(len(rows), n * 2)
            if time.time() > self.deadline: return None

    # ---- fit ---------------------------------------------------------------------------------------------------------
    def fit(self, train):
        t0 = time.time(); self.deadline = t0 + self.budget
        self._classes(train)
        elems = set(); ints = set(range(0, 10))
        for sit, _, _ in train:
            for x in sit:
                if P.CHECK[ELEM](x): elems.add(x)
                elif P.CHECK[SEQ](x):
                    for y in x:
                        if P.CHECK[ELEM](y): elems.add(y)
        rels = [p for p in P.pids() if P.signature(p) == ((INT, INT), BOOL)]
        sels = [("all",), ("any",)] + [("idx", k) for k in range(-1, 4)]
        self.universe = {HI: sorted(ints), HE: sorted(elems, key=repr), HR: rels, HS: sels}
        # dedupe probes: 8 situations of DIFFERENT sizes -- with 3, 'all records satisfy' and 'record 0 satisfies'
        # agreed on every probe and the quantifier construction was merged away (measured)
        by_size = {}
        for sit, _, _ in train:
            by_size.setdefault(len(sit), []).append(sit)
        probes = [x for k in sorted(by_size) for x in by_size[k][:3]][:8]
        if len(probes) < 8: probes += [sit for sit, _, _ in train[:8 - len(probes)]]
        enum = Enumerator(probes, elems, rels, sels)
        enum.table(False); self.table_seconds = time.time() - t0; self.t0 = t0; self.enum = enum
        self.demoted = set()
        by_len = collections.defaultdict(list)
        for row in train: by_len[len(row[1])].append(row)
        self.log = []
        final = t0 + self.budget
        # SELF-GENERATED CURRICULUM (the E-6 closure lesson applied to constructions): no authored order. After every
        # construction lands, everything is re-grouped (new constructions reduce more spans) and re-ranked by how much
        # of it is already PINNED -- the fraction of its slot words that have a denotation -- then by how many slot
        # classes are still unknown, then by evidence. The foundation (nothing pinned yet) gets the largest cap,
        # because every later skeleton is cheaper once it lands; a skeleton is retried whenever new pins arrive.
        tried = {}                                                # key -> number of pins when last attempted
        library_pass = False
        while time.time() < final:
            groups = collections.defaultdict(list); raw = collections.defaultdict(list)
            for sit, toks, tv in train:
                items = self._reduce(toks); key, fill = self._key(items)
                groups[key].append((sit, fill, tv))
                rkey, rfill = self._key([("c", self.cls[w], w) for w in toks]); raw[key].append((rkey, (sit, rfill, tv)))
            npins = len(self.dom)
            pinned_words = {k[0] for k in self.dom}
            def pinned_frac(key, rows):
                slots = {w for _, fill, _ in rows for w in fill if isinstance(w, str)}
                return sum(1 for w in slots if w in pinned_words) / len(slots) if slots else 1.0
            def unknown_classes(key):
                return sum(1 for k in key if k != "B" and k[0] == "C" and not any(self.cls.get(w) == k[1] for (w, _) in self.dom))
            pending = [(k, r) for k, r in groups.items() if k not in self.grammar and len(r) >= MIN_ROWS
                       and any(x != "B" and x[0] == "C" or x == "B" for x in k)]
            # a skeleton that CONTAINS an unsolved skeleton's pattern ("... and <field-vs-field>") cannot be solved before
            # that one is: defer it instead of spending a cap on it (measured: two such keys burned 120 s)
            failed = [k for k in tried if k not in self.grammar and "B" not in k]
            def contains_failed(key):
                return any(len(u) < len(key) and any(key[i:i + len(u)] == u for i in range(len(key) - len(u) + 1)) for u in failed)
            todo = [(k, r) for k, r in pending if tried.get(k, -1) < npins and not contains_failed(k)]
            # the plain search is done when every remaining skeleton has been tried once since the last pin, or when
            # less than 45% of the budget is left with something failed: the library is what widens reach from here
            plain_done = pending and all(k in tried for k, _ in pending)
            late = failed and (final - time.time()) < 0.45 * self.budget
            if pending and not library_pass and (plain_done or late) and fragments(self.grammar) and final - time.time() > 45:
                todo = []
            if not todo:
                # THE LIBRARY PASS: the plain search has nothing left it can reach. Re-enumerate with the fragments
                # of every adopted construction as LEAVES -- a 5-atom truth condition is then 2 applications over
                # fragments -- and give the unsolved skeletons one more round. Once.
                if library_pass or not fragments(self.grammar): break
                library_pass = True
                enum = Enumerator(probes, elems, rels, sels, library=fragments(self.grammar), max_ops=2)
                enum.table(False); self.library_seconds = time.time() - t0
                tried = {}; continue
            key, rows = max(todo, key=lambda kr: (pinned_frac(*kr), -unknown_classes(kr[0]), len(kr[1])))
            tried[key] = npins
            left = final - time.time()
            cap = 120 if npins == 0 else (90 if library_pass else 60)
            self.deadline = min(final, time.time() + min(cap, left))
            self._learn_key(key, rows, enum)
            if key not in self.grammar and any(k == "B" for k in key):
                by_raw = collections.defaultdict(list)                # the greedy reduction may have swallowed a
                for rkey, row in raw[key]: by_raw[rkey].append(row)   # non-constituent: try the sentence unreduced
                for rkey, rrows in by_raw.items():
                    if rkey not in self.grammar and len(rrows) >= MIN_ROWS and time.time() < final:
                        self.deadline = min(final, time.time() + 30); self._learn_key(rkey, rrows, enum)
        self.deadline = final
        self.log = [e for i, e in enumerate(self.log) if not (e[0] == "unsolved" and any(
            f[0] == "learned" and f[1] == e[1] for f in self.log[i + 1:]))]
        self.seconds = time.time() - t0
        return self

    def _learn_key(self, key, rows, enum):
        found = self._solve(key, rows, enum) if any(k[0] != "W" for k in key) else []
        if found:
            self._adopt(key, rows, found); return
        slot_classes = [k[1] for k in key if k[0] == "C"]
        for c in slot_classes:                                    # DEMOTE one slot class into the construction
            self.demoted.add(c)
            regroup = collections.defaultdict(list)
            for sit, fill, tv in rows:
                k2, f2 = self._rekey(key, fill)
                regroup[k2].append((sit, f2, tv))
            ok_any = False
            for k2, r2 in regroup.items():
                if k2 in self.grammar: ok_any = True; continue
                f2 = self._solve(k2, r2, enum) if any(k[0] != "W" for k in k2) else []
                if f2: self._adopt(k2, r2, f2); ok_any = True
            self.demoted.discard(c)
            if ok_any: return
        self.log.append(("unsolved", key, len(rows), time.time() - self.t0))

    def _rekey(self, key, fill):
        out, f2, fi = [], [], 0
        for k in key:
            if k[0] == "W": out.append(k); continue
            it = fill[fi]; fi += 1
            if k == "B": out.append("B"); f2.append(it); continue
            if k[1] in self.demoted: out.append(("W", it))
            else: out.append(k); f2.append(it)
        return tuple(out), f2

    def _adopt(self, key, rows, found):
        """the first (simplest, least novel) analysis pins the lexicon; an alternative survives only if every
        denotation it needs agrees with what is pinned -- alternatives that type a word otherwise are dropped,
        not merged (merging by intersection once emptied real denotations)."""
        t0, p0, d0 = found[0]
        for k, vals in d0.items():
            self.dom[k] = (self.dom[k] & vals) if k in self.dom and (self.dom[k] & vals) else set(vals)
        kept = [(t0, p0)]
        for t, p, d in found[1:]:
            if all(self.dom.get(k) == vals for k, vals in d.items()): kept.append((t, p))
        self.grammar[key] = kept
        self.rows_of[key] = rows
        self.log.append(("learned", key, len(rows), show(t0), len(kept), time.time() - self.t0))
        self._absorb(key)

    def _absorb(self, key):
        """A construction learned earlier AROUND one word (a demoted slot) is a special case of a construction that
        now takes the word's whole class as a slot. Pin that word's denotation through the general term on the rows
        it was learned from, so the word is usable everywhere its class is -- otherwise a sentence containing it
        inside a larger construction evaluates to nothing (the conjunction failure: 'n3' had no number)."""
        if any(k[0] == "W" for k in key if k != "B") and not any(k[0] == "C" for k in key if k != "B"): return
        t0, p0 = self.grammar[key][0]; hs = holes(t0); f = compile_term(t0)
        for other in list(self.grammar):
            if other == key or len(other) != len(key): continue
            diff = [(a, b) for a, b in zip(key, other) if a != b]
            if not diff or not all(a != "B" and b != "B" and a[0] == "C" and b[0] == "W" and self.cls.get(b[1]) == a[1] for a, b in diff): continue
            rows = []
            for sit, fill, tv in self.rows_of.get(other, []):
                it = iter(fill); f2 = [next(it) if k != "B" and k[0] == "C" else (next(it) if k == "B" else k[1]) for k in key]
                # rebuild the general fill: the demoted words become fillers in their slot positions
                rows.append((sit, [x if not (isinstance(x, tuple) and x and x[0] == "W") else x[1] for x in f2], tv))
            if len(rows) < MIN_ROWS: continue
            doms = self._initial_domains(rows, hs, p0)
            if doms is None: continue
            d = self._fit_rows(f, rows, hs, p0, doms)
            if d is None or d is self.LIMIT: continue
            for k, vals in d.items():
                if k not in self.dom: self.dom[k] = set(vals)

    # ---- predict -------------------------------------------------------------------------------------------------------
    def __call__(self, x):
        sit, toks = x
        if any(w not in self.cls for w in toks): return None
        self.demoted = set()
        items = self._reduce(toks)
        key, fill = self._span_key(items)
        if key is None: return None
        outs = self._sub_values(("B", key, fill), sit)
        return next(iter(outs)) if len(outs) == 1 else None
