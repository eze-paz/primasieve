"""STAGE 4a RUN -- constructions COMPOSED from the existing GAP combinator, gated on SLOG.

SLOG (Li et al. 2023) extends COGS with relative clauses, wh-questions, deeper PP/CP recursion and
center-embedding. Its official generalization set is password-protected; its test.tsv carries the new
construction categories and is the gate here. Gates A1-A5 are pre-registered in cogs_stage3a_prereg.md.

What 4a is, stated plainly: relative clauses and wh-questions are NOT new combinators. Both are a clause with
a GAP filled from outside -- the modified noun's head, or the fronted question word -- which the engine already
had for control. What was added is two ATTACHMENT SITES for it, plus three induced facts (a SET of sentence
terminators, the relative-clause marker and its modifier template, the question words). The gap's POSITION
inside the frame is learned per frame; the relative clause's EXTENT is decided by frame licensing +
uniqueness, with subcategorization as a tie-break, and abstention on genuine ambiguity.

Usage:  python cogs_stage4a.py"""
import os, sys, time, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_data import em
from cogs_gram import induce, generate, reproduce
from core.registry import selfcheck

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_nldata", "slog", "data", "cogs_LF")


def load_slog():
    def rd(f):
        return [tuple(l.rstrip("\n").split("\t")[:3])
                for l in open(os.path.join(D, f), encoding="utf-8") if l.strip()]
    return rd("train.tsv"), rd("dev.tsv"), rd("test.tsv")


GATES = {  # category -> (min EM, max CONFAB)
    "object_modifying_RC": (0.90, 0.01), "wh_Q_simple_trans": (0.90, 0.01),
    "center_embed_2": (0.90, 0.01), "center_embed_4": (0.90, 0.01),
    "pp_4": (0.90, 0.01), "cp_4": (0.90, 0.01), "in_distribution": (0.99, 0.01),
}

if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    tr, dev, te = load_slog()
    print(f"STAGE 4a -- SLOG: train {len(tr)}  test {len(te)}  (the Stage 3 engine scored EM 0.000, "
          f"abstain 1.000 on ALL of it before 4a: one terminator assumption killed every parse)\n")
    m = induce(tr, verbose=True)
    lex = m[0]
    print(f"  induced facts: terminators {sorted(lex.terminators)}  rc_markers {sorted(lex.rc_markers)} "
          f"rc_mid {lex.rc_mid}  wh {lex.wh}   ({time.time()-t0:.0f}s)")
    ok, wr, npar = reproduce(m, tr)
    print(f"  train reproduction {ok/max(ok+wr+npar,1):.4f}  wrong {wr}  no-parse {npar}\n")

    per = collections.defaultdict(collections.Counter)
    for s, g, c in te:
        p = generate(m, s)
        per[c]["n"] += 1
        if p is None:
            per[c]["ab"] += 1
        elif em(p, g):
            per[c]["em"] += 1
        else:
            per[c]["cf"] += 1
    print(f"  {'SLOG test category':22s} {'n':>5} {'CONFAB':>7} {'abstain':>8} {'EM':>6}   gate")
    allok = True
    for c, v in sorted(per.items(), key=lambda kv: -kv[1]["n"]):
        n = v["n"]
        emr, cfr = v["em"] / n, v["cf"] / n
        g = GATES.get(c)
        verdict = ""
        if g:
            okc = emr >= g[0] and cfr <= g[1]
            allok &= okc
            verdict = f"EM>={g[0]} CONFAB<={g[1]} -> {'PASS' if okc else 'FAIL'}"
        print(f"  {c:22s} {n:>5} {cfr:>7.3f} {v['ab']/n:>8.3f} {emr:>6.3f}   {verdict}")
    print(f"\n4a SLOG CONSTRUCTIONS: {'PASS' if allok else 'FAIL'}   "
          f"(A4 no-regression is checked by cogs_stage3a.py full, cogs_stage3b.py, cogs_stage3c.py, "
          f"core_selftest.py)")
    print(f"total {time.time()-t0:.0f}s")
