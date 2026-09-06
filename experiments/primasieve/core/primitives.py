"""THE UNNAMED EXECUTABLE PRIMITIVE INVENTORY -- given #4 of the irreducible minimum
(emergence/no_paradigm_prereg.md section 2).

WHAT THIS IS. The engine's whole executable base: a flat set of callables, each identified ONLY by an opaque
id and a structural TYPE SIGNATURE, each carrying the TARGET THAT FORCED ITS ADDITION. Nothing else. There is
no table from a name, a glyph or a word to a primitive here, and that absence is the point:

    a curated operator table is the paradigm this file exists to not be. The moment a lookup keyed by "+" or
    by "multiply" lives in the base, the engine's arithmetic has been authored rather than researched, and
    every later "the engine LEARNED what x means" is that table read back.

Names arrive LATER and from OUTSIDE, by research: a researched description is bound to a primitive by SEARCH
UNDER VERIFICATION over `candidates(sig)` -- try each primitive of the right shape, keep the one that
reproduces independently citable facts. This module makes that search possible (`candidates` returns ALL
matching primitives, never a best one) and deliberately does not pre-empt it. `l0.py` and `emergence/en_ops.py`
already bind this way: they keep their own legacy labels and their own witnesses, and core/ holds no labels.

THE CRITERION IT IS BUILT AGAINST (prereg section 0): a given is a PRIMITIVE iff it is
content-permutation-invariant and its size does not grow when a new capability is added.

  permutation-invariant   ids are a hash of (signature, behaviour on canonical probes). Not of a name, not of
                          a position, not of registration order. Shuffle the registrations and every id, and
                          the result of every `candidates` call, is identical -- the self-test proves it.
  does not grow           a new capability is a COMPOSITION over this set, found by search. The inventory
                          grows only when a TARGET is not expressible, and then only with a ledger entry.

THE MERGE (a real de-islanding, prereg section 5). Two threads independently reached the same idea and each
wrote it down as the lesson of its own file:

    l0.py         "a primitive may be added ONLY if it is itself an object-grammar node type, and every
                   addition is LOGGED with the target that forced it"     -> BINARY_BASE + FORCED_BY
    en_ops.py     "do not enumerate actions; derive the primitives from the REPRESENTATION and let everything
                   else be a composition found by search"                 -> one edit per field

Those are the same rule stated over two different representations (an expression grammar, a record). They now
live here once, and both files import their base back from this inventory, keeping their public names.

THE TYPE DISCIPLINE IS A REJECTOR, NEVER A SELECTOR (prereg section 2 item 3, section 3 rung 2). `apply`
refuses an ill-typed application; that is all it does. It never ranks, never prefers, never picks. `candidates`
returns every primitive of a shape precisely so that the choice is made downstream by VERIFICATION, and the
pre-registered ablation (NP-7) can hold: disabling well-typedness must change HOW MANY survive, never WHICH
one wins. Types are structural -- int, exact rational, float, str, set, tuple, record-with-fields -- and there
is no domain type anywhere in the vocabulary; a type named after content would be the reducer coming back."""
from fractions import Fraction as _Fr
import hashlib
import io
import tokenize

# ---------------------------------------------------------------------------------------------------------------
# STRUCTURAL TYPES. The tags are structure, never content. A checker rejects; none of them selects.
# Only int / rat / rec currently carry primitives -- the rest are here because the discipline must be able to
# refuse a value of any shape, not because anything was authored for them.
INT, RAT, FLT, STR, SET, TUP, REC = "int", "rat", "float", "str", "set", "tuple", "rec"


def _c_int(v): return isinstance(v, int) and not isinstance(v, bool)
def _c_rat(v): return isinstance(v, (int, _Fr)) and not isinstance(v, bool)   # an exact scalar; int is one
def _c_flt(v): return isinstance(v, float)
def _c_str(v): return isinstance(v, str)
def _c_set(v): return isinstance(v, (set, frozenset))
def _c_tup(v): return isinstance(v, tuple)
def _c_rec(v): return isinstance(v, tuple) and len(v) > 0 and all(_c_int(f) for f in v)   # flat record of fields


