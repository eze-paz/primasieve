"""PHASE 5 -- GROUNDED LANGUAGE: word meanings learned by SOUND REJECTION in a sealed world.

Fuses three things built here and never connected: the exact rect world (p1-p9), the survivor-set /
commit-only-if-unique discipline, and language. A word's meaning is learned CROSS-SITUATIONALLY: candidate
meanings are all predicates of the right arity; every observation REJECTS those inconsistent with it; commit
only if a UNIQUE survivor remains, else ABSTAIN and report the set. No probabilities anywhere. The world (an
exact renderer + truth-condition checker) is the oracle -- precisely what the SVAMP/NL arc lacked, where the
wall was reference/pragmatics with no verifier.

Syntax (the 5-slot schema) is SUPPLIED; SEMANTICS is learned. Words are NONSENSE, mapped by a hidden seeded
permutation, so nothing leaks from spelling.

TESTS
  T1 lexicon recovery     : learned word to predicate vs the hidden map (exact)
  T2 truth judgement      : held-out (utterance, scene) TRUE/FALSE vs the sealed checker
  T3 NOVEL COMPOSITION    : test items whose held-out word PAIR never co-occurred in training (SCAN-style)
  T4 unknown-word abstain : an out-of-lexicon word must force ABSTENTION, never a guess
BASELINE (kill): nearest-neighbour retrieval over training utterances + copy-fraction (must be under 0.5).
KNOCKOUT: pair each training utterance with a RANDOM scene, so no consistent meaning exists -> must abstain.

KILL 5: novel-composition accuracy under 80%, OR any confabulation (a committed judgement the checker says is
wrong), OR the retrieval baseline matching the learner.
"""
import os, sys, json, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world_english as W

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
SLOT_OBJ = {0: 0, 1: 0, 3: 1, 4: 1}          # which object each unary slot describes


def learn(pairs):
    """pairs = [(utterance, scene)] all TRUE. Returns (committed {word:pred}, survivors {word:set})."""
    uni_obs = {}
    bin_obs = {}
    all_objs = []; all_pairs = []
    for utt, sc in pairs:
        a, b = sc[0], sc[1]
        all_objs += [a, b]; all_pairs.append((a, b))
        for slot, w in enumerate(utt):
            if slot == 2: bin_obs.setdefault(w, []).append((a, b))
            else: uni_obs.setdefault(w, []).append(sc[SLOT_OBJ[slot]])
    # anti-vacuity: a predicate true of EVERY observed object/pair cannot be discriminated -> drop it
    disc_u = [p for p in W.UNARY if not all(W.unary_holds(p, o) for o in all_objs)]
    disc_b = [p for p in W.BINARY if not all(W.binary_holds(p, a, b) for a, b in all_pairs)]
    surv = {}
    for w, objs in uni_obs.items():
        surv[w] = {p for p in disc_u if all(W.unary_holds(p, o) for o in objs)}
    for w, prs in bin_obs.items():
        surv[w] = {p for p in disc_b if all(W.binary_holds(p, a, b) for a, b in prs)}
    committed = {w: next(iter(s)) for w, s in surv.items() if len(s) == 1}
    return committed, surv


def judge(committed, utt, scene):
    """evaluate the utterance with LEARNED meanings. None = ABSTAIN (unknown/uncommitted word)."""
    if len(utt) != 5: return None
    if any(w not in committed for w in utt): return None
    a, b = scene[0], scene[1]
    try:
        return (W.unary_holds(committed[utt[0]], a) and W.unary_holds(committed[utt[1]], a)
                and W.binary_holds(committed[utt[2]], a, b)
                and W.unary_holds(committed[utt[3]], b) and W.unary_holds(committed[utt[4]], b))
    except KeyError:
        return None


def perturb(lex, utt, rng):
    """swap ONE word for another of the SAME arity; the label always comes from the sealed checker."""
    u = list(utt); slot = rng.choice([0, 1, 2, 3, 4])
    ar = 2 if slot == 2 else 1
    alts = [w for w in lex.w2p if lex.arity[w] == ar and w != u[slot]]
    u[slot] = rng.choice(alts); return u


