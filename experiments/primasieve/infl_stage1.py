"""STAGE 1 (fable-scoped protocol) -- English inflection few-shot, honestly measured.
Fixes over the smoke run: (a) MULTI-GOLD -- any attested form for (lemma,bundle) counts correct (travelled/traveled);
(b) INDEPENDENT regularity oracle -- a frozen textbook rule set labels regular/irregular and gives the ceiling; it is
NEVER used by the engine (the engine's own rule/exception partition would be circular); (c) LEMMA-level global split
so a lemma's PST and PTCP never straddle; (d) the DECISIVE knockout -- longest-suffix ANALOGY (nearest-neighbour edit
copy), which commits everywhere: if the engine's precision/coverage frontier is not strictly better than analogy, the
induction machinery adds nothing. Reports W split by gold regularity + penalized score (correct - 5*wrong)."""
import os, sys, random, collections
sys.path.insert(0, os.path.dirname(__file__))
from infl_engine import Inflector, transform, apply_t

D = os.path.join(os.path.dirname(__file__), "_nldata")
PATH = os.path.join(D, "unimorph_eng.tsv")
V = set("aeiou")

def load(bundles):
    g = collections.defaultdict(lambda: collections.defaultdict(set))     # bundle -> lemma -> {forms}
    for line in open(PATH, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) != 3: continue
        lem, form, f = p[0].strip().lower(), p[1].strip().lower(), p[2].strip()
        if f not in bundles: continue
        if not lem.isalpha() or not form.isalpha(): continue
        g[f][lem].add(form)
    return g

# ---------- INDEPENDENT textbook oracle: labels regular/irregular + serves as the regular ceiling ----------
def cvc(l):  # final consonant-vowel-consonant, last not w/x/y
    return len(l) >= 3 and l[-1] not in V and l[-1] not in "wxy" and l[-2] in V and l[-3] not in V
def oracle_forms(lem, bundle):
    """All spellings a textbook would accept as REGULAR (a set; doubling is stress-dependent so both are allowed)."""
    out = set()
    if bundle in ("V;PST", "V;V.PTCP;PST"):
        if lem.endswith("e"): out.add(lem + "d")
        elif len(lem) > 1 and lem.endswith("y") and lem[-2] not in V: out.add(lem[:-1] + "ied")
        else:
            out.add(lem + "ed")
            if cvc(lem): out.add(lem + lem[-1] + "ed")
            if lem.endswith("l"): out.add(lem + "led")
    elif bundle == "V;PRS;3;SG":
        if lem.endswith(("s", "x", "z", "ch", "sh", "o")): out.add(lem + "es")
        elif len(lem) > 1 and lem.endswith("y") and lem[-2] not in V: out.add(lem[:-1] + "ies")
        else: out.add(lem + "s")
    elif bundle == "V;V.PTCP;PRS":
        if lem.endswith("ie"): out.add(lem[:-2] + "ying")
        elif lem.endswith("e") and not lem.endswith(("ee", "oe", "ye")): out.add(lem[:-1] + "ing")
        else:
            out.add(lem + "ing")
            if cvc(lem): out.add(lem + lem[-1] + "ing")
            if lem.endswith("l"): out.add(lem + "ling")
    elif bundle == "N;PL":
        if lem.endswith(("s", "x", "z", "ch", "sh")): out.add(lem + "es")
        elif len(lem) > 1 and lem.endswith("y") and lem[-2] not in V: out.add(lem[:-1] + "ies")
        else:
            out.add(lem + "s")
            if lem.endswith("o"): out.add(lem + "es")
            if lem.endswith("f"): out.add(lem[:-1] + "ves")
            if lem.endswith("fe"): out.add(lem[:-2] + "ves")
    return out
def is_regular(lem, golds, bundle):
    return bool(oracle_forms(lem, bundle) & golds)

# ---------- baselines ----------
class Analogy:
    """DECISIVE knockout: copy the lemma->form edit of the training lemma sharing the longest final substring.
    No rules, no abstention -- commits on everything."""
    def __init__(self, pairs):
        self.by_suf = collections.defaultdict(list)
        self.pairs = pairs
        for lem, form in pairs:
            T = transform(lem, form)
            for k in range(1, min(8, len(lem)) + 1): self.by_suf[lem[-k:]].append(T)
        c = collections.Counter(transform(l, f) for l, f in pairs)
        self.fallback = c.most_common(1)[0][0]
    def predict(self, lem):
        for k in range(min(8, len(lem)), 0, -1):
            lst = self.by_suf.get(lem[-k:])
            if lst:
                T = collections.Counter(lst).most_common(1)[0][0]
                out = apply_t(lem, T)
                if out is not None: return out
        return apply_t(lem, self.fallback) or lem

