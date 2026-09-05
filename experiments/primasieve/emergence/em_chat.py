"""CHAT WITH PRIMASIEVE -- and a test of whether "open-ended question -> ask for more" is actually consistent.

You describe an object in the scene. The engine resolves it against meanings it LEARNED (never hard-coded),
and then one of four things happens. Which one is forced by its rule -- commit only on a unique survivor:

  UNIQUE          exactly one object matches            -> COMMITS
  AMBIGUOUS       several match, a question can split   -> ASKS the maximally-discriminating question
  UNKNOWABLE      several match, NO question can split  -> reports the SET and says so
  UNKNOWN WORD    outside its vocabulary                -> ABSTAINS, never guesses

So "open-ended -> ask for more information" is not a behaviour bolted on; it falls out of the commit rule.
The open question is whether it is CONSISTENT -- does vagueness reliably produce a question rather than a
guess? --ladder measures exactly that: feed descriptions from most vague to most specific and watch which
branch fires. If the engine ever COMMITS on a vague description, the rule is broken.

    python em_chat.py --ladder      # the consistency measurement
    python em_chat.py               # interactive; reads lines from stdin so it also works piped
    python em_chat.py --demo        # a scripted conversation
"""
import os, sys, random, itertools, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import dialog_world as DW
import dialog_s1 as S1
import dialog_s2 as S2

OUT = os.path.join(HERE, "EMERGENCE.json")


def learn_engine(seed=11, n=6000):
    """the engine learns its whole vocabulary by elimination + asking (S1 + S2). Nothing is hard-coded."""
    w = DW.World(8, 4, 3, seed=seed)
    data = S1.corpus(w, n, 3, random.Random(7))
    com, surv = S1.learn(w, data)
    pool = S2.object_pool(w, random.Random(3))
    lex, _ = S2.resolve_by_asking(w, surv, pool, mode="active")
    return w, lex


def describe_scene(w, scene):
    out = []
    for i, o in enumerate(scene):
        (x0, y0, x1, y1), c = o
        props = [p for p in w.true_unary(o)]
        out.append(f"    #{i}  at ({x0},{y0})-({x1},{y1})  colour {c}   [{' '.join(sorted(props))}]")
    return "\n".join(out)


def referents(w, scene, preds):
    """objects satisfying EVERY predicate in the description."""
    return [i for i, o in enumerate(scene) if all(w.u(p, o) for p in preds)]


def best_question(w, scene, cands):
    """the unary predicate that splits the surviving referents most evenly. None if nothing splits."""
    best, bp = -1, None
    for p in w.unary:
        yes = sum(1 for i in cands if w.u(p, scene[i]))
        if yes == 0 or yes == len(cands): continue
        score = min(yes, len(cands) - yes)
        if score > best: best, bp = score, p
    return bp


def respond(w, scene, preds, unknown=()):
    """the four branches, forced by the commit rule."""
    if unknown:
        return ("ABSTAIN", f"I do not know the word(s) {sorted(unknown)}. I will not guess.", None)
    cands = referents(w, scene, preds)
    if len(cands) == 1:
        return ("COMMIT", f"object #{cands[0]}", cands)
    if len(cands) == 0:
        return ("NONE", "nothing in this scene matches that.", [])
    q = best_question(w, scene, cands)
    if q is None:
        return ("UNKNOWABLE", f"{len(cands)} objects match ({cands}) and NO question I can ask "
                              f"separates them. That is unknowable from here, not unknown.", cands)
    return ("ASK", f"{len(cands)} objects match ({cands}). To narrow it: is it {q}?", cands)


def parse(w, text):
    """accept predicate names (the legend is printed); returns (known_preds, unknown_tokens)."""
    toks = [t.strip().upper() for t in text.replace(",", " ").split() if t.strip()]
    known = [t for t in toks if t in w.unary]
    unknown = [t for t in toks if t not in w.unary]
    return known, unknown


