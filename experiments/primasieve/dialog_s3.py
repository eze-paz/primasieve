"""DIALOGUE SUITE S3 -- MULTI-TURN CONVERSATION: pronouns, discourse state, answering, abstaining.

S1/S2 gave the engine a vocabulary (101 concepts, 0 errors). This is the conversation itself.

A dialogue = two ASSERTIONS about a shared scene, then a QUESTION containing a PRONOUN:
    turn 1   <word> <word> <rel>        describes objects (i1, j1)
    turn 2   <word> <word> <rel>        describes objects (i2, j2)
    turn 3   <pronoun> <rel> <word> ?   'is IT <rel> the <word> one?'
The engine must carry discourse state across turns, resolve the pronoun, find the described object, evaluate
the relation, and answer -- or abstain and ask if anything is ambiguous.

CRUCIALLY the meaning of the pronoun is NOT hard-coded. It is LEARNED by the same elimination: candidate
meanings are DISCOURSE FUNCTIONS
    FIRST_MENTIONED  subject of turn 1
    LAST_SUBJECT     subject of turn 2
    LAST_OBJECT      object of turn 2
    MOST_RECENT      last object mentioned at all
and a function survives iff the answer it produces matches the world's truthful answer in EVERY training
dialogue. With a single prior turn these functions are co-extensive, so the task genuinely REQUIRES multi-turn
structure to separate them -- which is the point.

MEASURED: discourse-rule recovery, held-out answer accuracy, coverage, abstention on ambiguity, confabulations.
KILL: any confabulation (a committed answer the world says is wrong).
"""
import os, sys, json, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialog_world as DW
import dialog_s1 as S1
import dialog_s2 as S2

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))

DISCOURSE = ["FIRST_MENTIONED", "LAST_SUBJECT", "LAST_OBJECT", "MOST_RECENT"]


def apply_discourse(fn, turns):
    """turns = [(i1,j1),(i2,j2)] -> the object INDEX the pronoun denotes."""
    (i1, j1), (i2, j2) = turns
    if fn == "FIRST_MENTIONED": return i1
    if fn == "LAST_SUBJECT": return i2
    if fn == "LAST_OBJECT": return j2
    if fn == "MOST_RECENT": return j2 if j2 != i2 else i2
    raise KeyError(fn)


def describe(world, scene, i, j, rng):
    ua = world.true_unary(scene[i]); ub = world.true_unary(scene[j]); rb = world.true_binary(scene[i], scene[j])
    if not (ua and ub and rb): return None
    return [world.p2w[rng.choice(ua)], world.p2w[rng.choice(ub)], world.p2w[rng.choice(rb)]]


def make_dialogue(world, rng, n_obj, pronoun, true_fn):
    """two assertions + one pronoun question; returns the dialogue and the world's truthful answer."""
    scene = world.rand_scene(rng, n_obj)
    if scene is None: return None
    idx = list(range(n_obj))
    i1, j1 = rng.sample(idx, 2)
    i2, j2 = rng.sample(idx, 2)
    t1 = describe(world, scene, i1, j1, rng)
    t2 = describe(world, scene, i2, j2, rng)
    if not (t1 and t2): return None
    turns = [(i1, j1), (i2, j2)]
    ref = apply_discourse(true_fn, turns)
    # the question names a TARGET object by one unary predicate that must pick it out UNIQUELY
    tgt = rng.choice([k for k in idx if k != ref] or idx)
    cands = [p for p in world.true_unary(scene[tgt])
             if sum(1 for k in idx if world.u(p, scene[k])) == 1]
    if not cands: return None
    tw = world.p2w[rng.choice(cands)]
    relp = rng.choice(world.binary)
    q = [pronoun, world.p2w[relp], tw]
    ans = world.b(relp, scene[ref], scene[tgt])          # the world answers truthfully
    return {"scene": scene, "t1": t1, "t2": t2, "turns": turns, "q": q, "ans": ans, "ref": ref, "tgt": tgt}


def resolve_target(world, lex, scene, word):
    """objects satisfying the question's descriptive word, under the LEARNED lexicon."""
    if word not in lex: return None
    p = lex[word]
    if p not in world.unary: return None
    return [k for k in range(len(scene)) if world.u(p, scene[k])]


def answer_with(world, lex, fn, d):
    """answer the question using a candidate discourse function + the learned lexicon. None = abstain."""
    pron, relw, tw = d["q"]
    if relw not in lex or lex[relw] not in world.binary: return None
    tgts = resolve_target(world, lex, d["scene"], tw)
    if tgts is None or len(tgts) != 1: return None       # ambiguous / unknown description -> abstain
    ref = apply_discourse(fn, d["turns"])
    return world.b(lex[relw], d["scene"][ref], d["scene"][tgts[0]])


