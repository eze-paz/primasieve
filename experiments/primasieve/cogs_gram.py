"""STAGE 3a -- the HEAD-PASSING synchronous grammar for COGS (zero-LLM, pure stdlib).

Stage 2's inventory composed opaque STRINGS. COGS recursion emits `prev_head . nmod . prep ( x_prev , x_new )`:
a predicate that references the HEAD VARIABLE of a sibling constituent, and splices that sibling's HEAD LEMMA
into the predicate name. So the new output side is constituents that export a head:

    constituent = (head, lemma, defs, conj)        head = ('v', token_index) | ('c', proper_name)

GENERIC combinator inventory (frozen; contains no COGS-specific token, role name, count or ordering fact):
    PRIM(lemma)            a word denotes an entity / event / relation; head = its own token index
    EMIT(pred_tpl, args)   add a conjunct; pred_tpl may splice a CHILD's head LEMMA, args are CHILD HEAD VARS
    UNION(order)           concatenate children's conjunct lists in a rule-determined order
    HEAD(k)                head-select: which child's head this constituent exports

Everything below the inventory is INDUCED from (sentence, logical form) pairs and then SOUND-GATED:
  (1) word CLASSES from the alignment COGS gives for free -- variable indices ARE 0-based token positions, so a
      conjunct anchored at x_i is anchored at token i. A word is ENTITY if some `p ( x_i )` has p == word_i;
      EVENT if some `p . r ( x_i , .. )` does; RELATOR if it is the last segment of a binary `a . m . w`;
      NAME if it occurs as a constant argument; FUNCTOR if it never appears in any logical form.
  (2) DEFINITENESS: which functor preceding a noun sends that noun's conjunct to the `*` prefix list.
  (3) RELATION TEMPLATES: the constant middle segments of `lemma_i . <mid> . word_k ( x_i , x_j )`.
  (4) CLAUSE FRAMES -> role tuples, keyed on the SYNTACTIC FRAME (pre-marker + ordered slot markers/kinds).
      Verb identity is used ONLY where the frame alone is inconsistent (the unaccusative/unergative split),
      preferring the coarsest consistent key. This is what makes unacc_to_transitive / active_to_passive free.
  (5) two conjunct-ORDER policies, SEARCHED over a small generic space and chosen by measured reproduction --
      c5c942d measured that conjunct order is derivation-determined, not a sort, so it must be induced.
Sound gate: the grammar must regenerate every training pair exactly. Prediction commits only on a parse."""
import os, sys, re, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_lf import parse_lf, serialize, norm_lf

ENTITY, NAME, EVENT, REL, FUNC = "ENTITY", "NAME", "EVENT", "REL", "FUNC"


# ---------------------------------------------------------------- lexicon induction
class Lexicon:
    def __init__(self):
        self.cls = {}                 # word -> class
        self.lemma = {}               # word -> lemma (ENTITY / EVENT)
        self.definite = {}            # functor -> does it send the noun conjunct to the '*' list
        self.clause_marker = set()    # functors that introduce a finite embedded clause
        self.rel_mid = {}             # relator word -> constant middle segments, e.g. ('nmod',)
        self.vroles = {}              # verb lemma -> roles seen in its LAMBDA primitive row
        self.varity = {}              # verb lemma -> number of lambdas in its primitive row
        self.terminator = None        # the induced sentence-final punctuation token


def _lambda_entry(word, lf, lex, votes, lemvote):
    """A `primitive` row is a LEXICON entry, not a sentence: `LAMBDA a . ball ( a )` etc."""
    nlam = lf.count("LAMBDA")
    body = lf
    while body.startswith("LAMBDA "):
        body = body.split(" . ", 1)[1]
    heads = [p.strip() for p in re.findall(r"([A-Za-z_. ]+?) \( ", body)]
    if not heads:
        votes[word][NAME] += 1        # a bare lexicon row (`Paula -> Paula`) is a proper name, not a functor
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


