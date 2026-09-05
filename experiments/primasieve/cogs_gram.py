"""STAGE 3a/3b -- the HEAD-PASSING synchronous grammar engine (zero-LLM, pure stdlib).

Stage 2's inventory composed opaque STRINGS. COGS recursion emits `prev_head . nmod . prep ( x_prev , x_new )`:
a predicate that references the HEAD VARIABLE of a sibling constituent and splices that sibling's HEAD LEMMA
into the predicate name. So the output side is constituents that export a head:

    constituent = (head, lemma, defs, conj)        head = ('v', token_index) | ('c', proper_name)

GENERIC combinator inventory (frozen; no dataset-specific token, role name, count or ordering fact):
    PRIM(lemma)            a word denotes an entity / event / relation; head = its own token index
    EMIT(pred_tpl, args)   add a conjunct; pred_tpl may splice a CHILD's head LEMMA, args are CHILD HEAD VARS
    UNION(order)           concatenate children's conjunct lists in a rule-determined order
    HEAD(k)                head-select: which child's head this constituent exports

Everything above the inventory is INDUCED from (sentence, logical form) pairs and SOUND-GATED against them.
Two induction routes, and which route a fact takes is the whole content of Stage 3b:

  DIRECTLY OBSERVED (no search needed).
    word CLASSES, from the alignment COGS gives for free: variable indices ARE 0-based token positions, so a
      conjunct anchored at x_i is anchored at TOKEN i -- alignment by position, never by string equality.
    the LEMMA map, the sentence TERMINATOR, the DETERMINERS with their side (before/after the noun) and each
      determiner's DEFINITENESS REALIZATION (the `*` prefix list, an extra inline marker predicate, or none).
    the RELATION TEMPLATE middle segments.
    the FRAME -> role table, keyed on the syntactic frame, falling back to the verb only where the frame alone
      is inconsistent -- the coarsest consistent key.

  SEARCHED over a small generic space, kept by measured reproduction of train (class Schema).
    Stage 3a searched only the two conjunct-ORDER policies and WROTE the rest by hand. Stage 3b's knockout
    ladder showed that cost exactly: of 11 single-dimension knockouts of the authored structure, 1 survived.
    So the eight structural choices below are now searched by the same mechanism, not authored:
      np_branch  modifier right of its head noun | head-final, left of it
      np_head    a modified NP exports the HEAD's variable | the DEPENDENT's
      mod_pred   modifier predicate splices the HEAD's lemma | the DEPENDENT's | no lemma at all
      mod_args   modifier conjunct arguments (head, dep) | (dep, head)
      verb_pos   verb before its post-arguments | clause-final
      cl_head    a clause exports the EVENT variable | its SUBJECT's
      np_order   where a modifier conjunct sits among its own and its child's conjuncts (3 ways)
      cl_order   whether the subject's conjuncts precede the verb's role block

Prediction COMMITS on a derivation and ABSTAINS otherwise; still no probabilistic output, as in Stages 1-2."""
import os, sys, re, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_lf import parse_lf, serialize, norm_lf
from cogs_align import associate, to_positional, renumber_first_appearance

ENTITY, NAME, EVENT, REL, FUNC = "ENTITY", "NAME", "EVENT", "REL", "FUNC"
PARSE_BUDGET = 20000


# ================================================================ the searched schema
class Schema:
    SPACE = dict(np_branch=("right", "left"), np_head=("head", "dep"),
                 mod_pred=("head_lemma", "dep_lemma", "bare"), mod_args=("head_dep", "dep_head"),
                 verb_pos=("medial", "final"), cl_head=("event", "subject"),
                 np_order=("own_rel_inner", "own_inner_rel", "rel_own_inner"),
                 cl_order=("subj_first", "block_first"))
    DIMS = tuple(sorted(SPACE))

    def __init__(self, **kw):
        for d in self.DIMS:
            setattr(self, d, kw.get(d, self.SPACE[d][0]))

    def copy(self, **kw):
        c = Schema(**{d: getattr(self, d) for d in self.DIMS})
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    def __repr__(self):
        return "Schema(" + ", ".join(f"{d}={getattr(self, d)}" for d in self.DIMS) + ")"


