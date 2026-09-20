"""PHASE 5(b) -- REFERENTIAL UNCERTAINTY: learning meaning WITHOUT knowing what a word refers to.

Phase 5 recorded its own limit: 2 objects, so reference was handed over by the schema. That is the easy case.
The NL/SVAMP arc died on exactly the hard case -- REFERENCE/PRAGMATICS -- so this is the frontier worth taking.

Scenes now hold 3+ objects. The describer picks TWO of them and speaks; the learner is NOT told which two.
So every observation is ambiguous: a word might describe any object. This is the classic referential-uncertainty
problem in word learning, and the engine must solve it WITHOUT probabilities.

SOUND FORMULATION (arc consistency; never removes a true meaning):
  a meaning m survives for word w iff, for EVERY observation, there EXISTS an assignment of scene objects to
  the utterance's two referent slots under which ALL five words can hold with meanings still in their survivor
  sets. Iterate to a fixpoint. The true lexicon is always viable under the true assignment, so the true meaning
  is NEVER eliminated -- soundness is a theorem, not a measurement.

TESTS
  T1 lexicon under referential uncertainty (vs Phase 5 where reference was given)
  T2 data cost: how many more utterances than the 8 Phase 5 needed
  T3 REFERENCE RESOLUTION: which object is meant? return the SET; commit only if unique; a wrong commitment
     is a CONFABULATION and must be 0
  T4 scaling: 3 / 4 / 5 objects -- ambiguity should rise and coverage fall, with confabulation staying 0
KILL: any wrong lexicon commitment, or any wrong referent commitment.
"""
import os, sys, json, random, time, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world_english as W

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
G = 8


def rand_scene_n(rng, n, tries=600):
    """n pairwise NON-OVERLAPPING rects with colours; colours may REPEAT (that is what creates ambiguity)."""
    for _ in range(tries):
        objs = []
        ok = True
        for _ in range(n):
            placed = False
            for _ in range(120):
                x0 = rng.randrange(0, G - 1); x1 = rng.randrange(x0 + 1, min(G, x0 + 3) + 1)
                y0 = rng.randrange(0, G - 1); y1 = rng.randrange(y0 + 1, min(G, y0 + 3) + 1)
                r = (x0, y0, x1, y1)
                if all(not (r[2] > o[0][0] and o[0][2] > r[0] and r[3] > o[0][1] and o[0][3] > r[1])
                       for o in objs):
                    objs.append((r, rng.choice((1, 2, 3)))); placed = True; break
            if not placed: ok = False; break
        if ok and len(objs) == n: return objs
    return None


def speak(lex, scene, rng):
    """pick TWO objects and describe them. The learner never learns WHICH two."""
    idxs = list(range(len(scene)))
    rng.shuffle(idxs)
    for i, j in itertools.permutations(idxs, 2):
        a, b = scene[i], scene[j]
        rel = next((p for p in W.BINARY if W.binary_holds(p, a, b)), None)
        if rel is None: continue
        ca = next(p for p in ("C1", "C2", "C3") if W.unary_holds(p, a))
        sa = next(p for p in ("SQUARE", "WIDE", "TALL") if W.unary_holds(p, a))
        cb = next(p for p in ("C1", "C2", "C3") if W.unary_holds(p, b))
        sb = next(p for p in ("SQUARE", "WIDE", "TALL") if W.unary_holds(p, b))
        return [lex.p2w[ca], lex.p2w[sa], lex.p2w[rel], lex.p2w[cb], lex.p2w[sb]], (i, j)
    return None, None


def viable_assignments(utt, scene, surv):
    """assignments (i,j) under which EVERY word can hold with some meaning still in its survivor set."""
    out = []
    for i, j in itertools.permutations(range(len(scene)), 2):
        a, b = scene[i], scene[j]
        ok = (any(W.unary_holds(m, a) for m in surv[utt[0]])
              and any(W.unary_holds(m, a) for m in surv[utt[1]])
              and any(W.binary_holds(m, a, b) for m in surv[utt[2]])
              and any(W.unary_holds(m, b) for m in surv[utt[3]])
              and any(W.unary_holds(m, b) for m in surv[utt[4]]))
        if ok: out.append((i, j))
    return out


def learn_ru(obs, max_iter=12):
    """arc consistency to a fixpoint. obs = [(utterance, scene)]. Returns (committed, survivors)."""
    words = {w for u, _ in obs for w in u}
    surv = {}
    for u, _ in obs:
        for slot, w in enumerate(u):
            surv.setdefault(w, set(W.BINARY) if slot == 2 else set(W.UNARY))
    for _ in range(max_iter):
        changed = False
        for u, sc in obs:
            asg = viable_assignments(u, sc, surv)
            if not asg: continue
            keep = {w: set() for w in u}
            for (i, j) in asg:
                a, b = sc[i], sc[j]
                for slot, w in enumerate(u):
                    if slot == 2:
                        keep[w] |= {m for m in surv[w] if W.binary_holds(m, a, b)}
                    else:
                        o = a if slot in (0, 1) else b
                        keep[w] |= {m for m in surv[w] if W.unary_holds(m, o)}
            for w in u:
                if keep[w] and keep[w] != surv[w]:
                    surv[w] = keep[w]; changed = True
        if not changed: break
    committed = {w: next(iter(s)) for w, s in surv.items() if len(s) == 1}
    return committed, surv