def induce_lexicon(train):
    lex = Lexicon()
    votes = collections.defaultdict(collections.Counter)
    seen = collections.Counter()
    defvote = collections.defaultdict(collections.Counter)
    relmid = collections.defaultdict(collections.Counter)
    lemvote = collections.defaultdict(collections.Counter)
    lastvote = collections.Counter()
    cmark = collections.Counter()
    nsent = 0
    for s, lf, cat in train:
        toks = s.split()
        if cat == "primitive" or lf.startswith("LAMBDA"):
            _lambda_entry(toks[0], lf, lex, votes, lemvote)
            seen[toks[0]] += 1
            continue
        if len(toks) == 1:                                       # a bare proper-name row
            votes[toks[0]][NAME] += 1
            seen[toks[0]] += 1
            continue
        p = parse_lf(lf)
        if p is None or p[0] == "LAMBDA":
            continue
        defs, conj = p
        for w in toks:
            seen[w] += 1
        nsent += 1
        lastvote[toks[-1]] += 1
        # Alignment is by TOKEN POSITION, never by string equality: the variable index already names the token,
        # so a surface/lemma mismatch (the token `TV` under the predicate `tv`) costs nothing. Requiring
        # toks[i] == lemma silently made such words FUNCTORs and killed every parse containing them.
        for lem, i in defs:
            if i < len(toks):
                votes[toks[i]][ENTITY] += 1
                lemvote[toks[i]][lem] += 1
                if i:
                    defvote[toks[i - 1]][True] += 1
        for pred, args in conj:
            segs = [x.strip() for x in pred.split(" . ")]
            if len(segs) == 1 and len(args) == 1 and args[0][0] == "v":
                i = args[0][1]
                if i < len(toks):
                    votes[toks[i]][ENTITY] += 1
                    lemvote[toks[i]][segs[0]] += 1
                    if i:
                        defvote[toks[i - 1]][False] += 1
            elif len(segs) == 2 and len(args) == 2 and args[0][0] == "v":
                e = args[0][1]
                if e < len(toks):
                    votes[toks[e]][EVENT] += 1
                    lemvote[toks[e]][segs[0]] += 1
            elif len(segs) >= 3 and len(args) == 2 and args[0][0] == "v" and args[1][0] == "v":
                i, j = args[0][1], args[1][1]
                ks = [k for k in range(i + 1, min(j, len(toks))) if toks[k] == segs[-1]]
                k = ks[0] if ks else (i + 1 if i + 1 < min(j, len(toks)) else None)
                if k is not None:
                    votes[toks[k]][REL] += 1
                    lemvote[toks[k]][segs[-1]] += 1
                    relmid[toks[k]][tuple(segs[1:-1])] += 1
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
    for f, cc in defvote.items():
        if lex.cls.get(f) == FUNC:
            lex.definite[f] = cc.most_common(1)[0][0]
    for w, cc in relmid.items():
        lex.rel_mid[w] = cc.most_common(1)[0][0]
    # the sentence TERMINATOR, induced rather than assumed: the one token that ends (nearly) every training
    # sentence and never occurs anywhere else. Stripping "any trailing functor" instead ate unclassified words.
    for w, n in lastvote.items():
        if n >= 0.95 * nsent and n == seen[w]:
            lex.terminator = w
    # SECOND PASS for clause markers: a functor introduces a FINITE embedded clause when the verb's argument is
    # itself an EVENT token with its own subject in between (j > e+2). Needs the classes, hence a second pass --
    # a first-pass "any argument beyond the next token" heuristic wrongly swallowed the NP markers 'by'/'to'.
    for s, lf, cat in train:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            continue
        toks = s.split()
        p = parse_lf(lf)
        if p is None or p[0] == "LAMBDA":
            continue
        for pred, args in p[1]:
            segs = [x.strip() for x in pred.split(" . ")]
            if len(segs) != 2 or len(args) != 2 or args[0][0] != "v" or args[1][0] != "v":
                continue
            e, j = args[0][1], args[1][1]
            if j > e + 2 and j < len(toks) and lex.cls.get(toks[j]) == EVENT and lex.cls.get(toks[e + 1]) == FUNC:
                cmark[toks[e + 1]] += 1
    for w, n in cmark.items():
        if lex.cls.get(w) == FUNC and w not in lex.definite and n >= 5:
            lex.clause_marker.add(w)
    return lex


