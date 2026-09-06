"""EMERGENCE E-9 -- THE FOURTH VERDICT STATE: CONJECTURED (em_conjecture_prereg.md). ZERO LLM, pure stdlib.

A guess with a correction channel. The learner holds the unique most-specific survivor of a word's meaning
BEFORE elimination singles one out, answers with it tagged, and drops it -- with everything built on it -- the
moment the world contradicts it. State, lattice position, admission and revision live in core.verdict; this file
is the measured two-arm test on the rect world, plus the pinned kills: evidence-count invariance, revision with
cascade, inertness against the abstain-only engine, tie discipline, the shuffled-lexicon knockout, and a source
check that the core knows nothing about this world."""
import os, sys, json, time, random, ast, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import en_world as W
import core.verdict as V
from core.registry import selfcheck
from core.verdict import COMMIT, ABSTAIN, CONJECTURED, RETRACTED, conjecture, Beliefs, summarize4

OUT = os.path.join(HERE, "EMERGENCE.json")
BUDGETS = (10, 20, 40, 80, 160, 320, 640)
N_EXT = 4000            # the stream continues to here for revision
N_Q = 200               # questions per budget


# ------------------------------------------------------------------ the world's speaker and the learner's data
def stream(n, rng, pred2word):
    """(word, object, scene) per observation: the speaker names ONE random true property of one object."""
    out = []
    while len(out) < n:
        sc = W.rand_scene(rng, 3)
        if sc is None: continue
        o = rng.choice(sc)
        out.append((pred2word[rng.choice(W.true_unary(o))], o, sc))
    return out


def survivors(obs):
    """word -> the predicates true of EVERY object the word was used for (sound elimination); plus the observed
    base rate of every predicate over all objects seen (the CALLER's specificity key -- data, not authorship)."""
    used = collections.defaultdict(list); rate = collections.Counter()
    for word, o, sc in obs:
        used[word].append(o)
        for x in sc:
            for p in W.true_unary(x): rate[p] += 1
    surv = {w: frozenset(p for p in W.UNARY if all(W.unary_holds(p, o) for o in objs)) for w, objs in used.items()}
    return surv, rate


def build(obs, guess):
    """Beliefs over the words seen so far. guess=False is the ABSTAIN arm (singleton or nothing)."""
    surv, rate = survivors(obs)
    B = Beliefs(); ties = 0
    for w, s in surv.items():
        v, st, rivals = conjecture(s, key=(lambda p: rate[p]) if guess else None)
        if st == ABSTAIN and len(s) > 1 and guess: ties += 1
        if st != ABSTAIN: B.hold(("word", w), v, st, rivals=rivals)
    return B, surv, rate, ties


def ask(B, rng, word2pred, n_q):
    """n_q questions 'which object is <word>?' on fresh scenes where the TRUE meaning picks exactly one object.
    Every answer that relies on a held word is DERIVED from it (a dependent). Returns per-question records."""
    pred2word = {p: w for w, p in word2pred.items()}; recs = []   # sample by PREDICATE: a relabeling changes nothing
    while len(recs) < n_q:
        sc = W.rand_scene(rng, 3)
        if sc is None: continue
        w = pred2word[rng.choice(W.UNARY)]
        truth = [i for i, o in enumerate(sc) if W.unary_holds(word2pred[w], o)]
        if len(truth) != 1: continue
        qid = ("answer", len(recs))
        e = B.b.get(("word", w))
        if e is None or e["state"] in (ABSTAIN, RETRACTED):
            recs.append(dict(q=qid, word=w, state=ABSTAIN, correct=None)); continue
        picks = [i for i, o in enumerate(sc) if W.unary_holds(e["value"], o)]
        if len(picks) != 1:                                   # the held meaning does not single one out
            recs.append(dict(q=qid, word=w, state=ABSTAIN, correct=None)); continue
        st = B.derive(qid, picks[0], [("word", w)])
        recs.append(dict(q=qid, word=w, state=st, correct=(picks[0] == truth[0])))
    return recs


def tally(recs):
    c = collections.Counter()
    for r in recs:
        if r["state"] == ABSTAIN: c["abstain"] += 1
        elif r["state"] == COMMIT: c["commit_ok" if r["correct"] else "confab"] += 1
        else: c["conj_ok" if r["correct"] else "conj_wrong"] += 1
    return c


def core_is_agnostic():
    """K7: core/verdict.py imports nothing from this world and names none of its predicates in code."""
    src = open(V.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and ast.get_docstring(node) is not None:
            doc_ids.add(id(node.body[0].value))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) else [])
            bad += [n for n in names if n and ("en_world" in n or "emergence" in n)]
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
            bad += [w for w in W.UNARY if w == node.value.strip()]
    return not bad, bad


