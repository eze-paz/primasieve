"""COMPOSITIONAL SIGNATURE -- the measurement (nolf_sig_prereg.md). Imports core/ only through nolf_learn; the world
module is touched only for the S2 fits.

S1  under sig_mode="product", extend() is EQUIVALENT to a full build (records max_ops=4, the case that differed; both worlds at 2)
S2  a 240 s fit per world with the product signature adopts a superset of the rotation fit's constructions, CONFAB 0  (--fit)
S3  cost: the strings base table at max_ops=4, product vs rotation
S4  table size per level, product vs rotation

    python nolf_sig.py [--fit] [--no-s3]"""
import os, sys, time, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nolf_learn as NL
import nolf_rebuild as R
from core.registry import selfcheck


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def build(args, lib, max_ops, mode):
    t = time.time(); E = NL.Enumerator(*args, library=dict(lib), max_ops=max_ops, sig_mode=mode); E.table(False)
    return E, time.time() - t


def per_level(E):
    out = collections.Counter()
    for lam, where in E.where.items():
        for term, (k, ty, sig) in where.items(): out[(lam, k)] += 1
    return out


def s1(world, d, max_ops):
    NL.BANK_CAP = 60000
    args = (d["probes"], d["elems"], d["rels"], d["sels"]); L = d["fragments"]
    items = list(L.items()); L1 = dict(items[:len(items) // 2]); L2 = dict(items)
    Ef, tf = build(args, L2, max_ops, "product")
    E0, tb = build(args, {}, max_ops, "product"); t = time.time(); E0.extend(L2); te = time.time() - t
    E1, t1 = build(args, L1, max_ops, "product"); t = time.time(); E1.extend(L2); t12 = time.time() - t
    d1, n = R.equivalent(Ef, E0); d2, _ = R.equivalent(Ef, E1)
    say(f"  [{world}] max_ops={max_ops} product: full {tf:.1f} s ({n} signatures); base+extend {tb + te:.1f} s -> {'EQUIVALENT' if not d1 else 'DIFFERS ' + str(d1[:3])}; "
        f"L1 {t1:.1f} s + extend {t12:.1f} s -> {'EQUIVALENT' if not d2 else 'DIFFERS ' + str(d2[:3])}")
    return not d1 and not d2


def s4(world, d, max_ops):
    NL.BANK_CAP = 60000
    args = (d["probes"], d["elems"], d["rels"], d["sels"])
    Er, tr = build(args, {}, max_ops, "rotation"); Ep, tp = build(args, {}, max_ops, "product")
    cr, cp = per_level(Er), per_level(Ep)
    say(f"  [{world}] max_ops={max_ops} base table: rotation {tr:.1f} s, product {tp:.1f} s ({tp / tr if tr else 0:.1f}x)")
    for k in sorted(set(cr) | set(cp)):
        say(f"      lam={k[0]!s:5} level {k[1]}: rotation {cr[k]:6d}  product {cp[k]:6d}  {'+' if cp[k] > cr[k] else ('-' if cp[k] < cr[k] else '=')}{abs(cp[k] - cr[k])}")
    return tr, tp


def fit(world, mode, budget=240):
    import nolf_worlds as NW
    from core.verdict import score_two_mode
    W = NW.Records() if world == "records" else NW.Strings()
    sp = NW.splits(W, 1); t = time.time()
    real = NL.Enumerator
    class E(real):
        def __init__(self, *a, **k): k.setdefault("sig_mode", mode); super().__init__(*a, **k)
    NL.Enumerator = E
    try: L = NL.Learner(time_budget=budget).fit(sp["train"])
    finally: NL.Enumerator = real
    r = {s: score_two_mode(L, [((sit, toks), tv) for sit, toks, tv in sp[s]]) for s in ("heldout_iid", "heldout_comp")}
    keys = {tuple(x if x == "B" else x[1] for x in k) for k in L.grammar}
    say(f"  [{world}] {mode:8s} fit {time.time() - t:.0f} s: table {L.table_seconds:.0f} s, {len(L.grammar)} constructions, "
        f"comp EM {r['heldout_comp']['EM']:.4f} iid EM {r['heldout_iid']['EM']:.4f} CONFAB {r['heldout_comp']['confab'] + r['heldout_iid']['confab']:.4f}")
    return keys, r["heldout_comp"]["confab"] + r["heldout_iid"]["confab"]


if __name__ == "__main__":
    selfcheck(__file__)
    a = sys.argv
    say("COMPOSITIONAL SIGNATURE -- product-domain observational equivalence vs the shipped rotation (nolf_sig_prereg.md)")
    frags = {w: R.load_fragments(w) for w in ("records", "strings")}
    deep = "--deep" in a       # the depth-4 product builds: records' three S1 builds did not finish in 45 min on the registration day
    say("\nS1  EQUIVALENCE OF extend() UNDER THE PRODUCT SIGNATURE")
    ok1 = all([s1("records", frags["records"], 2), s1("strings", frags["strings"], 2)] + ([s1("records", frags["records"], 4)] if deep else []))
    say(f"S1  {'PASS' if ok1 else 'FAIL'} at max_ops=2 on both worlds" + ("" if deep else "; records max_ops=4 NOT RUN (three product builds exceeded 45 min; --deep to run)"))
    say("\nS4  TABLE SIZE PER LEVEL (base tables)")
    s4("records", frags["records"], 2); s4("strings", frags["strings"], 2)
    if deep: s4("records", frags["records"], 4)
    ratio = None
    if "--no-s3" not in a and deep:
        say("\nS3  COST: strings base table at max_ops=4")
        tr, tp = s4("strings", frags["strings"], 4); ratio = tp / tr if tr else float("inf")
        say(f"S3  product/rotation = {ratio:.2f}x   [<= 2x flips the default -> {'YES' if ratio <= 2 else 'NO: rotation stays the default'}]")
    if not deep:
        say("\nS3  COST: NOT RUN at depth 4 -- the records base table under the product signature did not finish three builds in 45 min against"
            " ~100 s each under rotation (> 9x; bar 2x). Measured at depth 2 instead (S4 above). Rotation stays the default.")
    ok2 = None
    if "--fit" in a and deep:
        say("\nS2  THE LEARNER UNDER EACH SIGNATURE (240 s per world)")
        res = {}
        for w in ("records", "strings"):
            kr, cr = fit(w, "rotation"); kp, cp = fit(w, "product")
            res[w] = (kr <= kp, cr + cp, sorted(kr - kp))
            say(f"      {w}: product superset of rotation {kr <= kp}; constructions rotation-only {sorted(kr - kp)}; confab {cr + cp:.4f}")
        ok2 = all(v[0] and v[1] == 0 for v in res.values())
        say(f"S2  {'PASS' if ok2 else 'FAIL'}")
    say(f"\nCOMPOSITIONAL SIGNATURE: S1 {'EQUIVALENT' if ok1 else 'NOT EQUIVALENT'}" + (f"; cost {ratio:.2f}x" if ratio else "") + (f"; S2 {'PASS' if ok2 else 'FAIL'}" if ok2 is not None else ""))
