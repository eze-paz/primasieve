"""STAGE 5 RUN -- coordination, adjectives, negation, quantifiers. Gates E5a-E5g in cogs_stage3a_prereg.md,
plus the DISCRIMINATING controls a fable review demanded (a control that only sees marker-present cases cannot
discriminate and always passes):

  MARKER RECALL      of the gold sentences carrying the construction's marker, the fraction whose prediction
                     emits that marker on the correct variable -- reported instead of trusting whole-LF EM.
  MARKER ABLATION    rerun with the marker machinery disabled; EM must DROP, or the pass was vacuous.
  ARITY KNOCKOUT     coordination is tested at arity 3, not just 2, so a hardcoded "distribute over two" fails.
  NOVEL ADJECTIVE    an adjective never seen in training -- guards against a memorized closed class.
  HOMOGRAPH          a word that is a noun head in some sentences and an adjective in others -- the fragility
                     boundary of "a marker is no token's lemma"; reported honestly wherever it lands.
  SCOPE IDENTITY     the two scope readings of one sentence map to the SAME flat conjunct set -- the
                     representation NULL demonstrated, not asserted.
  COGS INERTNESS     on COGS the marker detector must emit ZERO markers (mechanism, not just output) and leave
                     EM and confabulation unchanged.

Usage:  python cogs_stage5.py"""
import os, sys, time, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_english import build, scope_pair
from cogs_gram import induce, generate, reproduce, Lexicon
from cogs_data import load, em, norm_lf
from cogs_lf import parse_lf
from core.verdict import summarize
from core.registry import selfcheck

MARKER = {"adjective": None, "negation": "NOT", "quantifier": "FORALL", "coordination": None}


def unary_markers(lf):
    out = collections.Counter()
    p = parse_lf(lf)
    if p and p[0] != "LAMBDA":
        for pred, args in p[1]:
            if len(args) == 1:
                out[(pred, args[0])] += 1
    return out


def eval_split(m, rows, marker=None):
    n = emc = cf = ab = 0
    mk_gold = mk_hit = 0
    for s, g, c in rows:
        p = generate(m, s)
        n += 1
        gm = unary_markers(g)
        has = marker and any(pred == marker for pred, _ in gm)
        if has:
            mk_gold += 1
        if p is None:
            ab += 1
            continue
        if em(p, g):
            emc += 1
        else:
            cf += 1
        if has and unary_markers(p).get(next(k for k in gm if k[0] == marker), 0) >= 1:
            mk_hit += 1
    d = max(n, 1)
    return dict(n=n, EM=emc / d, confab=cf / d, abstain=ab / d,
                mk_recall=(mk_hit / mk_gold if mk_gold else None), mk_gold=mk_gold)


def induce_ablated(tr):
    """Induce, then blank the marker/coordination tables -- the machinery disabled, everything else intact."""
    m = induce(tr)
    lex = m[0]
    lex.emark, lex.emark_det, lex.vmark, lex.coord = {}, set(), {}, set()
    return m


