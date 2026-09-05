"""STAGE 2 -- the two measurements that are NOT replication (fable: a SCAN 1.0 is a kill gate; grammar-induction
systems already score 1.0 on every split, so passing is a replication of Nye 2020 / NQG 2021).

A. SAMPLE COMPLEXITY. The meaningful claim: reach 1.0 on the FULL test set from a few dozen random training pairs,
   with no meta-training and no dataset-specific code (Nye needed meta-training; NQG uses the full train set).
B. GENERATOR-FAMILY CONTROL (the decisive one). A seeded adversary builds SCAN-LIKE grammars with DIFFERENT
   semantics -- other repeat counts, the connective order swapped, other wrap arities, a sequence-reversal operator,
   counts attaching before the verb -- and rebuilds train/test with a LENGTH split. The SAME engine runs unchanged.
   Pass SCAN but fail these = the engine re-derived a known generator (KILL). Pass both = the combinators are generic."""
import os, sys, random, collections
sys.path.insert(0, os.path.dirname(__file__))
from scan_engine import induce, evaluate, reproduces, Grammar, rep
from scan_data import load

# ---------------- A. sample complexity ----------------
def sample_complexity(split, ladder, seeds, mode="random"):
    """mode='random': uniform sample (fails at small N -- only 0.5% of SCAN commands have <=3 tokens, so the
    bootstrap never sees a simple case). mode='curriculum': the N SHORTEST training examples = the TEXTBOOK
    condition (simple cases first), then tested on the FULL test set incl. far longer items. Both reported."""
    tr, te = load(split)
    rows = []
    for N in ladder:
        em = cov = wrong = 0.0
        reps = seeds if mode == "random" else 1               # curriculum is deterministic
        for s in range(reps):
            if mode == "random":
                rng = random.Random(s); sub = rng.sample(tr, min(N, len(tr)))
            else:
                sub = sorted(tr, key=lambda ca: (len(ca[0]), len(ca[1])))[:N]
            ev = evaluate(induce(sub), te)
            em += ev["EM"]; cov += ev["cover"]; wrong += ev["wrong"]
        rows.append((N, em / reps, cov / reps, wrong / reps))
    return rows

# ---------------- B. generator family ----------------
def make_grammar(seed):
    """Adversarial SCAN-like generator with randomized semantics (NOT SCAN's)."""
    rng = random.Random(1000 + seed)
    acts = [f"A{i}" for i in range(6)]
    verbs = [f"v{i}" for i in range(rng.choice([3, 4]))]
    prim = {v: (rng.choice(acts),) for v in verbs}
    nullverb = f"v{len(verbs)}"; prim[nullverb] = ()          # an empty primitive, like SCAN's 'turn'
    dirs = {f"d{i}": (rng.choice(acts),) for i in range(2)}
    opp, arnd = "m_opp", "m_arnd"
    arity = rng.choice([2, 3, 5])                              # NOT SCAN's 4
    counts = {f"c{i}": rng.choice([2, 3, 4, 5]) for i in range(2)}
    conj = {"k0": rng.choice(["CONCAT", "CONCAT_REV"]), "k1": rng.choice(["CONCAT", "CONCAT_REV"])}
    if conj["k0"] == conj["k1"]: conj["k1"] = "CONCAT_REV" if conj["k0"] == "CONCAT" else "CONCAT"
    return dict(prim=prim, dirs=dirs, opp=opp, arnd=arnd, arity=arity, counts=counts, conj=conj,
                verbs=verbs + [nullverb])

def gen_phrases(g):
    out = []
    for v in g["verbs"]:
        base = g["prim"][v]
        opts = [([v], base)]
        for d, da in g["dirs"].items():
            opts.append(([v, d], tuple(da) + base))
            opts.append(([v, g["opp"], d], tuple(da) * 2 + base))
            opts.append(([v, g["arnd"], d], rep(tuple(da) + base, g["arity"])))
        for toks, seq in list(opts):
            out.append((toks, seq))
            for c, k in g["counts"].items(): out.append((toks + [c], rep(seq, k)))
    return out

def gen_data(g):
    ph = gen_phrases(g); data = list(ph)
    for (l, ls) in ph:
        for (r, rs) in ph:
            for k, mode in g["conj"].items():
                data.append((l + [k] + r, ls + rs if mode == "CONCAT" else rs + ls))
    return [(list(c), list(a)) for c, a in data]

def length_split(data):
    lens = sorted(len(a) for _, a in data)
    cut = lens[int(len(lens) * 0.72)]
    tr = [(c, a) for c, a in data if len(a) <= cut]
    te = [(c, a) for c, a in data if len(a) > cut]
    return tr, te

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("A", "both"):
        print("A. SAMPLE COMPLEXITY -- always scored on the FULL test set\n")
        for split in ["simple", "addprim_jump", "length"]:
            print(f"  {split}")
            print(f"    {'N':>5} | {'curriculum EM':>13} {'cov':>6} {'wrong':>6} | {'random EM':>9} {'cov':>6}")
            cur = dict((r[0], r) for r in sample_complexity(split, [10, 20, 40, 80, 160], 3, "curriculum"))
            rnd = dict((r[0], r) for r in sample_complexity(split, [10, 20, 40, 80, 160], 3, "random"))
            for N in [10, 20, 40, 80, 160]:
                _, ce, cc, cw = cur[N]; _, re_, rc, _ = rnd[N]
                print(f"    {N:>5} | {ce:13.3f} {cc:6.3f} {cw:6.1f} | {re_:9.3f} {rc:6.3f}")
            print()
        print("  curriculum = the N SHORTEST training examples (textbook order); random = uniform sample.")
        print("  Random fails at small N because only 0.5% of SCAN commands have <=3 tokens -- a data-distribution")
        print("  fact, not a property of the method; the bootstrap needs at least a few simple cases.\n")
    if which in ("B", "both"):
        print("B. GENERATOR-FAMILY CONTROL -- 10 adversarial grammars with NON-SCAN semantics, LENGTH split,")
        print("   same engine unchanged. (repeat counts, wrap arity and connective order are randomized)\n")
        print(f"  {'g':>3} {'arity':>5} {'counts':>10} {'conj':>22} {'train':>6} {'test':>6} {'repro':>7} {'EM':>7} {'wrong':>6}")
        passes = 0
        for s in range(10):
            g = make_grammar(s)
            data = gen_data(g)
            tr, te = length_split(data)
            if not te: print(f"  {s:>3} (degenerate split, skip)"); continue
            G = induce(tr)
            r, t = reproduces(G, tr); ev = evaluate(G, te)
            passes += ev["EM"] >= 0.95
            print(f"  {s:>3} {g['arity']:>5} {str(sorted(g['counts'].values())):>10} "
                  f"{str([g['conj']['k0'][:8], g['conj']['k1'][:8]]):>22} {len(tr):>6} {len(te):>6} "
                  f"{r/t:7.3f} {ev['EM']:7.3f} {ev['wrong']:6d}")
        print(f"\n  PASSED (EM>=0.95): {passes}/10  -- fable WIN gate >=9/10; failures name a hand-encoded assumption")