# ---------------------------------------------------------------- structural parse (roles not needed yet)
class NP:
    __slots__ = ("det", "definite", "kind", "idx", "lemma", "rel", "inner")

    def __init__(self, det, definite, kind, idx, lemma, rel=None, inner=None):
        self.det, self.definite, self.kind, self.idx, self.lemma = det, definite, kind, idx, lemma
        self.rel, self.inner = rel, inner          # rel = (relator_index, relator_word)


class CL:
    __slots__ = ("event", "lemma", "pre", "slots", "gapped")

    def __init__(self, event, lemma, pre, slots, gapped):
        self.event, self.lemma, self.pre, self.slots, self.gapped = event, lemma, pre, slots, gapped
        # slots: list of (marker_word_or_None, kind, node);  kind in {'NP', 'CL', 'VP', 'GAP'}


def parse_np(lex, toks, i):
    """NP -> [functor] (ENTITY|NAME) [RELATOR NP] -- right-branching, head = the leftmost noun."""
    n = len(toks)
    if i >= n:
        return None
    det = None
    definite = False
    # only a functor actually OBSERVED as a determiner (i.e. one whose definiteness effect was induced) may head
    # an NP; taking any functor as a determiner silently swallowed the argument markers 'to' / 'by'
    if toks[i] in lex.definite and i + 1 < n and lex.cls.get(toks[i + 1]) in (ENTITY, NAME):
        det = toks[i]
        definite = bool(lex.definite.get(det, False))
        i += 1
    c = lex.cls.get(toks[i])
    if c == ENTITY:
        node = NP(det, definite, ENTITY, i, lex.lemma.get(toks[i], toks[i]))
    elif c == NAME:
        node = NP(det, False, NAME, i, toks[i])
    else:
        return None
    j = i + 1
    if j < n and lex.cls.get(toks[j]) == REL:
        sub = parse_np(lex, toks, j + 1)
        if sub is not None:
            node.rel = (j, toks[j])
            node.inner = sub[0]
            j = sub[1]
    return node, j


def parse_clause(lex, toks, i, gapped=False):
    """CLAUSE -> [NP] [functor] EVENT slot*    head = the EVENT token (this is what makes ccomp compose)."""
    n = len(toks)
    slots = []
    if gapped:
        slots.append((None, "GAP", None))
        j = i
    else:
        s = parse_np(lex, toks, i)
        if s is None:
            return None
        slots.append((None, "NP", s[0]))
        j = s[1]
    pre = None
    if j < n and lex.cls.get(toks[j]) == FUNC and j + 1 < n and lex.cls.get(toks[j + 1]) == EVENT:
        pre = toks[j]
        j += 1
    if j >= n or lex.cls.get(toks[j]) != EVENT:
        return None
    e = j
    lemma = lex.lemma.get(toks[e], toks[e])
    j += 1
    while j < n:
        w = toks[j]
        c = lex.cls.get(w)
        # the three slot shapes, tried most-specific first; a failed attempt FALLS THROUGH to the next shape
        # rather than aborting the clause (an early abort left tokens unconsumed and killed the whole parse)
        if c == FUNC and j + 1 < n and lex.cls.get(toks[j + 1]) == EVENT:        # marker + bare verb = control
            sub = parse_clause(lex, toks, j + 1, gapped=True)
            if sub is not None:
                slots.append((w, "VP", sub[0]))
                j = sub[1]
                continue
        if c == FUNC and w in lex.clause_marker:                                 # marker + finite clause
            sub = parse_clause(lex, toks, j + 1)
            if sub is not None:
                slots.append((w, "CL", sub[0]))
                j = sub[1]
                continue
        marker = None
        k = j
        if c == FUNC and w not in lex.definite:
            marker = w                                                            # 'to'/'by' introducing an NP
            k = j + 1
        sub = parse_np(lex, toks, k)
        if sub is None:
            break
        slots.append((marker, "NP", sub[0]))
        j = sub[1]
    return CL(e, lemma, pre, slots, gapped), j