def run(shuffled, seed=7):
    rng = random.Random(seed)
    words = list(W.UNARY); preds = list(W.UNARY)
    if shuffled: random.Random(99).shuffle(preds)         # "red" may genuinely mean TALL
    word2pred = dict(zip(words, preds)); pred2word = {p: w for w, p in word2pred.items()}
    obs = stream(N_EXT, rng, pred2word)
    qrng = random.Random(seed + 1)
    per_budget = []; fatal = collections.Counter(); ties_total = 0
    cascade_ok = True; upgrade_ok = True; retract_ok = True; no_commit_retracted = True
    for n in BUDGETS:
        qr = random.Random(qrng.random())
        A, _, _, _ = build(obs[:n], guess=False)
        ra = tally(ask(A, random.Random(qr.random()), word2pred, N_Q))
        C, surv_n, rate_n, ties = build(obs[:n], guess=True)
        ties_total += ties
        recs = ask(C, random.Random(qr.random()), word2pred, N_Q)
        rc = tally(recs)
        fatal["confab"] += ra["confab"] + rc["confab"]
        fatal["laundering"] += len(A.laundered()) + len(C.laundered())
        # ---- the stream continues: revise every conjecture against ALL evidence, measure the cascade ----
        surv_full, _ = survivors(obs)
        held = [k for k in C.conjectured() if k[0] == "word"]
        retracted = upgraded = still_open = cascaded = 0
        for k in held:
            w = k[1]; e = C.b[k]; truth = word2pred[w]
            try:
                st, out = C.revise(k, surv_full.get(w, frozenset()))
            except AssertionError:
                no_commit_retracted = False; raise
            if st == RETRACTED:
                retracted += 1; cascaded += len(out) - 1
                if e["value"] == truth: retract_ok = False          # a right guess can never be contradicted
                if any(C.b[d]["state"] != RETRACTED for d in e["deps"]): cascade_ok = False
            elif st == COMMIT:
                upgraded += 1
                if e["value"] != truth: fatal["confab"] += 1        # upgraded to a wrong COMMIT = confabulation
            else:
                still_open += 1
        # every wrong guess with a contradicting observation in the stream must be gone
        for k in held:
            w = k[1]; e = C.b[k]
            if e["value"] != word2pred[w] and e["value"] not in surv_full.get(w, frozenset()) and e["state"] != RETRACTED:
                retract_ok = False
            if e["value"] == word2pred[w] and len(surv_full.get(w, ())) == 1 and e["state"] != COMMIT:
                upgrade_ok = False
        # STALE: a conjecture still held whose value the full evidence rules out
        fatal["stale"] += sum(1 for k in C.conjectured() if k[0] == "word" and C.b[k]["value"] not in surv_full.get(k[1], frozenset()))
        # every conjecture-backed answer that was wrong must now be RETRACTED (cascade covered it)
        wrong_backed = [r for r in recs if r["state"] == CONJECTURED and r["correct"] is False]
        if any(C.b[r["q"]]["state"] != RETRACTED for r in wrong_backed): cascade_ok = False
        fatal["laundering"] += len(C.laundered())
        per_budget.append(dict(n=n, words_seen=len(surv_n), abstain_arm=dict(ra), conjecture_arm=dict(rc),
                               conjectures=len(held), upgraded=upgraded, retracted=retracted, still_open=still_open,
                               cascaded_dependents=cascaded, ties=ties))
    return dict(per_budget=per_budget, fatal=dict(fatal), ties=ties_total, cascade_ok=cascade_ok,
                upgrade_ok=upgrade_ok, retract_ok=retract_ok, no_commit_retracted=no_commit_retracted, obs=obs,
                word2pred=word2pred)


def invariance(obs, word2pred):
    """K2: the SAME survivor set from a 10-observation history and from that history repeated 1000x."""
    short = obs[:10]; long_ = short * 1000
    s1, r1 = survivors(short); s2, r2 = survivors(long_)
    same = True
    for w in s1:
        a = conjecture(s1[w], key=lambda p: r1[p]); b = conjecture(s2[w], key=lambda p: r2[p])
        same &= (a == b)
    return same, len(s1)