def resolve(committed, utt, scene):
    """REFERENCE RESOLUTION: the SET of (i,j) assignments consistent with the committed meanings."""
    if any(w not in committed for w in utt): return None
    out = []
    for i, j in itertools.permutations(range(len(scene)), 2):
        a, b = scene[i], scene[j]
        if (W.unary_holds(committed[utt[0]], a) and W.unary_holds(committed[utt[1]], a)
                and W.binary_holds(committed[utt[2]], a, b)
                and W.unary_holds(committed[utt[3]], b) and W.unary_holds(committed[utt[4]], b)):
            out.append((i, j))
    return out


def corpus_n(lex, n_obs, n_obj, rng):
    out = []
    guard = 0
    while len(out) < n_obs and guard < n_obs * 200:
        guard += 1
        sc = rand_scene_n(rng, n_obj)
        if sc is None: continue
        u, truth = speak(lex, sc, rng)
        if u is None: continue
        out.append((u, sc, truth))
    return out


if __name__ == "__main__":
    t0 = time.time()
    lex = W.Lexicon(seed=11)
    print("PHASE 5(b) -- referential uncertainty: the learner is NOT told which objects a word describes\n")

    print(f"{'objs':>5} {'N':>5} {'committed':>10} {'exact':>6} {'WRONG':>6} {'mean surv':>10} "
          f"{'ref unique':>11} {'ref WRONG':>10}")
    rows = []
    for n_obj in (3, 4, 5):
        for N in (20, 60, 150):
            rng = random.Random(100 + n_obj)
            data = corpus_n(lex, N, n_obj, rng)
            obs = [(u, sc) for u, sc, _ in data]
            com, surv = learn_ru(obs)
            exact = sum(1 for w, p in lex.w2p.items() if com.get(w) == p)
            wrong = sum(1 for w, p in lex.w2p.items() if w in com and com[w] != p)
            ms = sum(len(s) for s in surv.values()) / max(1, len(surv))
            # T3 reference resolution on held-out scenes
            test = corpus_n(lex, 60, n_obj, random.Random(999 + n_obj))
            uniq = 0; refwrong = 0; cov = 0
            for u, sc, truth in test:
                R = resolve(com, u, sc)
                if R is None: continue
                cov += 1
                if len(R) == 1:
                    uniq += 1
                    if R[0] != truth: refwrong += 1
            rows.append({"objects": n_obj, "N": N, "committed": len(com), "exact": exact, "wrong": wrong,
                         "mean_survivors": round(ms, 2), "ref_coverage": cov / max(1, len(test)),
                         "ref_unique": uniq / max(1, cov) if cov else 0.0, "ref_wrong": refwrong})
            print(f"{n_obj:>5} {N:>5} {len(com):>10} {exact:>6} {wrong:>6} {ms:>10.2f} "
                  f"{(uniq/max(1,cov) if cov else 0):>11.3f} {refwrong:>10}")

    tot_wrong = sum(r["wrong"] for r in rows)
    tot_refwrong = sum(r["ref_wrong"] for r in rows)
    best3 = max((r for r in rows if r["objects"] == 3), key=lambda r: r["exact"])
    print(f"\n  best at 3 objects: {best3['exact']}/10 words exact at N={best3['N']} "
          f"(Phase 5 needed N=8 with reference GIVEN)")
    print(f"  WRONG lexicon commitments across all settings: {tot_wrong}")
    print(f"  WRONG referent commitments across all settings: {tot_refwrong}")
    print(f"\n=== VERDICT ===")
    if tot_wrong == 0 and tot_refwrong == 0:
        print(f"  SOUND under referential uncertainty: the engine never commits a wrong meaning and never")
        print(f"  commits a wrong referent -- it abstains (survivor set > 1) instead. Reference ambiguity is")
        print(f"  paid for in COVERAGE, never in correctness. This is the pragmatics wall met with a verifier.")
    else:
        print(f"  UNSOUND: {tot_wrong} wrong meanings, {tot_refwrong} wrong referents -- report, do not tune.")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase5b_referential_uncertainty"] = {
        "grid": f"{G}x{G}", "rows": rows,
        "wrong_lexicon_commitments": tot_wrong, "wrong_referent_commitments": tot_refwrong,
        "phase5_reference_given_N": 8,
        "verdict": "SOUND" if (tot_wrong == 0 and tot_refwrong == 0) else "UNSOUND",
        "method": "arc consistency to a fixpoint: a meaning survives for w iff for EVERY observation there "
                  "EXISTS an object assignment under which all five words can hold with surviving meanings. "
                  "The true lexicon is viable under the true assignment, so the true meaning is never removed "
                  "-- soundness is a theorem. Ambiguity costs COVERAGE, never correctness.",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