# ================================================================ directly observed lexicon
class Lexicon:
    def __init__(self):
        self.cls = {}            # word -> ENTITY / NAME / EVENT / REL / FUNC
        self.lemma = {}          # word -> lemma
        self.det = {}            # determiner word -> 'plain' | 'prefix' | ('inline', marker_predicate)
        self.det_pos = "pre"     # which side of its noun a determiner sits on
        self.terminator = None
        self.rel_segs = {}       # relator word -> the observed full predicate segment lists
        self.vroles = {}         # verb lemma -> roles from its own LAMBDA lexicon row
        self.varity = {}


def _lambda_entry(word, lf, lex, votes, lemvote):
    """A `primitive` row is a LEXICON entry, not a sentence: `LAMBDA a . ball ( a )`, or a bare `Paula`."""
    nlam = lf.count("LAMBDA")
    body = lf
    while body.startswith("LAMBDA "):
        body = body.split(" . ", 1)[1]
    heads = [p.strip() for p in re.findall(r"([A-Za-z_. ]+?) \( ", body)]
    if not heads:
        votes[word][NAME] += 1          # a bare lexicon row is a proper name, not a functor
        return
    if all(" . " in h for h in heads):
        lemma = heads[0].split(" . ")[0].strip()
        votes[word][EVENT] += 1
        lemvote[word][lemma] += 1
        lex.vroles[lemma] = frozenset(h.split(" . ")[1].strip() for h in heads)
        lex.varity[lemma] = nlam - 1
    else:
        votes[word][ENTITY] += 1
        lemvote[word][heads[0]] += 1


def _rows(train):
    """(sentence tokens, definites, conjuncts) for the rows that are sentences, not lexicon entries."""
    for s, lf, cat in train:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            continue
        toks = s.split()
        if len(toks) < 2:
            continue
        p = parse_lf(lf)
        if p is None or p[0] == "LAMBDA":
            continue
        yield toks, p[0], p[1]


def induce_lexicon(train):
    lex = Lexicon()
    votes = collections.defaultdict(collections.Counter)
    lemvote = collections.defaultdict(collections.Counter)
    relsegs = collections.defaultdict(collections.Counter)
    seen, lastvote = collections.Counter(), collections.Counter()
    nsent = 0
    for s, lf, cat in train:
        toks = s.split()
        if cat == "primitive" or lf.startswith("LAMBDA"):
            _lambda_entry(toks[0], lf, lex, votes, lemvote)
            seen[toks[0]] += 1
        elif len(toks) == 1:
            votes[toks[0]][NAME] += 1
            seen[toks[0]] += 1
    for toks, defs, conj in _rows(train):
        for w in toks:
            seen[w] += 1
        nsent += 1
        lastvote[toks[-1]] += 1
        for lem, i in defs:
            if i < len(toks):
                votes[toks[i]][ENTITY] += 1
                lemvote[toks[i]][lem] += 1
        for pred, args in conj:
            segs = [x.strip() for x in pred.split(" . ")]
            if len(segs) == 1 and len(args) == 1 and args[0][0] == "v":
                i = args[0][1]
                if i < len(toks):
                    votes[toks[i]][ENTITY] += 1
                    lemvote[toks[i]][segs[0]] += 1
            elif len(segs) >= 2 and len(args) == 2 and args[0][0] == "v" and args[1][0] == "v":
                # RELATOR first, EVENT second: a modifier's predicate ENDS in a token that lies BETWEEN its two
                # arguments, which a verb's role predicate never does. Testing EVENT first mis-read a
                # lemma-less modifier predicate (`nmod . p1 ( x_10 , x_7 )`) as a two-segment verb frame.
                lo, hi = sorted((args[0][1], args[1][1]))
                hit = [k for k in range(lo + 1, min(hi, len(toks))) if toks[k] == segs[-1]]
                if hit:
                    votes[toks[hit[0]]][REL] += 1
                    relsegs[toks[hit[0]]][tuple(segs)] += 1
                    continue
                e = args[0][1]
                if len(segs) == 2 and e < len(toks):
                    votes[toks[e]][EVENT] += 1
                    lemvote[toks[e]][segs[0]] += 1
            elif len(segs) == 2 and len(args) == 2 and args[0][0] == "v":
                e = args[0][1]
                if e < len(toks):
                    votes[toks[e]][EVENT] += 1
                    lemvote[toks[e]][segs[0]] += 1
            for a in args:
                if a[0] == "c":
                    votes[a[1]][NAME] += 1
    for w in seen:
        if w not in votes:
            lex.cls[w] = FUNC
    for w, cc in votes.items():
        lex.cls[w] = cc.most_common(1)[0][0]
    for w, cc in lemvote.items():
        lex.lemma[w] = cc.most_common(1)[0][0]
    for w, cc in relsegs.items():
        lex.rel_segs[w] = cc
    for w, n in lastvote.items():
        if n >= 0.95 * max(nsent, 1) and n == seen[w]:
            lex.terminator = w
    _induce_determiners(lex, train)
    return lex