CHECK = {INT: _c_int, RAT: _c_rat, FLT: _c_flt, STR: _c_str, SET: _c_set, TUP: _c_tup, REC: _c_rec}

# Canonical probes, per type, used ONLY to fingerprint behaviour so that identity is behavioural. They are
# content-free values, and the fingerprint is order-independent given the signature.
PROBES = {
    INT: (0, 1, -1, 2, 7),
    RAT: (_Fr(0), _Fr(1), _Fr(-1), _Fr(3, 2), _Fr(-5, 4)),
    FLT: (0.0, 1.5, -2.25),
    STR: ("", "u", "uv"),
    SET: (frozenset(), frozenset({0}), frozenset({0, 1})),
    TUP: ((), (0,), (0, 1)),
    REC: ((0,), (1, 2, 3), (4, -1)),
}
_PARTIAL = "!"          # the probe was outside the primitive's domain -- part of its behaviour, not an error


class IllTyped(TypeError):
    """An application the type discipline REFUSES. Refusal is the discipline's only power."""


class NoForcingRecord(ValueError):
    """A primitive offered without the target that forced it. A given with no forcing record is a paradigm."""


_SIG = {}          # pid -> ((argtype, ...), resulttype)
_FN = {}           # pid -> callable
_FORCED = {}       # pid -> the target that forced this primitive into existence


def _fingerprint(fn, args, result):
    """Behaviour of `fn` on the cartesian product of its argument types' canonical probes. This is the whole
    of a primitive's identity here: two primitives that agree everywhere ARE the same primitive (the
    observational-equivalence rule core/generate.py's SignatureBank is built on)."""
    grids = [PROBES[t] for t in args]
    rows, combos = [], [()]
    for g in grids:
        combos = [c + (v,) for c in combos for v in g][:512]
    for c in combos:
        try:
            out = fn(*c)
        except Exception:
            rows.append(_PARTIAL); continue
        rows.append(repr(out) if CHECK[result](out) else _PARTIAL)
    return tuple(rows)


def register(fn, args, result, forced_by):
    """Put an executable into the inventory. -> its opaque pid.

    `forced_by` is mandatory and is the ledger entry: WHICH target could not be expressed without it. There is
    no default, and an empty one raises: an unforced primitive is exactly what the prereg calls a paradigm."""
    if not isinstance(forced_by, str) or not forced_by.strip():
        raise NoForcingRecord("a primitive needs the target that forced it; refusing to hold an unforced one")
    for t in tuple(args) + (result,):
        if t not in CHECK:
            raise IllTyped(f"unknown structural type {t!r}")
    sig = (tuple(args), result)
    fp = _fingerprint(fn, sig[0], sig[1])
    h = hashlib.blake2s(repr((sig, fp)).encode("utf-8"), digest_size=5).hexdigest()
    if h in _SIG:
        raise ValueError(f"{h}: an observationally identical primitive is already held (forced by "
                         f"{_FORCED[h]!r}); a duplicate is a second name for one primitive")
    _SIG[h], _FN[h], _FORCED[h] = sig, fn, forced_by.strip()
    return h


# ---------------------------------------------------------------------------------------------------------------
# THE INVENTORY. Every entry states the target that forced it, copied from the ledger of the thread that paid
# for it. Read the second column, not the first: the first is an opaque hash on purpose.

_L0 = ("l0 Phase-1 reachability audit (KILL 1): the 6 discovered parametric operators must be L0 programs. "
       "E8 growth rule -- admissible because it IS an object-grammar node type: ")
_ENOPS = ("emergence/en_ops.py: the primitive edits are derived from the OBJECT REPRESENTATION, one per "
          "field; nothing here was added because a test failed. ")