def run(bundle, lemma_gold, ntrain, seed, shuffle=False):
    lems = sorted(lemma_gold)
    rng = random.Random(seed); rng.shuffle(lems)
    tr_l, te_l = lems[:ntrain], lems[ntrain:]
    train = [(l, sorted(lemma_gold[l])[0]) for l in tr_l]
    if shuffle:
        fs = [f for _, f in train]; rng.shuffle(fs); train = [(l, fs[i]) for i, (l, _) in enumerate(train)]
    inf = Inflector(train); ana = Analogy(train)
    c = collections.Counter(transform(l, f) for l, f in train); Tmf = c.most_common(1)[0][0]
    R = collections.Counter()
    for l in te_l:
        golds = lemma_gold[l]
        reg = is_regular(l, golds, bundle)
        R["Nreg" if reg else "Nirr"] += 1
        st, pred, _ = inf.predict(l)
        if st == "commit":
            R["C"] += 1; ok = pred in golds
            R["P"] += ok
            if reg: R["Creg"] += 1; R["Preg"] += ok; R["Wreg"] += (not ok)
            else: R["Cirr"] += 1; R["Pirr"] += ok; R["Wirr"] += (not ok)
        else:
            R["hard" if st == "hard" else "soft"] += 1
            if reg: R["ab_reg"] += 1
        # baselines on the SAME item
        R["A_ok"] += ana.predict(l) in golds
        if reg: R["A_reg_ok"] += ana.predict(l) in golds
        R["B_ok"] += (apply_t(l, Tmf) in golds if apply_t(l, Tmf) else False)
        R["O_ok"] += bool(oracle_forms(l, bundle) & golds)
    R["n"] = len(te_l); R["ntrain_exc"] = sum(1 for l, f in train if not is_regular(l, {f}, bundle))
    return R

if __name__ == "__main__":
    BUNDLES = ["V;PST", "V;PRS;3;SG", "V;V.PTCP;PRS", "N;PL"]
    SEEDS = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--seeds=")), 5))
    LADDER = [int(x) for x in next((a.split("=")[1] for a in sys.argv if a.startswith("--ladder=")), "50,200").split(",")]
    data = load(set(BUNDLES))
    print(f"STAGE 1 (fable protocol) | multi-gold, independent regularity oracle, {SEEDS} seeds\n")
    for N in LADDER:
        print(f"  === N = {N} training lemmas / bundle ===")
        print(f"  {'bundle':13s} {'C_reg':>6} {'P_reg':>6} {'Wreg':>5} | {'Wirr':>5} {'irr%':>5} {'exc%':>5} | "
              f"{'ENGINE':>7} {'ANALOGY':>7} {'mfT':>6} {'oracle':>6}")
        tot = collections.Counter()
        for b in BUNDLES:
            acc = collections.Counter()
            for s in range(SEEDS):
                for k, v in run(b, data[b], N, s).items(): acc[k] += v
            n = acc["n"]; Cr = acc["Creg"]; Nr = acc["Nreg"]
            eng_em = acc["P"] / n
            print(f"  {b:13s} {Cr/Nr if Nr else 0:6.3f} {acc['Preg']/Cr if Cr else 0:6.3f} {acc['Wreg']:5d} | "
                  f"{acc['Wirr']:5d} {acc['Nirr']/n:5.3f} {acc['ntrain_exc']/(N*SEEDS):5.3f} | "
                  f"{eng_em:7.3f} {acc['A_ok']/n:7.3f} {acc['B_ok']/n:6.3f} {acc['O_ok']/n:6.3f}")
            for k, v in acc.items(): tot[k] += v
        n = tot["n"]; Cr = tot["Creg"]; Nr = tot["Nreg"]
        pen_e = tot["P"] - 5 * (tot["Wreg"] + tot["Wirr"]); pen_a = tot["A_ok"] - 5 * (n - tot["A_ok"])
        print(f"  {'POOLED':13s} {Cr/Nr:6.3f} {tot['Preg']/Cr:6.3f} {tot['Wreg']:5d} | {tot['Wirr']:5d} "
              f"{tot['Nirr']/n:5.3f} {tot['ntrain_exc']/(N*SEEDS*len(BUNDLES)):5.3f} | "
              f"{tot['P']/n:7.3f} {tot['A_ok']/n:7.3f} {tot['B_ok']/n:6.3f} {tot['O_ok']/n:6.3f}")
        print(f"  -> engine W_reg rate on committed regulars = {tot['Wreg']/Cr:.4f} (fable WIN gate <=0.003)")
        print(f"  -> analogy W_reg rate = {(tot['Nreg']-tot['A_reg_ok'])/Nr:.4f} on ALL regulars (it never abstains)")
        print(f"  -> penalized (correct-5*wrong): engine {pen_e:+d}  analogy {pen_a:+d}")
        print(f"  -> calibration: train-exception rate {tot['ntrain_exc']/(N*SEEDS*len(BUNDLES)):.3f} vs observed irregular share {tot['Nirr']/n:.3f}\n")
    sh = collections.Counter()
    for b in BUNDLES:
        for k, v in run(b, data[b], LADDER[-1], 0, shuffle=True).items(): sh[k] += v
    print(f"  K1 shuffle-pairing: commit {sh['C']} of {sh['n']} (C={sh['C']/sh['n']:.4f}) correct {sh['P']} -- must collapse (<0.05)")