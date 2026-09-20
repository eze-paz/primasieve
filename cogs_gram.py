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
from core.search import exhaustive
from core.tolerance import induce_eps, LADDER as EPS_LADDER_CORE
from core.vote import plurality, decisive_purity

ENTITY, NAME, EVENT, REL, FUNC = "ENTITY", "NAME", "EVENT", "REL", "FUNC"
PARSE_BUDGET = 20000
EPS_LADDER = EPS_LADDER_CORE      # from core.tolerance: one ladder, shared with Phase 6's mechanism


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
        self.terminator = None      # kept for compatibility: the most frequent terminator
        self.terminators = set()    # STAGE 4a: English has more than one (. and ?). A single-terminator rule
                                    # returned None on SLOG (`.` ends 92.7% < 95%) and killed every parse.
        self.rc_markers = set()     # functors introducing a RELATIVE CLAUSE on the preceding noun ('that')
        self.rc_mid = ()            # the constant segments of the noun->clause modifier predicate ('nmod',)
        self.wh = {}                # fronted question words -> the constant they denote ('Who' -> '?')
        self.rel_segs = {}       # relator word -> the observed full predicate segment lists
        self.vroles = {}         # verb lemma -> roles from its own LAMBDA lexicon row
        self.varity = {}
        # STAGE 4b -- open vocabulary. Suffix rules (surface suffix -> lemma suffix) induced from the lexicon's
        # own surface/lemma pairs, per class; unimorph is used only as an ORACLE to score them, never as input.
        self.open_vocab = True
        self.rules = {ENTITY: [], EVENT: []}
        # STAGE 5. A MARKER is a unary predicate that is no token's lemma, on an entity or event variable,
        # triggered by a functor: an adjective (A2 <- a2), a quantifier (FORALL <- every), negation (NOT <- not).
        self.emark = {}          # functor token -> marker predicate contributed on the FOLLOWING noun's var
        self.emark_det = set()   # markers that also stand in for a determiner (a quantifier: no det, no def)
        self.vmark = {}          # functor token -> marker predicate contributed on the EVENT's var
        self.coord = set()       # coordinator tokens joining two same-type constituents
        self.senses = {}         # word -> set of classes it is indexed under (a homograph has >1)
        self.adj = {}            # ADJECTIVE token -> the predicate it contributes on the FOLLOWING head noun
                                 # (positive signal: an EXTRA unary on a head's variable, not "no token's
                                 # lemma"). Allows a HOMOGRAPH -- a word that is a noun head in one place and an
                                 # adjective in another -- because the predicate may be the word's own lemma.

    def unknown(self, w):
        return self.open_vocab and w not in self.cls and w not in self.terminators

    def has_sense(self, w, cls):
        """A homograph (duck = noun AND verb) is indexed under EACH of its senses; position disambiguates."""
        return cls in self.senses.get(w, {self.cls.get(w)})

    def lemma_of(self, w, cls=None):
        """Known word -> its lemma. Unknown word -> the best-supported suffix rule of the guessed class, else
        the surface form itself (which is exactly right for COGS nouns: `monastery` -> monastery)."""
        if w in self.lemma:
            return self.lemma[w]
        for sfx, lsfx, n in self.rules.get(cls, []):
            if sfx and w.endswith(sfx) and len(w) > len(sfx) + 1:
                return w[:len(w) - len(sfx)] + lsfx
        return w


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


def induce_lexicon(train, eps=0.0):
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
    # TOLERANCE (Phase 6). "A functor is a word that appears in NO logical form" is an EXACT test wearing the
    # clothes of a vote: one corrupted row gives `d0` a single spurious ENTITY vote and it stops being a
    # functor, which empties the determiner set and makes every sentence unparseable. The tolerant form asks
    # whether its votes are NEGLIGIBLE against its occurrences.
    for w in seen:
        if sum(votes[w].values()) <= eps * seen[w]:
            lex.cls[w] = FUNC
    # PLURALITY, and Stage 3d measured what that costs. This is where the only confabulations in the whole
    # noise experiment come from: a rare noun in a mispaired row gets `tomb` read as the lemma `like`, or
    # `cobra` as `boy`, and the engine then commits a confidently wrong logical form. Two decisive-vote
    # replacements were tried and BOTH are far worse -- purity (winner holds >= 1-eps of the votes) and a
    # margin over the runner-up each drop so many words that exact match falls to 0.04-0.23 at 5% corruption,
    # because dropping a word makes every sentence containing it abstain. So plurality stands, the
    # confabulation onset it causes is MEASURED (~10% corruption on real COGS, reported in cogs_stage3d.py)
    # instead of argued away, and closing it is the open item.
    for w, cc in votes.items():
        if lex.cls.get(w) != FUNC:
            lex.cls[w] = cc.most_common(1)[0][0]
        # MULTIPLE SENSES per surface form (duck = noun AND verb). Keep every class whose support is a real
        # share of the word's occurrences, not just the majority -- a homograph is INDEXED under each of its
        # senses, and the parser picks the sense by POSITION (after a determiner -> the entity sense; in the
        # verb slot -> the event sense), the same way the noun/adjective homograph is disambiguated.
        tot = sum(cc.values())
        lex.senses[w] = {c for c, k in cc.items() if k >= max(3, 0.15 * tot)} or {lex.cls.get(w)}
    for w, cc in lemvote.items():
        lex.lemma[w] = cc.most_common(1)[0][0]
    for w, cc in relsegs.items():
        lex.rel_segs[w] = cc
    # likewise the terminator: `n == seen[w]` demands it occur NOWHERE but sentence-finally, so a single
    # corrupted row that moves it inside a sentence removes the terminator entirely
    # terminators = tokens that end sentences and occur (almost) nowhere else. A SET, not a singleton, and
    # decided BEFORE class: the question constant `?` in the logical form collides with the punctuation token
    # `?`, which had been collecting NAME votes and so was neither a terminator nor "absent from the sentence".
    for w, n in lastvote.items():
        if n >= 20 and seen[w] - n <= eps * max(seen[w], 1):
            lex.terminators.add(w)
            lex.cls[w] = FUNC
    lex.terminator = max(lex.terminators, key=lambda w: lastvote[w]) if lex.terminators else None
    _induce_determiners(lex, train, eps)
    _induce_gap_constructions(lex, train)
    _induce_suffix_rules(lex)
    _induce_markers(lex, train)
    return lex