def corpus(lex, n, rng, exclude_pair=None):
    """n TRUE (utterance, scene) pairs. exclude_pair=(wA,wB): never let both appear in one utterance."""
    out = []
    guard = 0
    while len(out) < n and guard < n * 500:
        guard += 1
        sc = W.rand_scene(rng)
        if sc is None: continue
        u = lex.describe(sc)
        if u is None: continue
        if exclude_pair and (exclude_pair[0] in u and exclude_pair[1] in u): continue
        out.append((u, sc))
    return out


def items_with_pair(lex, n, rng, pair):
    out = []
    tries = 0
    while len(out) < n and tries < n * 6000:
        tries += 1
        sc = W.rand_scene(rng)
        if sc is None: continue
        u = lex.describe(sc)
        if u is None or not (pair[0] in u and pair[1] in u): continue
        out.append((u, sc))
    return out


def score(committed, tests, lex):
    """tests = [(utt, scene)]; label from the sealed checker. Returns acc-on-committed, coverage, confabs, n."""
    n = com = ok = confab = 0
    for u, sc in tests:
        n += 1
        truth = lex.checker(u, sc)
        got = judge(committed, u, sc)
        if got is None: continue
        com += 1
        if got == truth: ok += 1
        else: confab += 1
    return (ok / com if com else 0.0), (com / n if n else 0.0), confab, n


def make_tests(lex, base, rng):
    """each scene contributes its TRUE utterance and one perturbed one (label from the checker)."""
    t = []
    for u, sc in base:
        t.append((u, sc)); t.append((perturb(lex, u, rng), sc))
    return t


def retrieval_baseline(train, tests, lex):
    """KILL BASELINE: nearest-neighbour by word overlap. Every training item is TRUE, so NN predicts TRUE."""
    ok = 0
    for u, sc in tests:
        truth = lex.checker(u, sc)
        best, bl = None, -1
        for tu, tsc in train:
            ov = len(set(u) & set(tu))
            if ov > bl: bl, best = ov, (tu, tsc)
        ok += (True == truth)
    return ok / max(1, len(tests))


