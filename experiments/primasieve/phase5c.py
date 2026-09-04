"""PHASE 5(c) -- ASKING A CLARIFYING QUESTION: COLLECT at the reference layer.

Phase 5(b) left the engine able to DETECT irreducible reference ambiguity (100% of its abstentions are still
ambiguous under the true lexicon) but unable to RESOLVE it -- correctly, because one utterance does not carry
the information. The remedy is not better inference, it is MORE INFORMATION. So the engine asks.

QUERY LANGUAGE (generic, not a lookup): a question is
    (slot, predicate)              -- does the intended FIRST/SECOND referent satisfy this unary predicate?
    (slot, predicate, object k)    -- does it stand in this binary relation to scene object k?
The engine picks the question that maximally SPLITS its surviving referent set (E6/p8 belief-splitting), the
world answers truthfully, and inconsistent assignments are REJECTED. Commit only on a unique survivor.
Asking 'is it pair (i,j)?' is forbidden -- that would be guessing dressed as a query.

CONTROL: ACTIVE question choice vs RANDOM question choice at equal budget. Unlike the integ probe (where the
pool was dense with discriminators and random nearly tied), the referent question space is large, so this is
a fair test of whether active design actually buys anything.
KILL: any wrong referent commitment.
"""
import os, sys, json, random, time, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import world_english as W
import phase5b as P5B

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))


def questions(scene):
    """the generic question space over a scene."""
    qs = []
    for slot in (0, 1):
        for p in W.UNARY:
            qs.append((slot, p, None))
        for p in W.BINARY:
            for k in range(len(scene)):
                qs.append((slot, p, k))
    return qs


def answer(q, scene, assignment):
    """truthful answer from the world, given the INTENDED assignment."""
    slot, p, k = q
    obj = scene[assignment[slot]]
    if k is None:
        return W.unary_holds(p, obj)
    if assignment[slot] == k: return None            # degenerate self-relation: uninformative
    return W.binary_holds(p, obj, scene[k])


def split(cands, q, scene):
    """how many distinct answers the surviving assignments give -- the belief-splitting criterion."""
    vals = set()
    for a in cands:
        vals.add(answer(q, scene, a))
    return len(vals)


def clarify(mode, cands, scene, truth, budget=6, rng=None):
    """ask until the referent set is a singleton (or no question splits / budget spent)."""
    qs = questions(scene)
    used = []
    while len(cands) > 1 and len(used) < budget:
        pool = [q for q in qs if q not in used]
        if not pool: break
        if mode == "active":
            q = max(pool, key=lambda x: split(cands, x, scene))
            if split(cands, q, scene) < 2: break     # genuinely unknowable within this question language
        else:
            q = rng.choice(pool)
        used.append(q)
        a = answer(q, scene, truth)
        cands = [c for c in cands if answer(q, scene, c) == a]
    return cands, used


if __name__ == "__main__":
    t0 = time.time()
    lex = W.Lexicon(seed=11)
    print("PHASE 5(c) -- the engine asks a clarifying question (COLLECT at the reference layer)\n")
    print(f"{'objs':>5} {'ambiguous':>10} {'ACTIVE resolved':>16} {'q':>5} {'RANDOM resolved':>16} {'q':>5} "
          f"{'wrong':>6}")
    rows = []
    for n_obj in (3, 4, 5):
        data = P5B.corpus_n(lex, 60, n_obj, random.Random(100 + n_obj))
        com, _ = P5B.learn_ru([(u, sc) for u, sc, _ in data])
        test = P5B.corpus_n(lex, 150, n_obj, random.Random(999 + n_obj))
        amb = 0
        ares = 0; aq = 0; rres = 0; rq = 0; wrong = 0
        for u, sc, truth in test:
            R = P5B.resolve(com, u, sc)
            if R is None or len(R) <= 1: continue
            amb += 1
            ca, ua = clarify("active", list(R), sc, truth)
            aq += len(ua)
            if len(ca) == 1:
                ares += 1
                if ca[0] != truth: wrong += 1
            cr, ur = clarify("random", list(R), sc, truth, rng=random.Random(amb))
            rq += len(ur)
            if len(cr) == 1:
                rres += 1
                if cr[0] != truth: wrong += 1
        if amb == 0:
            print(f"{n_obj:>5} {0:>10}  (no ambiguous cases)"); continue
        rows.append({"objects": n_obj, "ambiguous": amb,
                     "active_resolved": ares / amb, "active_q": aq / amb,
                     "random_resolved": rres / amb, "random_q": rq / amb, "wrong": wrong})
        print(f"{n_obj:>5} {amb:>10} {ares/amb:>16.3f} {aq/amb:>5.2f} {rres/amb:>16.3f} {rq/amb:>5.2f} "
              f"{wrong:>6}")

    tw = sum(r["wrong"] for r in rows)
    ta = sum(r["active_q"] * r["ambiguous"] for r in rows) / max(1, sum(r["ambiguous"] for r in rows))
    tr = sum(r["random_q"] * r["ambiguous"] for r in rows) / max(1, sum(r["ambiguous"] for r in rows))
    ares_all = sum(r["active_resolved"] * r["ambiguous"] for r in rows) / max(1, sum(r["ambiguous"] for r in rows))
    rres_all = sum(r["random_resolved"] * r["ambiguous"] for r in rows) / max(1, sum(r["ambiguous"] for r in rows))
    print(f"\n  ACTIVE: {ares_all:.1%} of irreducible ambiguities resolved in {ta:.2f} questions")
    print(f"  RANDOM: {rres_all:.1%} resolved in {tr:.2f} questions   -> active is {tr/max(1e-9,ta):.2f}x fewer")
    print(f"  WRONG referent commitments: {tw}")
    print(f"\n=== VERDICT ===")
    if tw == 0 and ares_all > 0.5:
        print(f"  LOOP CLOSED: perceive -> learn meaning without knowing reference -> DETECT that the")
        print(f"  remaining ambiguity is irreducible -> ASK the question that splits it -> commit. The engine")
        print(f"  never guesses a referent; it converts an abstention into an answer by acquiring information.")
    else:
        print(f"  Not closed: resolved {ares_all:.1%}, wrong {tw} -- report, do not tune.")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase5c_clarifying_questions"] = {
        "rows": rows, "active_resolved": round(ares_all, 4), "active_questions": round(ta, 3),
        "random_resolved": round(rres_all, 4), "random_questions": round(tr, 3),
        "active_advantage": round(tr / max(1e-9, ta), 3), "wrong_referent_commitments": tw,
        "verdict": "LOOP CLOSED" if (tw == 0 and ares_all > 0.5) else "not closed",
        "note": "questions are generic (slot x predicate [x object]); asking 'is it pair (i,j)?' is forbidden "
                "as that would be guessing dressed as a query.",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