def learn_discourse(world, lex, dialogues):
    """a discourse function survives iff it reproduces the world's answer in EVERY training dialogue."""
    surv = set(DISCOURSE)
    used = 0
    for d in dialogues:
        keep = set()
        for fn in surv:
            a = answer_with(world, lex, fn, d)
            if a is None or a == d["ans"]: keep.add(fn)
        # NOTE: an EMPTY keep means NO discourse rule explains this observation. Earlier this branch silently
        # retained the stale survivor set -- i.e. it IGNORED contradicting evidence, which the shuffled-answer
        # knockout correctly exposed as a leak. The survivor set is now allowed to go EMPTY: that is the engine
        # reporting that its hypothesis space is refuted, which is the sound response.
        if keep != surv:
            used += 1
        surv = keep
        if not surv: break
    return surv, used


if __name__ == "__main__":
    t0 = time.time()
    N_OBJ = 4
    print("DIALOGUE S3 -- multi-turn conversation with learned pronoun resolution\n")
    world = DW.World(16, 6, 4, seed=11)
    V = len(world.w2p)

    # 1) learn the vocabulary (S1 elimination + S2 asking)
    data = S1.corpus(world, 6000, 3, random.Random(7))
    com, surv = S1.learn(world, data)
    pool = S2.object_pool(world, random.Random(3))
    lex, asked = S2.resolve_by_asking(world, surv, pool, mode="active")
    exact = sum(1 for w, p in world.w2p.items() if lex.get(w) == p)
    print(f"vocabulary: {exact}/{V} concepts learned "
          f"({sum(1 for w,p in world.w2p.items() if w in lex and lex[w]!=p)} wrong)")

    # 2) learn the PRONOUN's discourse function
    pronoun = "zzit"
    true_fn = "LAST_SUBJECT"
    rng = random.Random(21)
    train = []
    while len(train) < 400:
        d = make_dialogue(world, rng, N_OBJ, pronoun, true_fn)
        if d: train.append(d)
    survd, used = learn_discourse(world, lex, train)
    print(f"\ndiscourse rule for '{pronoun}': survivors {sorted(survd)}  "
          f"(true = {true_fn}); dialogues that eliminated something: {used}")
    committed_fn = next(iter(survd)) if len(survd) == 1 else None
    print(f"  committed: {committed_fn}   correct: {committed_fn == true_fn}")

    # how many dialogues were needed?
    need = None
    for N in (2, 5, 10, 20, 40, 80, 160, 400):
        s, _ = learn_discourse(world, lex, train[:N])
        if len(s) == 1 and next(iter(s)) == true_fn:
            need = N; break
    print(f"  dialogues needed to pin the discourse rule: {need}")

    # 3) held-out conversation
    rng2 = random.Random(555)
    test = []
    while len(test) < 400:
        d = make_dialogue(world, rng2, N_OBJ, pronoun, true_fn)
        if d: test.append(d)
    ok = com_ = ab = confab = 0
    for d in test:
        a = answer_with(world, lex, committed_fn, d) if committed_fn else None
        if a is None: ab += 1; continue
        com_ += 1
        if a == d["ans"]: ok += 1
        else: confab += 1
    print(f"\nheld-out conversation ({len(test)} dialogues):")
    print(f"  answered {com_}  abstained {ab}  correct {ok}  CONFABULATIONS {confab}")
    print(f"  accuracy-on-answered {ok/max(1,com_):.3f}   coverage {com_/len(test):.3f}")

    # 4) knockout: shuffle which dialogue each answer belongs to -> the rule must not be learnable
    sh = list(train)
    ans = [d["ans"] for d in sh]
    random.Random(9).shuffle(ans)
    shuf = [dict(d, ans=ans[i]) for i, d in enumerate(sh)]
    sk, _ = learn_discourse(world, lex, shuf)
    print(f"\n  KNOCKOUT (answers shuffled): survivors {sorted(sk)} -> "
          f"{'collapses (no rule commits)' if len(sk) != 1 else 'LEAKS'}")

    print(f"\n=== VERDICT ===")
    good = (committed_fn == true_fn) and confab == 0
    if good:
        print(f"  CONVERSATION WORKS in this world: the engine carries discourse state across turns, LEARNS")
        print(f"  what the pronoun refers to (it was never told), answers held-out questions at "
              f"{ok/max(1,com_):.1%} with {confab} confabulations, and abstains when the description is ambiguous.")
    else:
        print(f"  Not working: rule={committed_fn} (true {true_fn}), confabulations {confab}.")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["dialog_s3_conversation"] = {
        "concepts": V, "vocab_learned": exact, "true_discourse_fn": true_fn,
        "committed_discourse_fn": committed_fn, "dialogues_to_learn_rule": need,
        "heldout": {"n": len(test), "answered": com_, "abstained": ab, "correct": ok,
                    "confabulations": confab, "accuracy": round(ok / max(1, com_), 4),
                    "coverage": round(com_ / len(test), 4)},
        "knockout_survivors": sorted(sk),
        "verdict": "CONVERSATION WORKS" if good else "not working",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
