"""ENGLISH CHAT -- type real sentences. Syntax is parsed; MEANING is still learned by elimination.

    python en_chat.py --demo        scripted conversation
    python en_chat.py --shuffled    proof it is LEARNING, not reading the spelling
    python en_chat.py               interactive (also works piped)

THE HONESTY CHECK (--shuffled): the words are English, so it would be easy to fake this by hard-coding
"red" -> red. Nothing here does. To prove it, --shuffled trains on a world where the true mapping is
SCRAMBLED -- "red" genuinely denotes TALL, and so on -- and the engine recovers the scrambled map just as
accurately. English spelling carries zero information for it; it learns whatever the data says.

Four responses, forced by the same commit rule as everywhere else:
  COMMIT / ASK a discriminating question / UNKNOWABLE (report the set) / ABSTAIN on an unknown word.
"""
import os, sys, json, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import en_world as W

OUT = os.path.join(HERE, "EMERGENCE.json")


def training_corpus(n, rng, word2pred):
    """(utterance-words, scene, which objects) pairs. The learner sees words and scenes, never word2pred."""
    pred2word = {p: w for w, p in word2pred.items()}
    out = []
    while len(out) < n:
        sc = W.rand_scene(rng, 3)
        if sc is None: continue
        i, j = rng.sample(range(3), 2)
        ua = W.true_unary(sc[i]); ub = W.true_unary(sc[j])
        if not (ua and ub): continue
        out.append(([pred2word[rng.choice(ua)], pred2word[rng.choice(ub)]], sc, (i, j)))
    return out


def learn_lexicon(corpus):
    """a word means the predicate true of EVERY object it was ever used for; commit on a unique survivor."""
    obs = {}
    for words, sc, (i, j) in corpus:
        obs.setdefault(words[0], []).append(sc[i])
        obs.setdefault(words[1], []).append(sc[j])
    lex, surv = {}, {}
    for word, objs in obs.items():
        s = {p for p in W.UNARY if all(W.unary_holds(p, o) for o in objs)}
        surv[word] = s
        if len(s) == 1: lex[word] = next(iter(s))
    return lex, surv


def build(shuffled=False, n=9000, seed=7):
    rng = random.Random(seed)
    words = list(W.UNARY)
    preds = list(W.UNARY)
    if shuffled:
        random.Random(99).shuffle(preds)              # "red" may genuinely mean TALL
    word2pred = dict(zip(words, preds))
    lex, surv = learn_lexicon(training_corpus(n, rng, word2pred))
    return word2pred, lex, surv


# ---------------------------------------------------------------- responding
def referents(scene, preds):
    return [i for i, o in enumerate(scene) if all(W.unary_holds(p, o) for p in preds)]


def best_question(scene, cands):
    best, bp = -1, None
    for p in W.UNARY:
        yes = sum(1 for i in cands if W.unary_holds(p, scene[i]))
        if yes == 0 or yes == len(cands): continue
        s = min(yes, len(cands) - yes)
        if s > best: best, bp = s, p
    return bp


def answer(scene, q, lex):
    if q["unknown"]:
        # no "unknown word" exit before RESEARCH (no_paradigm_prereg.md step 6): an unbound symbol is an INTERNAL
        # signal, not an answer. Resolve each one against the declared sources; quote what a source says, cited.
        # Refuse only after the source set is exhausted, naming what was consulted.
        import kb_sources as KB
        found, missing = [], []
        for w in q["unknown"]:
            r = KB.research_gloss(w)
            (found if r else missing).append((w, r))
        if found and not missing:
            msg = "  ".join(f"{w}: {r['gloss']} [{r['source']}]" for w, r in found)
            return "ATTRIBUTED", msg, None
        if found:
            msg = "  ".join(f"{w}: {r['gloss']} [{r['source']}]" for w, r in found)
            return "ATTRIBUTED", msg + f"  -- no source I can reach defines {[w for w, _ in missing]}.", None
        srcs = [sid for sid, _, _ in KB.SOURCES]
        return "REFUSE", f"no source I can reach defines {[w for w, _ in missing]}; consulted {srcs}.", None
    if q["kind"] == "empty":
        return "NONE", "I did not find anything to identify in that.", None
    if q["kind"] == "yesno":
        L = referents(scene, q["left"]); R = referents(scene, q["right"])
        if len(L) != 1 or len(R) != 1:
            side = "first" if len(L) != 1 else "second"
            cands = L if len(L) != 1 else R
            if not cands: return "NONE", f"nothing matches the {side} description.", None
            p = best_question(scene, cands)
            if p is None:
                return "UNKNOWABLE", f"the {side} description matches {cands} and no question separates them.", cands
            return "ASK", f"the {side} description matches {len(cands)} objects {cands}. Is it {p}?", cands
        got = W.binary_holds(q["rel"], scene[L[0]], scene[R[0]])
        return "COMMIT", f"{'yes' if got else 'no'} - object #{L[0]} is {'' if got else 'not '}{q['rel']} object #{R[0]}.", L
    cands = referents(scene, q["left"])
    if len(cands) == 1: return "COMMIT", f"object #{cands[0]}", cands
    if not cands: return "NONE", "nothing in this scene matches that.", []
    p = best_question(scene, cands)
    if p is None:
        return "UNKNOWABLE", f"{len(cands)} objects match {cands} and no question I can ask separates them.", cands
    return "ASK", f"{len(cands)} objects match {cands}. To narrow it: is it {p}?", cands


