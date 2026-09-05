"""DIALOGUE SUITE -- a SCALABLE sealed world (the Phase-5 rect world, grown to hundreds of concepts).

Phase 5 used 10 concepts. To ask whether learning-by-elimination survives scale, the world must be able to
generate an arbitrary number of predicates while staying EXACTLY checkable. Predicate families here:

  colour      C0..C{n}          exactly one holds per object
  shape       SQUARE WIDE TALL  exactly one holds
  size        SZ0..SZ{n}        area bands, exactly one holds
  position    horizontal x vertical zones (LEFTMOST..., TOP...), exactly one of each holds
  binary      spatial (left/right/above/below/near/far) + comparative (bigger/smaller/taller/wider/
              same-colour/different-colour)

Everything is a deterministic function of the scene, so the truth-condition checker stays exact -- the whole
method depends on that and it must not be weakened as the world grows.

Words are NONSENSE strings generated deterministically, mapped to predicates by a hidden seeded permutation,
so nothing can leak from spelling.
"""
import random

G = 12                                   # field size


def build_predicates(n_colour=8, n_size=4, n_zone=3):
    """returns (unary_names, binary_names, unary_fn, binary_fn) for a world of the requested granularity."""
    colours = [f"C{i}" for i in range(n_colour)]
    shapes = ["SQUARE", "WIDE", "TALL"]
    sizes = [f"SZ{i}" for i in range(n_size)]
    hzones = [f"H{i}" for i in range(n_zone)]
    vzones = [f"V{i}" for i in range(n_zone)]
    unary = colours + shapes + sizes + hzones + vzones
    binary = ["LEFT_OF", "RIGHT_OF", "ABOVE", "BELOW", "NEAR", "FAR",
              "BIGGER", "SMALLER", "TALLER", "WIDER", "SAME_COLOUR", "DIFF_COLOUR"]

    max_area = 4 * 4

    def u(p, layer):
        (x0, y0, x1, y1), c = layer
        w, h = x1 - x0, y1 - y0
        if p.startswith("C") and p[1:].isdigit(): return c == int(p[1:])
        if p == "SQUARE": return w == h
        if p == "WIDE": return w > h
        if p == "TALL": return h > w
        if p.startswith("SZ"):
            i = int(p[2:])
            band = min(n_size - 1, (w * h - 1) * n_size // max_area)
            return band == i
        if p.startswith("H"):
            i = int(p[1:])
            return min(n_zone - 1, ((x0 + x1) // 2) * n_zone // G) == i
        if p.startswith("V"):
            i = int(p[1:])
            return min(n_zone - 1, ((y0 + y1) // 2) * n_zone // G) == i
        raise KeyError(p)

    def b(p, A, B):
        (ax0, ay0, ax1, ay1), ac = A
        (bx0, by0, bx1, by1), bc = B
        aw, ah = ax1 - ax0, ay1 - ay0
        bw, bh = bx1 - bx0, by1 - by0
        acx, acy = (ax0 + ax1) / 2, (ay0 + ay1) / 2
        bcx, bcy = (bx0 + bx1) / 2, (by0 + by1) / 2
        d = abs(acx - bcx) + abs(acy - bcy)
        if p == "LEFT_OF": return ax1 <= bx0
        if p == "RIGHT_OF": return ax0 >= bx1
        if p == "ABOVE": return ay1 <= by0
        if p == "BELOW": return ay0 >= by1
        if p == "NEAR": return d <= 4
        if p == "FAR": return d > 8
        if p == "BIGGER": return aw * ah > bw * bh
        if p == "SMALLER": return aw * ah < bw * bh
        if p == "TALLER": return ah > bh
        if p == "WIDER": return aw > bw
        if p == "SAME_COLOUR": return ac == bc
        if p == "DIFF_COLOUR": return ac != bc
        raise KeyError(p)

    return unary, binary, u, b


def make_words(n, seed=0):
    rng = random.Random(seed)
    cons = "bdfgklmnprstvzq"; vow = "aeiou"
    out = set()
    while len(out) < n:
        w = "".join(rng.choice(cons) + rng.choice(vow) for _ in range(2)) + rng.choice(cons)
        out.add(w)
    return sorted(out)


class World:
    def __init__(self, n_colour=8, n_size=4, n_zone=3, seed=11, shuffle=False):
        self.unary, self.binary, self.u, self.b = build_predicates(n_colour, n_size, n_zone)
        self.n_colour = n_colour
        preds = list(self.unary) + list(self.binary)
        words = make_words(len(preds), seed=seed)
        rng = random.Random(seed)
        wl = list(words); rng.shuffle(wl)
        if shuffle:
            rng2 = random.Random(seed + 999); preds = list(preds); rng2.shuffle(preds)
        self.w2p = dict(zip(wl, preds))
        self.p2w = {p: w for w, p in self.w2p.items()}
        self.arity = {w: (2 if self.w2p[w] in self.binary else 1) for w in self.w2p}

    # ---- scene generation ----
    def rand_scene(self, rng, n_obj, tries=400):
        for _ in range(tries):
            objs = []
            ok = True
            for _ in range(n_obj):
                placed = False
                for _ in range(200):
                    x0 = rng.randrange(0, G - 1); x1 = rng.randrange(x0 + 1, min(G, x0 + 4) + 1)
                    y0 = rng.randrange(0, G - 1); y1 = rng.randrange(y0 + 1, min(G, y0 + 4) + 1)
                    r = (x0, y0, x1, y1)
                    if all(not (r[2] > o[0][0] and o[0][2] > r[0] and r[3] > o[0][1] and o[0][3] > r[1])
                           for o in objs):
                        objs.append((r, rng.randrange(self.n_colour))); placed = True; break
                if not placed: ok = False; break
            if ok and len(objs) == n_obj: return objs
        return None

    def true_unary(self, layer):
        return [p for p in self.unary if self.u(p, layer)]

    def true_binary(self, A, B):
        return [p for p in self.binary if self.b(p, A, B)]