def _induce_markers(lex, train):
    """Markers = unary predicates that are no token's lemma. Co-occurrence is counted PER ROW (necessity is a
    set fact, not a multiplicity), the trigger is EVERY necessary functor, and a coordinator must join two
    flanks that fill the SAME (event, role) -- an argument marker like `to` introduces a different role and is
    therefore not a coordinator."""
    lemmas = set(lex.lemma.values())
    seen = collections.Counter()
    adjcand = collections.defaultdict(collections.Counter)   # token -> contributed adjective predicate counts
    adjtok = collections.Counter()                           # token -> times it acted as a pre-nominal modifier
    coa = collections.defaultdict(collections.Counter)
    target = collections.defaultdict(collections.Counter)
    det_like = collections.defaultdict(lambda: [0, 0])
    coordv = collections.Counter()
    for toks, defs, conj in _rows(train):
        ts = set(toks)
        for w in ts:
            seen[w] += 1
        markers_here = set()
        role_args = collections.defaultdict(list)     # (event, role predicate) -> [arg token positions]
        unary_on = collections.defaultdict(list)      # variable position -> [predicates] (for EXTRA detection)
        for pred, args in conj:
            segs = [x.strip() for x in pred.split(" . ")]
            if len(segs) == 1 and len(args) == 1 and args[0][0] == "v":
                unary_on[args[0][1]].append(segs[0])
                if segs[0] not in lemmas:
                    j = args[0][1]
                    if j < len(toks):
                        markers_here.add(segs[0])
                        target[segs[0]][lex.cls.get(toks[j])] += 1
                        left2 = (j >= 1 and toks[j - 1] in lex.det) or (j >= 2 and toks[j - 2] in lex.det)
                        det_like[segs[0]][0 if left2 else 1] += 1
            elif len(segs) == 2 and len(args) == 2 and args[0][0] == "v" and args[1][0] == "v":
                role_args[(args[0][1], pred)].append(args[1][1])
        # ADJECTIVE: a head noun at j whose variable carries a unary predicate that is NOT its own lemma. That
        # extra predicate is contributed by the pre-nominal token(s) before j (skipping a determiner). This is
        # a POSITIVE signal keyed on position, so it survives a homograph (predicate == the word's noun lemma).
        for j, preds in unary_on.items():
            if j >= len(toks):
                continue
            selfl = lex.lemma.get(toks[j])
            if selfl is None or selfl not in preds:
                continue                              # j is not acting as a head noun here
            k = j - 1
            if k >= 0 and toks[k] in lex.det:
                k -= 1
            for P in preds:
                if P == selfl:
                    continue
                if 0 <= k < len(toks):
                    adjcand[toks[k]][P] += 1
                    adjtok[toks[k]] += 1
        for m in markers_here:
            for w in ts:                              # co-occurrence, ONCE per row
                coa[m][w] += 1
        for (_ev, _pred), positions in role_args.items():
            if len(positions) < 2:
                continue
            positions = sorted(positions)             # a distributed role: two+ heads under one predicate
            for lo, hi in zip(positions, positions[1:]):
                for k in range(lo + 1, hi):
                    if lex.cls.get(toks[k]) == FUNC and toks[k] not in lex.det:
                        coordv[toks[k]] += 1
    for m in set(target):
        trig = [w for w in coa[m] if coa[m][w] == seen[w] and lex.cls.get(w) == FUNC]
        if not trig:
            continue
        tgt = target[m].most_common(1)[0][0]
        if tgt == EVENT:
            for w in trig:                            # `did` AND `not` both trigger NOT -> consume the run
                lex.vmark[w] = m
        elif tgt == ENTITY:
            w = min(trig, key=lambda w: seen[w])      # the most specific necessary functor is the adjective
            lex.emark[w] = m
            if det_like[m][1] > det_like[m][0]:
                lex.emark_det.add(w)
    for w, cc in adjcand.items():
        P, c = cc.most_common(1)[0]
        # a modifier token is an ADJECTIVE if one predicate dominates its pre-nominal contributions; a
        # determiner (whose realization already adds an inline marker like DEFMARK) is excluded -- that marker
        # is not an adjective, it is the determiner's own definiteness realization.
        if c >= 10 and c >= 0.9 * adjtok[w] and w not in lex.det and w not in lex.emark_det:
            lex.adj[w] = P
    for w, n in coordv.items():
        if (n >= 10 and lex.cls.get(w) == FUNC and w not in lex.det and w not in lex.emark
                and w not in lex.vmark and w not in lex.adj):
            lex.coord.add(w)


