"""PHASE 3 -- TWO SEALED WORLDS WITH DESCRIBERS (nolf_prereg.md). Imported by the gate runner, NEVER by the learner.

Neither world is the rect world and neither shares content with the other: A is relational records with integer
fields, B is strings over a small alphabet. Each has an exact truth-checker for its own predicates and a sealed
DESCRIBER whose vocabulary is a seeded permutation over nonsense forms, so no meaning leaks through spelling and
the shuffled-lexicon knockout is one seed away. The describer's grammar is the ORACLE's business: it is not the
learner's target and is never exposed. What the learner sees is (situation, sentence tokens, truth value).

Both worlds expose the same interface, so the learner and the gates are written once:
    sample(rng)              -> situation
    describe(rng, situation) -> (tokens, truth, construction_id, content_words)
    splits(seed, n)          -> dict(train, heldout_iid, heldout_compositional) of (situation, tokens, truth)
`heldout_compositional` holds every sentence whose (content word, construction) pair never occurs in train --
the compositional-generalization split the prereg's G2 is scored on."""
import random

FORMS = ["vorp", "quim", "blen", "traz", "gloop", "snik", "drovel", "yark", "plim", "zumo", "frell", "kib",
         "morth", "wexal", "tunk", "jarn", "oskel", "prith", "dulm", "casp", "ribbet", "sarn", "tovel", "ulk"]


class _Lex:
    """hidden concept -> nonsense form (a seeded permutation); `shuffle` re-permutes for the knockout."""
    def __init__(self, concepts, seed):
        forms = list(FORMS); random.Random(seed).shuffle(forms)
        self.c2f = dict(zip(concepts, forms)); self.f2c = {f: c for c, f in self.c2f.items()}
    def __getitem__(self, c): return self.c2f[c]


# ============================================================ WORLD A: records with integer fields
class Records:
    """situation = 3..4 records, each (f0, f1, f2) in 0..9. Predicates: field of the k-th record vs a numeral
    (above / below / equals), field-vs-field of the same record, NOT, AND, and EVERY/SOME over records."""
    name = "records"
    FIELDS = ("f0", "f1", "f2"); ORD = ("first", "second", "third", "fourth")
    REL = ("above", "below", "equals")

    def __init__(self, seed=11):
        self.lex_seed = seed
        concepts = list(self.FIELDS) + list(self.ORD) + list(self.REL) + ["not", "and", "every", "some"] + [f"n{i}" for i in range(10)]
        self.lex = _Lex(concepts, seed)

    def sample(self, rng):
        return tuple(tuple(rng.randrange(10) for _ in self.FIELDS) for _ in range(rng.randint(3, 4)))

    @staticmethod
    def _rel(rel, x, y):
        return x > y if rel == "above" else x < y if rel == "below" else x == y

    def _atom(self, rng, sit):
        """-> (tokens, truth, construction, content) for one atomic claim about one record."""
        k = rng.randrange(len(sit)); f = rng.randrange(3); rel = rng.choice(self.REL)
        if rng.random() < 0.6:                                    # field vs numeral
            n = rng.randrange(10)
            toks = [self.lex[self.ORD[k]], self.lex[self.FIELDS[f]], self.lex[rel], self.lex[f"n{n}"]]
            return toks, self._rel(rel, sit[k][f], n), "num:" + rel, {self.FIELDS[f], f"n{n}"}
        g = (f + rng.randint(1, 2)) % 3                            # field vs field
        toks = [self.lex[self.ORD[k]], self.lex[self.FIELDS[f]], self.lex[rel], self.lex[self.FIELDS[g]]]
        return toks, self._rel(rel, sit[k][f], sit[k][g]), "ff:" + rel, {self.FIELDS[f], self.FIELDS[g]}

    def describe(self, rng, sit):
        r = rng.random()
        if r < 0.45:
            return self._atom(rng, sit)
        if r < 0.65:                                               # negation
            toks, tv, c, cw = self._atom(rng, sit)
            return [self.lex["not"]] + toks, (not tv), "not+" + c, cw
        if r < 0.85:                                               # conjunction
            t1, v1, c1, w1 = self._atom(rng, sit); t2, v2, c2, w2 = self._atom(rng, sit)
            return t1 + [self.lex["and"]] + t2, (v1 and v2), "and", w1 | w2
        q = rng.choice(["every", "some"]); f = rng.randrange(3); rel = rng.choice(self.REL); n = rng.randrange(10)
        vals = [self._rel(rel, rec[f], n) for rec in sit]
        tv = all(vals) if q == "every" else any(vals)
        toks = [self.lex[q], self.lex[self.FIELDS[f]], self.lex[rel], self.lex[f"n{n}"]]
        return toks, tv, "quant:" + q, {self.FIELDS[f], f"n{n}"}