def _realization(toks, defs, conj, i):
    """How the noun at token i realizes its own conjunct -- this is what a DETERMINER controls, and reading it
    off the data is what makes both the `*` prefix list and an inline marker predicate induced rather than
    written in. Returns 'prefix' | ('inline', marker) | 'plain' | None."""
    lem = None
    for l, j in defs:
        if j == i:
            return "prefix"
    unary = [p for p, a in conj if len(a) == 1 and a[0] == ("v", i)]
    if not unary:
        return None
    lem = unary[0]
    extra = [p for p in unary[1:] if p != lem]
    return ("inline", extra[0]) if extra else "plain"


def _induce_determiners(lex, train):
    """A determiner is a functor that sits on a CONSISTENT side of an entity token AND whose adjacent noun has
    a CONSISTENT conjunct realization. That second condition is what separates a determiner from an argument
    marker: a marker leaves the noun's realization untouched, so its realizations are mixed."""
    side = {-1: collections.defaultdict(collections.Counter), 1: collections.defaultdict(collections.Counter)}
    cover = {-1: collections.Counter(), 1: collections.Counter()}
    for toks, defs, conj in _rows(train):
        for i, w in enumerate(toks):
            if lex.cls.get(w) != ENTITY:
                continue
            r = _realization(toks, defs, conj, i)
            if r is None:
                continue
            for d in (-1, 1):
                j = i + d
                if 0 <= j < len(toks) and lex.cls.get(toks[j]) == FUNC and toks[j] != lex.terminator:
                    side[d][toks[j]][r] += 1
                    cover[d][toks[j]] += 1
    best = None
    for d in (-1, 1):
        dets = {}
        n = 0
        for w, cc in side[d].items():
            r, c = cc.most_common(1)[0]
            if cover[d][w] >= 10 and c >= 0.95 * cover[d][w]:
                dets[w] = r
                n += c
        if best is None or n > best[0]:
            best = (n, "pre" if d == -1 else "post", dets)
    lex.det_pos = best[1]
    lex.det = best[2]


def induce_relmid(lex, train, sch):
    """The constant middle segments, under this schema's reading of the predicate template."""
    mid = {}
    for w, cc in lex.rel_segs.items():
        v = collections.Counter()
        for segs, n in cc.items():
            v[segs[:-1] if sch.mod_pred == "bare" else segs[1:-1]] += n
        mid[w] = v.most_common(1)[0][0] if v else ()
    return mid


