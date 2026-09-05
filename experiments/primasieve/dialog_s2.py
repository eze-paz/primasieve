"""DIALOGUE SUITE S2 -- the SUBSET PROBLEM, and solving it by asking.

S1 found that elimination scales soundly (0 wrong commitments at every size) but leaves some words uncommitted.
Diagnosis: those words denote predicates that ENTAIL another predicate in this world. SZ3 (top size band) is
only reachable by a 4x4 rect, which is always SQUARE, so SZ3 is a SUBSET of SQUARE. Learning from POSITIVE
examples alone can never separate a predicate from any superset of it -- every situation that supports SZ3 also
supports SQUARE. This is the classic no-negative-evidence / subset problem in language acquisition, and the
engine's response is already the correct one: abstain with survivors {SZ3, SQUARE}, never guess.

The principled fix is not more data of the same kind -- no amount helps -- it is NEGATIVE evidence, obtained by
ASKING. The engine finds an object on which its surviving meanings DISAGREE (something SQUARE but not SZ3, e.g.
a 1x1), asks 'does this word apply here?', and a truthful NO eliminates the superset.

  S2a  characterise: are the uncommitted words exactly the entailment (subset) cases?
  S2b  resolve by asking: subset-aware probing, ACTIVE vs RANDOM object choice
  KILL: any wrong commitment after probing.
"""
import os, sys, json, random, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialog_world as DW
import dialog_s1 as S1

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))


def object_pool(world, rng, n=1200):
    """a pool of objects the engine may point at when asking a question."""
    pool = []
    while len(pool) < n:
        sc = world.rand_scene(rng, 3)
        if sc is None: continue
        pool.extend(sc)
    return pool[:n]


def entails(world, p, q, pool):
    """does p entail q over the pool? Works for unary (objects) and binary (ordered object PAIRS)."""
    isb = p in world.binary
    if isb != (q in world.binary): return False
    seen = False
    if not isb:
        for o in pool:
            if world.u(p, o):
                seen = True
                if not world.u(q, o): return False
    else:
        for i in range(0, len(pool) - 1, 2):
            a, b = pool[i], pool[i + 1]
            if world.b(p, a, b):
                seen = True
                if not world.b(q, a, b): return False
    return seen


def ask_unary(world, word, obj):
    """the world answers truthfully: does this word's TRUE predicate apply to this object?"""
    return world.u(world.w2p[word], obj)


def resolve_by_asking(world, surv, pool, mode="active", budget=8, rng=None):
    """for each uncommitted unary word, ask about objects until one meaning survives (or budget spent)."""
    committed = {}
    asked = {}
    for w, S in surv.items():
        S = set(S)
        if len(S) == 1:
            committed[w] = next(iter(S)); asked[w] = 0; continue
        isb = all(p in world.binary for p in S)
        items = pool if not isb else [(pool[i], pool[i + 1]) for i in range(0, len(pool) - 1, 2)]
        hold = (lambda p, x: world.u(p, x)) if not isb else (lambda p, x: world.b(p, x[0], x[1]))
        n = 0
        while len(S) > 1 and n < budget:
            if mode == "active":
                best, bo = -1, None
                for o in items:
                    yes = sum(1 for p in S if hold(p, o))
                    if yes == 0 or yes == len(S): continue   # does not split
                    score = min(yes, len(S) - yes)
                    if score > best: best, bo = score, o
                if bo is None: break                         # nothing can split -> genuinely co-extensive
                o = bo
            else:
                cand = [x for x in items if 0 < sum(1 for p in S if hold(p, x)) < len(S)]
                if not cand: break
                o = rng.choice(cand)
            n += 1
            a = hold(world.w2p[w], o)                        # the world answers truthfully
            S = {p for p in S if hold(p, o) == a}
        asked[w] = n
        if len(S) == 1: committed[w] = next(iter(S))
    return committed, asked


