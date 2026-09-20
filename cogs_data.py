"""STAGE 3 -- COGS loader, scorers and the mandatory baselines (carried from Stages 1-2, where nearest-neighbour
analogy killed Stage 1 and had to be beaten in Stage 2).

Two scorers, because COGS variable indices are 0-BASED TOKEN POSITIONS ("A rose was helped by a dog" -> rose(x_1),
help(x_3), dog(x_6)). Exact match therefore partly measures index bookkeeping rather than semantics, so we report:
  EM        exact string match on the normalised logical form (the standard COGS metric), and
  EM_alpha  alpha-equivalent match -- variables canonically renamed by order of first appearance, so a prediction
            with the right predicate-argument structure but shifted indices still counts.
A high EM with a much higher EM_alpha means the engine has the semantics and is losing on bookkeeping; the reverse
would mean it is exploiting the positional regularity without the structure. Report both, always."""
import os, sys, re, collections

D = os.path.join(os.path.dirname(__file__), "_nldata", "cogs")

def read(fn):
    rows = []
    for line in open(os.path.join(D, fn), encoding="utf-8"):
        line = line.rstrip("\n")
        if not line.strip(): continue
        p = line.split("\t")
        if len(p) < 2: continue
        rows.append((p[0].strip(), p[1].strip(), (p[2].strip() if len(p) > 2 else "")))
    return rows

def load():
    return read("train.tsv"), read("dev.tsv"), read("test.tsv"), read("gen.tsv")

# ---------- normalisation + scoring ----------
def norm_lf(lf):
    return " ".join(lf.split())

VAR = re.compile(r"x _ (\d+)")
def alpha_canon(lf):
    """Canonically rename variables by order of first appearance -> alpha-equivalence."""
    lf = norm_lf(lf); mapping = {}; out = []
    for m in VAR.finditer(lf):
        v = m.group(1)
        if v not in mapping: mapping[v] = str(len(mapping))
    def sub(m): return "x _ " + mapping[m.group(1)]
    return VAR.sub(sub, lf)

def em(pred, gold): return pred is not None and norm_lf(pred) == norm_lf(gold)
def em_alpha(pred, gold): return pred is not None and alpha_canon(pred) == alpha_canon(gold)

def evaluate(model, rows, by_category=True):
    agg = collections.Counter(); per = collections.defaultdict(collections.Counter)
    for s, gold, cat in rows:
        pred, st = model.predict(s)
        agg["n"] += 1; per[cat]["n"] += 1
        if st == "commit":
            agg["C"] += 1; per[cat]["C"] += 1
            a = em(pred, gold); b = em_alpha(pred, gold)
            agg["em"] += a; agg["ema"] += b; agg["wrong"] += (not a)
            per[cat]["em"] += a; per[cat]["ema"] += b
        else:
            agg["abstain"] += 1; per[cat]["abstain"] += 1
    return agg, (per if by_category else None)

# ---------- baselines: now core.gates, shared with SCAN and every future testbed ----------
from core.gates import Memorize as _Memorize, Analogy as _Analogy


class Memorize:
    def __init__(self, train):
        self.b = _Memorize([(s, lf) for s, lf, _ in train])

    def predict(self, s):
        v = self.b.predict(s)
        return (v, "commit") if v is not None else (None, "hard")


class Analogy:
    """The Stage-1 killer, ported. On COGS it scores 0.000 EM on all 21000 gen items at coverage 1.000 --
    copying an answer is structurally impossible here, which is exactly why COGS was the right testbed."""

    def __init__(self, train, cap=300):
        self.b = _Analogy([(s, lf) for s, lf, _ in train], cap=cap)

    def predict(self, s):
        return (self.b.predict(s), "commit")


if __name__ == "__main__":
    tr, dev, test, gen = load()
    print(f"COGS: train {len(tr)}  dev {len(dev)}  test {len(test)}  gen {len(gen)}\n")
    STRUCTURAL = {"pp_recursion", "cp_recursion", "obj_pp_to_subj_pp"}
    for name, model in [("memorize", Memorize(tr)), ("analogy", Analogy(tr))]:
        agg, per = evaluate(model, gen)
        n = agg["n"]
        print(f"  {name:9s} gen: EM {agg['em']/n:.3f}  EM_alpha {agg['ema']/n:.3f}  coverage {agg['C']/n:.3f}")
        rows = sorted(per.items(), key=lambda kv: -kv[1]["n"])
        struct = [(c, v) for c, v in rows if c in STRUCTURAL]
        print(f"    structural categories: " + "  ".join(f"{c}={v['em']/v['n']:.3f}" for c, v in struct))
    print("\n  (EM = standard COGS metric; EM_alpha = alpha-equivalent, ignores variable-index bookkeeping)")