# ================================================================ structural parse
class NP:
    __slots__ = ("det", "kind", "idx", "lemma", "rel", "inner")

    def __init__(self, det, kind, idx, lemma):
        self.det, self.kind, self.idx, self.lemma = det, kind, idx, lemma
        self.rel = self.inner = None


class CL:
    __slots__ = ("event", "lemma", "pre", "slots")

    def __init__(self, event, lemma, pre, slots):
        self.event, self.lemma, self.pre, self.slots = event, lemma, pre, slots


def parse_base(lex, sch, toks, i):
    """A bare NP core: [det] noun | noun [det] | proper name."""
    n = len(toks)
    if i >= n:
        return None
    c = lex.cls.get(toks[i])
    if lex.det_pos == "pre" and toks[i] in lex.det and i + 1 < n and lex.cls.get(toks[i + 1]) == ENTITY:
        return NP(toks[i], ENTITY, i + 1, lex.lemma.get(toks[i + 1], toks[i + 1])), i + 2
    if lex.det_pos == "post" and c == ENTITY and i + 1 < n and toks[i + 1] in lex.det:
        return NP(toks[i + 1], ENTITY, i, lex.lemma.get(toks[i], toks[i])), i + 2
    if c == NAME:
        return NP(None, NAME, i, toks[i]), i + 1
    if c == ENTITY:
        return NP(None, ENTITY, i, lex.lemma.get(toks[i], toks[i])), i + 1
    return None


def parse_np(lex, sch, toks, i):
    """NP -> base (RELATOR base)*, folded per np_branch: head-initial makes the FIRST base the outer head,
    head-final makes the LAST one. Same token run, opposite nesting."""
    b = parse_base(lex, sch, toks, i)
    if b is None:
        return None
    bases, rels = [b[0]], []
    j = b[1]
    while j < len(toks) and lex.cls.get(toks[j]) == REL:
        b2 = parse_base(lex, sch, toks, j + 1)
        if b2 is None:
            break
        rels.append(toks[j])
        bases.append(b2[0])
        j = b2[1]
    if sch.np_branch == "right":
        cur = bases[0]
        for r, nxt in zip(rels, bases[1:]):
            cur.rel, cur.inner = r, nxt
            cur = nxt
        return bases[0], j
    cur = bases[-1]
    for r, nxt in zip(reversed(rels), reversed(bases[:-1])):
        cur.rel, cur.inner = r, nxt
        cur = nxt
    return bases[-1], j


def _is_verb_here(lex, toks, j):
    n = len(toks)
    if j < n and lex.cls.get(toks[j]) == EVENT:
        return j, None
    if (j + 1 < n and lex.cls.get(toks[j]) == FUNC and toks[j] not in lex.det
            and lex.cls.get(toks[j + 1]) == EVENT):
        return j + 1, toks[j]
    return None


def _slots_from(lex, sch, toks, j, budget):
    """Every way to read zero or more argument slots starting at j. Slot-taking alternatives come FIRST so the
    maximal reading is found before the empty one; the sentence level then keeps only readings that consume
    every token, which is what disambiguates a marker introducing an NP from one introducing a clause."""
    n = len(toks)
    if budget[0] <= 0:
        return
    budget[0] -= 1
    if j < n:
        w = toks[j]
        c = lex.cls.get(w)
        marked = c == FUNC and w not in lex.det and w != lex.terminator
        # LAZILY: each alternative is expanded only as far as the consumer needs. Collecting the alternatives
        # into a list first enumerated every parse of every embedded clause before returning any of them,
        # which is exponential in embedding depth -- it cost 564 of 1000 cp_recursion items to a budget wall.
        base = j + 1 if marked else j
        for kind, gapped in (("VP", True), ("CL", False)):
            if kind == "VP" and not (marked and base < n and lex.cls.get(toks[base]) == EVENT):
                continue
            for sub, j2 in parses_cl(lex, sch, toks, base, gapped, budget):
                if j2 <= j:
                    continue
                for rest, j3 in _slots_from(lex, sch, toks, j2, budget):
                    yield [(w if marked else None, kind, sub)] + rest, j3
        p = parse_np(lex, sch, toks, base)
        if p is not None and p[1] > j:
            for rest, j3 in _slots_from(lex, sch, toks, p[1], budget):
                yield [(w if marked else None, "NP", p[0])] + rest, j3
    yield [], j