def parse_sentence(lex, s):
    toks = s.split()
    while toks and toks[-1] == lex.terminator:
        toks = toks[:-1]
    r = parse_clause(lex, toks, 0)
    if r is None or r[1] != len(toks):
        return None
    return r[0], toks


def frame_key(cl):
    return (cl.pre, tuple((m, k) for m, k, _ in cl.slots))


# ---------------------------------------------------------------- derivation -> logical form
class Order:
    """The induced conjunct-ORDER policies. c5c942d measured that COGS conjunct order is DERIVATION-determined
    (only 74.5% of training LFs are in sorted-by-argument order), so the order must be induced, not assumed.
    Both fields are chosen by measured reproduction over a small generic space, never hardcoded."""

    def __init__(self, np="own_rel_inner", cl="subj_first"):
        self.np, self.cl = np, cl

    NP_SPACE = ("own_rel_inner", "own_inner_rel", "rel_own_inner")
    CL_SPACE = ("subj_first", "block_first")

    def __repr__(self):
        return f"Order(np={self.np}, cl={self.cl})"


def ev_np(lex, node, order, defs, conj):
    """Evaluate an NP -> its exported head. Appends its definites and conjuncts in derivation order."""
    if node.kind == NAME:
        head = ("c", node.lemma)
        own = []
    else:
        head = ("v", node.idx)
        if node.definite:
            defs.append((node.lemma, node.idx))
            own = []
        else:
            own = [(node.lemma, (head,))]
    if node.rel is None:
        conj.extend(own)
        return head
    relword = node.rel[1]
    inner_conj = []
    ihead = ev_np(lex, node.inner, order, defs, inner_conj)
    pred = " . ".join((node.lemma,) + tuple(lex.rel_mid.get(relword, ())) + (relword,))
    modc = (pred, (head, ihead))
    if order.np == "own_rel_inner":
        conj.extend(own + [modc] + inner_conj)
    elif order.np == "own_inner_rel":
        conj.extend(own + inner_conj + [modc])
    else:
        conj.extend([modc] + own + inner_conj)
    return head


def ev_cl(lex, node, roles, order, defs, conj, inherited=None):
    """Evaluate a clause -> its exported head = the EVENT variable (HEAD-select over the event token)."""
    ev = ("v", node.event)
    heads = []
    subconj = []
    for m, kind, sub in node.slots:
        c = []
        if kind == "GAP":
            if inherited is None:
                return None
            heads.append(inherited)
            subconj.append(c)
            continue
        if kind == "NP":
            h = ev_np(lex, sub, order, defs, c)
        else:
            h = ev_cl(lex, sub, roles, order, defs, c, inherited=(heads[0] if heads else inherited))
            if h is None:
                return None
        heads.append(h)
        subconj.append(c)
    fk = frame_key(node)
    rs = roles.get(fk)                                    # the coarsest key: the syntactic frame alone
    if rs is None:
        rs = roles.get((fk, node.lemma))                  # verb-keyed, only where the frame is inconsistent
    if rs is None and len(heads) == 1:
        # verb never seen in this frame: read the argument structure off its own LAMBDA lexicon entry, which
        # states it directly (`inflate . theme` = unaccusative vs `stutter . agent` = unergative)
        vr = lex.vroles.get(node.lemma)
        if vr and len(vr) == 1:
            rs = (next(iter(vr)),)
    if rs is None:
        rs = roles.get(("__fallback__", fk))              # last resort: the frame's majority role tuple
    if rs is None or len(rs) != len(heads):
        return None
    block = [(node.lemma + " . " + r, (ev, h)) for r, h in zip(rs, heads)]
    if order.cl == "subj_first":
        conj.extend(subconj[0] + block + [x for c in subconj[1:] for x in c])
    else:
        conj.extend(block + [x for c in subconj for x in c])
    return ev


def generate(lex, roles, order, s):
    """The full head-passing derivation: sentence -> logical form, or None if no derivation exists."""
    p = parse_sentence(lex, s)
    if p is None:
        return None
    defs, conj = [], []
    if ev_cl(lex, p[0], roles, order, defs, conj) is None:
        return None
    return serialize(defs, conj)


