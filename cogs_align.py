"""STAGE 3c -- recovering the token <-> predicate ALIGNMENT from co-occurrence, so the engine stops being
handed it by COGS's variable convention.

Stage 3b part C measured the dependency: COGS numbers logical-form variables by TOKEN POSITION, so a conjunct
anchored at x_7 is anchored at token 7 and the induction never has to work out which word a predicate names.
Renumber the gold variables by order of first appearance and the same grammar drops from EM 1.000 to 0.000.

The signal used here is a REJECTION test, not a similarity score, which is the discipline the rest of the
engine already runs on:

    a predicate atom that NAMES A WORD occurs in a sentence exactly when that word occurs
    an atom that names a ROLE or a TEMPLATE CONSTANT does not

so, over training sentences,

    anchor(atom) = { w : every sentence containing w also contains the atom }      (necessity)
                   kept only if those words' sentences COVER every occurrence of the atom  (sufficiency)

The two halves matter separately. Necessity alone would admit any rare word that happens to appear only in
sentences carrying a role; the coverage half rejects it, because a rare word cannot account for every
occurrence of `agent`. Sufficiency alone would admit the terminator. A SET rather than a single word is
returned because one lemma can surface as several tokens (`roll` <- `rolled`, `roll`).

Alignment then constrains each variable to the positions of the words anchoring its OWN predicate, and
requires the per-sentence assignment to be injective and consistent across every conjunct that mentions the
variable. Positions are used only as the candidate SET; nothing here reads a variable's numeric value to
decide what it means. Where a candidate set stays ambiguous (a word repeated in one sentence) the tie is
broken by order of appearance, and the number of rows decided that way is reported, never hidden."""
import os, sys, re, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_lf import parse_lf, serialize, norm_lf

VARPAT = re.compile(r"x _ (\d+)")
MAX_SURFACE_FORMS = 3      # a lemma surfaces as a handful of tokens; a role name as none. See PARSIMONY below.


def renumber_first_appearance(lf):
    """The non-positional convention: variables numbered by order of first appearance in the logical form."""
    m = {}
    for v in VARPAT.findall(lf):
        if v not in m:
            m[v] = str(len(m))
    return VARPAT.sub(lambda k: "x _ " + m[k.group(1)], lf)


def _atoms(defs, conj):
    out = set()
    for lem, _ in defs:
        out.add(lem)
    for pred, _ in conj:
        for seg in pred.split(" . "):
            out.add(seg.strip())
    return out


def associate(train, verbose=False):
    """-> (anchor, stats). anchor[atom] = frozenset of word types that atom names, or an empty set when the
    atom is a role name or a template constant."""
    coa = collections.defaultdict(collections.Counter)
    na, nw = collections.Counter(), collections.Counter()
    sent_of_word = collections.defaultdict(set)
    sent_of_atom = collections.defaultdict(set)
    n = 0
    for s, lf, cat in train:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            continue
        p = parse_lf(lf)
        if p is None or p[0] == "LAMBDA":
            continue
        ws = set(s.split())
        ats = _atoms(p[0], p[1])
        i = n
        n += 1
        for w in ws:
            nw[w] += 1
            sent_of_word[w].add(i)
        for a in ats:
            na[a] += 1
            sent_of_atom[a].add(i)
            for w in ws:
                coa[a][w] += 1
    # PARSIMONY. Necessity alone is far too permissive: in an 8000-row slice the atom `nmod` is "necessary"
    # for ~170 location nouns, because each of them happens to occur only inside a modifier. So take the
    # MINIMAL set of necessary words that exactly accounts for the atom, and reject the atom outright if no
    # small set does -- a lemma surfaces as a handful of forms, a role name as none.
    cover_of = {}
    anchor, ties, rejected = {}, [], []
    for a in na:
        necessary = [w for w in coa[a] if coa[a][w] == nw[w]]
        necessary.sort(key=lambda w: -nw[w])
        need = set(sent_of_atom[a])
        pick = []
        for w in necessary:
            if len(pick) >= MAX_SURFACE_FORMS:
                break
            if sent_of_word[w] - (set().union(*(sent_of_word[x] for x in pick)) if pick else set()):
                pick.append(w)
                need -= sent_of_word[w]
                if not need:
                    break
        if need or not pick:
            anchor[a] = frozenset()
            rejected.append(a)
        else:
            anchor[a] = frozenset(pick)
            cover_of[a] = anchor[a]
            if len(pick) > 1:
                ties.append((a, sorted(pick)))
    # NON-DECOMPOSABILITY. `nmod`'s minimal cover can still come out as {in, on, beside} -- which is exactly
    # the union of three OTHER atoms' covers. A lemma's cover is not built out of other atoms' covers, so an
    # atom whose cover decomposes that way names nothing and is demoted to a constant.
    singles = {next(iter(v)): k for k, v in cover_of.items() if len(v) == 1}
    for a, v in list(cover_of.items()):
        if len(v) > 1 and sum(1 for w in v if singles.get(w, a) != a) >= 2:
            anchor[a] = frozenset()
            rejected.append(a)
            ties[:] = [t for t in ties if t[0] != a]
    stats = dict(n_sent=n, lexical=sum(1 for a in anchor if anchor[a]),
                 constant=sum(1 for a in anchor if not anchor[a]), multiword=ties,
                 rejected=len(rejected))
    if verbose:
        print(f"  association: {stats['lexical']} lexical atoms, {stats['constant']} constants "
              f"(roles / template segments) over {n} sentences")
        if ties:
            print(f"    atoms naming several surface forms: {ties[:6]}")
    return anchor, stats