# ============================================================ WORLD B: strings over a small alphabet
class Strings:
    """situation = a string of 4..8 symbols over {p,q,r,s}. Predicates: contains x, starts-with x, ends-with x,
    x before y (some x precedes some y), count of x equals n, NOT, AND, every x followed-by y."""
    name = "strings"
    ALPHA = ("p", "q", "r", "s")

    def __init__(self, seed=23):
        self.lex_seed = seed
        concepts = list(self.ALPHA) + ["contains", "starts", "ends", "before", "count", "not", "and", "every", "followed"] + [f"n{i}" for i in range(9)]
        self.lex = _Lex(concepts, seed)

    def sample(self, rng):
        return "".join(rng.choice(self.ALPHA) for _ in range(rng.randint(4, 8)))

    def _atom(self, rng, s):
        x = rng.choice(self.ALPHA); r = rng.random()
        if r < 0.3:
            return [self.lex["contains"], self.lex[x]], x in s, "contains", {x}
        if r < 0.45:
            return [self.lex["starts"], self.lex[x]], s[0] == x, "starts", {x}
        if r < 0.6:
            return [self.lex["ends"], self.lex[x]], s[-1] == x, "ends", {x}
        if r < 0.8:
            y = rng.choice([a for a in self.ALPHA if a != x])
            tv = any(i < j for i, a in enumerate(s) if a == x for j, b in enumerate(s) if b == y)
            return [self.lex[x], self.lex["before"], self.lex[y]], tv, "before", {x, y}
        n = rng.randrange(0, 5)
        return [self.lex["count"], self.lex[x], self.lex[f"n{n}"]], s.count(x) == n, "count", {x, f"n{n}"}

    def describe(self, rng, s):
        r = rng.random()
        if r < 0.5:
            return self._atom(rng, s)
        if r < 0.7:
            toks, tv, c, cw = self._atom(rng, s)
            return [self.lex["not"]] + toks, (not tv), "not+" + c, cw
        if r < 0.9:
            t1, v1, c1, w1 = self._atom(rng, s); t2, v2, c2, w2 = self._atom(rng, s)
            return t1 + [self.lex["and"]] + t2, (v1 and v2), "and", w1 | w2
        x = rng.choice(self.ALPHA); y = rng.choice(self.ALPHA)
        idx = [i for i, a in enumerate(s) if a == x]
        tv = bool(idx) and all(i + 1 < len(s) and s[i + 1] == y for i in idx)
        return [self.lex["every"], self.lex[x], self.lex["followed"], self.lex[y]], tv, "every-followed", {x, y}


def splits(world, seed, n_train=3000, n_test=600):
    """(situation, tokens, truth) triples. The compositional held-out set is built by holding out a fixed set of
    (content word, construction) PAIRS from training: sentences containing a held-out pair go to heldout_comp."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n_train + 2 * n_test):
        sit = world.sample(rng)
        toks, tv, c, cw = world.describe(rng, sit)
        rows.append((sit, toks, bool(tv), c, cw))
    pairs = sorted({(w, c) for _, _, _, c, cw in rows for w in cw})
    held = set(random.Random(seed + 1).sample(pairs, max(1, len(pairs) // 6)))
    comp = [r for r in rows if any((w, r[3]) in held for w in r[4])]
    rest = [r for r in rows if r not in comp]
    return dict(train=[r[:3] for r in rest[:n_train]], heldout_iid=[r[:3] for r in rest[n_train:n_train + n_test]],
                heldout_comp=[r[:3] for r in comp[:n_test]], held_pairs=sorted(held))


if __name__ == "__main__":
    for W in (Records(), Strings()):
        sp = splits(W, 1)
        print(f"{W.name}: train {len(sp['train'])}  iid {len(sp['heldout_iid'])}  compositional {len(sp['heldout_comp'])}  held pairs {len(sp['held_pairs'])}")
        for sit, toks, tv in sp["train"][:3]:
            print(f"   {str(sit):40s} {' '.join(toks):40s} {tv}")
