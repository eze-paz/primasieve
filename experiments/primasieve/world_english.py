"""PHASE 5 world -- a SEALED deterministic describer over the rect world, with an exact truth-condition checker.

Sealed exactly like the p1-p9 rasterizer: the word->predicate map is a HIDDEN seeded permutation over NONSENSE
words, so nothing about meaning can leak from English spelling. Syntax (the utterance schema) is SUPPLIED --
the plan's claim is meaning through a verifier, not syntax induction. SEMANTICS is what must be learned.

  scene     = two non-overlapping rects with distinct colors: [((x0,y0,x1,y1), color), ...]
  predicates: unary  C1 C2 C3 (colour) / SQUARE WIDE TALL (shape)   -- exactly one colour and one shape hold
              binary LEFT_OF RIGHT_OF ABOVE BELOW                    -- at least one holds (non-overlapping)
  utterance = [cw(A), sw(A), rw(A,B), cw(B), sw(B)]  (5 nonsense words; slots 0,1,3,4 unary, slot 2 binary)
  checker(utterance, scene) -> exact truth value via the hidden map. This is the sound oracle.
"""
import random

UNARY = ("C1", "C2", "C3", "SQUARE", "WIDE", "TALL")
BINARY = ("LEFT_OF", "RIGHT_OF", "ABOVE", "BELOW")
NONSENSE = ["vorp", "quim", "blen", "traz", "gloop", "snik", "drovel", "yark", "plim", "zumo",
            "frell", "kib", "morth", "wexal", "tunk"]


def unary_holds(p, layer):
    (x0, y0, x1, y1), c = layer
    w, h = x1 - x0, y1 - y0
    if p == "C1": return c == 1
    if p == "C2": return c == 2
    if p == "C3": return c == 3
    if p == "SQUARE": return w == h
    if p == "WIDE": return w > h
    if p == "TALL": return h > w
    raise KeyError(p)


def binary_holds(p, a, b):
    (ax0, ay0, ax1, ay1), _ = a
    (bx0, by0, bx1, by1), _ = b
    if p == "LEFT_OF": return ax1 <= bx0
    if p == "RIGHT_OF": return ax0 >= bx1
    if p == "ABOVE": return ay1 <= by0
    if p == "BELOW": return ay0 >= by1
    raise KeyError(p)


class Lexicon:
    """the HIDDEN sealed word<->predicate map (a seeded permutation over nonsense words)."""
    def __init__(self, seed=11, shuffle_meanings=False):
        rng = random.Random(seed)
        words = list(NONSENSE); rng.shuffle(words)
        preds = list(UNARY) + list(BINARY)
        if shuffle_meanings:                      # KNOCKOUT: destroy the word<->meaning correspondence
            rng2 = random.Random(seed + 999); preds = list(preds); rng2.shuffle(preds)
        self.w2p = {}
        self.p2w = {}
        for p, w in zip(preds, words):
            self.w2p[w] = p; self.p2w[p] = w
        self.arity = {w: (2 if self.w2p[w] in BINARY else 1) for w in self.w2p}

    def describe(self, scene):
        """scene -> the (unique, canonical) TRUE utterance. Deterministic."""
        a, b = scene[0], scene[1]
        ca = next(p for p in ("C1", "C2", "C3") if unary_holds(p, a))
        sa = next(p for p in ("SQUARE", "WIDE", "TALL") if unary_holds(p, a))
        cb = next(p for p in ("C1", "C2", "C3") if unary_holds(p, b))
        sb = next(p for p in ("SQUARE", "WIDE", "TALL") if unary_holds(p, b))
        rel = next((p for p in BINARY if binary_holds(p, a, b)), None)
        if rel is None: return None
        return [self.p2w[ca], self.p2w[sa], self.p2w[rel], self.p2w[cb], self.p2w[sb]]

    def checker(self, utt, scene):
        """utterance |= scene ?  EXACT truth condition via the hidden map (the sound oracle)."""
        if len(utt) != 5: return False
        a, b = scene[0], scene[1]
        try:
            return (unary_holds(self.w2p[utt[0]], a) and unary_holds(self.w2p[utt[1]], a)
                    and binary_holds(self.w2p[utt[2]], a, b)
                    and unary_holds(self.w2p[utt[3]], b) and unary_holds(self.w2p[utt[4]], b))
        except KeyError:
            return None                            # unknown word -> undefined, must ABSTAIN


def rand_scene(rng, G=6):
    """two NON-OVERLAPPING rects with DISTINCT colours (so every predicate is well defined)."""
    for _ in range(400):
        def r():
            x0 = rng.randrange(0, G - 1); x1 = rng.randrange(x0 + 1, min(G, x0 + 4) + 1)
            y0 = rng.randrange(0, G - 1); y1 = rng.randrange(y0 + 1, min(G, y0 + 4) + 1)
            return (x0, y0, x1, y1)
        ra, rb = r(), r()
        ax0, ay0, ax1, ay1 = ra; bx0, by0, bx1, by1 = rb
        if ax1 > bx0 and bx1 > ax0 and ay1 > by0 and by1 > ay0: continue   # overlap -> reject
        ca = rng.choice((1, 2, 3)); cb = rng.choice([c for c in (1, 2, 3) if c != ca])
        sc = [(ra, ca), (rb, cb)]
        if any(binary_holds(p, sc[0], sc[1]) for p in BINARY): return sc
    return None


def render(scene, G=6):
    """exact pixel grid (the sealed renderer; non-overlapping so painter order is irrelevant)."""
    g = [0] * (G * G)
    for (x0, y0, x1, y1), c in scene:
        for py in range(y0, y1):
            for px in range(x0, x1):
                g[py * G + px] = c
    return g
