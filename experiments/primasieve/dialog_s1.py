"""DIALOGUE SUITE S1 -- does learning-by-elimination SURVIVE SCALE?

Phase 5 learned 10 concepts from 8 sentences. The load-bearing question before any dialogue work: what happens
at 30, 60, 120, 250 concepts? Two things could break:
  (a) ambiguity explosion -- with many predicates true of every object, no word ever reaches a UNIQUE survivor,
      so the engine abstains forever and learns nothing;
  (b) soundness loss -- it starts committing WRONG meanings. That must never happen; it is the whole claim.

An utterance mentions ONE unary predicate per object plus a relation, chosen at random from those that hold --
so the learner cannot rely on a fixed slot meaning 'colour'. Meaning is recovered purely by elimination across
situations.

MEASURED per vocabulary size: sentences needed to commit ALL words, wrong commitments (must be 0), and the
survivor-set decay curve. KILL: any wrong commitment at any scale.
"""
import os, sys, json, random, time, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialog_world as DW

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
SLOT_OBJ = {0: 0, 1: 1}                 # slot 0 describes object A, slot 1 describes object B, slot 2 = relation


def speak(world, scene, rng):
    """utterance = [unary(A), unary(B), binary(A,B)] with each predicate picked at RANDOM from those true."""
    i, j = rng.sample(range(len(scene)), 2)
    A, B = scene[i], scene[j]
    ua = world.true_unary(A); ub = world.true_unary(B); rb = world.true_binary(A, B)
    if not (ua and ub and rb): return None, None
    return ([world.p2w[rng.choice(ua)], world.p2w[rng.choice(ub)], world.p2w[rng.choice(rb)]], (i, j))


def learn(world, obs):
    """survivors(w) = predicates true in EVERY situation w was used; commit on a unique survivor."""
    uni, bino = {}, {}
    for utt, sc, (i, j) in obs:
        A, B = sc[i], sc[j]
        uni.setdefault(utt[0], []).append(A)
        uni.setdefault(utt[1], []).append(B)
        bino.setdefault(utt[2], []).append((A, B))
    surv = {}
    for w, objs in uni.items():
        surv[w] = {p for p in world.unary if all(world.u(p, o) for o in objs)}
    for w, prs in bino.items():
        surv[w] = {p for p in world.binary if all(world.b(p, a, b) for a, b in prs)}
    committed = {w: next(iter(s)) for w, s in surv.items() if len(s) == 1}
    return committed, surv


def corpus(world, n, n_obj, rng):
    out = []
    guard = 0
    while len(out) < n and guard < n * 100:
        guard += 1
        sc = world.rand_scene(rng, n_obj)
        if sc is None: continue
        u, asg = speak(world, sc, rng)
        if u is None: continue
        out.append((u, sc, asg))
    return out


if __name__ == "__main__":
    t0 = time.time()
    CONFIGS = [(3, 2, 2), (8, 4, 3), (16, 6, 4), (32, 8, 5), (64, 10, 6)]
    N_OBJ = 3
    print("DIALOGUE S1 -- does elimination survive scale?\n")
    print(f"{'concepts':>9} {'unary':>6} {'binary':>7} {'sentences to learn ALL':>23} {'WRONG':>6} "
          f"{'mean surv @N/4':>15}")
    rows = []
    for (nc, nsz, nz) in CONFIGS:
        world = DW.World(n_colour=nc, n_size=nsz, n_zone=nz, seed=11)
        V = len(world.w2p)
        rng = random.Random(7)
        data = corpus(world, 4000, N_OBJ, rng)
        # incremental: how many sentences before every word is committed CORRECTLY?
        need = None; wrong_total = 0; mid_surv = None
        for N in list(range(10, 401, 10)) + list(range(450, 4001, 50)):
            if N > len(data): break
            com, surv = learn(world, data[:N])
            wrong = sum(1 for w, p in world.w2p.items() if w in com and com[w] != p)
            wrong_total = max(wrong_total, wrong)
            seen = {w for u, _, _ in data[:N] for w in u}
            if mid_surv is None and len(seen) >= V:
                mid_surv = statistics.mean([len(s) for s in surv.values()])
            exact = sum(1 for w, p in world.w2p.items() if com.get(w) == p)
            if exact == V and need is None:
                need = N; break
        rows.append({"concepts": V, "unary": len(world.unary), "binary": len(world.binary),
                     "sentences": need, "wrong": wrong_total,
                     "mean_survivors_at_full_coverage": round(mid_surv, 2) if mid_surv else None})
        print(f"{V:>9} {len(world.unary):>6} {len(world.binary):>7} {str(need):>23} {wrong_total:>6} "
              f"{(round(mid_surv,2) if mid_surv else 0):>15}")

    tw = sum(r["wrong"] for r in rows)
    got = [r for r in rows if r["sentences"]]
    print(f"\n  learned ALL concepts at every scale tested: {len(got)}/{len(rows)}")
    if len(got) >= 2:
        a, b = got[0], got[-1]
        print(f"  scaling: {a['concepts']} concepts <- {a['sentences']} sentences ; "
              f"{b['concepts']} concepts <- {b['sentences']} sentences "
              f"({b['concepts']/a['concepts']:.1f}x concepts for {b['sentences']/a['sentences']:.1f}x data)")
    print(f"  WRONG commitments across all scales: {tw}")
    print(f"\n=== VERDICT ===")
    if tw == 0 and len(got) == len(rows):
        print(f"  ELIMINATION SCALES: every concept learned at every size, zero wrong commitments.")
        print(f"  Data grows far slower than vocabulary -- each sentence constrains MANY words at once, so")
        print(f"  the method gets relatively CHEAPER as the world grows.")
    elif tw:
        print(f"  UNSOUND at scale: {tw} wrong commitments -- report, do not tune.")
    else:
        print(f"  PARTIAL: {len(got)}/{len(rows)} scales fully learned; ambiguity blocks the rest.")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["dialog_s1_scaling"] = {"rows": rows, "wrong_total": tw, "n_obj": N_OBJ,
                              "verdict": "SCALES" if (tw == 0 and len(got) == len(rows)) else "partial/unsound"}
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