def parses_cl(lex, sch, toks, i, gapped, budget):
    """CLAUSE -> [subject] [marker] EVENT slot*   (verb_pos 'medial')
                [subject] slot* [marker] EVENT    (verb_pos 'final')
    The clause exports a head, which is what lets a clause be an ARGUMENT of another clause."""
    if budget[0] <= 0:
        return
    budget[0] -= 1
    if gapped:
        head_slots, j = [(None, "GAP", None)], i
    else:
        p = parse_np(lex, sch, toks, i)
        if p is None:
            return
        head_slots, j = [(None, "NP", p[0])], p[1]
    if sch.verb_pos == "medial":
        v = _is_verb_here(lex, toks, j)
        if v is None:
            return
        e, pre = v
        for slots, j2 in _slots_from(lex, sch, toks, e + 1, budget):
            yield CL(e, lex.lemma.get(toks[e], toks[e]), pre, head_slots + slots), j2
    else:
        for slots, j2 in _slots_from(lex, sch, toks, j, budget):
            v = _is_verb_here(lex, toks, j2)
            if v is None:
                continue
            e, pre = v
            yield CL(e, lex.lemma.get(toks[e], toks[e]), pre, head_slots + slots), e + 1


def parse_sentence(lex, sch, toks, want=1):
    """Complete parses only: every token consumed. `want` caps how many are collected (2 to detect ambiguity)."""
    budget = [PARSE_BUDGET]
    out = []
    for node, j in parses_cl(lex, sch, toks, 0, False, budget):
        if j == len(toks):
            out.append(node)
            if len(out) >= want:
                break
    return out


def strip_term(lex, s):
    toks = s.split()
    while toks and toks[-1] == lex.terminator:
        toks = toks[:-1]
    return toks


def frame_key(cl):
    return (cl.pre, tuple((m, k) for m, k, _ in cl.slots))


# ================================================================ derivation -> logical form
def ev_np(lex, sch, mid, node, defs, conj):
    """-> the head this NP exports. HEAD-select (np_head) decides whether that is the head noun's variable or
    the dependent's; the modifier predicate template (mod_pred) decides whose LEMMA is spliced into it."""
    if node.kind == NAME:
        own_head, own = ("c", node.lemma), []
    else:
        own_head = ("v", node.idx)
        r = lex.det.get(node.det, "plain") if node.det else "plain"
        if r == "prefix":
            defs.append((node.lemma, node.idx))
            own = []
        elif isinstance(r, tuple):
            own = [(node.lemma, (own_head,)), (r[1], (own_head,))]
        else:
            own = [(node.lemma, (own_head,))]
    if node.rel is None:
        conj.extend(own)
        return own_head
    inner_conj = []
    ihead = ev_np(lex, sch, mid, node.inner, defs, inner_conj)
    dep_lemma = node.inner.lemma
    if sch.mod_pred == "head_lemma":
        pieces = (node.lemma,) + tuple(mid.get(node.rel, ())) + (node.rel,)
    elif sch.mod_pred == "dep_lemma":
        pieces = (dep_lemma,) + tuple(mid.get(node.rel, ())) + (node.rel,)
    else:
        pieces = tuple(mid.get(node.rel, ())) + (node.rel,)
    args = (own_head, ihead) if sch.mod_args == "head_dep" else (ihead, own_head)
    modc = (" . ".join(pieces), args)
    if sch.np_order == "own_rel_inner":
        conj.extend(own + [modc] + inner_conj)
    elif sch.np_order == "own_inner_rel":
        conj.extend(own + inner_conj + [modc])
    else:
        conj.extend([modc] + own + inner_conj)
    return own_head if sch.np_head == "head" else ihead


