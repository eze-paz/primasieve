"""STAGE 1b -- three alternate probes of the SAME idea (does rule induction beat memorization/analogy?), after the
head-to-head EM test killed Stage 1a. Analogy wins on plain EM because English inflection is ~95% regular and
memorizable. These probes target regimes where rules SHOULD win if the idea is right:

  A. LOW-DATA ladder (N=10..200): a rule generalizes from a handful; analogy needs a near neighbour to copy.
  B. MATCHED-COVERAGE frontier: 1a compared engine@83% vs analogy@100% (unfair). Give analogy a confidence score
     (unanimity, then matched-suffix length, then count) and let it abstain to the engine's EXACT coverage; compare
     accuracy on equal terms. This is the honest selective-prediction comparison.
  C. RULE RECOVERY: does the engine induce English's actual spelling rules (e-drop, y->ies, doubling)? Analogy
     yields no rules at all -- if the engine recovers the grammar from ~50 examples that is a deliverable analogy
     cannot produce at any coverage.
Pre-registered read: if A shows no low-N crossover, B shows no matched-coverage win, and C fails to recover the
rules, Stage 1 is dead and we go to Stage 2."""
import os, sys, random, collections
sys.path.insert(0, os.path.dirname(__file__))
from infl_engine import Inflector, transform, apply_t
from infl_stage1 import load, is_regular, oracle_forms, Analogy

BUNDLES = ["V;PST", "V;PRS;3;SG", "V;V.PTCP;PRS", "N;PL"]

class AnalogyConf(Analogy):
    """Analogy + a confidence score so it can abstain to a matched coverage budget."""
    def predict_conf(self, lem):
        for k in range(min(8, len(lem)), 0, -1):
            lst = self.by_suf.get(lem[-k:])
            if lst:
                c = collections.Counter(lst); T, n = c.most_common(1)[0]
                unan = n / len(lst)
                out = apply_t(lem, T)
                if out is not None: return out, (unan, k, n)
        return apply_t(lem, self.fallback) or lem, (0.0, 0, 0)

def probe(bundle, lemma_gold, N, seed):
    lems = sorted(lemma_gold); rng = random.Random(seed); rng.shuffle(lems)
    tr_l, te_l = lems[:N], lems[N:]
    train = [(l, sorted(lemma_gold[l])[0]) for l in tr_l]
    inf = Inflector(train); ana = AnalogyConf(train)
    eng, anas = [], []
    for l in te_l:
        golds = lemma_gold[l]
        st, pred, _ = inf.predict(l)
        eng.append((st == "commit", (pred in golds) if st == "commit" else None))
        ap, conf = ana.predict_conf(l)
        anas.append((ap in golds, conf))
    C = sum(1 for c, _ in eng if c)
    eng_ok = sum(1 for c, ok in eng if c and ok)
    ana_full = sum(1 for ok, _ in anas if ok)
    # B: analogy restricted to its C most-confident items
    order = sorted(range(len(anas)), key=lambda i: anas[i][1], reverse=True)[:C]
    ana_matched = sum(1 for i in order if anas[i][0])
    return dict(n=len(te_l), C=C, eng_ok=eng_ok, ana_full=ana_full, ana_matched=ana_matched)

def rule_recovery(bundle, lemma_gold, N, seed):
    """C: did the engine induce the real English conditions? Probe with nonce lemmas per condition."""
    lems = sorted(lemma_gold); rng = random.Random(seed); rng.shuffle(lems)
    train = [(l, sorted(lemma_gold[l])[0]) for l in lems[:N]]
    inf = Inflector(train)
    # nonce words (not English) per orthographic condition
    probes = {"e-drop": ["blime", "trode", "flape"], "cons+y": ["blimy", "trody", "flapy"],
              "vowel+y": ["bloay", "treey", "flaoy"], "CVC-double": ["blim", "trod", "flap"],
              "plain": ["blimk", "trosk", "flant"], "sibilant": ["blish", "trotch", "flass"]}
    res = {}
    for cond, words in probes.items():
        hits = tot = 0
        for w in words:
            st, pred, _ = inf.predict(w)
            gold = oracle_forms(w, bundle)
            if not gold: continue
            tot += 1
            if st == "commit" and pred in gold: hits += 1
        res[cond] = (hits, tot)
    return res

if __name__ == "__main__":
    SEEDS = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--seeds=")), 3))
    data = load(set(BUNDLES))
    print("STAGE 1b -- alternate probes (A low-data, B matched-coverage, C rule recovery)\n")
    print("A + B:  engine vs analogy@full vs analogy@MATCHED coverage (exact match on held-out)")
    print(f"  {'N':>5} {'cover':>6} {'ENGINE':>7} {'ana@match':>10} {'delta':>7} | {'ana@full':>8}")
    for N in [10, 20, 50, 100, 200]:
        tot = collections.Counter()
        for b in BUNDLES:
            for s in range(SEEDS):
                for k, v in probe(b, data[b], N, s).items(): tot[k] += v
        n, C = tot["n"], tot["C"]
        eng = tot["eng_ok"] / C if C else 0
        am = tot["ana_matched"] / C if C else 0
        print(f"  {N:>5} {C/n:6.3f} {eng:7.3f} {am:10.3f} {eng-am:+7.3f} | {tot['ana_full']/n:8.3f}")
    print("\n  (engine and ana@match are accuracy ON THE SAME NUMBER OF ITEMS = the honest frontier comparison)")

    print("\nC: rule recovery -- nonce-word probes per orthographic condition (V;PST, N=50)")
    agg = collections.defaultdict(lambda: [0, 0])
    for s in range(SEEDS):
        for cond, (h, t) in rule_recovery("V;PST", data["V;PST"], 50, s).items():
            agg[cond][0] += h; agg[cond][1] += t
    for cond, (h, t) in agg.items():
        print(f"  {cond:12s} {h}/{t}  {'OK' if t and h == t else 'partial' if h else 'MISS'}")
    print("\n  (analogy induces no rules at all; this column is only producible by the rule engine)")