def _induce_suffix_rules(lex, min_support=3):
    """(surface suffix -> lemma suffix) per class, from the lexicon's own pairs, ranked by support. `rolled` ->
    roll gives ('ed', ''); `liked` -> like gives ('d', ''); an irregular pair (`ate` -> eat) yields a rule with
    support 1 and is dropped. Identity is the implicit last rule."""
    cnt = {ENTITY: collections.Counter(), EVENT: collections.Counter()}
    for w, lem in lex.lemma.items():
        c = lex.cls.get(w)
        if c not in cnt or w == lem:
            continue
        k = 0
        while k < min(len(w), len(lem)) and w[k] == lem[k]:
            k += 1
        if k >= 2:
            cnt[c][(w[k:], lem[k:])] += 1
    for c in cnt:
        # LONGEST suffix first, support second: `liked` must meet ('d','') before ('ed','') or it becomes `lik`
        lex.rules[c] = sorted([(a, b, n) for (a, b), n in cnt[c].most_common() if n >= min_support],
                              key=lambda t: (-len(t[0]), -t[2]))


def _induce_gap_constructions(lex, train):
    """STAGE 4a. Two constructions that COMPOSE from the existing GAP combinator (control already filled a
    gap with an inherited head):
      RELATIVE CLAUSE  noun . mid ( x_noun , x_event ): the noun's variable fills a gap in the clause that a
                       functor right after the noun introduces -> lex.rc_markers, lex.rc_mid
      WH-QUESTION      a constant argument (`?`) that is NO token of the sentence, co-occurring exactly with a
                       fronted word (`Who`) -> lex.wh, by the same necessity+cover test as core.align
    Neither adds a combinator type; both add an attachment site for one that exists."""
    rcm, rcmid = collections.Counter(), collections.Counter()
    whco = collections.defaultdict(collections.Counter)
    tokn = collections.Counter()
    for toks, defs, conj in _rows(train):
        ts = set(toks)
        for w in ts:
            tokn[w] += 1
        for pred, args in conj:
            segs = [x.strip() for x in pred.split(" . ")]
            if len(segs) >= 2 and len(args) == 2 and args[0][0] == "v" and args[1][0] == "v":
                i, j = args[0][1], args[1][1]
                if (i < len(toks) and j < len(toks) and lex.cls.get(toks[i]) == ENTITY
                        and lex.cls.get(toks[j]) == EVENT and lex.lemma.get(toks[i]) == segs[0]
                        and i + 1 < len(toks) and lex.cls.get(toks[i + 1]) == FUNC
                        and toks[i + 1] not in lex.det):
                    rcm[toks[i + 1]] += 1
                    rcmid[tuple(segs[1:])] += 1
            for a in args:
                if a[0] == "c" and a[1] not in (ts - lex.terminators):
                    for w in ts - lex.terminators:
                        whco[a[1]][w] += 1
    for w, n in rcm.items():
        if n >= 10:
            lex.rc_markers.add(w)
    if rcmid:
        lex.rc_mid = rcmid.most_common(1)[0][0]
    first = collections.Counter()
    for toks, defs, conj in _rows(train):
        first[toks[0]] += 1
    for c, cc in whco.items():
        for w, n in cc.items():
            # w occurs ONLY with this constant AND is FRONTED (sentence-initial): `did` co-occurs only with
            # `?` too, but it is an auxiliary in second position, not the question word
            if n == tokn[w] and lex.cls.get(w) == FUNC and n >= 10 and first[w] >= 0.9 * tokn[w]:
                lex.wh[w] = c


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


def _induce_determiners(lex, train, eps=0.0):
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
            if cover[d][w] >= 10 and c >= (1 - max(eps, 0.05)) * cover[d][w]:
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
    __slots__ = ("det", "kind", "idx", "lemma", "rel", "inner", "rc", "marks", "conj_heads", "amarks")

    def __init__(self, det, kind, idx, lemma):
        self.det, self.kind, self.idx, self.lemma = det, kind, idx, lemma
        self.rel = self.inner = None
        self.rc = None              # (marker, gapped CL) -- a relative clause modifying this NP's head
        self.marks = ()             # marker predicates contributed on this head (adjective / quantifier)
        self.amarks = ()            # adjective predicates contributed on this head
        self.conj_heads = None      # for a coordinated NP: the list of member NP nodes


class CL:
    __slots__ = ("event", "lemma", "pre", "slots", "front")

    def __init__(self, event, lemma, pre, slots, front=None):
        self.event, self.lemma, self.pre, self.slots = event, lemma, pre, slots
        self.front = front          # (wh NP node, marker) for a fronted question, else None


