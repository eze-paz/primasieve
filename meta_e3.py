"""E3 (the missing verb): PROPOSE — autonomous, LABEL-FREE curriculum. Given only base operators and a
world of UNEXPLAINED observation-sets (hidden transforms, no labels, no ordering), the loop PROPOSES its
own hypotheses (compositions of its current library), tests them against the world (world-as-oracle:
a hypothesis is REJECTED unless it reproduces an observation-set), and CRYSTALLIZES the ones that explain
something -- which advances the frontier so previously-unexplainable phenomena become reachable next round.

This closes GENERATE-REJECT-COMPRESS-COMPOSE with PROPOSE: no external task labels, no curriculum order --
the curriculum EMERGES from the frontier signal (propose minimal-new-depth compositions first; defer the
rest until the library grows). Discriminator vs brute force: frontier+crystallize yields REUSABLE HIERARCHY
(operators on operators) at low cost; blind deep search reaches the same answers with NO hierarchy and
exponential cost. Knockouts: K-brute (no crystallize/reuse), K-shuffle (mismatched I/O -> explains nothing).
ZERO LLM."""
import os, sys, random, itertools
sys.path.insert(0, os.path.dirname(__file__))
import meta_e2 as E2

def make_world(levels, seed=100):
    """Unexplained phenomena = observation-sets from hidden nth-derivative transforms (labels hidden)."""
    w = [(n, E2.gen_obs(n, random.Random(seed + n))) for n in levels]
    random.Random(7).shuffle(w)                       # no ordering given to the learner
    return w

def autonomous(levels):
    """PROPOSE loop: each round, propose FRONTIER candidates = length-2 chains over the CURRENT library
    (whose ops may themselves be composites), keep any that explain an unexplained phenomenon."""
    L = E2.discover_base()                            # base depth-1 ops (diff, integ), honestly discovered
    world = make_world(levels); explained = {}; rounds = 0; cost = 0
    while True:
        rounds += 1; progress = False
        cands = [(a, b) for a in list(L) for b in list(L)]     # PROPOSE: self-generated compositions
        for oi, (n, obs) in enumerate(world):
            if oi in explained: continue
            for (a, b) in cands:
                chain = L[a]["chain"] + L[b]["chain"]; cost += 1
                if E2.reproduces(chain, obs):
                    depth = 1 + max(L[a]["depth"], L[b]["depth"])
                    name = f"L{n}"; L[name] = {"chain": chain, "depth": depth}
                    explained[oi] = (n, f"{a} o {b}", depth); progress = True; break
        if not progress: break
    return L, explained, rounds, cost, world

def brute(levels, maxlen=6):
    """KNOCKOUT: no crystallization/reuse -- explain each phenomenon with a chain of BASE ops only."""
    base = E2.discover_base(); world = make_world(levels); explained = {}; cost = 0
    keys = list(base)
    for oi, (n, obs) in enumerate(world):
        for Ln in range(1, maxlen + 1):
            done = False
            for combo in itertools.product(keys, repeat=Ln):
                chain = [fr for k in combo for fr in base[k]["chain"]]; cost += 1
                if E2.reproduces(chain, obs):
                    explained[oi] = (n, " o ".join(combo), 2 if Ln >= 2 else 1); done = True; break
            if done: break
    maxd = max((d for _, _, d in explained.values()), default=1)
    return explained, cost, maxd

if __name__ == "__main__":
    LV = [2, 3, 4, 5]
    print("=== PROPOSE: autonomous, label-free curriculum (world = unlabeled nth-deriv observations) ===")
    L, expl, rounds, cost, world = autonomous(LV)
    print(f"base library: diff, integ (depth 1). World has {len(world)} unlabeled phenomena (n in {LV}, shuffled).\n")
    for oi in sorted(expl, key=lambda i: expl[i][0]):
        n, how, d = expl[oi]; print(f"  explained hidden d^{n}  as  {how:12s}  (crystallized, depth {d})")
    maxd = max((o["depth"] for o in L.values()), default=1)
    print(f"\n  rounds {rounds}, hypotheses tested {cost}, phenomena explained {len(expl)}/{len(world)}, "
          f"MAX HIERARCHY DEPTH {maxd}")

    print("\n=== KNOCKOUTS ===")
    be, bc, bd = brute(LV)
    print(f"  K-brute (no crystallize/reuse): explained {len(be)}/{len(world)}, hypotheses tested {bc}, "
          f"max reusable depth {bd}  (reaches answers, NO hierarchy, higher cost)")
    # K-shuffle: pair each input with a RANDOM other phenomenon's output -> mismatched I/O, no explanation
    Ls = E2.discover_base(); ws = make_world(LV)
    pairs = [(inp, out) for _, obs in ws for (inp, out) in obs]
    ins = [p[0] for p in pairs]; outs = [p[1] for p in pairs]; random.Random(3).shuffle(outs)
    shuf_obs = list(zip(ins, outs))                   # one mismatched pool
    ex = sum(1 for a in Ls for b in Ls if E2.reproduces(Ls[a]["chain"] + Ls[b]["chain"], shuf_obs))
    print(f"  K-shuffle (mismatched I/O): {ex} chains explain it  (must be 0)")

    print(f"\nAUTONOMOUS: label-free loop climbed to depth {maxd} by PROPOSING+crystallizing on its own, "
          f"vs brute depth {bd} at {bc}x vs {cost} hypotheses.")