def ev_cl(lex, sch, mid, node, roles, defs, conj, inherited=None):
    ev = ("v", node.event)
    heads, subconj = [], []
    for m, kind, sub in node.slots:
        c = []
        if kind == "GAP":
            if inherited is None:
                return None
            heads.append(inherited)
            subconj.append(c)
            continue
        if kind == "NP":
            h = ev_np(lex, sch, mid, sub, defs, c)
        else:
            h = ev_cl(lex, sch, mid, sub, roles, defs, c,
                      inherited=(heads[0] if heads else inherited))
            if h is None:
                return None
        heads.append(h)
        subconj.append(c)
    fk = frame_key(node)
    rs = roles.get(fk)
    if rs is None:
        rs = roles.get((fk, node.lemma))
    if rs is None and len(heads) == 1:
        vr = lex.vroles.get(node.lemma)
        if vr and len(vr) == 1:
            rs = (next(iter(vr)),)
    if rs is None:
        rs = roles.get(("__fallback__", fk))
    if rs is None or len(rs) != len(heads):
        return None
    block = [(node.lemma + " . " + r, (ev, h)) for r, h in zip(rs, heads)]
    if sch.cl_order == "subj_first":
        conj.extend(subconj[0] + block + [x for c in subconj[1:] for x in c])
    else:
        conj.extend(block + [x for c in subconj for x in c])
    return ev if sch.cl_head == "event" else heads[0]


def lf_of(lex, sch, mid, roles, node):
    defs, conj = [], []
    if ev_cl(lex, sch, mid, node, roles, defs, conj) is None:
        return None
    return serialize(defs, conj)


def generate(model, s):
    """model = (lex, schema, mid, roles, varconv). -> the logical form, or None if no derivation exists.
    Derivations are always built over TOKEN POSITIONS; varconv only renames the variables on the way out."""
    lex, sch, mid, roles, varconv = model
    ps = parse_sentence(lex, sch, strip_term(lex, s), want=1)
    if not ps:
        return None
    lf = lf_of(lex, sch, mid, roles, ps[0])
    if lf is None:
        return None
    return lf if varconv == "position" else renumber_first_appearance(lf)


# ================================================================ frame -> role induction
def _cl_head(lex, sch, mid, node, inherited):
    """The head a clause EXPORTS -- the event variable, or (head-select) its subject's."""
    if sch.cl_head == "event":
        return ("v", node.event)
    m, kind, sub = node.slots[0]
    if kind == "GAP":
        return inherited
    if kind == "NP":
        return ev_np(lex, sch, mid, sub, [], [])
    return _cl_head(lex, sch, mid, sub, inherited)


def clause_nodes(lex, sch, mid, node, inherited=None):
    """Walk a derivation and yield (clause, slot heads) -- structure only, roles not needed yet."""
    heads = []
    for m, kind, sub in node.slots:
        if kind == "GAP":
            heads.append(inherited)
        elif kind == "NP":
            heads.append(ev_np(lex, sch, mid, sub, [], []))
        else:
            heads.append(_cl_head(lex, sch, mid, sub, heads[0] if heads else inherited))
    out = [(node, heads)]
    for m, kind, sub in node.slots:
        if kind in ("CL", "VP"):
            out.extend(clause_nodes(lex, sch, mid, sub, inherited=(heads[0] if heads else inherited)))
    return out


def gold_roles(lf):
    p = parse_lf(lf)
    if p is None or p[0] == "LAMBDA":
        return None
    m = {}
    for pred, args in p[1]:
        segs = [x.strip() for x in pred.split(" . ")]
        if len(segs) == 2 and len(args) == 2 and args[0][0] == "v":
            m[(args[0][1], args[1])] = segs[1]
    return m