def parse_base(lex, sch, toks, i):
    """A bare NP core: [det|quant] [adjective*] noun | noun [det] | proper name. Entity-markers (adjectives,
    quantifiers) are consumed here and attached to the head's variable (STAGE 5)."""
    n = len(toks)
    if i >= n:
        return None
    if lex.det_pos == "pre":
        # [determiner | quantifier] [adjective*] noun -- markers attach to the head's variable
        marks = []
        det = None
        k = i
        if k < n and toks[k] in lex.emark_det:                # a quantifier stands in for a determiner
            marks.append(lex.emark[toks[k]]); k += 1
        elif k < n and toks[k] in lex.det and not (k + 1 < n and toks[k + 1] in lex.coord):
            det = toks[k]; k += 1
        while k < n and toks[k] in lex.emark and toks[k] not in lex.emark_det:
            marks.append(lex.emark[toks[k]]); k += 1        # quantifier-style entity markers
        # ADJECTIVES: consume pre-nominal adjective tokens, but ONLY while a head noun still follows -- this is
        # what disambiguates a homograph (n0 as adjective before another noun vs n0 as the head itself).
        amarks = []
        while (k < n and toks[k] in lex.adj and k + 1 < n
               and (lex.has_sense(toks[k + 1], ENTITY) or toks[k + 1] in lex.adj
                    or (lex.unknown(toks[k + 1]) and not toks[k + 1][:1].isupper()))):
            amarks.append(lex.adj[toks[k]]); k += 1
        if k < n and (lex.has_sense(toks[k], ENTITY) or (lex.unknown(toks[k]) and not toks[k][:1].isupper())):
            if det is not None or marks or amarks:
                node = NP(det, ENTITY, k, lex.lemma_of(toks[k], ENTITY))
                node.marks = tuple(marks)
                node.amarks = tuple(amarks)
                return node, k + 1
    else:
        c = lex.cls.get(toks[i])
        if c == ENTITY and i + 1 < n and toks[i + 1] in lex.det:
            return NP(toks[i + 1], ENTITY, i, lex.lemma.get(toks[i], toks[i])), i + 2
    if toks[i] in lex.wh:
        return NP(None, NAME, i, lex.wh[toks[i]]), i + 1
    c = lex.cls.get(toks[i])
    if c == NAME or (lex.unknown(toks[i]) and toks[i][:1].isupper()):
        return NP(None, NAME, i, toks[i]), i + 1
    if lex.has_sense(toks[i], ENTITY):
        return NP(None, ENTITY, i, lex.lemma.get(toks[i], toks[i])), i + 1
    return None


def _coord_np(lex, sch, toks, i, budget):
    """[base] (coord [base])+ as ONE NP exporting every member's head, so a role distributes over all."""
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    b = parse_base(lex, sch, toks, i)
    if b is None:
        return None
    members = [b[0]]
    j = b[1]
    while j < len(toks) and toks[j] in lex.coord:
        b2 = parse_base(lex, sch, toks, j + 1)
        if b2 is None:
            break
        members.append(b2[0]); j = b2[1]
    if len(members) == 1:
        return None
    node = NP(None, members[0].kind, members[0].idx, members[0].lemma)
    node.conj_heads = members
    return node, j


def _run(lex, sch, toks, i):
    """The base run of an NP: base (RELATOR base)*. -> (bases, rels, j) or None."""
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
    return bases, rels, j


def _fold(sch, bases, rels):
    """Fresh nodes each call (alternatives must not share mutable structure). -> (head, nearest noun)."""
    bs = [NP(x.det, x.kind, x.idx, x.lemma) for x in bases]
    for a, b in zip(bs, bases):
        a.marks = b.marks
        a.amarks = b.amarks
    if sch.np_branch == "right":
        for k, r in enumerate(rels):
            bs[k].rel, bs[k].inner = r, bs[k + 1]
        return bs[0], bs[-1]
    for k, r in enumerate(rels):
        bs[k + 1].rel, bs[k + 1].inner = r, bs[k]
    return bs[-1], bs[-1]


def parses_np(lex, sch, toks, i, budget=None):
    if budget is None:
        budget = [PARSE_BUDGET]
    if budget[0] <= 0:
        return
    budget[0] -= 1
    c = _coord_np(lex, sch, toks, i, budget)
    if c is not None:
        yield c
        return
    """NP -> base (RELATOR base)* [RELATIVE CLAUSE]. A GENERATOR, because a relative clause's extent is
    genuinely ambiguous at the string level (`the rose that the cat studied to Jack`: is `to Jack` the
    clause's or the matrix verb's?). Every reading is yielded; FRAME LICENSING + UNIQUENESS decide
    downstream: a reading whose clauses use frames never seen in training produces no logical form, and if
    more than one licensed reading survives the engine ABSTAINS. A fixed extent convention (min / max) was
    tried first and is wrong both ways -- 0.563 and 0.858 exact match, with confabulation either way."""
    r = _run(lex, sch, toks, i)
    if r is None:
        return
    bases, rels, j = r
    if j < len(toks) and toks[j] in lex.rc_markers:
        n = 0
        for sub, j2 in parses_cl(lex, sch, toks, j + 1, "auto", budget):
            head, target = _fold(sch, bases, rels)
            target.rc = (toks[j], sub)                 # attaches to the nearest noun
            yield head, j2
            n += 1
            if n >= 6:
                break
    head, _ = _fold(sch, bases, rels)
    yield head, j                                      # no-RC reading: the marker may open a matrix clause


def parse_np(lex, sch, toks, i):
    """First reading only -- for callers that need one node, never for deciding between readings."""
    for out in parses_np(lex, sch, toks, i):
        return out
    return None