P_RAT = tuple(sorted({
    register(lambda a, b: a + b, (RAT, RAT), RAT, _L0 + "ast.Add (CODE_PARAM c'=c+1, CODE_STRUCT_PARAM c'=c+e)"),
    register(lambda a, b: a - b, (RAT, RAT), RAT, _L0 + "ast.Sub (STRUCT_PARAM diff e'=e-1)"),
    register(lambda a, b: a * b, (RAT, RAT), RAT, _L0 + "ast.Mult (STRUCT_PARAM diff c'=c*e)"),
    register(lambda a, b: a // b, (RAT, RAT), RAT, _L0 + "ast.FloorDiv (E8 base set)"),
    register(lambda a, b: _Fr(a) / _Fr(b), (RAT, RAT), RAT,
             "l0.FORCED_BY, verbatim: integ frame c'=c/(e+1) needs exact rational division; ast.Div IS an "
             "object-grammar node type"),
}))

P_RAT1 = tuple(sorted({
    register(lambda a: abs(a), (RAT,), RAT,
             _L0 + "ast.Call/abs -- E8's trunc target is UNREACHABLE without it (the ablation knockout: "
                   "trunc reaches E=109203 with it, nothing without)"),
    register(lambda a: (a > 0) - (a < 0), (RAT,), RAT,
             _L0 + "the signmod target; same ablation knockout as the magnitude primitive"),
    register(lambda a: -a, (RAT,), RAT, _L0 + "ast.USub (the NEGATE operator target, c'=-c)"),
}))

P_INT = tuple(sorted({
    register(lambda a, b: a + b, (INT, INT), INT,
             _ENOPS + "an integer field of the record is stepped by +1/-1; the step is integer addition"),
    register(lambda a, b: a % b, (INT, INT), INT,
             _ENOPS + "the colour field has FINITE EXTENT, so its successor wraps; en_ops' colour+1 is this "
                      "composed with the integer step, not a primitive of its own"),
}))

P_REC = (register(lambda r, i, d: r[:i] + (r[i] + d,) + r[i + 1:], (REC, INT, INT), REC,
                  _ENOPS + "the representation ((x0,y0,x1,y1), colour) HAS those fields; one edit per field is "
                           "forced by the representation itself. widen/move/rotate are compositions, not entries"),)

# ---------------------------------------------------------------------------------------------------------------
# THE INTERFACE. Four calls, and none of them chooses.


def pids():
    """Every primitive held, in an order that depends on nothing but the ids themselves."""
    return tuple(sorted(_SIG))


def signature(pid):
    """((argtype, ...), resulttype) -- the only thing besides the id that identifies a primitive."""
    return _SIG[pid]


def forced_by(pid):
    """The target that forced this primitive into the inventory."""
    return _FORCED[pid]


def ledger():
    """The growth ledger, whole: pid -> (signature, forcing record). Nothing is held that is not in here."""
    return {p: (_SIG[p], _FORCED[p]) for p in pids()}


def candidates(sig):
    """EVERY primitive of this shape, sorted by id. Never a best one, never a first one, never one.

    This is the search space a binder searches under verification. Returning a single "the" primitive for a
    shape would be the operator table again, wearing a type signature as a disguise."""
    return tuple(p for p in pids() if _SIG[p] == sig)


def apply(pid, *args):
    """Run a primitive, REFUSING an ill-typed application. The refusal is the whole of the discipline: it
    removes candidates, it never ranks them (prereg NP-7 -- ablating this must change how many survive, never
    which wins). A primitive may be partial; a domain error propagates rather than being silently absorbed."""
    argt, rest = _SIG[pid]
    if len(args) != len(argt):
        raise IllTyped(f"{pid}: arity {len(argt)}, applied to {len(args)}")
    for v, t in zip(args, argt):
        if not CHECK[t](v):
            raise IllTyped(f"{pid}: expects {t}, got {type(v).__name__}")
    out = _FN[pid](*args)
    if not CHECK[rest](out):
        raise IllTyped(f"{pid}: result is not {rest}")
    return out


def unchecked(pid):
    """The raw executable, for a caller that has ALREADY bound and type-checked and now runs a hot loop
    (l0's signature-deduped BFS is one). Sound because the discipline is a rejector: bypassing a rejector can
    never change WHICH primitive a caller holds, only whether a bad application is caught early or late."""
    return _FN[pid]


# ---------------------------------------------------------------------------------------------------------------
# THE STATIC GATE ON THIS FILE (prereg NP-1, restricted to what this module can be blamed for): no string that
# names an operation or draws an operator may appear in KEY or LOOKUP position in this source. That is the
# mechanical form of "the base holds no name table". Implementations use Python operators, of course -- what is
# forbidden is a name that RETRIEVES a primitive.
FORBIDDEN = frozenset("""
+ - * / x × ÷ ^ % add plus sum total minus subtract sub multiply times product mul divide quotient div
negate abs absolute sign colour color widen move rotate
""".split())


def name_keyed_lookups(source):
    """-> the forbidden strings found in key or lookup position in `source`. Must be empty for this file."""
    bad, toks = [], list(tokenize.generate_tokens(io.StringIO(source).readline))
    sig_toks = [t for t in toks if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT,
                                                  tokenize.INDENT, tokenize.DEDENT)]
    for i, t in enumerate(sig_toks):
        if t.type != tokenize.STRING:
            continue
        try:
            val = eval(t.string)                     # a literal from this file, not input
        except Exception:
            continue
        if not isinstance(val, str) or val.lower() not in FORBIDDEN:
            continue
        prv = sig_toks[i - 1].string if i else ""
        nxt = sig_toks[i + 1].string if i + 1 < len(sig_toks) else ""
        if nxt in (":",) or prv == "[" or nxt == "]":
            bad.append(val)
    return bad


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.registry import selfcheck
    selfcheck(__file__)

    ok = True
    print("UNNAMED EXECUTABLE PRIMITIVE INVENTORY (given #4) -- ledger, with the target that forced each\n")
    for pid, (sig, why) in ledger().items():
        shape = f"({', '.join(sig[0])}) -> {sig[1]}"
        print(f"  {pid}  {shape:<24}  forced by: {why}")
    print(f"\n  held: {len(pids())} primitives, {len(pids())} forcing records "
          f"(every primitive is forced; an unforced one cannot be registered)")

    print("\n-- the ledger is mandatory ------------------------------------------------------------------")
    try:
        register(lambda a: a, (INT,), INT, "   ")
        print("  FAIL: an unforced primitive was admitted"); ok = False
    except NoForcingRecord as e:
        print(f"  refused an unforced primitive: {e}")

    print("\n-- the type discipline REJECTS, and only rejects ---------------------------------------------")
    probe = candidates(((RAT, RAT), RAT))[0]
    for bad_args in ((_Fr(1),), (_Fr(1), "u"), (_Fr(1), (0, 1))):
        try:
            apply(probe, *bad_args)
            print(f"  FAIL: ill-typed application {bad_args!r} was executed"); ok = False
        except IllTyped as e:
            print(f"  refused {str(bad_args):<16} -> {e}")
    print(f"  well-typed application still runs: {apply(probe, _Fr(3), _Fr(4))!r}")

    print("\n-- candidates returns ALL, so no primitive is privileged -------------------------------------")
    for sig in (((INT, INT), INT), ((RAT, RAT), RAT), ((RAT,), RAT), ((REC, INT, INT), REC)):
        cs = candidates(sig)
        shape = f"({', '.join(sig[0])}) -> {sig[1]}"
        print(f"  {shape:<26}{len(cs)} candidate{'s' if len(cs) != 1 else ''}: {', '.join(cs)}")
    n_ii = len(candidates(((INT, INT), INT)))
    if n_ii > 1:
        print(f"  ({INT}, {INT}) -> {INT} has {n_ii} candidates -- there is no 'the' operation of that shape")
    else:
        print(f"  FAIL: a single primitive owns ({INT},{INT})->{INT}; that is an operator table"); ok = False

    print("\n-- permutation invariance: ids are behaviour, not order or name ------------------------------")
    import random
    shuffled = list(pids())
    random.Random(0).shuffle(shuffled)
    redone = {hashlib.blake2s(repr((_SIG[p], _fingerprint(_FN[p], *_SIG[p]))).encode("utf-8"),
                              digest_size=5).hexdigest() for p in shuffled}
    same = redone == set(pids())
    print(f"  re-deriving every id from signature+behaviour alone, in a SHUFFLED order, reproduces the "
          f"identical id set: {same}")
    fp = _fingerprint(lambda a, b: a + b, (RAT, RAT), RAT)
    h1 = hashlib.blake2s(repr((((RAT, RAT), RAT), fp)).encode("utf-8"), digest_size=5).hexdigest()
    print(f"  an anonymous callable written fresh here lands on the id it is behaviourally equal to: "
          f"{h1 in _SIG} ({h1})")
    ok &= same and h1 in _SIG

    print("\n-- no name-keyed lookup in this source (NP-1, this file's share) -----------------------------")
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    found = name_keyed_lookups(src)
    print(f"  operation words / operator glyphs in key or lookup position: {found or 'none'}")
    print(f"  (the scanner sees {len(FORBIDDEN)} forbidden strings and reads its own source)")
    ok &= not found

    print("\n-- the two threads this inventory absorbed still import, with their old names -----------------")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "emergence"))
    # NOTE: this check reads the two threads' surfaces BY BEHAVIOUR, never by subscripting them with one of
    # their labels -- a lookup keyed by a glyph would be exactly the thing this file's static gate forbids,
    # and writing one here just to "verify the old names" would put the operator table back in the base.
    import l0
    print(f"  l0.BINARY_BASE {len(l0.BINARY_BASE)} labels, BINARY_FULL {len(l0.BINARY_FULL)}, "
          f"UNARY {len(l0.UNARY)} -- keys unchanged: {sorted(l0.BINARY_FULL)}, {sorted(l0.UNARY)}")
    # sets, not lists: an exact scalar compares and hashes equal whatever exact carrier holds it, and the
    # comparison must not depend on which label sits in front of which behaviour.
    b_got = {(f(_Fr(3), _Fr(4)), f(_Fr(7), _Fr(2)), f(_Fr(3), 0), f(l0.X, _Fr(4))) for f in l0.BINARY_FULL.values()}
    u_got = {(f(_Fr(-3)), f(_Fr(3)), f(l0.X)) for f in l0.UNARY.values()}
    b_want = {(7, 9, 3, l0.X), (-1, 5, 3, l0.X), (12, 14, 0, l0.X),
              (0, 3, l0.X, l0.X), (_Fr(3, 4), _Fr(7, 2), l0.X, l0.X)}
    u_want = {(3, 3, l0.X), (-1, 1, l0.X), (3, -3, l0.X)}
    l0ok = (b_got == b_want and u_got == u_want and set(l0.BINARY_BASE) < set(l0.BINARY_FULL)
            and len(l0.BINARY_BASE) == 4 and len(l0.UNARY) == 3)
    print(f"  l0's whole labelled surface reproduces its published behaviour on the shared "
          f"inventory (incl. X propagation and division by zero): {l0ok}")
    ok &= l0ok

    import en_ops
    obj = ((2, 2, 4, 6), 2)
    edits = {f(obj) for f in en_ops.PRIMS.values()}
    want = {((1, 2, 4, 6), 2), ((3, 2, 4, 6), 2), ((2, 1, 4, 6), 2), ((2, 3, 4, 6), 2),
            ((2, 2, 5, 6), 2), ((2, 2, 3, 6), 2), ((2, 2, 4, 7), 2), ((2, 2, 4, 5), 2), ((2, 2, 4, 6), 3)}
    path, _fin = en_ops.plan(obj, "wide")
    eok = edits == want and path is not None and len(path) == 3
    print(f"  en_ops.PRIMS {len(en_ops.PRIMS)} labels, keys unchanged: {sorted(en_ops.PRIMS)}")
    print(f"  every field edit and the BFS over them reproduce their published behaviour: {eok} "
          f"(goal 'wide' in {len(path) if path else '-'} steps)")
    ok &= eok

    print(f"\nPRIMITIVE INVENTORY: {'SOUND' if ok else 'FAIL'} -- {len(pids())} primitives, "
          f"{len(ledger())} forcing records, 0 name-keyed lookups")
    print("  SOUND, not PASS: this file is an inventory and a ledger. It demonstrates that the base holds no")
    print("  name table and that both absorbed threads still run on it. It does NOT show that a researched")
    print("  description can be bound to the right primitive -- that is NP-2/NP-4, and it needs the binder.")