def induce_roles(lex, sch, mid, train):
    byframe = collections.defaultdict(collections.Counter)
    byverb = collections.defaultdict(collections.Counter)
    for s, lf, cat in train:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            continue
        ps = parse_sentence(lex, sch, strip_term(lex, s), want=1)
        g = gold_roles(lf)
        if not ps or g is None:
            continue
        for cl, heads in clause_nodes(lex, sch, mid, ps[0]):
            rs = tuple(g.get((cl.event, h)) for h in heads)
            if any(r is None for r in rs):
                continue
            byframe[frame_key(cl)][rs] += 1
            byverb[(frame_key(cl), cl.lemma)][rs] += 1
    roles = {}
    ambiguous = []
    for f, cc in byframe.items():
        if len(cc) == 1:
            roles[f] = cc.most_common(1)[0][0]
        else:
            ambiguous.append((f, dict(cc)))
    for key, cc in byverb.items():
        if key[0] not in roles:
            roles[key] = cc.most_common(1)[0][0]
    for f, _ in ambiguous:
        roles[("__fallback__", f)] = byframe[f].most_common(1)[0][0]
    return roles, ambiguous


# ================================================================ sound gate and schema search
def reproduce(model, rows):
    ok = wrong = nopar = 0
    for s, lf, cat in rows:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            continue
        g = generate(model, s)
        if g is None:
            nopar += 1
        elif g == norm_lf(lf):
            ok += 1
        else:
            wrong += 1
    return ok, wrong, nopar


PARSE_DIMS = ("np_branch", "verb_pos")          # the only dimensions that change the PARSE; the rest only
                                                # change how a fixed derivation is read out as a logical form


def _parse_rows(lex, sch, rows):
    return [(parse_sentence(lex, sch, strip_term(lex, s), want=1) or [None])[0] for s, _, _ in rows]


def _score_parsed(lex, sch, rows, nodes):
    """Reproduction count for this schema, reusing derivations already parsed for its (np_branch, verb_pos)."""
    mid = induce_relmid(lex, rows, sch)
    byframe = collections.defaultdict(collections.Counter)
    byverb = collections.defaultdict(collections.Counter)
    for (s, lf, cat), node in zip(rows, nodes):
        if node is None:
            continue
        g = gold_roles(lf)
        if g is None:
            continue
        for cl, heads in clause_nodes(lex, sch, mid, node):
            rs = tuple(g.get((cl.event, h)) for h in heads)
            if not any(r is None for r in rs):
                byframe[frame_key(cl)][rs] += 1
                byverb[(frame_key(cl), cl.lemma)][rs] += 1
    roles = {}
    for f, cc in byframe.items():
        if len(cc) == 1:
            roles[f] = cc.most_common(1)[0][0]
        else:
            roles[("__fallback__", f)] = cc.most_common(1)[0][0]
    for key, cc in byverb.items():
        if key[0] not in roles:
            roles[key] = cc.most_common(1)[0][0]
    ok = 0
    for (s, lf, cat), node in zip(rows, nodes):
        if node is not None and lf_of(lex, sch, mid, roles, node) == norm_lf(lf):
            ok += 1
    return ok