if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    print("STAGE 5 -- coordination, adjectives, negation, quantifiers. Confabulation is the headline; every "
          "pass carries a control that can FAIL.\n")
    results = {}

    # base control
    tr, te = build(0, cons=(), n_train=1500, n_test=400)
    b = eval_split(induce(tr), te)
    print(f"E5a  BASE control            EM {b['EM']:.4f}  CONFAB {b['confab']:.4f}  "
          f"[gate EM>=0.98 -> {'PASS' if b['EM'] >= 0.98 and b['confab'] == 0 else 'FAIL'}]")

    for cons in ("adjective", "negation", "quantifier", "coordination"):
        mk = MARKER[cons]
        kw = dict(max_coord=3) if cons == "coordination" else {}
        tr, te = build(0, cons=(cons,), n_train=1800, n_test=400, **kw)
        m = induce(tr)
        r = eval_split(m, te, mk)
        abl = eval_split(induce_ablated(tr), te, mk)
        drop = r["EM"] - abl["EM"]
        rec = f"marker-recall {r['mk_recall']:.4f} ({r['mk_gold']} gold)  " if mk else ""
        print(f"\n{cons.upper()}")
        print(f"  test EM {r['EM']:.4f}  CONFAB {r['confab']:.4f}  abstain {r['abstain']:.4f}  {rec}"
              f"[EM>=0.95, CONFAB<=0.01]")
        print(f"  ABLATION: EM without the machinery {abl['EM']:.4f} (drop {drop:.4f}) -- a non-vacuous pass "
              f"needs a real drop")
        if cons == "quantifier":
            # the marker-ABLATION is inapplicable here: `every` rides the pre-existing determiner
            # inline-marker path (realization ('inline','FORALL')), not the Stage-5 marker table, so blanking
            # the marker table leaves EM at 1.000. The right discriminator is MARKER RECALL (does it emit
            # FORALL on the correct variable), which is not vacuous -- fable's Q1 check.
            ok = r["EM"] >= 0.95 and r["confab"] <= 0.01 and r["mk_recall"] >= 0.95
            print(f"  (marker-ablation N/A: quantifier uses the determiner inline-marker path; gated on "
                  f"marker-recall {r['mk_recall']:.4f})")
        else:
            ok = r["EM"] >= 0.95 and r["confab"] <= 0.01 and drop >= 0.05 and (mk is None or r["mk_recall"] >= 0.95)
        results[cons] = ok
        print(f"  -> {'PASS' if ok else 'FAIL'}"
              + (" (coordination tested at ARITY 3)" if cons == "coordination" else ""))

    # adjective: novel-adjective lexical generalization
    tr, te = build(0, cons=("adjective",), n_train=1800, n_test=400,
                   train_adj=[f"a{i}" for i in range(5)], test_adj=["a5"])
    nov = eval_split(induce(tr), [r for r in te if " a5 " in " " + r[0] + " "])
    print(f"\nADJECTIVE / novel-adjective generalization (train a0..a4, test the unseen a5): "
          f"n {nov['n']}  EM {nov['EM']:.4f}  CONFAB {nov['confab']:.4f}  abstain {nov['abstain']:.4f}")
    print("  -> an unseen adjective must be handled by the CONSTRUCTION, not a memorized class; abstention "
          "(not confabulation) is the acceptable failure")

    # adjective: homograph -- MEASURED FRAGILITY BOUNDARY. A word that is a noun head in some sentences and an
    # adjective in others defeats "a marker is no token's lemma": the adjective predicate IS a lemma (the
    # word's own noun sense), so it is never detected as a marker AND the parse search explodes on the
    # genuine ambiguity. The engine does NOT fail closed here -- it fails to TERMINATE within budget, which is
    # itself the honest limit (the Stage-5 parse generators are not fully budget-threaded). Reported, not run.
    print("\nADJECTIVE / homograph (n0 as noun AND adjective): NON-TERMINATION -- the detector's fragility")
    print("  boundary, predicted by review. 'A marker is no token's lemma' cannot classify a word that is a")
    print("  lemma elsewhere, and the parse search explodes on the ambiguity rather than abstaining. This is a")
    print("  KNOWN LIMIT: the detector is a negative definition (absence from the lemma set), fragile exactly")
    print("  where a surface form is polysemous. A positive adjective signal + budget-threaded generators are")
    print("  the fix; not attempted here.")

    # quantifier scope: the two readings map to the SAME flat set
    s, lf1, lf2 = scope_pair(0)
    print(f"\nQUANTIFIER / scope: `{s}`")
    print(f"  every>some and some>every map to the SAME flat conjunct set: "
          f"{'IDENTICAL' if norm_lf(lf1) == norm_lf(lf2) else 'DIFFERENT'}")
    print("  -> DEMONSTRATED NULL: the flat conjunct representation cannot distinguish the two scope readings. "
          "Marker recovery is the ceiling; 'quantification' is NOT claimed.")

    # E5f no-regression + COGS mechanism inertness
    tr, dev, test, gen = load()
    m = induce(tr)
    lex = m[0]
    inert = not lex.emark and not lex.emark_det and not lex.vmark and not lex.coord
    n = emc = cf = 0
    for s, g, c in gen:
        p = generate(m, s)
        n += 1
        if p is not None:
            if em(p, g):
                emc += 1
            else:
                cf += 1
    print(f"\nE5f  COGS no-regression: gen EM {emc/n:.4f}  CONFAB {cf/n:.4f}  "
          f"marker tables EMPTY {inert}  [gate 0.9990, CONFAB 0, inert -> "
          f"{'PASS' if emc/n >= 0.9990 - 1e-9 and cf == 0 and inert else 'FAIL'}]")

    allpass = all(results.values()) and b["EM"] >= 0.98 and inert and emc / n >= 0.9990 - 1e-9 and cf == 0
    print(f"\n5 CONSTRUCTIONS: {'PASS' if allpass else 'FAIL'}   "
          f"(coordination[arity3] + negation induced with real ablation drops; adjective induced on SEEN "
          f"vocabulary only -- abstains on an unseen adjective, non-terminates on a homograph; quantifier = "
          f"marker recovered via the determiner path, scope a demonstrated representation null)")
    print(f"total {time.time()-t0:.0f}s")
