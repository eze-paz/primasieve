"""STAGE 1 -- ENGLISH INFLECTION from few examples (zero-LLM, pure stdlib). Ports the proven grammar-induction
mechanism to English morphology on public UniMorph English (lemma<TAB>form<TAB>features). Few-shot: a small seeded
training sample per feature bundle; predict inflected forms for thousands of HELD-OUT lemmas; exact match.

MECHANISM (all induced, no hand-coded spelling rules): each training pair yields a transformation T=(suffix removed,
suffix added) via longest-common-prefix (walk->walked: +ed; bake->baked: +d; try->tried: y->ied; stop->stopped:
+ped; go->went: whole-word). A RULE = a lemma-ending CONTEXT that is UNANIMOUS about T in training. Prediction uses
the LONGEST unanimous context matching the test lemma with >=MINATT attestations (sound: the rule never saw a
counterexample). Conflicting contexts (hop->hopped vs develop->developed both end -op) -> back off to a longer
unanimous context or ABSTAIN. Irregulars are memorized as full-lemma contexts; a NOVEL irregular that matches a regular
context is the inherent, honestly-reported failure (W split by regular/irregular gold). Metrics P/C/W + abstain."""
import os, sys, random, collections

D = os.path.join(os.path.dirname(__file__), "_nldata")
PATH = os.path.join(D, "unimorph_eng.tsv")
MINATT = 2

def load(bundles):
    rows = collections.defaultdict(dict)                  # bundle -> lemma -> form (first seen)
    for line in open(PATH, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) != 3: continue
        lemma, form, feats = p[0].strip().lower(), p[1].strip().lower(), p[2].strip()
        if feats not in bundles or not lemma or not form or " " in lemma or " " in form: continue
        rows[feats].setdefault(lemma, form)
    return rows

def transform(lemma, form):
    n = 0
    for a, b in zip(lemma, form):
        if a != b: break
        n += 1
    return (lemma[n:], form[n:])                         # (removed, added)

def apply_t(lemma, T):
    rem, add = T
    if rem and not lemma.endswith(rem): return None
    return (lemma[:len(lemma) - len(rem)] if rem else lemma) + add

class Inflector:
    """Per-bundle rule set = suffix-context -> Counter(T). Sound prediction via longest unanimous context."""
    def __init__(self, pairs, maxctx=6):
        self.ctx = collections.defaultdict(collections.Counter)   # (k, suffix) -> Counter(T)
        self.full = {}
        self.maxctx = maxctx
        for lemma, form in pairs:
            T = transform(lemma, form)
            self.full[lemma] = T
            for k in range(1, min(self.maxctx, len(lemma)) + 1):
                self.ctx[(k, lemma[-k:])][T] += 1
        self.tcount = collections.Counter(T for T in self.full.values())

    def predict(self, lemma):
        """('commit', form, why) | ('soft', None, why) | ('hard', None, why)."""
        if lemma in self.full:                                       # memorized (incl. irregular) exception
            return ("commit", apply_t(lemma, self.full[lemma]), "memorized")
        for k in range(min(self.maxctx, len(lemma)), 0, -1):         # longest context first
            c = self.ctx.get((k, lemma[-k:]))
            if not c: continue
            if len(c) == 1:
                T, n = next(iter(c.items()))
                if n >= MINATT:
                    out = apply_t(lemma, T)
                    if out is not None: return ("commit", out, f"ctx=-{lemma[-k:]} n={n}")
                continue                                             # too few attestations -> try shorter
            # conflicting Ts at this context: only accept if longer contexts already failed AND this is decisive?
            # (no) -> keep backing off; if we reach k=1 still conflicting -> soft abstain
            if k == 1: return ("soft", None, f"conflict at -{lemma[-1:]}")
        return ("hard", None, "no context")

def regular_ts(train_pairs, top=3):
    """The productive transformations for a bundle = top-k T's by lemma count (used only to SPLIT the report)."""
    c = collections.Counter(transform(l, f) for l, f in train_pairs)
    return {T for T, _ in c.most_common(top)}

def evaluate(inf, test_pairs, regs):
    P = C = W = hard = soft = 0; Wreg = Wirr = 0; Nreg = Nirr = 0; Preg = Pirr = 0
    for lemma, form in test_pairs:
        isreg = transform(lemma, form) in regs
        if isreg: Nreg += 1
        else: Nirr += 1
        st, pred, why = inf.predict(lemma)
        if st == "commit":
            C += 1
            if pred == form:
                P += 1; (Preg if False else None)
                if isreg: Preg += 1
                else: Pirr += 1
            else:
                W += 1
                if isreg: Wreg += 1
                else: Wirr += 1
        else:
            hard += st == "hard"; soft += st == "soft"
    return dict(n=len(test_pairs), C=C, P=P, W=W, hard=hard, soft=soft,
                Nreg=Nreg, Nirr=Nirr, Wreg=Wreg, Wirr=Wirr, Preg=Preg, Pirr=Pirr)

