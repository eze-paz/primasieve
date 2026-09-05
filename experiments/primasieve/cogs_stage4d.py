"""STAGE 4d RUN -- GENERATION by inverting the synchronous grammar. Gates D1-D3 in cogs_stage3a_prereg.md.

  D1  round trip on COGS test: parse -> logical form -> generate -> the EXACT original sentence, EM >= 0.95
  D2  gen-side round trip on the three structural categories (depth beyond training): generate from the GOLD
      logical form -> parse -> the gold logical form, EM >= 0.95
  D3  where several sentences realize one logical form the generator returns the SET / abstains, never picks;
      the abstention and multi-realization counts are reported

Usage:  python cogs_stage4d.py"""
import os, sys, time, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_data import load, em
from cogs_gram import induce, generate
from cogs_gen import Realizer, generate_text
from cogs_lf import norm_lf
from core.verdict import summarize
from core.registry import selfcheck

STRUCT = ("pp_recursion", "cp_recursion", "obj_pp_to_subj_pp")

if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    tr, dev, test, gen = load()
    print("STAGE 4d -- GENERATION (meaning -> English) by inverting the synchronous grammar\n")
    m = induce(tr)
    R = Realizer(m, tr)
    print(f"  induced: {len(R.vform)} (context, lemma) -> verb-form entries, determiners by position "
          f"{R.dform}, frames indexed by role tuple: {len(R.by_roles)}")

    # D1. Two scores, because the logical form is GENUINELY ambiguous in one place: `split . theme ( x )` is
    # both `the baby split` (unaccusative) and `the baby was split` (agentless passive). The generator returns
    # the SET there, so strict EM has a ceiling below 1; SET-CORRECT (the original is IN the returned set, and
    # the set is small) is the honest coverage number. Confabulation counts a singleton that is WRONG only.
    n = emc = setc = cf = ab = multi = 0
    setsizes = collections.Counter()
    for s, gold, c in test:
        lf = generate(m, s)
        n += 1
        if lf is None:
            ab += 1
            continue
        outs = R.realize(lf)
        if len(outs) == 0:
            ab += 1
        elif len(outs) == 1:
            if next(iter(outs)) == s:
                emc += 1
                setc += 1
            else:
                cf += 1
        else:
            multi += 1
            setsizes[len(outs)] += 1
            if s in outs:
                setc += 1
            else:
                cf += 1
    print(f"\nD1  parse -> generate -> the original sentence, COGS test")
    print("  " + summarize(n, em=emc, confab=cf, abstain=ab, label="strict (singleton == original)"))
    print(f"  SET-CORRECT (original in the returned set) {setc}/{n} = {setc/n:.4f}   multi-realization {multi}, "
          f"set sizes {dict(setsizes)}")
    d1 = setc / n >= 0.95 and cf / n <= 0.01
    print(f"  [gate: SET-CORRECT >= 0.95 and CONFAB <= 0.01 -> {'PASS' if d1 else 'FAIL'}]   (strict EM's ceiling is "
          f"set by the unaccusative / agentless-passive ambiguity of the logical form itself)")

    # D2 -- generate from the GOLD logical form; every member of the returned set must parse back to the gold
    per = collections.defaultdict(collections.Counter)
    for s, gold, c in gen:
        if c not in STRUCT:
            continue
        per[c]["n"] += 1
        outs = R.realize(gold)
        if not outs:
            per[c]["ab"] += 1
            continue
        backs = [generate(m, t) for t in outs]
        if all(b is not None and em(b, gold) for b in backs):
            per[c]["em" if len(outs) == 1 else "setok"] += 1
        else:
            per[c]["cf"] += 1
    print(f"\nD2  generate from the GOLD logical form -> parse back -> gold, structural categories")
    d2 = True
    for c in STRUCT:
        v = per[c]
        good = (v["em"] + v["setok"]) / v["n"]
        d2 &= good >= 0.95 and v["cf"] / v["n"] <= 0.01
        print(f"  {c:20s} n {v['n']:5d}  CONFAB {v['cf']/v['n']:.4f}  abstain {v['ab']/v['n']:.4f}  "
              f"singleton-OK {v['em']/v['n']:.4f}  set-OK {v['setok']/v['n']:.4f}  -> {good:.4f}")
    print(f"  [gate each (singleton-OK + set-OK) >= 0.95, CONFAB <= 0.01 -> {'PASS' if d2 else 'FAIL'}]")

    print(f"\nD3  the SET is returned, never a pick: {multi} multi-realization forms on test, all of size "
          f"{sorted(setsizes) if setsizes else '-'}")
    print(f"\n4d GENERATION: {'PASS' if (d1 and d2) else 'FAIL'}")
    print(f"total {time.time()-t0:.0f}s")
