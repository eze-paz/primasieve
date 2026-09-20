"""STAGE 2 -- SCAN loader, eval harness, and the two mandatory baselines (carried forward from Stage 1, where the
analogy knockout killed the engine). SCAN: English commands -> action sequences, exact match on the FULL output.
Splits: simple (random, in-distribution), addprim_jump (train sees 'jump' only in isolation; test combines it),
length (test outputs longer than any in train). Seq2seq models fail the latter two badly; LLMs pass SCAN only with
a hand-designed decomposition crutch. The scientific payload of Stage 2 is the CONTRAST: analogy was at ceiling on
Stage 1's memorizable task and should FAIL here, where the answer cannot be copied from a near neighbour."""
import os, sys, collections

D = os.path.join(os.path.dirname(__file__), "_nldata", "scan")
SPLITS = {"simple": ("tasks_train_simple.txt", "tasks_test_simple.txt"),
          "addprim_jump": ("tasks_train_addprim_jump.txt", "tasks_test_addprim_jump.txt"),
          "length": ("tasks_train_length.txt", "tasks_test_length.txt")}

def read(fn):
    out = []
    for line in open(os.path.join(D, fn), encoding="utf-8"):
        line = line.strip()
        if not line.startswith("IN:"): continue
        cmd, act = line[3:].split("OUT:")
        out.append((cmd.strip().split(), act.strip().split()))
    return out

def load(split):
    tr, te = SPLITS[split]
    return read(tr), read(te)

# ---------- baselines: now core.gates, shared with COGS and every future testbed ----------
# These were duplicated here and in cogs_data.py. Analogy is the knockout that KILLED Stage 1 (0.951 on
# inflection, at ceiling) and scores 0.000 on COGS gen -- the contrast that validated COGS as a testbed.
from core.gates import Memorize as _Memorize, Analogy as _Analogy


class Memorize:
    def __init__(self, train):
        self.b = _Memorize([(tuple(c), a) for c, a in train], key=tuple)

    def predict(self, cmd):
        a = self.b.predict(tuple(cmd))
        return (a, "commit") if a is not None else (None, "hard")


class Analogy:
    def __init__(self, train):
        self.b = _Analogy([(tuple(c), a) for c, a in train], tokenize=list)

    def predict(self, cmd):
        return (self.b.predict(tuple(cmd)) or [], "commit")


def evaluate(model, test):
    C = ok = wrong = hard = 0
    for cmd, gold in test:
        pred, st = model.predict(cmd)
        if st == "commit":
            C += 1
            if pred is not None and list(pred) == list(gold): ok += 1
            else: wrong += 1
        else: hard += 1
    n = len(test)
    return dict(n=n, C=C, ok=ok, wrong=wrong, hard=hard,
                EM=ok / n, P=(ok / C if C else 0.0), cover=C / n)

if __name__ == "__main__":
    print("STAGE 2 -- SCAN baselines (the Stage-1 knockout carried forward)\n")
    print(f"  {'split':14s} {'train':>6} {'test':>6} | {'memorize EM':>11} {'analogy EM':>10} {'analogy P':>9}")
    for s in ["simple", "addprim_jump", "length"]:
        tr, te = load(s)
        m = evaluate(Memorize(tr), te)
        a = evaluate(Analogy(tr), te)
        print(f"  {s:14s} {len(tr):6d} {len(te):6d} | {m['EM']:11.3f} {a['EM']:10.3f} {a['P']:9.3f}")
    print("\n  (memorize EM = fraction of test commands seen verbatim in train; analogy never abstains so EM=P)")
    print("  If analogy is at ceiling on addprim_jump/length, composition isn't required -> rethink the testbed.")