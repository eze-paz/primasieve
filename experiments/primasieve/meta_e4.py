"""E4 (fable-designed): BIDIRECTIONALITY / oracle-free spec inference with RESIDUAL attribution. The
INVERSE direction: given an artifact (no tests, no original, no spec), INFER a generating spec and let
the RESIDUAL (what the spec fails to explain) do triple duty: interpretation, oracle-free bug detection
+ localization, and (E5) new-primitive trigger. ZERO LLM, ZERO external oracle.

fable's honest frame: consistency is MDL relative to a description language = our frame library. An artifact
= a polynomial whose terms should follow ONE generating rule coeff=g(exp). Coherent <=> a rule explains ALL
terms (empty residual); bug <=> minimal residual is small+local (the violating term = the bug, localized with
NO reference to any correct answer); unexplainable <=> no rule fits (large residual -> ABSTAIN). Two traps
MEASURED not hidden: COHERENT BUGS (a mutation that still fits some other rule = undetectable by construction)
and SPECIAL cases (legit guard terms -> false positives = 'regularity prior wearing a bug-detector costume').

Knockouts: K2 shuffled library (random rules -> detection must fall to baseline = signal comes from the belief
web, not textual anomaly); baselines random/rarest-coeff (must beat). NULL: held-out ~ shuffled/rarest, or
FP on SPECIAL ~ recall on BUGGY (regularity prior, not bug detector)."""
import os, sys, random, statistics
sys.path.insert(0, os.path.dirname(__file__))

def grammar():
    """The belief web = candidate generating rules coeff = g(exp). ~dozens of low-complexity rules."""
    G = [("e", lambda e: e)]
    for k in (1, 2, 3): G += [(f"e+{k}", lambda e, k=k: e + k), (f"e-{k}", lambda e, k=k: e - k),
                              (f"{k}*e", lambda e, k=k: k * e), (f"{k}", lambda e, k=k: k)]
    G += [("e*e", lambda e: e * e), ("e*(e-1)", lambda e: e * (e - 1)), ("e*(e+1)", lambda e: e * (e + 1))]
    for a in (2, 3):
        for b in (-2, -1, 1, 2): G.append((f"{a}*e+{b}", lambda e, a=a, b=b: a * e + b))
    return G
GAP_RULES = [("e**3", lambda e: e ** 3), ("e**3-e", lambda e: e ** 3 - e), ("e*e*e+e", lambda e: e**3 + e)]

def infer_spec(terms, G):
    """MDL: pick rule g minimizing (residual size, description length). Residual = terms g fails to predict."""
    best = None
    for lab, fn in G:
        res = [i for i, (c, e) in enumerate(terms) if abs(fn(e) - c) > 1e-6]
        key = (len(res), len(lab))
        if best is None or key < best[0]: best = (key, lab, res)
    return best[1], best[2]

def verdict(terms, G):
    lab, res = infer_spec(terms, G)
    if len(res) == 0: return "coherent", None, lab
    if len(res) == 1: return "bug", res[0], lab           # residual localizes the bug, oracle-free
    return "abstain", None, lab

def gen(cls, rng, G):
    d = rng.randint(5, 6); exps = rng.sample(range(1, 9), d)
    lab, fn = rng.choice(GAP_RULES if cls == "gap" else G)
    terms = [(fn(e), e) for e in exps]; inj = None
    if cls == "buggy":
        i = rng.randrange(d); c, e = terms[i]; terms[i] = (c + rng.choice([-2, -1, 1, 2, 3]), e); inj = i
    if cls == "special":
        terms.append((rng.randint(2, 9), 0))              # a legit guard term off the main rule (confound)
    return terms, inj

def rarest(terms):                                        # baseline: flag the coeff furthest from the mean
    m = statistics.mean(c for c, e in terms)
    return max(range(len(terms)), key=lambda i: abs(terms[i][0] - m))

if __name__ == "__main__":
    G = grammar(); rng = random.Random(1); N = 60
    print(f"belief web = {len(G)} generating rules; {N}/class; ZERO external oracle\n")
    print(f"{'class':8s} {'coherent':>9s} {'bug':>6s} {'abstain':>8s}   note")
    stats = {}
    data = {c: [gen(c, rng, G) for _ in range(N)] for c in ("clean", "buggy", "special", "gap")}
    for cls in ("clean", "buggy", "special", "gap"):
        vs = [verdict(t, G) for t, _ in data[cls]]
        coh = sum(v[0] == "coherent" for v in vs); bug = sum(v[0] == "bug" for v in vs); ab = sum(v[0] == "abstain" for v in vs)
        stats[cls] = vs
        note = {"clean": "want coherent", "buggy": "want bug", "special": "FP if flagged bug", "gap": "want abstain"}[cls]
        print(f"{cls:8s} {coh:>9d} {bug:>6d} {ab:>8d}   {note}")

    # localization + coherent-bug miss (buggy)
    loc = sum(1 for (v, (t, inj)) in zip(stats["buggy"], data["buggy"]) if v[0] == "bug" and v[1] == inj)
    detb = sum(v[0] == "bug" for v in stats["buggy"])
    cohbug = sum(v[0] == "coherent" for v in stats["buggy"])       # mutation still fits some rule = coherent bug
    rnd = sum(1 for (t, inj) in data["buggy"] if inj == random.Random(9).randrange(len(t)))
    rare = sum(1 for (t, inj) in data["buggy"] if inj == rarest(t))
    fp_clean = sum(v[0] == "bug" for v in stats["clean"]); fp_spec = sum(v[0] == "bug" for v in stats["special"])
    print(f"\n  BUG DETECTION recall {detb}/{N}   LOCALIZATION top-1 {loc}/{detb} "
          f"(baselines: random {rnd*100//N}%, rarest-coeff {rare}/{N})")
    print(f"  COHERENT-BUG miss (undetectable by construction, MEASURED): {cohbug}/{N}")
    print(f"  FALSE POSITIVES: clean {fp_clean}/{N}, SPECIAL {fp_spec}/{N} (guard confound)")
    print(f"  ABSTAIN on GAP (needs held-out primitive): {sum(v[0]=='abstain' for v in stats['gap'])}/{N}")
    # residual SHAPE (E5 bridge): BUGGY = small/local (~1), GAP = large/diffuse -> distinguishable
    for cls in ("clean", "buggy", "gap"):
        sizes = [len(infer_spec(t, G)[1]) for t, _ in data[cls]]
        print(f"    residual size {cls:6s}: mean {statistics.mean(sizes):.2f}  (E5: recurring GAP residuals -> new primitive)")

    # K2 knockout: shuffle the belief web -> random rules; detection must collapse to ~baseline
    Gs = [(f"r{i}", (lambda e, v=random.Random(i).uniform(-5, 25): v)) for i in range(len(G))]
    kb = sum(verdict(t, Gs)[0] == "bug" for t, _ in data["buggy"])
    kc = sum(verdict(t, Gs)[0] == "coherent" for t, _ in data["clean"])
    print(f"\n  K2 shuffled belief web: bug-detection {kb}/{N} (must COLLAPSE vs {detb}), clean-coherent {kc}/{N}")
