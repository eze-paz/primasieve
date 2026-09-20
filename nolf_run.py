"""PHASE 3 -- GATE RUNNER for language from situations only (nolf_prereg.md). ZERO LLM.

One fit per invocation (each stays inside the 5-minute test cap); `--report` scores the gates over the saved fits.

    python nolf_run.py --world records            # fit + score, writes nolf_results.json[records]
    python nolf_run.py --world strings --shuffled # the G5 knockout: every word form re-permuted
    python nolf_run.py --report                   # G1-G7 over whatever fits are saved

Baselines (G3): a bag-of-words truth predictor and a nearest-sentence Analogy, both situation-blind. Scoring is
two-mode (core.verdict): confabulation first. G6 (scope collision) is not testable on these worlds -- neither
describer has a scope interaction -- and is reported as such, not scored."""
import os, sys, json, time, collections, re
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_worlds as NW
import nolf_learn as NL
from core.verdict import score_two_mode, line

OUT = os.path.join(HERE, "nolf_results.json")


class BagOfWords:
    """the truth value most often seen with the sentence's multiset of tokens; abstains on a new bag."""
    def __init__(self, train):
        self.c = collections.defaultdict(collections.Counter)
        for sit, toks, tv in train: self.c[tuple(sorted(toks))][tv] += 1
    def __call__(self, x):
        c = self.c.get(tuple(sorted(x[1])))
        if not c: return None
        (tv, n), = c.most_common(1)
        return tv if n / sum(c.values()) >= 0.9 else None


class Analogy:
    """nearest training sentence by token overlap, its truth value copied -- the Stage 1 killer."""
    def __init__(self, train):
        self.rows = [(set(toks), tv) for _, toks, tv in train]
    def __call__(self, x):
        s = set(x[1])
        best = max(self.rows, key=lambda r: len(r[0] & s) - 0.01 * len(r[0] ^ s))
        return best[1] if len(best[0] & s) >= max(1, len(s) - 1) else None


def fit_one(world, shuffled, budget):
    W = (NW.Records(seed=71) if shuffled else NW.Records()) if world == "records" else (NW.Strings(seed=72) if shuffled else NW.Strings())
    sp = NW.splits(W, 1)
    print(f"=== {W.name}{' SHUFFLED' if shuffled else ''} (lexicon seed {W.lex_seed}): train {len(sp['train'])}  iid {len(sp['heldout_iid'])}  "
          f"compositional {len(sp['heldout_comp'])}  held-out pairs {len(sp['held_pairs'])}", flush=True)
    L = NL.Learner(time_budget=budget).fit(sp["train"])
    print(f"  learner: {len(L.cls)} words in {len(L.members)} classes; {len(L.grammar)} constructions in {L.seconds:.0f}s (table {L.table_seconds:.0f}s)")
    for e in L.log:
        k = [x if x == "B" else x[1] for x in e[1]]
        print(f"    {'learned ' if e[0] == 'learned' else 'UNSOLVED'} {e[2]:4d} rows  {e[3] if e[0] == 'learned' else ''}  <- {k}")
    res = {}
    for name, m in [("bag-of-words", BagOfWords(sp["train"])), ("analogy", Analogy(sp["train"])), ("learner", L)]:
        for split in ("heldout_iid", "heldout_comp"):
            r = score_two_mode(m, [((sit, toks), tv) for sit, toks, tv in sp[split]])
            res[f"{name}/{split}"] = {k: v for k, v in r.items() if k != "per"}
            print(line(f"{name} / {split}", r, width=30))
    hidden = {f: c for c, f in W.lex.c2f.items()}
    lex = {}
    for (w, kind), vals in L.dom.items():
        if len(vals) == 1: lex.setdefault(hidden.get(w, w), {})[kind] = repr(next(iter(vals)))[:12]
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d[f"{world}{'_shuffled' if shuffled else ''}"] = dict(scores=res, constructions=len(L.grammar), seconds=round(L.seconds),
                                                          learned=[[x if x == "B" else x[1] for x in e[1]] for e in L.log if e[0] == "learned"],
                                                          unsolved=[[x if x == "B" else x[1] for x in e[1]] for e in L.log if e[0] != "learned"],
                                                          lexicon=lex)
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True, default=str)


def report():
    d = json.load(open(OUT))
    ok = True
    for w in ("records", "strings"):
        if w not in d: print(f"{w}: NO FIT SAVED"); ok = False; continue
        r = d[w]["scores"]; Lc = r["learner/heldout_comp"]; Li = r["learner/heldout_iid"]
        base = max(r["bag-of-words/heldout_comp"]["EM"], r["analogy/heldout_comp"]["EM"])
        g1 = Li["confab"] == 0 and Lc["confab"] == 0
        g2 = Lc["EM"] >= 0.80 and Lc["confab"] == 0
        g3 = Lc["EM"] >= 1.5 * base and Lc["confab"] == 0
        print(f"{w}: G1 soundness {g1}   G2 compositional >= 0.80 at 0 confab {g2} (EM {Lc['EM']:.3f}; iid {Li['EM']:.3f})   "
              f"G3 >= 1.5x better baseline ({base:.3f}) {g3}   constructions {d[w]['constructions']}")
        ok &= g1 and g2 and g3
        s = d.get(w + "_shuffled")
        if s:
            Sc = s["scores"]["learner/heldout_comp"]
            g5 = abs(Sc["EM"] - Lc["EM"]) <= 0.05 and Sc["confab"] == 0
            print(f"    G5 shuffled lexicon: compositional EM {Sc['EM']:.3f} vs {Lc['EM']:.3f}, confab {Sc['confab']:.4f}   [{g5}]")
            ok &= g5
        else:
            print("    G5 shuffled lexicon: NO FIT SAVED"); ok = False
    src = open(NL.__file__, encoding="utf-8").read()
    leak = [x for x in ("agent", "theme", "recipient", "FORALL", "LAMBDA", "x_") if re.search(r"\b" + re.escape(x), src)]
    print(f"G7 LF vocabulary in nolf_learn.py: {leak}   [{not leak}]"); ok &= not leak
    print("G4 same code on both worlds: structural (one Learner, no world import: see core_selftest C4)")
    print("G6 scope collision: NOT TESTABLE on these worlds -- reported, not scored")
    print("\nNO-LF LANGUAGE: PASS" if ok else "\nNO-LF LANGUAGE: NOT PASSED -- read the gate lines; the learner is real and the budget is the bar it misses")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report(); sys.exit(0)
    world = sys.argv[sys.argv.index("--world") + 1] if "--world" in sys.argv else "records"
    budget = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else 240
    t0 = time.time(); fit_one(world, "--shuffled" in sys.argv, budget); print(f"({time.time()-t0:.0f}s)")