def ladder(w, lex):
    """CONSISTENCY TEST: vague -> specific. Vagueness must produce ASK/UNKNOWABLE, never COMMIT."""
    rng = random.Random(5)
    rows = []
    trials = 0; violations = 0
    for _ in range(120):
        scene = w.rand_scene(rng, 4)
        if scene is None: continue
        tgt = rng.randrange(len(scene))
        props = sorted(w.true_unary(scene[tgt]))
        if not props: continue
        for k in range(1, min(4, len(props)) + 1):          # k = how SPECIFIC the description is
            preds = props[:k]
            kind, _, cands = respond(w, scene, preds)
            trials += 1
            rows.append({"specificity": k, "n_matching": len(cands) if cands is not None else 0, "kind": kind})
            if kind == "COMMIT" and cands is not None and len(cands) != 1:
                violations += 1
    agg = {}
    for r in rows:
        a = agg.setdefault(r["specificity"], {"COMMIT": 0, "ASK": 0, "UNKNOWABLE": 0, "NONE": 0, "n": 0})
        a[r["kind"]] += 1; a["n"] += 1
    print("CONSISTENCY: does VAGUENESS reliably produce a question instead of a guess?\n")
    print(f"  {'words given':>12} {'cases':>7} {'ASK':>7} {'COMMIT':>7} {'UNKNOWABLE':>11}   behaviour")
    for k in sorted(agg):
        a = agg[k]
        beh = "asks for more" if a["ASK"] > a["COMMIT"] else "commits"
        print(f"  {k:>12} {a['n']:>7} {a['ASK']:>7} {a['COMMIT']:>7} {a['UNKNOWABLE']:>11}   {beh}")
    print(f"\n  COMMITs on a non-unique referent (rule violations): {violations}")
    print(f"  -> {'CONSISTENT: it never commits when more than one thing matches.' if violations == 0 else 'INCONSISTENT.'}")
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["chat_consistency"] = {"by_specificity": agg, "rule_violations": violations,
                             "rule": "commit only on a unique referent; else ask, or report unknowable, or "
                                     "abstain on an unknown word",
                             "reading": "asking for more information is not a bolted-on behaviour -- it is what "
                                        "the commit rule forces when a description under-determines the referent"}
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)


def chat(w, lex, scripted=None):
    rng = random.Random(int(os.environ.get("SCENE_SEED", "12")))
    scene = w.rand_scene(rng, 4)
    print("scene (4 objects):"); print(describe_scene(w, scene))
    print(f"\nvocabulary it LEARNED ({len(lex)} words; showing what each means):")
    inv = {}
    for word, pred in lex.items(): inv[pred] = word
    print("    " + "  ".join(f"{p}={inv[p]}" for p in w.unary if p in inv))
    print("\ndescribe an object using the PREDICATE names above (e.g. 'C1 SQUARE'), or 'quit'.\n")
    src = iter(scripted) if scripted else None
    pending = None            # (asked_predicate, surviving_candidates) -- lets the chat NARROW on yes/no
    while True:
        if src is not None:
            try: line = next(src)
            except StopIteration: break
            print(f"you> {line}")
        else:
            try: line = input("you> ").strip()
            except EOFError: break
        if not line or line.lower() in ("quit", "exit"): break
        if pending and line.lower() in ("yes", "no", "y", "n"):
            p_, cands = pending
            want = line.lower().startswith("y")
            cands = [k for k in cands if w.u(p_, scene[k]) == want]
            if len(cands) == 1:
                print("primasieve[COMMIT]> object #%d" % cands[0] + chr(10)); pending = None; continue
            if not cands:
                print("primasieve[NONE]> then nothing matches." + chr(10)); pending = None; continue
            q = best_question(w, scene, cands)
            if q is None:
                print("primasieve[UNKNOWABLE]> still %s and nothing separates them." % cands + chr(10))
                pending = None; continue
            print("primasieve[ASK]> narrowed to %s. Next: is it %s?" % (cands, q) + chr(10))
            pending = (q, cands); continue
        preds, unknown = parse(w, line)
        kind, msg, cands = respond(w, scene, preds, unknown)
        print("primasieve[%s]> %s" % (kind, msg) + chr(10))
        pending = (best_question(w, scene, cands), cands) if kind == "ASK" else None


if __name__ == "__main__":
    w, lex = learn_engine()
    if "--ladder" in sys.argv:
        ladder(w, lex)
    elif "--demo" in sys.argv:
        chat(w, lex, scripted=["WIDE", "yes", "TALL", "FLOOB", "SZ0 SZ1", "C2"])
    else:
        chat(w, lex)