def _is_verb_here(lex, toks, j):
    n = len(toks)

    def verbish(k):
        w = toks[k]
        return lex.has_sense(w, EVENT) or (lex.unknown(w) and not w[:1].isupper())

    if j < n and verbish(j):
        return j, None
    if (j + 1 < n and lex.cls.get(toks[j]) == FUNC and toks[j] not in lex.det and verbish(j + 1)):
        return j + 1, toks[j]
    k = j
    seenmark = None
    while k < n and toks[k] in lex.vmark:
        seenmark = toks[k]; k += 1
    if seenmark is not None and k < n and verbish(k):
        return k, seenmark
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
        for npn, j2 in parses_np(lex, sch, toks, base, budget):
            if j2 <= j:
                continue
            for rest, j3 in _slots_from(lex, sch, toks, j2, budget):
                yield [(w if marked else None, "NP", npn)] + rest, j3
    yield [], j


def parses_cl(lex, sch, toks, i, gapped, budget):
    """CLAUSE -> [subject] [marker] EVENT slot*   (verb_pos 'medial')
                [subject] slot* [marker] EVENT    (verb_pos 'final')
    gapped: False | True/'subj' (subject gap, as for control) | 'post' (an argument gap after the verb)
    | 'auto' (by lookahead: a verb right here means the SUBJECT is the gap).
    The clause exports a head, which is what lets a clause be an ARGUMENT of another clause."""
    if gapped == "auto":
        gapped = "subj" if _is_verb_here(lex, toks, i) else "post"
    if gapped is True:
        gapped = "subj"
    if budget[0] <= 0:
        return
    budget[0] -= 1
    def with_gap(slots):
        """A post-verbal GAP sits where the missing argument sits in the un-gapped frame -- the theme before a
        `to`-phrase, the recipient before a theme. That position is part of the FRAME, so every position is
        offered and the frame table decides which are attested. Fixing it canonically last produced 35
        order-only confabulations on SLOG's relative clauses."""
        if gapped != "post":
            yield slots
            return
        for k in range(len(slots), -1, -1):
            yield slots[:k] + [(None, "GAP", None)] + slots[k:]

    def after_subject(head_slots, j):
        if sch.verb_pos == "medial":
            v = _is_verb_here(lex, toks, j)
            if v is None:
                return
            e, pre = v
            for slots, j2 in _slots_from(lex, sch, toks, e + 1, budget):
                for sl in with_gap(slots):
                    yield CL(e, lex.lemma_of(toks[e], EVENT), pre, head_slots + sl), j2
        else:
            for slots, j2 in _slots_from(lex, sch, toks, j, budget):
                v = _is_verb_here(lex, toks, j2)
                if v is None:
                    continue
                e, pre = v
                for sl in with_gap(slots):
                    yield CL(e, lex.lemma_of(toks[e], EVENT), pre, head_slots + sl), e + 1

    if gapped == "subj":
        yield from after_subject([(None, "GAP", None)], i)
    else:
        for npn, j in parses_np(lex, sch, toks, i, budget):
            yield from after_subject([(None, "NP", npn)], j)


def parse_sentence(lex, sch, toks, want=1, cap=None):
    """Complete parses only: every token consumed. `want` caps how many are collected (2 to detect ambiguity).

    A hard iteration cap makes the parser FAIL CLOSED: the coordination/marker generators are not all
    budget-threaded, so a genuinely ambiguous input (a homograph -- a word that is a noun in one place and an
    adjective in another -- is the case that hits this) can explode the search tree. Capping the yielded
    partial parses turns that into an ABSTENTION, never a hang."""
    lim = cap if cap is not None else PARSE_BUDGET
    budget = [lim]
    out = []
    seen_parts = 0
    for node, j in parses_cl(lex, sch, toks, 0, False, budget):
        seen_parts += 1
        if seen_parts > min(12000, lim):    # fail closed on a search explosion (a homograph); the SCHEMA
            return []                       # SEARCH passes a small cap so ambiguity is cut off cheaply
        if j == len(toks):
            out.append(node)
            if len(out) >= want:
                break
    if not out and toks and toks[0] in lex.wh:
        # FRONTED QUESTION: the wh phrase fills a GAP in the clause that follows, optionally after a functor
        # (`Who did a bird love`). Same combinator as the relative clause, different attachment site.
        wh = NP(None, NAME, 0, lex.wh[toks[0]])
        k, mark = 1, None
        if k < len(toks) and lex.cls.get(toks[k]) == FUNC and toks[k] not in lex.det and toks[k] not in lex.wh:
            mark, k = toks[k], k + 1
        for node, j in parses_cl(lex, sch, toks, k, "auto", [PARSE_BUDGET]):
            if j == len(toks):
                node.front = (wh, mark)
                out.append(node)
                break
    return out


def strip_term(lex, s):
    toks = s.split()
    while toks and toks[-1] in lex.terminators:
        toks = toks[:-1]
    return toks


def frame_key(cl):
    return (cl.pre, tuple((m, k) for m, k, _ in cl.slots), cl.front[1] if cl.front else None)


# ================================================================ derivation -> logical form
class _NoDerivation(Exception):
    pass


def _np_export(lex, sch, mid, node):
    return ("c", node.lemma) if node.kind == NAME else ("v", node.idx)


