"""STAGE 3d RUN -- NOISE. Gates N1-N5 are pre-registered in cogs_stage3a_prereg.md, and the mechanism is
Phase 6's (f3c09bb): acceptance within a TOLERANCE eps, the output a SET, soundness scored in TWO modes.

CONFABULATION (committed and wrong) is printed before any exact-match number, because that is the property
the component is actually sold on. An exact-match figure that holds up by guessing is worse than one that
falls into abstention.

  N1  the cliff: the eps = 0 engine against training-corruption rate
  N2  soundness in two modes at every rate and for every corruption type SEPARATELY
  N3  the mechanism: tolerance-set induction, eps induced by measured reproduction
  N4  BOTH sides of Phase 6's precondition, via a forced eps x noise grid
  N5  no regression at rate 0

Usage:  python cogs_stage3d.py [quick|full]"""
import os, sys, time, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_adversary import build, COGS_DEFAULT
from cogs_gram import induce, generate, reproduce, EPS_LADDER
from cogs_noise import corrupt, score, TYPES

RATES_FULL = (0.0, 0.01, 0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90)
RATES_QUICK = (0.0, 0.05, 0.20, 0.90)
HDR = f"  {'rate':>6} {'CONFAB':>8} {'abstain':>8} {'EM':>7} {'precision':>10} {'train repro':>12}"


def line(p, r, repro=None):
    return (f"  {p:>6.2f} {r['confab']:>8.4f} {r['abstain']:>8.4f} {r['EM']:>7.4f} "
            f"{r['precision']:>10.4f} {'' if repro is None else f'{repro:>12.4f}'}")


def run(train, test, p, kind=None, force_eps=None, seed=1):
    ctr, _ = corrupt(train, p, kind=kind, seed=seed)
    m = induce(ctr, force_eps=force_eps)
    ok, wr, npar = reproduce(m, ctr)
    return score(m, test, generate), ok / max(ok + wr + npar, 1), m


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    t0 = time.time()
    g, tr, te = build(100, overrides=dict(COGS_DEFAULT))
    print("STAGE 3d -- NOISE. Corruption is applied to TRAINING pairs only; the test set stays clean gold.")
    print(f"Adversary grammar with COGS structure: {len(tr)} train / {len(te)} clean test.")
    print("CONFAB = committed an answer that was wrong. That column is the result; EM is context.\n")

    print("N1/N2 -- THE eps = 0 ENGINE (exact tests everywhere), which is what Stages 3a-3c were")
    print(HDR)
    for p in ((0.0, 0.01, 0.05, 0.20) if mode != "full" else (0.0, 0.01, 0.02, 0.05, 0.10, 0.20)):
        r, rep, _ = run(tr, te, p, force_eps=0.0)
        print(line(p, r, rep))
    print("   -> the cliff Phase 6 predicted for an exact-match engine: 1% corruption is enough.")
    print("      But CONFAB stays at 0: it collapses into ABSTENTION, not into wrong answers.\n")

    print("N2 -- per corruption type at rate 0.05, eps = 0 (a mixed curve attributes nothing)")
    print(f"  {'type':16s} {'CONFAB':>8} {'abstain':>8} {'EM':>7}")
    for k in TYPES:
        r, _, _ = run(tr, te, 0.05, kind=k, force_eps=0.0, seed=2)
        print(f"  {k:16s} {r['confab']:>8.4f} {r['abstain']:>8.4f} {r['EM']:>7.4f}")
    print("   -> the logical-form corruptions are survivable even at eps = 0, because those decisions are")
    print("      already MAJORITY votes over the corpus -- Phase 6's denoise-first, arrived at by accident.")
    print("      The sentence-side ones are fatal: they break the exact tests (a functor is a word appearing")
    print("      in NO logical form; the terminator occurs NOWHERE else). One bad row kills each.\n")

    print("N3 -- THE MECHANISM: tolerance-set induction, eps INDUCED by measured reproduction")
    print(HDR)
    for p in (RATES_FULL if mode == "full" else RATES_QUICK):
        r, rep, m = run(tr, te, p)
        print(line(p, r, rep))
    print("   -> exact match is restored and holds far past the pre-registered 0.05 target; the breaking")
    print("      point is where the clean rows stop forming a plurality per decision.\n")

    print("N3 -- per corruption type at rate 0.20, eps induced")
    print(f"  {'type':16s} {'CONFAB':>8} {'abstain':>8} {'EM':>7}")
    for k in TYPES:
        r, _, _ = run(tr, te, 0.20, kind=k, seed=2)
        print(f"  {k:16s} {r['confab']:>8.4f} {r['abstain']:>8.4f} {r['EM']:>7.4f}")

    print("\nN4 -- BOTH SIDES OF THE PRECONDITION: forced eps (rows) x corruption rate (columns), exact match")
    print("     Phase 6: eps >= corruption is sound and costs abstention; eps < corruption REJECTS THE TRUTH.")
    cols = (0.0, 0.02, 0.05, 0.10, 0.20) if mode == "full" else (0.02, 0.20)
    ladder = EPS_LADDER if mode == "full" else (0.0, 0.02, 0.05)
    print("       eps  " + "".join(f"{c:>8.2f}" for c in cols))
    for e in ladder:
        row = []
        for c in cols:
            r, _, _ = run(tr, te, c, force_eps=e)
            row.append(r["EM"])
        print(f"  {e:>8.2f}  " + "".join(f"{v:>8.3f}" for v in row))
    print("   -> the lower-left triangle is the cliff: an eps below the corruption excludes the truth.")
    print("      Note the induced eps is an ESTIMATE, not a bound, so soundness here is not the theorem it")
    print("      was in Phase 6 -- which is why CONFAB is measured at every cell rather than argued.")

    if mode == "full":
        print("\nN5 + HEADLINE -- REAL COGS")
        from cogs_data import load
        ctr_, dev, test_, gen = load()
        print(HDR)
        for p in (0.0, 0.05, 0.20):
            r, rep, m = run(ctr_, gen, p)
            print(line(p, r, rep))
        print("   -> rate 0.00 must match Stage 3c exactly: gen EM 0.9990, CONFAB 0.0000.")
    print(f"\ntotal {time.time()-t0:.1f}s")