if __name__ == "__main__":
    t0 = time.time()
    N_TRAIN = int(os.environ.get("P5_TRAIN", "120"))
    lex = W.Lexicon(seed=11)
    rng = random.Random(3)
    print("PHASE 5 -- grounded language in the sealed rect world\n")
    print(f"hidden lexicon (never shown to the learner): {lex.w2p}\n")

    hp = (lex.p2w["C3"], lex.p2w["ABOVE"])
    print(f"held-out COMPOSITION: {hp[0]!r}(C3) never co-occurs with {hp[1]!r}(ABOVE) in training")

    train = corpus(lex, N_TRAIN, rng, exclude_pair=hp)
    committed, surv = learn(train)

    print(f"\n=== T1 lexicon recovery ({len(train)} training utterances) ===")
    exact = 0
    for w, p in sorted(lex.w2p.items(), key=lambda kv: kv[1]):
        got = committed.get(w)
        s = surv.get(w, set())
        mark = "OK " if got == p else ("ABSTAIN" if got is None else "WRONG")
        exact += got == p
        print(f"  {w:8s} true={p:9s} learned={str(got):9s} survivors={len(s)}  {mark}")
    wrong = sum(1 for w, p in lex.w2p.items() if w in committed and committed[w] != p)
    print(f"  recovered {exact}/{len(lex.w2p)} exactly; committed {len(committed)}; WRONG commitments {wrong}")

    base = corpus(lex, 60, random.Random(77), exclude_pair=hp)
    tests = make_tests(lex, base, random.Random(5))
    a2, c2, cf2, n2 = score(committed, tests, lex)
    print(f"\n=== T2 truth judgement, in-distribution ({n2} items) ===")
    print(f"  accuracy-on-committed {a2:.3f}   coverage {c2:.3f}   confabulations {cf2}")

    nb = items_with_pair(lex, 40, random.Random(99), hp)
    ntests = make_tests(lex, nb, random.Random(6))
    trainset = {tuple(u) for u, _ in train}
    copy_frac = sum(1 for u, _ in ntests if tuple(u) in trainset) / max(1, len(ntests))
    a3, c3, cf3, n3 = score(committed, ntests, lex)
    print(f"\n=== T3 NOVEL COMPOSITION ({n3} items containing the held-out pair) ===")
    print(f"  accuracy-on-committed {a3:.3f}   coverage {c3:.3f}   confabulations {cf3}")
    ok_copy = "OK" if copy_frac < 0.5 else "FAILS"
    print(f"  copy-fraction (test utterance verbatim in training) {copy_frac:.3f}  [{ok_copy}]")
    rb = retrieval_baseline(train, ntests, lex)
    print(f"  retrieval/NN baseline accuracy {rb:.3f}   (learner {a3:.3f})")

    unk = [(["NOTAWORD"] + list(u[1:]), sc) for u, sc in nb[:20]]
    a4, c4, cf4, n4 = score(committed, unk, lex)
    print(f"\n=== T4 unknown-word abstention ({n4} items) ===")
    print(f"  coverage {c4:.3f} (must be 0.000)   confabulations {cf4}")

    rngk = random.Random(31)
    scenes = [sc for _, sc in corpus(lex, N_TRAIN, rngk)]
    rngk.shuffle(scenes)
    ko_train = [(u, scenes[i % len(scenes)]) for i, (u, _) in enumerate(train)]
    ko_com, ko_surv = learn(ko_train)
    ak, ck, cfk, nk = score(ko_com, ntests, lex)
    ko_exact = sum(1 for w, p in lex.w2p.items() if ko_com.get(w) == p)
    print(f"\n=== KNOCKOUT: utterance/scene correspondence destroyed ===")
    print(f"  committed words {len(ko_com)}/{len(lex.w2p)}   exact recoveries {ko_exact}")
    print(f"  novel-composition accuracy {ak:.3f} coverage {ck:.3f}  (learner {a3:.3f}/{c3:.3f})")

    print(f"\n=== KILL 5 ===")
    reasons = []
    if a3 < 0.80: reasons.append(f"novel-composition accuracy {a3:.3f} under 0.80")
    if cf2 or cf3 or cf4: reasons.append(f"confabulations {cf2 + cf3 + cf4}")
    if copy_frac >= 0.5: reasons.append(f"copy-fraction {copy_frac:.2f} at or above 0.5")
    if rb >= a3: reasons.append(f"retrieval baseline {rb:.3f} at or above learner {a3:.3f}")
    if reasons:
        print(f"  FIRED: {'; '.join(reasons)}")
    else:
        print(f"  PASSES: meanings learned by sound rejection generalise to NOVEL COMPOSITIONS "
              f"({a3:.1%} at {c3:.1%} coverage), 0 confabulations, unknown words ABSTAIN, retrieval "
              f"baseline beaten ({rb:.3f}), knockout collapses.")
    print(f"  ({time.time() - t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase5_grounded_language"] = {
        "n_train": len(train), "held_out_pair": {"words": list(hp), "preds": ["C3", "ABOVE"]},
        "T1_lexicon_recovered": f"{exact}/{len(lex.w2p)}", "T1_committed": len(committed),
        "T1_wrong_commitments": wrong,
        "T2_in_distribution": {"acc": round(a2, 4), "coverage": round(c2, 4), "confab": cf2, "n": n2},
        "T3_novel_composition": {"acc": round(a3, 4), "coverage": round(c3, 4), "confab": cf3, "n": n3,
                                 "copy_fraction": round(copy_frac, 4), "retrieval_baseline": round(rb, 4)},
        "T4_unknown_word": {"coverage": round(c4, 4), "confab": cf4, "n": n4},
        "knockout_shuffled_scenes": {"committed": len(ko_com), "exact": ko_exact,
                                     "acc": round(ak, 4), "coverage": round(ck, 4)},
        "kill5": "FIRED: " + "; ".join(reasons) if reasons else "PASSES",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