def ev_np(lex, sch, mid, node, defs, conj):
    """-> the head this NP exports. HEAD-select (np_head) decides whether that is the head noun's variable or
    the dependent's; the modifier predicate template (mod_pred) decides whose LEMMA is spliced into it."""
    if node.conj_heads is not None:
        for mem in node.conj_heads:
            ev_np(lex, sch, mid, mem, defs, conj)
        return ("multi", tuple(_np_export(lex, sch, mid, m) for m in node.conj_heads))
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
    own = own + [(m, (own_head,)) for m in node.marks]          # quantifier / inline markers
    own = own + [(m, (own_head,)) for m in node.amarks]         # adjective predicates on the head
    if node.rc is not None:
        # noun . mid ( head , event ) then the clause's conjuncts, with the GAP filled by this head
        marker, sub = node.rc
        rc_conj = []
        ev = ev_cl(lex, sch, mid, sub, ev_np.roles, defs, rc_conj, inherited=own_head)
        if ev is None:
            raise _NoDerivation()
        own = own + [(" . ".join((node.lemma,) + tuple(lex.rc_mid)), (own_head, ev))] + rc_conj
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
    ev_np.roles = roles
    if node.front is not None:
        inherited = ("c", node.front[0].lemma)            # the fronted wh phrase fills the gap
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
    if rs is None and node.lemma in lex.lemma.values():
        rs = roles.get(("__fallback__", fk))     # the plurality guess is allowed only for a KNOWN verb
    if rs is None or len(rs) != len(heads):
        return None
    block = []
    for r, h in zip(rs, heads):
        if isinstance(h, tuple) and h and h[0] == "multi":
            for hh in h[1]:
                block.append((node.lemma + " . " + r, (ev, hh)))
        else:
            block.append((node.lemma + " . " + r, (ev, h)))
    if node.pre in lex.vmark:
        block.append((lex.vmark[node.pre], (ev,)))     # negation: the event marker sits IN the role block
    if sch.cl_order == "subj_first":
        conj.extend(subconj[0] + block + [x for c in subconj[1:] for x in c])
    else:
        conj.extend(block + [x for c in subconj for x in c])
    return ev if sch.cl_head == "event" else heads[0]


def lf_of(lex, sch, mid, roles, node):
    defs, conj = [], []
    try:
        if ev_cl(lex, sch, mid, node, roles, defs, conj) is None:
            return None
    except _NoDerivation:
        return None
    return serialize(defs, conj)


def generate(model, s):
    """model = (lex, schema, mid, roles, varconv). -> the logical form, or None if no derivation exists.
    Derivations are always built over TOKEN POSITIONS; varconv only renames the variables on the way out."""
    lex, sch, mid, roles, varconv = model
    readings = {}
    for p in parse_sentence(lex, sch, strip_term(lex, s), want=12):
        lf = lf_of(lex, sch, mid, roles, p)
        if lf is not None:                             # a reading using an unseen FRAME is not licensed
            readings.setdefault(lf, p)
    if len(readings) > 1:
        # SUBCATEGORIZATION as a tie-break only: among competing readings keep those whose every (frame, verb)
        # pair was attested in training. A SINGLE novel reading is never rejected here -- that is how a verb
        # seen only intransitively still parses transitively (the COGS lexical-generalization categories).
        att = roles.get("__attested__", frozenset())
        keep = {lf: p for lf, p in readings.items()
                if all((frame_key(cl), cl.lemma) in att for cl, _ in clause_nodes(lex, sch, mid, p))}
        if keep:
            readings = keep
    if len(readings) != 1:
        return None                                    # none, or a GENUINE ambiguity: abstain, never pick
    lf = next(iter(readings))
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
        return _np_head_only(lex, sch, mid, sub)
    return _cl_head(lex, sch, mid, sub, inherited)


def _walk_np(np):
    while np is not None:
        yield np
        np = np.inner


def _np_rcs(np):
    """(relative-clause node, filler head) for every NP in a modifier chain."""
    return [(n.rc[1], ("c", n.lemma) if n.kind == NAME else ("v", n.idx)) for n in _walk_np(np) if n.rc]


def _np_head_only(lex, sch, mid, np):
    """An NP's exported head WITHOUT evaluating its relative clauses (roles may not exist yet)."""
    saved = [(n, n.rc) for n in _walk_np(np)]
    for n, _ in saved:
        n.rc = None
    try:
        return ev_np(lex, sch, mid, np, [], [])
    finally:
        for n, rc in saved:
            n.rc = rc


def clause_nodes(lex, sch, mid, node, inherited=None):
    """Walk a derivation and yield (clause, slot heads) -- structure only, roles not needed yet.
    Relative clauses inside NPs are walked too, their GAP filled by the NP they modify; a fronted wh phrase
    fills the gap of the clause it fronts."""
    if node.front is not None:
        inherited = ("c", node.front[0].lemma)
    heads = []
    for m, kind, sub in node.slots:
        if kind == "GAP":
            heads.append(inherited)
        elif kind == "NP":
            heads.append(_np_head_only(lex, sch, mid, sub))
        else:
            heads.append(_cl_head(lex, sch, mid, sub, heads[0] if heads else inherited))
    out = [(node, heads)]
    for m, kind, sub in node.slots:
        if kind in ("CL", "VP"):
            out.extend(clause_nodes(lex, sch, mid, sub, inherited=(heads[0] if heads else inherited)))
        elif kind == "NP":
            for rc, filler in _np_rcs(sub):
                out.extend(clause_nodes(lex, sch, mid, rc, inherited=filler))
    return out