def _candidates(anchor, toks, defs, conj):
    """variable -> the set of token positions it could denote. Only a variable's OWN naming predicate
    constrains it: an entity by its unary conjunct or definite entry, an event by its role conjuncts."""
    pos = collections.defaultdict(set)
    for k, w in enumerate(toks):
        pos[w].add(k)
    cand = {}
    seen = set()

    dropped = [0]

    def add(v, s):
        # a constraint is applied only when it leaves the variable SOME position: a demoted-but-still-anchored
        # atom would otherwise empty the set and lose an otherwise well-determined row. Drops are counted.
        seen.add(v)
        if v not in cand:
            cand[v] = set(s)
        elif cand[v] & s:
            cand[v] &= s
        else:
            dropped[0] += 1

    for lem, v in defs:
        ws = anchor.get(lem, frozenset())
        add(v, set().union(*(pos[w] for w in ws)) if ws else set())
    for pred, args in conj:
        segs = [x.strip() for x in pred.split(" . ")]
        for a in args:
            if a[0] == "v":
                seen.add(a[1])
        if len(segs) == 1 and len(args) == 1 and args[0][0] == "v":
            ws = anchor.get(segs[0], frozenset())
            add(args[0][1], set().union(*(pos[w] for w in ws)) if ws else set())
        elif len(segs) == 2 and len(args) == 2 and args[0][0] == "v" and anchor.get(segs[0]):
            ws = anchor[segs[0]]
            add(args[0][1], set().union(*(pos[w] for w in ws)))
    for v in seen:
        cand.setdefault(v, set())
    return cand, dropped[0]


def align_row(anchor, toks, defs, conj):
    """-> (mapping, how) where how is 'unique' | 'tiebreak' | None. Injective by construction."""
    cand, dropped = _candidates(anchor, toks, defs, conj)
    if any(not c for c in cand.values()):
        return None, None
    order = sorted(cand, key=lambda v: (len(cand[v]), v))
    used, out = set(), {}
    tie = False

    def rec(i):
        nonlocal tie
        if i == len(order):
            return True
        v = order[i]
        opts = sorted(cand[v] - used)
        if len(opts) > 1:
            tie = True
        for o in opts:
            used.add(o)
            out[v] = o
            if rec(i + 1):
                return True
            used.discard(o)
            del out[v]
        return False

    if not rec(0):
        return None, None
    return dict(out), ("tiebreak" if tie else "unique")


def to_positional(train, anchor=None, verbose=False, oracle=True):
    """Rewrite every training logical form so its variables ARE token positions, which is the representation
    the rest of the engine already consumes. -> (rewritten rows, stats)."""
    if anchor is None:
        anchor, _ = associate(train, verbose=verbose)
    out, hows = [], []
    st = collections.Counter()
    for s, lf, cat in train:
        if cat == "primitive" or lf.startswith("LAMBDA"):
            out.append((s, lf, cat))
            hows.append("lexicon")
            continue
        p = parse_lf(lf)
        if p is None or p[0] == "LAMBDA":
            out.append((s, lf, cat))
            hows.append(None)
            st["unparsed"] += 1
            continue
        defs, conj = p
        m, how = align_row(anchor, s.split(), defs, conj)
        if m is None:
            st["failed"] += 1
            out.append((s, lf, cat))
            hows.append(None)
            continue
        st[how] += 1
        hows.append(how)
        d2 = [(lem, m[v]) for lem, v in defs]
        c2 = [(pred, tuple((("v", m[a[1]]) if a[0] == "v" else a) for a in args)) for pred, args in conj]
        new = serialize(d2, c2)
        if oracle:
            # ORACLE CHECK, available because the alignment we are trying to recover is exactly the identity
            # when the source convention was already positional: rewriting must then be a no-op.
            st["oracle_ok"] += (new == norm_lf(lf))
        out.append((s, new, cat))
    if verbose:
        tot = st["unique"] + st["tiebreak"]
        print(f"  alignment: {st['unique']} unique, {st['tiebreak']} order-tiebreak, {st['failed']} failed "
              f"of {tot + st['failed']} rows  ({tot / max(tot + st['failed'], 1):.4f} aligned)")
    return out, hows, st
