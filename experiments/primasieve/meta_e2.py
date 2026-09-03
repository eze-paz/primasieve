"""E2 (fable-designed): the MINIMAL-CORE / HIERARCHY test (owner point 1). Does the loop build operators
ON TOP OF discovered operators (hierarchy depth >=2 = genuine emergence), or only accumulate flat?

Probe = higher derivatives. The 2nd-derivative single-term frame is c*e*(e-1) — DEPTH-3, OUTSIDE the flat
450-relation frame grammar (max depth-2), so it CANNOT be discovered flat. But it IS diff o diff — reachable
ONLY by COMPOSING the already-discovered diff operator with itself. So explaining 2nd-derivative observations
forces the system to build on a discovered op = depth 2. 3rd/4th derivatives = depth 3/4 -> unbounded hierarchy
from composition. Observations are UNLABELED I/O (no 'this is 2nd derivative'); the loop must find the chain.

Knockouts: (K-empty) with an EMPTY library nothing composes -> depth stays 1; (K-shuffle) shuffled I/O pairs
must yield NO chain. Null: max depth stays 1 = accumulation, not emergence. ZERO LLM."""
import os, sys, random, itertools
sys.path.insert(0, os.path.dirname(__file__))
import meta_param as MP

SEEDS = [[(3, 2)], [(2, 3)], [(5, 4)], [(4, 2)], [(2, 5)]]

def discover_base():
    """Honestly re-derive the depth-1 operators diff & integ from single-term traces (not hardcoded)."""
    lib = {}
    for key, tf in (("diff", MP.differentiate), ("integ", MP.integrate)):
        tr = MP.bootstrap_traces(tf, SEEDS); rc = MP.discover_relation(tr, 0); re = MP.discover_relation(tr, 1)
        if rc and re: lib[key] = {"name": key, "chain": [(rc[2], re[2])], "depth": 1, "label": (rc[0], re[0])}
    return lib

def apply_frame(terms, fr):
    out = []
    for c, e in terms:
        ne = int(round(fr[1](c, e)))
        if ne >= 0: out.append((fr[2] if False else fr[0](c, e), ne))   # keep nonneg-degree terms
    return out
def apply_chain(terms, chain):
    for fr in chain: terms = apply_frame(terms, fr)
    return terms
def _canon(terms): return tuple(sorted((round(c, 6), e) for c, e in terms))
def reproduces(chain, obs): return all(_canon(apply_chain(inp, chain)) == _canon(out) for inp, out in obs)

def compo_search(library, obs, maxlen=4):
    """Search chains of LIBRARY ops (each may itself be composite) that reproduce all observations.
    Returns the shortest working chain of op-keys, or None."""
    keys = list(library)
    for L in range(1, maxlen + 1):
        for combo in itertools.product(keys, repeat=L):
            chain = [fr for k in combo for fr in library[k]["chain"]]
            if reproduces(chain, obs): return list(combo)
    return None

def nth_derivative(n):
    def tf(terms):
        for _ in range(n): terms = [(c * e, e - 1) for c, e in terms if e >= 1]
        return terms
    return tf

def gen_obs(n, rng, k=None):
    tf = nth_derivative(n); obs = []
    for _ in range(6):
        kk = k or rng.randint(1, 3); es = rng.sample(range(n, n + 5), kk)   # e>=n so degree stays >=0
        terms = [(rng.randint(2, 9), e) for e in es]
        obs.append((terms, tf(terms)))
    return obs

if __name__ == "__main__":
    rng = random.Random(0)
    lib = discover_base()
    print("base library (depth-1 operators, honestly discovered):")
    for k, o in lib.items(): print(f"  {k:6s} depth {o['depth']}  frame {o['label']}")

    print("\n=== HIERARCHY: explain nth-derivative observations (UNLABELED I/O) ===")
    print(f"{'target':>10s}  {'flat grammar':>22s}  {'compositional (on discovered ops)':>34s}  depth")
    maxdepth = 1
    for n in (2, 3, 4):
        obs = gen_obs(n, random.Random(100 + n))
        # FLAT: can a single depth-<=2 grammar frame explain it?
        single = [(t[0][0], t[1][0]) for t in gen_obs(n, random.Random(7), k=1)]   # single-term traces
        rc = MP.discover_relation([(a, b) for a, b in single], 0); re = MP.discover_relation([(a, b) for a, b in single], 1)
        flat_ok = False
        if rc and re:
            flat_ok = reproduces([(rc[2], re[2])], obs)                              # does it GENERALIZE?
        # COMPOSITIONAL: chain discovered library ops
        chain = compo_search(lib, obs)
        depth = (1 + max(lib[k]["depth"] for k in chain)) if chain else 0   # TRUE recursion depth
        maxdepth = max(maxdepth, depth)
        # crystallize the composite into the library so the NEXT n can build on IT (real hierarchy)
        if chain and depth >= 2:
            newop = {"name": f"d{n}", "chain": [fr for k in chain for fr in lib[k]["chain"]], "depth": depth}
            lib[f"d{n}"] = newop
        fl = f"frame {rc[0] if rc else None} " + ("GENERALIZES" if flat_ok else "does NOT generalize")
        cp = (" o ".join(chain) + f"  depth {depth}") if chain else "NONE"
        print(f"{'d^'+str(n)+'/dx':>10s}  {fl:>22s}  {cp:>34s}  {depth}")

    print("\n=== KNOCKOUTS ===")
    obs2 = gen_obs(2, random.Random(100 + 2))
    print(f"  K-empty  (no library): {compo_search({}, obs2) or 'NONE'}   (must be NONE)")
    shuf = list(obs2); ins = [o[0] for o in shuf]; random.Random(1).shuffle(ins)
    shuf = [(ins[i], shuf[i][1]) for i in range(len(shuf))]                          # mismatched I/O
    lib2 = discover_base()
    print(f"  K-shuffle (mismatched I/O): {compo_search(lib2, shuf) or 'NONE'}   (must be NONE)")

    print(f"\nMAX HIERARCHY DEPTH REACHED = {maxdepth}  "
          f"({'>=2 => genuine emergence (operators built on operators)' if maxdepth >= 2 else '1 => flat accumulation, NO emergence'})")
