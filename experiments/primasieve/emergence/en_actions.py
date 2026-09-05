"""ACTIONS -- why "remove blue" failed, and the fix.

The engine refused every verb, and the reason was not stubbornness. Its hypothesis space was 19 VISUAL
PROPERTIES. Learning by elimination needs candidate meanings for a word to survive as; there was no candidate
operation, because the world had no operations. "remove" could not mean anything, so it could not be learned.
WordNet knows the word perfectly well -- ACQUIRE stayed silent only because it bridges to words already in the
lexicon, and there is no path from a verb to a colour.

So the fix is not a bigger dictionary. It is giving the world a space of ACTIONS, at which point action words
have something to denote and the SAME elimination mechanism learns them, one level up:

    a property word is learned from   (word, object)          -- eliminate properties the object lacks
    an action word is learned from    (word, before, after)   -- eliminate operations that do not reproduce it

Verification stays exact: apply the candidate operation to the before-scene and compare to the after-scene.
An operation that does not reproduce the observed change is rejected, same as always. Commit on a unique
survivor, else abstain.
"""
import os, sys, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import en_world as W


def _clamp(v, lo, hi): return max(lo, min(hi, v))


def a_remove(sc, i):
    return [o for k, o in enumerate(sc) if k != i]


def a_grow(sc, i):
    out = list(sc)
    (x0, y0, x1, y1), c = out[i]
    out[i] = ((x0, y0, _clamp(x1 + 1, x0 + 1, W.G), _clamp(y1 + 1, y0 + 1, W.G)), c)
    return out


def a_shrink(sc, i):
    out = list(sc)
    (x0, y0, x1, y1), c = out[i]
    out[i] = ((x0, y0, max(x0 + 1, x1 - 1), max(y0 + 1, y1 - 1)), c)
    return out


def a_recolour(sc, i):
    out = list(sc)
    (r, c) = out[i]
    out[i] = (r, (c + 1) % len(W.COLOURS))
    return out


def a_widen(sc, i):
    out = list(sc); (x0, y0, x1, y1), c = out[i]
    out[i] = ((x0, y0, _clamp(x1 + 1, x0 + 1, W.G), y1), c); return out


def a_heighten(sc, i):
    out = list(sc); (x0, y0, x1, y1), c = out[i]
    out[i] = ((x0, y0, x1, _clamp(y1 + 1, y0 + 1, W.G)), c); return out


OPS = {"OP_REMOVE": a_remove, "OP_GROW": a_grow, "OP_SHRINK": a_shrink, "OP_RECOLOUR": a_recolour,
       "OP_WIDEN": a_widen, "OP_HEIGHTEN": a_heighten}

# English words the world actually uses when it narrates an action. The engine is NOT told which is which.
ACTION_WORDS = ["remove", "delete", "grow", "enlarge", "shrink", "recolour", "widen", "heighten"]
TRUE_MAP = {"remove": "OP_REMOVE", "delete": "OP_REMOVE", "grow": "OP_GROW",
            "enlarge": "OP_GROW", "shrink": "OP_SHRINK", "recolour": "OP_RECOLOUR",
            "widen": "OP_WIDEN", "heighten": "OP_HEIGHTEN"}


def training(n, rng, true_map=None):
    """(word, before, target_index, after) -- the learner sees the transition, never the mapping."""
    tm = true_map or TRUE_MAP
    out = []
    while len(out) < n:
        sc = W.rand_scene(rng, 4)
        if sc is None: continue
        w = rng.choice(list(tm))
        i = rng.randrange(len(sc))
        after = OPS[tm[w]](sc, i)
        out.append((w, sc, i, after))
    return out


def learn_actions(corpus):
    """an action word means the operation that reproduces EVERY transition it was used for."""
    obs = {}
    for w, before, i, after in corpus:
        obs.setdefault(w, []).append((before, i, after))
    lex, surv = {}, {}
    for w, trs in obs.items():
        s = {op for op, fn in OPS.items()
             if all(fn(b, i) == a for b, i, a in trs)}
        surv[w] = s
        if len(s) == 1: lex[w] = next(iter(s))
    return lex, surv


if __name__ == "__main__":
    rng = random.Random(4)
    lex, surv = learn_actions(training(400, rng))
    ok = sum(1 for w, op in TRUE_MAP.items() if lex.get(w) == op)
    wrong = sum(1 for w, op in TRUE_MAP.items() if w in lex and lex[w] != op)
    print("learning ACTION words by elimination over (before -> after) transitions\n")
    for w in ACTION_WORDS:
        print(f"  {w:9s} survivors {sorted(surv.get(w, []))!s:38s} -> {lex.get(w)}")
    print(f"\n  recovered {ok}/{len(TRUE_MAP)}   wrong {wrong}")
    # honesty check: scramble the truth -- spelling must carry no information
    sm = dict(zip(TRUE_MAP, list(TRUE_MAP.values())[::-1]))
    lex2, _ = learn_actions(training(400, random.Random(4), true_map=sm))
    ok2 = sum(1 for w, op in sm.items() if lex2.get(w) == op)
    print(f"  SCRAMBLED truth: recovered {ok2}/{len(sm)}  e.g. remove->{lex2.get('remove')} "
          f"(truth {sm['remove']})  => learned from transitions, not spelling")