# ---------------------------------------------------------------- frame -> role induction
def clause_nodes(lex, node, order, inherited=None):
    """Walk a derivation and yield (clause_node, slot_heads) -- structure only, no roles required."""
    heads = []
    out = []
    for m, kind, sub in node.slots:
        if kind == "GAP":
            heads.append(inherited)
        elif kind == "NP":
            heads.append(ev_np(lex, sub, order, [], []))
        else:
            heads.append(("v", sub.event))
    for m, kind, sub in node.slots:
        if kind in ("CL", "VP"):
            out.extend(clause_nodes(lex, sub, order, inherited=(heads[0] if heads else inherited)))
    return [(node, heads)] + out


def gold_roles(lf):
    """(event_index, argument) -> role, read straight off the gold logical form."""
    p = parse_lf(lf)
    if p is None or p[0] == "LAMBDA":
        return None
    m = {}
    for pred, args in p[1]:
        segs = [x.strip() for x in pred.split(" . ")]
        if len(segs) == 2 and len(args) == 2 and args[0][0] == "v":
            m[(args[0][1], args[1])] = segs[1]
    return m


def induce_roles(lex, train, order):
    """Key on the SYNTACTIC FRAME; fall back to (frame, verb) only where the frame alone is inconsistent.
    Preferring the coarsest consistent key is what makes unacc_to_transitive / active_to_passive free."""
    byframe = collections.defaultdict(collections.Counter)
    byverb = collections.defaultdict(collections.Counter)
    for s, lf, cat in train:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            continue
        p = parse_sentence(lex, s)
        if p is None:
            continue
        g = gold_roles(lf)
        if g is None:
            continue
        for cl, heads in clause_nodes(lex, p[0], order):
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
    for f, _ in ambiguous:                 # a verb-independent fallback for verbs unseen in this frame
        cc = byframe[f]
        roles.setdefault(("__fallback__", f), cc.most_common(1)[0][0])
    return roles, ambiguous


def reproduce(lex, roles, order, rows):
    ok = wrong = nopar = 0
    for s, lf, cat in rows:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            continue
        g = generate(lex, roles, order, s)
        if g is None:
            nopar += 1
        elif g == norm_lf(lf):
            ok += 1
        else:
            wrong += 1
    return ok, wrong, nopar


def induce_order(lex, train, sample=1500):
    """SEARCH the small generic order space and keep what measurably reproduces best. Not assumed."""
    rows = [r for r in train if r[2] != "primitive"][:sample]
    best = None
    table = []
    for npo in Order.NP_SPACE:
        for clo in Order.CL_SPACE:
            o = Order(npo, clo)
            roles, _ = induce_roles(lex, rows, o)
            ok, wrong, nopar = reproduce(lex, roles, o, rows)
            table.append((npo, clo, ok, wrong, nopar))
            if best is None or ok > best[0]:
                best = (ok, o)
    return best[1], table


def induce(train, verbose=False):
    lex = induce_lexicon(train)
    order, table = induce_order(lex, train)
    roles, ambiguous = induce_roles(lex, train, order)
    if verbose:
        print(f"  order search (np, cl, ok, wrong, no-parse):")
        for row in table:
            print("    " + str(row))
        print(f"  chosen {order}")
        print(f"  classes: " + str(collections.Counter(lex.cls.values())))
        print(f"  definite functors {lex.definite}  clause markers {sorted(lex.clause_marker)}"
              f"  relators {lex.rel_mid}")
        print(f"  frames: {len([k for k in roles if isinstance(k, tuple) and len(k) == 2 and isinstance(k[1], str) and k[0] != '__fallback__'])} verb-keyed"
              f" / {len(roles)} total; frame-ambiguous {len(ambiguous)}")
        for f, cc in ambiguous[:4]:
            print(f"    AMBIGUOUS {f} -> {cc}")
    return lex, roles, order


class Engine:
    """COMMIT only on a derivation; ABSTAIN otherwise. Kept from Stages 1-2: no probabilistic output."""

    def __init__(self, train):
        self.lex, self.roles, self.order = induce(train)

    def predict(self, s):
        g = generate(self.lex, self.roles, self.order, s)
        return (g, "commit") if g is not None else (None, "hard")