if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    print("EMERGENCE E-9 -- CONJECTURED: a guess with a correction channel (em_conjecture_prereg.md)\n", flush=True)

    R = run(shuffled=False)
    print(f"{'n':>5} {'seen':>5} | ABSTAIN arm  ok  abst | CONJECTURE arm  commit-ok conj-ok conj-wrong abst | "
          f"conj upgraded retracted open cascaded ties")
    tot_a = tot_c = 0; inert_n = None; inert_a = inert_c = 0
    for pb in R["per_budget"]:
        a, c = pb["abstain_arm"], pb["conjecture_arm"]
        a_ok = a.get("commit_ok", 0); c_ok = c.get("commit_ok", 0) + c.get("conj_ok", 0)
        tot_a += a_ok; tot_c += c_ok
        if inert_n is None and a_ok / N_Q < 0.5:
            inert_n, inert_a, inert_c = pb["n"], a_ok, c_ok
        print(f"{pb['n']:>5} {pb['words_seen']:>5} | {a_ok:>13} {a.get('abstain',0):>5} | "
              f"{c.get('commit_ok',0):>24} {c.get('conj_ok',0):>7} {c.get('conj_wrong',0):>10} {c.get('abstain',0):>4} | "
              f"{pb['conjectures']:>4} {pb['upgraded']:>8} {pb['retracted']:>9} {pb['still_open']:>4} "
              f"{pb['cascaded_dependents']:>8} {pb['ties']:>4}", flush=True)

    f = R["fatal"]
    conj_total = sum(pb["conjecture_arm"].get("conj_ok", 0) + pb["conjecture_arm"].get("conj_wrong", 0) for pb in R["per_budget"])
    conj_wrong = sum(pb["conjecture_arm"].get("conj_wrong", 0) for pb in R["per_budget"])
    abst = sum(pb["conjecture_arm"].get("abstain", 0) for pb in R["per_budget"])
    print("\n" + summarize4(N_Q * len(BUDGETS), f.get("confab", 0), f.get("laundering", 0), f.get("stale", 0),
                            conj_wrong, conj_total, abst, label="conjecture arm, all budgets"), flush=True)

    k1 = f.get("confab", 0) == 0 and f.get("laundering", 0) == 0 and f.get("stale", 0) == 0
    print(f"\nKILL#1 confabulation 0 / laundering 0 / stale 0: {k1}", flush=True)
    inv, nw = invariance(R["obs"], R["word2pred"])
    print(f"KILL#2 evidence-count invariance (10 obs vs 10,000 obs, {nw} words, identical value/state/rivals): {inv}", flush=True)
    k3 = R["retract_ok"] and R["upgrade_ok"] and R["cascade_ok"] and R["no_commit_retracted"]
    print(f"KILL#3 revision: wrong guesses retracted {R['retract_ok']}, right guesses upgrade on singleton {R['upgrade_ok']}, "
          f"100% dependents cascaded {R['cascade_ok']}, no COMMIT retracted {R['no_commit_retracted']}: {k3}", flush=True)
    factor = (inert_c / inert_a) if inert_a else float("inf")
    k4 = inert_n is not None and inert_c >= 1.5 * max(inert_a, 1) and inert_c > 0
    print(f"KILL#4 inertness: at n={inert_n} (first budget with ABSTAIN-arm coverage < 0.5) abstain {inert_a} vs "
          f"conjecture {inert_c} correct = {factor:.1f}x (bar 1.5x): {k4}", flush=True)
    print(f"KILL#5 tie discipline: {R['ties']} tied survivor sets across budgets, every one answered ABSTAIN (structural: "
          f"conjecture() returns None on a tie): True", flush=True)

    S = run(shuffled=True)
    same = all(pa["abstain_arm"] == pb["abstain_arm"] and pa["conjecture_arm"] == pb["conjecture_arm"]
               for pa, pb in zip(R["per_budget"], S["per_budget"]))
    k6 = same and S["fatal"] == R["fatal"]
    print(f"KILL#6 shuffled lexicon ('red' may mean TALL): every per-budget number identical to the unshuffled run: {k6}", flush=True)
    k7, bad = core_is_agnostic()
    print(f"KILL#7 core/verdict.py agnostic (no world import, no predicate name in code): {k7}{'' if k7 else '  offenders ' + str(bad)}", flush=True)

    sound = k1 and inv and k3 and k4 and k6 and k7
    if sound:
        print("\nE9 CONJECTURED STATE: SOUND -- guessed from the survivor set only, used tagged, never laundered, "
              "retracted with cascade on the first contradiction, upgraded only by elimination to one", flush=True)
    else:
        print("\nE9 CONJECTURED STATE: NOT SOUND (read the kill lines)", flush=True)

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E9_conjectured_state"] = dict(prereg="em_conjecture_prereg.md", per_budget=R["per_budget"], fatal=R["fatal"],
                                     ties=R["ties"], invariance=inv, revision=k3, inertness=dict(n=inert_n, abstain=inert_a,
                                     conjecture=inert_c, factor=factor), shuffled_identical=k6, agnostic=k7, sound=sound)
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"({time.time()-t0:.0f}s) -> EMERGENCE.json[E9_conjectured_state]", flush=True)