def search_schema(lex, train, sample=350, verbose=False):
    """EXHAUSTIVE over the schema space, scored by how much of train the grammar REPRODUCES exactly -- the same
    search-a-small-space-and-keep-what-reproduces mechanism Stage 3a used for the two order policies, extended
    to the structural dimensions rather than special-cased.

    Exhaustive is affordable because only np_branch and verb_pos change the PARSE: derivations are computed
    once per (np_branch, verb_pos) and reused across the 144 read-out combinations. Coordinate descent was
    tried first and is NOT sufficient -- on adversary grammar 2 it stranded at 248/350 because np_branch,
    np_head, mod_args and np_order have to move together, a mirror-image local optimum no single move escapes."""
    rows = [r for r in train if r[2] != "primitive"][:sample]
    others = [d for d in Schema.DIMS if d not in PARSE_DIMS]
    best = (-1, Schema())          # if NOTHING parses -- e.g. variables are not positions at all -- the
                                   # default is returned and the caller's reproduction gate rejects it
    evals = 0
    combos = [{}]
    for nb in Schema.SPACE["np_branch"]:
        for vp in Schema.SPACE["verb_pos"]:
            nodes = _parse_rows(lex, Schema(np_branch=nb, verb_pos=vp), rows)
            if not any(n is not None for n in nodes):
                continue
            combos = [{}]
            for d in others:
                combos = [dict(c, **{d: v}) for c in combos for v in Schema.SPACE[d]]
            for c in combos:
                sch = Schema(np_branch=nb, verb_pos=vp, **c)
                sc = _score_parsed(lex, sch, rows, nodes)
                evals += 1
                if sc > best[0]:
                    best = (sc, sch)
    if verbose:
        print(f"  schema search: {evals} of {2*2*len(combos)} combinations on {len(rows)} rows, "
              f"best reproduces {best[0]}/{len(rows)}\n  {best[1]}")
    return best[1], best[0], len(rows)


def _induce_positional(train, verbose=False):
    """Everything downstream of the alignment: variables are already token positions here."""
    lex = induce_lexicon(train)
    sch, sc, ns = search_schema(lex, train, verbose=verbose)
    mid = induce_relmid(lex, train, sch)
    roles, ambiguous = induce_roles(lex, sch, mid, train)
    if verbose:
        print(f"  classes {dict(collections.Counter(lex.cls.values()))}   terminator {lex.terminator!r}")
        print(f"  determiners ({lex.det_pos}-nominal) {lex.det}   relators {mid}")
        print(f"  frames: {len(roles)} entries, frame-ambiguous {len(ambiguous)}")
        for f, cc in ambiguous[:3]:
            print(f"    AMBIGUOUS {f} -> {cc}")
    return lex, sch, mid, roles


def induce(train, verbose=False, gate=0.99):
    """-> model = (lex, schema, mid, roles, varconv).

    The VARIABLE CONVENTION is the last thing that was an assumption rather than an induction. COGS numbers
    variables by token position, which hands the induction its token<->predicate alignment; Stage 3b part C
    measured what that was worth (EM 1.000 -> 0.000 under first-appearance numbering). So it is now chosen the
    same way everything else is: try reading variables AS positions, and if that fails to reproduce train,
    RECOVER the alignment from co-occurrence (cogs_align) and rewrite train into positional form first.

    Only rows whose alignment is UNAMBIGUOUS are used for induction -- learning from a row whose alignment was
    settled by a tie-break would be learning from a guess, and the fraction dropped is reported."""
    model = _induce_positional(train, verbose=verbose) + ("position",)
    ok, wrong, nopar = reproduce(model, train)
    frac = ok / max(ok + wrong + nopar, 1)
    if frac >= gate:
        if verbose:
            print(f"  variable convention: POSITION (reproduces {frac:.4f} of train as-is)")
        return model
    if verbose:
        print(f"  variable convention: positions reproduce only {frac:.4f} -> recovering the ALIGNMENT")
    anchor, astats = associate(train, verbose=verbose)
    rows, hows, st = to_positional(train, anchor, verbose=verbose, oracle=False)
    fit = [r for r, h in zip(rows, hows) if h in ("unique", "lexicon")]
    if verbose:
        n = st["unique"] + st["tiebreak"] + st["failed"]
        print(f"  inducing from the {st['unique']} unambiguously aligned rows of {n} "
              f"({st['unique']/max(n,1):.4f}); {st['tiebreak']} tie-broken rows and {st['failed']} failures"
              f" are DROPPED, not guessed")
    return _induce_positional(fit, verbose=verbose) + ("first_appearance",)


class Engine:
    """COMMIT on a derivation, ABSTAIN otherwise. No probabilistic output, as in Stages 1-2."""

    def __init__(self, train):
        self.model = induce(train)

    def predict(self, s):
        g = generate(self.model, s)
        return (g, "commit") if g is not None else (None, "hard")
