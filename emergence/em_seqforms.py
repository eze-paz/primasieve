"""EMERGENCE E-5 -- can the SAME discovery routine DERIVE the combinators sandpie-91 had to HAND-FREEZE?

sandpie-91 (the Rosetta/SCAN thread) reports that iteration is load-bearing in its Stage-2 grammar induction:
ablating REPEAT(k) and PREPEND_EACH(seq,k) collapses SCAN test EM from 1.000 -> 0.053 (simple) and 1.000 ->
0.000 (length split). But it HAND-FROZE those two combinators into a fixed inventory before touching SCAN, as
an anti-rig guard. Its own words: the inventory being generic is "something I argue rather than something I
demonstrate".

That is exactly the gap this layer can close. If the SAME discovery routine that derived ITERATE over
attribute-pair frames also derives the sequence-rewrite versions, then a hand-frozen combinator is replaced by
a DERIVED one -- strictly better on the anti-rig axis, because genericity becomes demonstrated.

THE MOVE: make discovery carrier-agnostic. It needs only (compose, signature) -- nothing about what the
objects ARE. Then run the IDENTICAL function over two carriers:
    PAIR  (c, e) attribute frames        -- the existing MATH/CODE/GRID domains
    SEQ   (tokens, unit) sequence states -- SCAN-shaped rewrites
On SEQ the base ops are pure endofunctions on a pair, exactly parallel to the attribute case:
    APPEND_UNIT   (cur, u) -> (cur ++ u, u)   iterated k times = u repeated k   == REPEAT(k)
    PREPEND_UNIT  (cur, u) -> (u ++ cur, u)   iterated k times = u^k ++ cur     == PREPEND_EACH(u, k)

HONEST SCOPE (91 flagged this and it is right): the FINDING transfers, the CODE does not drop into its engine.
This shows the derivation is carrier-independent; wiring it into a SCAN interpreter is separate work.
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import em_loop as E
import em_recursion as R

OUT = os.path.join(HERE, "EMERGENCE.json")


# ---------------- carrier-agnostic discovery: needs ONLY compose + signature ----------------
def discover_iterate_generic(entries, compose, signature, max_k=None):
    """entries = {k: op}. Is there a base B with entry_k == B iterated k times, for EVERY k present?
    Requires >=3 entries and entry_1 present; a corrupted series must be rejected."""
    if len(entries) < 3: return None
    ks = sorted(entries)
    if ks[0] != 1: return None
    base = entries[1]
    for k in ks:
        it = base
        for _ in range(k - 1):
            it = compose(base, it)
        if signature(it) != signature(entries[k]): return None
    return base


def iterate_generic(base, n, compose):
    it = base
    for _ in range(n - 1):
        it = compose(base, it)
    return it


# ---------------- carrier 1: attribute-pair frames (the existing domains) ----------------
def pair_carrier(inputs):
    compose = E.compose
    def signature(fr): return R.fsig(fr, inputs)
    return compose, signature


# ---------------- carrier 2: token-sequence rewrites (SCAN-shaped) ----------------
class Op:
    """a sequence rewrite as a pure endofunction on the state (tokens, unit)."""
    def __init__(self, fn, label): self.fn, self.label = fn, label


def seq_compose(a, b):
    return Op(lambda x: a.fn(b.fn(x)), f"({a.label} o {b.label})")


APPEND_UNIT = Op(lambda st: (st[0] + st[1], st[1]), "APPEND_UNIT")
PREPEND_UNIT = Op(lambda st: (st[1] + st[0], st[1]), "PREPEND_UNIT")

# PROBES MUST HAVE tokens != unit. An earlier version used tokens == unit everywhere, which makes
# APPEND_UNIT and PREPEND_UNIT EXTENSIONALLY IDENTICAL (cur+u+u == u+u+cur when cur==u) -- so the corrupted
# series passed and the guard read False. The guard failing is what exposed it. Same extensional-collapse
# trap as E-2a and the Phase 2(e) dedup bug: a probe set that cannot separate the hypotheses is not a test.
SEQ_PROBES = [
    ((), ("JUMP",)),                       # empty start: iterating n gives exactly unit^n
    (("WALK",), ("LTURN",)),
    (("LOOK", "RTURN"), ("JUMP",)),
    (("RUN",), ("WALK", "LTURN")),
    (("JUMP", "JUMP"), ("RTURN",)),
]


def seq_carrier(probes=SEQ_PROBES):
    def signature(op): return tuple(str(op.fn(p)) for p in probes)
    return seq_compose, signature


if __name__ == "__main__":
    t0 = time.time()
    res = {}
    print("E-5 -- ONE discovery routine, TWO carriers\n")

    # ---- carrier 1: attribute pairs (replicates E-3 through the generic function) ----
    mi = R.DOMAINS["MATH"]["inputs"]
    pc, psig = pair_carrier(mi)
    pair_entries = {k: R.iterate(R.DOMAINS["MATH"]["base"], k) for k in (1, 2, 3, 4)}
    pbase = discover_iterate_generic(pair_entries, pc, psig)
    pbogus = dict(pair_entries); pbogus[3] = R.DOMAINS["CODE"]["base"]
    pguard = discover_iterate_generic(pbogus, pc, psig) is None
    print(f"  PAIR carrier (c,e) frames : discovered={pbase is not None}   guard rejects corrupted={pguard}")

    # ---- carrier 2: token sequences (the SCAN-shaped ops 91 hand-froze) ----
    sc, ssig = seq_carrier()
    out = {}
    for name, base in (("REPEAT (= APPEND_UNIT iterated)", APPEND_UNIT),
                       ("PREPEND_EACH (= PREPEND_UNIT iterated)", PREPEND_UNIT)):
        entries = {k: iterate_generic(base, k, sc) for k in (1, 2, 3, 4)}
        got = discover_iterate_generic(entries, sc, ssig)
        bogus = dict(entries); bogus[3] = iterate_generic(PREPEND_UNIT if base is APPEND_UNIT else APPEND_UNIT, 3, sc)
        guard = discover_iterate_generic(bogus, sc, ssig) is None
        # extrapolate to k never seen
        unseen = {}
        for k in (7, 11, 23):
            tgt = ssig(iterate_generic(base, k, sc))
            found = None
            for n in range(1, 40):
                if ssig(iterate_generic(got, n, sc)) == tgt: found = n; break
            unseen[k] = found
        out[name] = {"discovered": got is not None, "guard_rejects_corrupted": guard, "unseen_k": unseen}
        print(f"  SEQ  carrier tokens      : {name:38s} discovered={got is not None} "
              f"guard={guard} unseen k->n {unseen}")

    # ---- show what it actually computes on SCAN-shaped inputs ----
    print(f"\n  worked examples (state = (tokens, unit)):")
    st = ((), ("JUMP",))                    # start EMPTY so iterating n yields exactly n copies
    print(f"    'jump twice'        REPEAT n=2   -> {iterate_generic(APPEND_UNIT, 2, sc).fn(st)[0]}")
    print(f"    'jump thrice'       REPEAT n=3   -> {iterate_generic(APPEND_UNIT, 3, sc).fn(st)[0]}")
    st2 = (("WALK",), ("LTURN",))
    print(f"    'walk around left'  PREPEND n=4  -> {iterate_generic(PREPEND_UNIT, 4, sc).fn(st2)[0]}")

    ok = (pbase is not None and pguard
          and all(v["discovered"] and v["guard_rejects_corrupted"] for v in out.values())
          and all(all(n is not None for n in v["unseen_k"].values()) for v in out.values()))
    print(f"\n=== VERDICT ===")
    if ok:
        print(f"  THE SAME ROUTINE DERIVES BOTH. discover_iterate_generic is carrier-agnostic -- it needs only")
        print(f"  (compose, signature) -- and it derives sandpie-91's REPEAT(k) and PREPEND_EACH(seq,k) from a")
        print(f"  generated series, with corrupted series rejected and extrapolation to k never seen.")
        print(f"  Those two combinators were HAND-FROZEN there as an anti-rig guard; here they are DERIVED,")
        print(f"  which converts 'my inventory is generic' from an argument into a demonstration.")
    else:
        print(f"  Partial -- pair={pbase is not None} seq={out}")
    print(f"\n  HONEST SCOPE (91's point, and it is right): the FINDING transfers, the CODE does not. Its ops run")
    print(f"  inside a SCAN interpreter over token sequences; wiring this derivation in is separate work.")
    res = {"pair_carrier": {"discovered": pbase is not None, "guard": pguard}, "seq_carrier": out,
           "verdict": "same routine derives both" if ok else "partial",
           "peer_ablation_reported_by_sandpie_91": {
               "scan_simple_EM": "1.000 -> 0.053 when REPEAT/PREPEND_EACH removed",
               "scan_length_EM": "1.000 -> 0.000 (coverage 0.000)",
               "note": "their numbers, quoted as reported; not re-run here"},
           "significance": "sandpie-91 hand-froze REPEAT/PREPEND_EACH before touching SCAN as an anti-rig guard "
                           "and notes its genericity is argued not demonstrated. The same discovery routine that "
                           "derived ITERATE over attribute frames derives those two over token sequences, so the "
                           "hand-frozen inventory can in principle be replaced by a derived one."}
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E5_carrier_agnostic_derivation"] = res
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  ({time.time()-t0:.0f}s) -> {os.path.basename(OUT)}")