if __name__ == "__main__":
    t0 = time.time()
    print("DIALOGUE S2 -- the subset problem, and solving it by asking\n")
    CONFIGS = [(8, 4, 3), (16, 6, 4), (32, 8, 5), (64, 10, 6)]
    N_SENT = int(os.environ.get("N_SENT", "6000"))
    rows = []
    print(f"{'concepts':>9} {'after elimination':>18} {'uncommitted':>12} {'are subset cases':>17} "
          f"{'after ASKING':>13} {'questions':>10} {'WRONG':>6}")
    for cfg in CONFIGS:
        world = DW.World(*cfg, seed=11)
        V = len(world.w2p)
        rng = random.Random(7)
        data = S1.corpus(world, N_SENT, 3, rng)
        com, surv = S1.learn(world, data)
        pool = object_pool(world, random.Random(3))
        unc = [w for w in world.w2p if w in surv and w not in com]
        # S2a: is every uncommitted word an ENTAILMENT case?
        subset_cases = 0
        for w in unc:
            true_p = world.w2p[w]
            others = [p for p in surv[w] if p != true_p]
            if others and all(entails(world, true_p, p, pool) for p in others):
                subset_cases += 1
        # S2b: resolve by asking
        com2, asked = resolve_by_asking(world, surv, pool, mode="active")
        wrong = sum(1 for w, p in world.w2p.items() if w in com2 and com2[w] != p)
        exact2 = sum(1 for w, p in world.w2p.items() if com2.get(w) == p)
        nq = sum(asked.values())
        spoken = {x for u, _, _ in data for x in u}
        unspoken = V - len(spoken)
        rows.append({"concepts": V, "spoken": len(spoken), "never_spoken": unspoken,
                     "after_elimination": len(com), "uncommitted": len(unc),
                     "subset_cases": subset_cases, "after_asking": exact2, "questions": nq, "wrong": wrong})
        print(f"{V:>9} {len(com):>18} {len(unc):>12} {f'{subset_cases}/{len(unc)}':>17} "
              f"{f'{exact2}/{len(spoken)}':>13} {nq:>10} {wrong:>6}  (never spoken {unspoken})")

    # control: ACTIVE vs RANDOM object choice
    world = DW.World(32, 8, 5, seed=11)
    data = S1.corpus(world, 1500, 3, random.Random(7))
    com, surv = S1.learn(world, data)
    pool = object_pool(world, random.Random(3))
    ca, aa = resolve_by_asking(world, surv, pool, mode="active")
    cr, ar = resolve_by_asking(world, surv, pool, mode="random", rng=random.Random(5))
    ea = sum(1 for w, p in world.w2p.items() if ca.get(w) == p)
    er = sum(1 for w, p in world.w2p.items() if cr.get(w) == p)
    print(f"\n  CONTROL at {len(world.w2p)} concepts: ACTIVE {ea} words with {sum(aa.values())} questions; "
          f"RANDOM {er} words with {sum(ar.values())} questions")

    tw = sum(r["wrong"] for r in rows)
    allsub = all(r["subset_cases"] == r["uncommitted"] for r in rows)
    full = all(r["after_asking"] == r["spoken"] for r in rows)   # scored over words actually USED
    print(f"\n=== VERDICT ===")
    print(f"  every uncommitted word is an ENTAILMENT/subset case: {allsub}")
    print(f"  all SPOKEN concepts learned after asking, at every scale: {full}")
    print(f"  (words never uttered in the corpus cannot be learned -- that is data coverage, not a "
          f"learning failure; counts shown per row)")
    print(f"  WRONG commitments after probing: {tw}")
    if allsub and full and tw == 0:
        print(f"\n  The failure S1 hit was NOT ambiguity explosion and NOT data starvation -- it was the classic")
        print(f"  no-negative-evidence SUBSET problem, which no amount of positive data can fix. The engine")
        print(f"  detects it, asks for the negative evidence, and closes it soundly at every scale.")
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["dialog_s2_subset_problem"] = {
        "rows": rows, "all_uncommitted_are_subset_cases": allsub, "all_learned_after_asking": full,
        "wrong_after_probing": tw,
        "control": {"active_words": ea, "active_questions": sum(aa.values()),
                    "random_words": er, "random_questions": sum(ar.values())},
        "reading": "learning from POSITIVE examples alone cannot separate a predicate from any SUPERSET of it; "
                   "this is the classic subset / no-negative-evidence problem. The engine abstains (correct), "
                   "then obtains NEGATIVE evidence by asking about an object where its surviving meanings "
                   "disagree. Sound throughout.",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  ({time.time()-t0:.0f}s)  -> merged into {os.path.basename(OUT)}")
