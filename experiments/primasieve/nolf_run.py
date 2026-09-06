"""PHASE 3 -- GATE RUNNER for language from situations only (nolf_prereg.md). ZERO LLM.

Runs the two sealed worlds through the BASELINES the prereg pins (G3: bag-of-words truth predictor; nearest-sentence
Analogy) and through the learner in `nolf_learn.py`, scoring truth prediction on the iid and the compositional
held-out splits in two-mode form (core.verdict). The learner is the OPEN SLOT of Phase 3: the version shipped
with this harness ABSTAINS on everything, so this file today establishes the baseline numbers the real learner
must beat and demonstrates the harness end-to-end. No claim is registered until the learner exists and passes
G1-G7; the verdict line below prints PASS only then.

    python nolf_run.py            # both worlds, baselines + learner, ~1 min"""
import os, sys, time, collections, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nolf_worlds as NW
import nolf_learn as NL
from core.verdict import score_two_mode, line


class BagOfWords:
    """G3 baseline 1: predicts the truth value most often seen with the sentence's multiset of tokens; abstains on
    a never-seen bag. Situation-blind on purpose: if it scores well, the describer leaks truth through form."""
    def __init__(self, train):
        self.c = collections.defaultdict(collections.Counter)
        for sit, toks, tv in train: self.c[tuple(sorted(toks))][tv] += 1
    def __call__(self, x):
        sit, toks = x
        c = self.c.get(tuple(sorted(toks)))
        if not c: return None
        (tv, n), = c.most_common(1)
        return tv if n / sum(c.values()) >= 0.9 else None


class Analogy:
    """G3 baseline 2: nearest training sentence by token overlap, its truth value copied -- the Stage 1 killer."""
    def __init__(self, train):
        self.rows = [(set(toks), tv) for _, toks, tv in train]
    def __call__(self, x):
        sit, toks = x
        s = set(toks)
        best = max(self.rows, key=lambda r: len(r[0] & s) - 0.01 * len(r[0] ^ s))
        return best[1] if len(best[0] & s) >= max(1, len(s) - 1) else None


def run_world(W, seed=1):
    sp = NW.splits(W, seed)
    print(f"\n=== {W.name}: train {len(sp['train'])}  iid {len(sp['heldout_iid'])}  compositional {len(sp['heldout_comp'])}  held-out pairs {len(sp['held_pairs'])}")
    out = {}
    models = [("bag-of-words", BagOfWords(sp["train"])), ("analogy", Analogy(sp["train"])),
              ("learner", NL.Learner().fit(sp["train"]))]
    for name, m in models:
        for split in ("heldout_iid", "heldout_comp"):
            rows = [((sit, toks), tv) for sit, toks, tv in sp[split]]
            r = score_two_mode(m, rows)
            out[(name, split)] = r
            print(line(f"{name} / {split}", r, width=30))
    return out


if __name__ == "__main__":
    t0 = time.time()
    print("PHASE 3 -- LANGUAGE FROM SITUATIONS ONLY: baselines and the learner slot (nolf_prereg.md)")
    res = {}
    for W in (NW.Records(), NW.Strings()):
        res[W.name] = run_world(W)
    ok = True
    for wname, r in res.items():
        L = r[("learner", "heldout_comp")]; base = max(r[("bag-of-words", "heldout_comp")]["EM"], r[("analogy", "heldout_comp")]["EM"])
        g1 = r[("learner", "heldout_iid")]["confab"] == 0
        g2 = L["EM"] >= 0.80 and L["confab"] == 0
        g3 = L["EM"] >= 1.5 * base and L["confab"] == 0
        print(f"\n{wname}: G1 soundness {g1}   G2 compositional coverage >= 0.80 at 0 confab {g2} (EM {L['EM']:.3f})   "
              f"G3 >= 1.5x the better baseline ({base:.3f}) {g3}")
        ok &= g1 and g2 and g3
    print("\nNO-LF LANGUAGE: PASS" if ok else "\nNO-LF LANGUAGE: NOT PASSED -- the learner slot is open; the numbers above are the bar it must clear")
    print(f"({time.time()-t0:.0f}s)")
