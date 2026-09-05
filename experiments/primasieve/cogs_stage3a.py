"""STAGE 3a RUN -- induce the head-passing grammar, then score the PRE-REGISTERED gates in
cogs_stage3a_prereg.md. Gates: G1 soundness on train, G2 in-distribution test, G3 the three structural
categories substitution cannot solve, G4 the 18 substitution-solvable kill gates, G6 EM vs EM_alpha.

Usage:  python cogs_stage3a.py [quick|full]
  quick  -- induce on a 6000-row train slice and score dev + the 3 structural categories (fits the 5-min cap)
  full   -- induce on all of train and score train / test / all 21 gen categories"""
import os, sys, time, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_data import load, em, em_alpha, norm_lf
from cogs_gram import Engine, induce, generate, reproduce, parse_sentence
from cogs_lf import parse_lf, alpha_canon_bag

STRUCTURAL = ("pp_recursion", "cp_recursion", "obj_pp_to_subj_pp")


def score(lex, roles, order, rows):
    agg = collections.Counter()
    per = collections.defaultdict(collections.Counter)
    for s, gold, cat in rows:
        pred = generate(lex, roles, order, s)
        agg["n"] += 1
        per[cat]["n"] += 1
        if pred is None:
            agg["abstain"] += 1
            per[cat]["abstain"] += 1
            continue
        agg["C"] += 1
        per[cat]["C"] += 1
        a, b = em(pred, gold), em_alpha(pred, gold)
        agg["em"] += a
        agg["ema"] += b
        per[cat]["em"] += a
        per[cat]["ema"] += b
    return agg, per


def line(name, agg):
    n = max(agg["n"], 1)
    return (f"  {name:22s} n {agg['n']:6d}  EM {agg['em']/n:.4f}  EM_alpha {agg['ema']/n:.4f}  "
            f"coverage {agg['C']/n:.4f}  abstain {agg['abstain']:5d}")


def failures(lex, roles, order, rows, k=4):
    out = []
    for s, gold, cat in rows:
        pred = generate(lex, roles, order, s)
        if pred is None or pred != norm_lf(gold):
            out.append((cat, s, gold, pred))
            if len(out) >= k:
                break
    return out


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    t0 = time.time()
    tr, dev, test, gen = load()
    fit = tr if mode == "full" else tr[:6000]
    print(f"STAGE 3a -- head-passing synchronous grammar. induce on {len(fit)} train rows ({mode})\n")
    lex, roles, order = induce(fit, verbose=True)
    print(f"  induction {time.time()-t0:.1f}s\n")

    ok, wrong, nopar = reproduce(lex, roles, order, tr)
    tot = ok + wrong + nopar
    print(f"G1 SOUNDNESS  train reproduction {ok}/{tot} = {ok/tot:.4f}   wrong {wrong}  no-parse {nopar}"
          f"   [gate >= 0.99 -> {'PASS' if ok/tot >= 0.99 else 'FAIL'}]")

    a, _ = score(lex, roles, order, test if mode == "full" else test[:2000])
    print(f"G2 IN-DISTRIBUTION\n{line('test', a)}"
          f"   [gate EM >= 0.95 -> {'PASS' if a['em']/max(a['n'],1) >= 0.95 else 'FAIL'}]")

    rows = gen if mode == "full" else [r for r in gen if r[2] in STRUCTURAL]
    agg, per = score(lex, roles, order, rows)
    print(f"\nG3 STRUCTURAL (the real test -- substitution cannot solve these)")
    g3 = True
    for c in STRUCTURAL:
        v = per[c]
        if not v["n"]:
            continue
        g3 &= v["em"] / v["n"] >= 0.90
        print(line(c, v))
    print(f"   [gate each EM >= 0.90 -> {'PASS' if g3 else 'FAIL'}]")

    others = [(c, v) for c, v in per.items() if c not in STRUCTURAL and v["n"]]
    if others:
        print(f"\nG4 SUBSTITUTION KILL GATES ({len(others)} categories)")
        for c, v in sorted(others, key=lambda kv: kv[1]["em"] / kv[1]["n"]):
            print(line(c, v))
        mean = sum(v["em"] / v["n"] for _, v in others) / len(others)
        print(f"   mean EM over the {len(others)} substitution categories {mean:.4f}"
              f"   [gate >= 0.90 -> {'PASS' if mean >= 0.90 else 'FAIL'}]")

    print(f"\nG6 BOOKKEEPING vs SEMANTICS{line('gen (all scored)', agg)}")
    n = max(agg["n"], 1)
    gap = (agg["ema"] - agg["em"]) / n
    print(f"   EM_alpha - EM = {gap:.4f}  (a large gap would be a serializer bug, not a semantic result)")

    # OOV accounting: an abstain caused by a word absent from the entire training file is a DATA limit, not a
    # structural failure, and the prereg requires it to be reported rather than folded into the score.
    oov = collections.Counter()
    nz = 0
    for s_, gold, cat in rows:
        if generate(lex, roles, order, s_) is None:
            m = [w for w in s_.split() if w not in lex.cls]
            if m:
                oov.update(m)
            else:
                nz += 1
    print(f"   abstains caused by UNSEEN VOCABULARY {dict(oov)}"
          f"   -- abstains with every word known: {nz}")

    fs = [f for f in failures(lex, roles, order, rows, k=10 ** 9)
          if all(w in lex.cls for w in f[1].split())]
    print(f"\nnon-vocabulary failures: {len(fs)}")
    for cat, s_, gold, pred in fs[:3]:
        print(f"  [{cat}] {s_}\n    gold {gold}\n    pred {pred}")
    print(f"\ntotal {time.time()-t0:.1f}s")