def gold_order(lf, skip_role=None):
    """event -> its arguments in GOLD ORDER (2-segment binaries only, the RC modifier excluded)."""
    p = parse_lf(lf)
    if p is None or p[0] == "LAMBDA":
        return None
    m = collections.defaultdict(list)
    for pred, args in p[1]:
        segs = [x.strip() for x in pred.split(" . ")]
        if len(segs) == 2 and len(args) == 2 and args[0][0] == "v" and segs[1] != skip_role:
            m[args[0][1]].append(args[1])
    return dict(m)


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


def induce_roles(lex, sch, mid, train, eps=0.0):
    """TOLERANCE SETS (Phase 6). A frame's reading was taken as global only `if len(cc) == 1`, so a SINGLE
    corrupted row made every frame contested. The tolerant test is whether one reading holds in at least
    (1 - eps) of that frame's observations. Where nothing does -- at frame level, then at (frame, verb) level
    -- the frame is CONTESTED and the engine ABSTAINS on any clause using it, rather than committing the
    plurality reading. That is Phase 6's rule: output the eps-consistent set, commit only on a singleton."""
    byframe = collections.defaultdict(collections.Counter)
    byverb = collections.defaultdict(collections.Counter)

    def observe(node, g):
        for cl, heads in clause_nodes(lex, sch, mid, node):
            rs = tuple(g.get((cl.event, h)) for h in heads)
            if not any(r is None for r in rs):
                byframe[frame_key(cl)][rs] += 1
                byverb[(frame_key(cl), cl.lemma)][rs] += 1

    # Which reading of a training sentence to learn from is decided by STRUCTURAL CONSISTENCY WITH THE GOLD:
    # a reading's set of (event, argument-head) pairs must equal the gold's binary-conjunct set. This needs no
    # role table, so it works for the GAP frames that only ever occur in relative clauses. (A two-round scheme
    # -- unique parses first, then gold-reproduction -- was tried and could never learn those frames, because
    # every relative-clause sentence has >= 2 readings and its frames are absent from round 1.)
    rc_role = lex.rc_mid[0] if lex.rc_mid else None

    def consistent(node, lf):
        # ORDER-AWARE: each clause's heads, in slot order, must equal the gold's arguments for that event in
        # gold order. Order is what distinguishes gap positions; a set comparison could not. The RC modifier
        # `noun . nmod ( noun , event )` is excluded -- it is a binary conjunct but not a clause argument.
        go = gold_order(lf, skip_role=rc_role)
        if go is None:
            return False
        seen = {}
        for cl, heads in clause_nodes(lex, sch, mid, node):
            seen[cl.event] = list(heads)
        return seen == go

    for s, lf, cat in train:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            continue
        g = gold_roles(lf)
        if g is None:
            continue
        pick = [q for q in parse_sentence(lex, sch, strip_term(lex, s), want=12) if consistent(q, lf)]
        if len(pick) == 1:                              # several consistent readings -> ambiguous -> skipped
            observe(pick[0], g)
    roles, ambiguous = _settle(byframe, byverb, eps)
    roles["__attested__"] = frozenset(byverb)      # every (frame, verb) pair actually seen: subcategorization
    return roles, ambiguous


def _settle(byframe, byverb, eps):
    roles = {}
    ambiguous = []

    def settled(cc):
        tot = sum(cc.values())
        top, n = cc.most_common(1)[0]
        return top if tot and n >= (1 - eps) * tot else None

    for f, cc in byframe.items():
        r = settled(cc)
        if r is not None:
            roles[f] = r
        else:
            ambiguous.append((f, dict(cc)))
    for key, cc in byverb.items():
        if key[0] not in roles:
            r = settled(cc)
            if r is not None:
                roles[key] = r
    for f, _ in ambiguous:
        # A PLURALITY GUESS, kept deliberately. Gating it on eps (so a contested frame abstains instead) is
        # more principled and was tried: it costs adversary grammar 0 its train reproduction, 1.000 -> 0.654,
        # because cl_head = subject makes two clauses share a head and legitimately contests frames there.
        # So it stays, and Stage 3d records it as one of the two identified confabulation sources -- the other
        # being the plurality lexicon vote. Removing a guess that a passing gate depends on, with nothing to
        # replace it, is a regression, not a fix.
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


SEARCH_CAP = 1500   # per-parse budget DURING the exhaustive schema search: enough to reproduce ordinary
                    # sentences, small enough that adversarial noun/adjective ambiguity is cut off cheaply.
                    # The final fit (induce_roles, reproduce) uses the full PARSE_BUDGET.


def _parse_rows(lex, sch, rows):
    return [(parse_sentence(lex, sch, strip_term(lex, s), want=1, cap=SEARCH_CAP) or [None])[0]
            for s, _, _ in rows]


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
    # via core.search.exhaustive, STAGED on the parse-relevant dimensions only: derivations are computed once
    # per (np_branch, verb_pos) and reused across the 144 read-out combinations. core.search carries the
    # measured reason this is exhaustive rather than coordinate descent.
    space = {d: Schema.SPACE[d] for d in Schema.DIMS}
    pt, sc = exhaustive(
        space,
        score=lambda p, nodes: _score_parsed(lex, Schema(**p), rows, nodes),
        stage_key=lambda p: (p["np_branch"], p["verb_pos"]),
        stage=lambda p: (lambda ns: ns if any(n is not None for n in ns) else None)(
            _parse_rows(lex, Schema(np_branch=p["np_branch"], verb_pos=p["verb_pos"]), rows)),
        verbose=verbose, label="schema search")
    best = (sc if sc is not None else -1, Schema(**pt) if pt else Schema())
    return best[1], best[0], len(rows)


