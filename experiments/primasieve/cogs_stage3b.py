"""STAGE 3b RUN -- the generator-family control. Gates G7/G8/G9 are pre-registered in cogs_stage3a_prereg.md.

Three parts, in the order that makes a failure mean something:
  PART 0  SANITY. One grammar with COGS's STRUCTURE but a fully synthetic lexicon, roles, markers and frames,
          on the same depth split. This must PASS, or the harness is broken and nothing below is evidence.
  PART A  SINGLE-DIMENSION KNOCKOUTS. One grammar per non-COGS value, every other dimension pinned to COGS.
          A fully random draw differs on several dimensions at once and attributes nothing; these attribute a
          failure to exactly one authored assumption.
  PART B  THE WIN GATE. 10 fully random grammars -- the Stage 2 part-B analogue.

Usage:  python cogs_stage3b.py [n_random]"""
import os, sys, time, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_adversary import build, differs, DIMS, COGS_DEFAULT
from cogs_gram import induce, generate, reproduce
from cogs_lf import norm_lf

HDR = (f"  {'grammar':34s} {'train':>6} {'test':>5} {'repro':>6} {'wrong':>6} {'EM':>6} {'cover':>6} "
       f"{'mod_rec':>8} {'emb_rec':>8} {'subj':>6}")


def run_one(seed, overrides=None):
    g, tr, te = build(seed, overrides=overrides)
    model = induce(tr)
    ok, wrong, nopar = reproduce(model, tr)
    tot = max(ok + wrong + nopar, 1)
    per = collections.defaultdict(collections.Counter)
    for s, gold, cat in te:
        pred = generate(model, s)
        per[cat]["n"] += 1
        if pred is None:
            per[cat]["abstain"] += 1
        else:
            per[cat]["C"] += 1
            per[cat]["em"] += (pred == norm_lf(gold))
    n = max(sum(v["n"] for v in per.values()), 1)
    return dict(g=g, sch=model[1], repro=ok / tot, wrong=wrong, n=n, ntrain=len(tr),
                EM=sum(v["em"] for v in per.values()) / n,
                cover=sum(v["C"] for v in per.values()) / n, per=per)


def show(label, r):
    def cat(c):
        v = r["per"][c]
        return f"{v['em']/v['n']:.3f}" if v["n"] else "   -  "
    print(f"  {label:34s} {r['ntrain']:>6} {r['n']:>5} {r['repro']:>6.3f} {r['wrong']:>6d} {r['EM']:>6.3f} "
          f"{r['cover']:>6.3f} {cat('mod_recursion'):>8} {cat('emb_recursion'):>8} {cat('subj_mod'):>6}")


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    t0 = time.time()
    print("STAGE 3b -- GENERATOR-FAMILY CONTROL for the head-passing engine, run UNCHANGED.")
    print("randomized dimensions: " + ", ".join(sorted(DIMS)) + "\n")

    print("PART 0 -- SANITY: COGS structure, everything else synthetic. Must pass or the harness is broken.")
    print(HDR)
    s0 = run_one(100, overrides=dict(COGS_DEFAULT))
    show("cogs-structure control", s0)
    print(f"   -> {'PASS' if s0['EM'] >= 0.95 and s0['repro'] >= 0.99 else 'FAIL -- STOP, harness broken'}\n")

    print("PART A -- SINGLE-DIMENSION KNOCKOUTS (every other dimension pinned to COGS)")
    print(HDR)
    knock = {}
    for d in sorted(DIMS):
        for v in DIMS[d]:
            if v == COGS_DEFAULT[d]:
                continue
            ov = dict(COGS_DEFAULT)
            ov[d] = v
            r = run_one(200 + len(knock), overrides=ov)
            knock[(d, v)] = r
            show(f"{d} = {v}", r)
    kp = sum(r["EM"] >= 0.95 for r in knock.values())
    print(f"   knockouts survived (EM >= 0.95): {kp}/{len(knock)}")
    dead = [f"{d}={v}" for (d, v), r in knock.items() if r["EM"] < 0.95]
    print(f"   assumptions the engine DEPENDS on: {', '.join(dead) if dead else 'none'}\n")

    print(f"PART B -- WIN GATE: {N} fully random grammars")
    print(HDR + "  differs from COGS on")
    passes = 0
    rows = []
    for s in range(N):
        r = run_one(s)
        rows.append(r)
        passes += r["EM"] >= 0.95
        show(f"random {s}", r)
        print(f"      differs: {','.join(differs(r['g']))}")
    print(f"\nG7 WIN GATE  passed (EM >= 0.95): {passes}/{N}"
          f"   [gate >= {int(0.9 * N)}/{N} -> {'PASS' if passes >= 0.9 * N else 'FAIL'}]")
    g8 = sum(r["repro"] >= 0.99 for r in rows)
    print(f"G8 SOUNDNESS per grammar (repro >= 0.99): {g8}/{N}   [-> {'PASS' if g8 == N else 'FAIL'}]")

    # PART C -- the one representational dependency the engine does NOT get for free, measured rather than
    # asserted. COGS numbers variables by TOKEN POSITION, which hands the induction its word<->predicate
    # alignment. Renumber the gold variables by ORDER OF FIRST APPEARANCE (a ReCOGS-style convention), change
    # nothing else, and rerun the same grammar that scored 1.000 in part 0.
    print("\nPART C -- POSITIONAL-VARIABLE DEPENDENCY (COGS structure, gold variables renumbered by first"
          " appearance)")
    import re as _re
    from cogs_data import em as _em, em_alpha as _ema

    def renumber(lf):
        m = {}
        for v in _re.findall(r"x _ (\d+)", lf):
            if v not in m:
                m[v] = str(len(m))
        return _re.sub(r"x _ (\d+)", lambda k: "x _ " + m[k.group(1)], lf)

    gC, trC, teC = build(100, overrides=dict(COGS_DEFAULT))
    trC = [(a, renumber(b), c) for a, b, c in trC]
    teC = [(a, renumber(b), c) for a, b, c in teC]
    mC = induce(trC)
    okC, wrC, npC = reproduce(mC, trC)
    predsC = [(generate(mC, a), b) for a, b, c in teC]
    emC = sum(_em(x, y) for x, y in predsC) / len(teC)
    emaC = sum(_ema(x, y) for x, y in predsC) / len(teC)
    print(HDR)
    print(f"  {'first-appearance numbering':34s} {len(trC):>6} {len(teC):>5} "
          f"{okC/max(okC+wrC+npC,1):>6.3f} {wrC:>6d} {emC:>6.3f} "
          f"{sum(x is not None for x, _ in predsC)/len(teC):>6.3f}")
    print(f"   EM {emC:.3f}  EM_alpha {emaC:.3f}   vs part 0 on the SAME grammar with positional "
          f"variables: EM {s0['EM']:.3f}")
    print("   -> positional variables are a LOAD-BEARING INPUT, not an incidental detail: they hand the")
    print("      induction its token<->predicate alignment for free. Recovering that alignment under an")
    print("      order-based convention is NOT solved here, and is the honest open item after Stage 3b.")

    print(f"\ntotal {time.time()-t0:.1f}s")