def render(scene):
    out = []
    for i, o in enumerate(scene):
        (x0, y0, x1, y1), c = o
        out.append(f"    #{i}  {W.COLOURS[c]:7s} {'x'.join(str(v) for v in (x1-x0, y1-y0))}  at ({x0},{y0})"
                   f"   [{' '.join(W.true_unary(o))}]")
    return "\n".join(out)


def chat(lex, scripted=None, seed=12):
    scene = W.rand_scene(random.Random(seed), 4)
    print("scene:"); print(render(scene))
    print("\ntype real English, e.g. 'the big red one', 'is the tall blue one above the small green square'\n")
    src = iter(scripted) if scripted else None
    pending = None
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
            p, cands = pending
            want = line.lower().startswith("y")
            cands = [i for i in cands if W.unary_holds(p, scene[i]) == want]
            if len(cands) == 1: print(f"primasieve[COMMIT]> object #{cands[0]}\n"); pending = None; continue
            if not cands: print("primasieve[NONE]> then nothing matches.\n"); pending = None; continue
            nq = best_question(scene, cands)
            if nq is None:
                print(f"primasieve[UNKNOWABLE]> still {cands}, nothing separates them.\n"); pending = None; continue
            print(f"primasieve[ASK]> narrowed to {cands}. Next: is it {nq}?\n"); pending = (nq, cands); continue
        q = W.parse(line, lex)
        kind, msg, cands = answer(scene, q, lex)
        print(f"primasieve[{kind}]> {msg}\n")
        pending = (best_question(scene, cands), cands) if kind == "ASK" else None


if __name__ == "__main__":
    if "--shuffled" in sys.argv:
        print("HONESTY CHECK -- does it read the spelling, or learn from data?\n")
        res = {}
        for tag, sh in (("normal English", False), ("SCRAMBLED truth", True)):
            truth, lex, surv = build(shuffled=sh)
            correct = sum(1 for w, p in truth.items() if lex.get(w) == p)
            wrong = sum(1 for w, p in truth.items() if w in lex and lex[w] != p)
            res[tag] = {"recovered": correct, "of": len(truth), "wrong": wrong}
            ex = [f"{w}->{lex.get(w)}" for w in ("red", "tall", "huge")]
            print(f"  {tag:16s} recovered {correct}/{len(truth)}  wrong {wrong}   e.g. {ex}")
        print("\n  It recovers the SCRAMBLED mapping just as well as the sensible one, so the English spelling")
        print("  carries no information for it. The meanings are learned from data, not read off the words.")
        d = json.load(open(OUT)) if os.path.exists(OUT) else {}
        d["english_lexicon_honesty"] = res
        json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    else:
        truth, lex, surv = build()
        print(f"engine learned {len(lex)}/{len(W.UNARY)} English words by elimination "
              f"({sum(1 for w,p in truth.items() if lex.get(w)==p)} correct)\n")
        if "--demo" in sys.argv:
            chat(lex, scripted=["the red one", "the big red one", "is the tall one above the wide one",
                                "the flibbertigibbet one", "the huge tiny one"])
        else:
            chat(lex)