def baselines(train_pairs, test_pairs):
    """B1 copy lemma; B2 most-frequent T for the bundle (applied to all)."""
    c = collections.Counter(transform(l, f) for l, f in train_pairs)
    Tmf = c.most_common(1)[0][0]
    b1 = sum(1 for l, f in test_pairs if l == f)
    b2 = sum(1 for l, f in test_pairs if apply_t(l, Tmf) == f)
    return b1, b2, Tmf

def run_bundle(bundle, lemma_forms, ntrain, seed, shuffle=False):
    items = sorted(lemma_forms.items())
    rng = random.Random(seed); rng.shuffle(items)
    train = items[:ntrain]; test = items[ntrain:]
    if shuffle:                                                        # K1: destroy lemma<->form pairing
        forms = [f for _, f in train]; rng.shuffle(forms)
        train = [(l, forms[i]) for i, (l, _) in enumerate(train)]
    inf = Inflector(train)
    regs = regular_ts(train)
    ev = evaluate(inf, test, regs)
    b1, b2, Tmf = baselines(train, test)
    return train, test, inf, regs, ev, b1, b2, Tmf

if __name__ == "__main__":
    BUNDLES = ["V;PST", "V;PRS;3;SG", "V;V.PTCP;PRS", "N;PL", "ADJ;CMPR"]
    NTRAIN = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--ntrain=")), 200))
    SEEDS = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--seeds=")), 3))
    data = load(set(BUNDLES))
    print(f"STAGE 1 -- English inflection, few-shot (ntrain={NTRAIN} lemmas/bundle, {SEEDS} seeds), MINATT={MINATT}\n")
    print(f"  {'bundle':14s} {'held-out':>8} {'commit':>6} {'P':>5} {'C':>5} {'W':>4} {'Wreg':>4} {'Wirr':>4} {'hard':>5} {'soft':>5} | {'B1copy':>6} {'B2mostfreqT':>11}")
    pooled = collections.Counter()
    for b in BUNDLES:
        lf = data[b]
        if len(lf) < NTRAIN + 50: print(f"  {b:14s} (only {len(lf)} lemmas, skip)"); continue
        acc = collections.Counter(); B1 = B2 = 0
        for s in range(SEEDS):
            _, test, inf, regs, ev, b1, b2, Tmf = run_bundle(b, lf, NTRAIN, s)
            for k, v in ev.items(): acc[k] += v
            B1 += b1; B2 += b2
        n = acc["n"]; C = acc["C"]; P = acc["P"]
        print(f"  {b:14s} {n:8d} {C:6d} {P/C if C else 0:5.3f} {C/n:5.3f} {acc['W']:4d} {acc['Wreg']:4d} {acc['Wirr']:4d} "
              f"{acc['hard']:5d} {acc['soft']:5d} | {B1/n:6.3f} {B2/n:11.3f}")
        for k, v in acc.items(): pooled[k] += v
        pooled["B1"] += B1; pooled["B2"] += B2
    n = pooled["n"]; C = pooled["C"]; P = pooled["P"]
    print(f"\n  POOLED: held-out {n}  commit {C} (C={C/n:.3f})  correct {P} (P={P/C if C else 0:.3f})  wrong {pooled['W']} "
          f"(on regular gold {pooled['Wreg']}, on irregular gold {pooled['Wirr']})  abstain hard {pooled['hard']} soft {pooled['soft']}")
    print(f"  baselines EM: copy-lemma {pooled['B1']/n:.3f} | most-frequent-T {pooled['B2']/n:.3f} | engine EM (correct/total) {P/n:.3f}")
    # K1 shuffle control (pooled, seed 0)
    sh = collections.Counter()
    for b in BUNDLES:
        lf = data[b]
        if len(lf) < NTRAIN + 50: continue
        _, test, inf, regs, ev, *_ = run_bundle(b, lf, NTRAIN, 0, shuffle=True)
        for k in ("n", "C", "P", "W"): sh[k] += ev[k]
    print(f"  K1 shuffle-pairing: commit {sh['C']} correct {sh['P']} wrong {sh['W']} of {sh['n']} (must collapse)")