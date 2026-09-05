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

# ---------- baselines ----------
class Memorize:
    """Exact lookup of the training command; abstains otherwise. Floor: measures how much of test is verbatim seen."""
    def __init__(self, train): self.m = {tuple(c): a for c, a in train}
    def predict(self, cmd):
        a = self.m.get(tuple(cmd))
        return (a, "commit") if a is not None else (None, "hard")

class Analogy:
    """THE KNOCKOUT that killed Stage 1: copy the output of the most similar training command (token-overlap +
    longest common prefix/suffix). Never abstains. If this scores well on the compositional splits, composition is
    not actually required and Stage 2 is as hollow as Stage 1."""
    def __init__(self, train):
        self.train = [(c, a) for c, a in train]
        self.index = collections.defaultdict(list)
        for i, (c, a) in enumerate(self.train):
            for w in set(c): self.index[w].append(i)
    def predict(self, cmd):
        cs = set(cmd); best = None; bs = -1
        cand = collections.Counter()
        for w in cs:
            for i in self.index.get(w, ()): cand[i] += 1
        for i, _ in cand.most_common(200):
            c, a = self.train[i]
            inter = len(cs & set(c)); union = len(cs | set(c))
            jac = inter / union if union else 0
            pre = 0
            for x, y in zip(cmd, c):
                if x != y: break
                pre += 1
            s = jac * 10 + pre + (1.0 if len(c) == len(cmd) else 0)
            if s > bs: bs = s; best = a
        return (best if best is not None else [], "commit")

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