def _induce_positional(train, verbose=False, eps=0.0):
    """Everything downstream of the alignment: variables are already token positions here."""
    lex = induce_lexicon(train, eps)
    sch, sc, ns = search_schema(lex, train, verbose=verbose)
    mid = induce_relmid(lex, train, sch)
    roles, ambiguous = induce_roles(lex, sch, mid, train, eps)
    if verbose:
        print(f"  classes {dict(collections.Counter(lex.cls.values()))}   terminator {lex.terminator!r}")
        print(f"  determiners ({lex.det_pos}-nominal) {lex.det}   relators {mid}")
        print(f"  frames: {len(roles)} entries, frame-ambiguous {len(ambiguous)}")
        for f, cc in ambiguous[:3]:
            print(f"    AMBIGUOUS {f} -> {cc}")
    return lex, sch, mid, roles


def induce(train, verbose=False, gate=0.99, force_eps=None):
    """-> model = (lex, schema, mid, roles, varconv).

    The VARIABLE CONVENTION is the last thing that was an assumption rather than an induction. COGS numbers
    variables by token position, which hands the induction its token<->predicate alignment; Stage 3b part C
    measured what that was worth (EM 1.000 -> 0.000 under first-appearance numbering). So it is now chosen the
    same way everything else is: try reading variables AS positions, and if that fails to reproduce train,
    RECOVER the alignment from co-occurrence (cogs_align) and rewrite train into positional form first.

    Only rows whose alignment is UNAMBIGUOUS are used for induction -- learning from a row whose alignment was
    settled by a tie-break would be learning from a guess, and the fraction dropped is reported.

    The choice between the two conventions is COMPARATIVE, not a threshold. An absolute "positions must
    reproduce >= 0.99, else align" test looks equivalent on clean data and is not: at 1% training corruption
    it flipped a positional corpus onto the aligned path, whose output renumbering is then wrong for every
    single prediction. Noise found that; clean data never could. So score both and keep the better."""
    def _frac(m):
        ok, wrong, nopar = reproduce(m, train)
        return ok / max(ok + wrong + nopar, 1)

    def _pos():
        """The TOLERANCE eps is itself induced, over a ladder, by measured reproduction -- ties go to the
        SMALLEST eps, so clean data keeps the exact eps = 0 engine and nothing regresses. Phase 6's warning
        stands and is not papered over: an eps chosen empirically is an ESTIMATE, not a bound, so soundness
        is no longer a theorem here -- which is exactly why cogs_stage3d.py reports both sides of the
        precondition (eps >= noise, and eps < noise) instead of only the favourable one."""
        if force_eps is not None:
            # Phase 6's precondition has TWO sides and only a forced eps can show the unfavourable one:
            # eps < the actual corruption must be demonstrated to reject the truth, not just asserted.
            return _induce_positional(train, verbose=verbose, eps=force_eps) + ("position",)
        samp = [r for r in train if r[2] != "primitive"][:1500]
        lex0 = [r for r in train if r[2] == "primitive"]

        def fit_and_score(e):
            m = _induce_positional(lex0 + samp, verbose=False, eps=e) + ("position",)
            ok, wr, npar = reproduce(m, samp)
            return ok / max(ok + wr + npar, 1)

        e, _sc, _walked = induce_eps(fit_and_score, EPS_LADDER, gate=gate, verbose=verbose)
        return _induce_positional(train, verbose=verbose, eps=e) + ("position",)

    mpos = _pos()
    fpos = _frac(mpos)
    if fpos >= gate:
        if verbose:
            print(f"  variable convention: POSITION (reproduces {fpos:.4f} of train as-is)")
        return mpos
    if verbose:
        print(f"  variable convention: positions reproduce {fpos:.4f} -- also trying the recovered ALIGNMENT")
    anchor, astats = associate(train, verbose=verbose)
    rows, hows, st = to_positional(train, anchor, verbose=verbose, oracle=False)
    fit = [r for r, h in zip(rows, hows) if h in ("unique", "lexicon")]
    if verbose:
        n = st["unique"] + st["tiebreak"] + st["failed"]
        print(f"  inducing from the {st['unique']} unambiguously aligned rows of {n} "
              f"({st['unique']/max(n,1):.4f}); {st['tiebreak']} tie-broken rows and {st['failed']} failures"
              f" are DROPPED, not guessed")
    mali = _induce_positional(fit, verbose=verbose, eps=mpos and 0.0) + ("first_appearance",)
    fali = _frac(mali)
    if verbose:
        print(f"  variable convention: position {fpos:.4f} vs alignment {fali:.4f} -> "
              f"{'POSITION' if fpos >= fali else 'FIRST_APPEARANCE'}")
    return mpos if fpos >= fali else mali


class Engine:
    """COMMIT on a derivation, ABSTAIN otherwise. No probabilistic output, as in Stages 1-2."""

    def __init__(self, train):
        self.model = induce(train)

    def predict(self, s):
        g = generate(self.model, s)
        return (g, "commit") if g is not None else (None, "hard")
