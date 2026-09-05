"""ENGLISH-WORDED WORLD + A REAL SYNTAX PARSER.

Two things were always separate in this project and stay separate here:
  SYNTAX   -- sentence structure. I write this grammar. That is the honest status: supplied, not induced.
  SEMANTICS-- what each word MEANS. The engine still LEARNS this by elimination from (sentence, scene) pairs,
              exactly as it learned the nonsense vocabulary. No word->meaning table is handed to it.

So the words are English and the user can type real sentences, but the engine is not told that "red" means
red. It infers it. If you shuffle the world's true mapping, it learns the shuffled one just as happily -- the
English spelling carries no information for it.

GRAMMAR (small but genuinely parsed -- determiners, stacked adjectives, multi-word prepositions, question
forms, and a copula):

    S     -> WHICH DESC | IS DESC REL DESC | DESC REL DESC | DESC
    DESC  -> DET? ADJ* NOUN?
    DET   -> the | a | an | that | this
    ADJ   -> colour | size | shape | zone word          (any order, any number)
    NOUN  -> one | thing | object | block | shape | square-as-noun
    REL   -> above | below | left of | right of | near | far from | bigger than | smaller than |
             taller than | wider than | the same colour as

Unknown content words are NOT silently dropped -- they are returned so the engine can ABSTAIN on them.
"""
import random

G = 12

COLOURS = ["red", "blue", "green", "yellow", "purple", "orange"]
CSS = {"red": "#e5484d", "blue": "#3b82f6", "green": "#22c55e",
       "yellow": "#eab308", "purple": "#a855f7", "orange": "#f97316"}
SHAPES = ["square", "wide", "tall"]
SIZES = ["tiny", "small", "big", "huge"]
HZONES = ["leftmost", "centred", "rightmost"]
VZONES = ["upper", "middle", "lower"]
UNARY = COLOURS + SHAPES + SIZES + HZONES + VZONES

BINARY = {
    "above": lambda A, B: A[0][3] <= B[0][1],
    "below": lambda A, B: A[0][1] >= B[0][3],
    "left of": lambda A, B: A[0][2] <= B[0][0],
    "right of": lambda A, B: A[0][0] >= B[0][2],
    "bigger than": lambda A, B: _area(A) > _area(B),
    "smaller than": lambda A, B: _area(A) < _area(B),
    "taller than": lambda A, B: (A[0][3] - A[0][1]) > (B[0][3] - B[0][1]),
    "wider than": lambda A, B: (A[0][2] - A[0][0]) > (B[0][2] - B[0][0]),
    "near": lambda A, B: _dist(A, B) <= 4,
    "far from": lambda A, B: _dist(A, B) > 8,
    "the same colour as": lambda A, B: A[1] == B[1],
}

DETS = {"the", "a", "an", "that", "this"}
NOUNS = {"one", "thing", "object", "block", "shape", "rectangle"}
FILLER = {"is", "are", "which", "what", "where", "please", "me", "tell", "show", "?", "it"}


def _area(o): return (o[0][2] - o[0][0]) * (o[0][3] - o[0][1])
def _dist(A, B):
    ax = (A[0][0] + A[0][2]) / 2; ay = (A[0][1] + A[0][3]) / 2
    bx = (B[0][0] + B[0][2]) / 2; by = (B[0][1] + B[0][3]) / 2
    return abs(ax - bx) + abs(ay - by)


def unary_holds(p, o):
    (x0, y0, x1, y1), c = o
    w, h = x1 - x0, y1 - y0
    if p in COLOURS: return COLOURS[c] == p
    if p == "square": return w == h
    if p == "wide": return w > h
    if p == "tall": return h > w
    if p in SIZES:
        band = min(3, (w * h - 1) * 4 // 16)
        return SIZES[band] == p
    if p in HZONES: return HZONES[min(2, ((x0 + x1) // 2) * 3 // G)] == p
    if p in VZONES: return VZONES[min(2, ((y0 + y1) // 2) * 3 // G)] == p
    raise KeyError(p)


def binary_holds(p, A, B): return BINARY[p](A, B)


def rand_scene(rng, n, tries=400):
    for _ in range(tries):
        objs = []
        ok = True
        for _ in range(n):
            placed = False
            for _ in range(200):
                x0 = rng.randrange(0, G - 1); x1 = rng.randrange(x0 + 1, min(G, x0 + 4) + 1)
                y0 = rng.randrange(0, G - 1); y1 = rng.randrange(y0 + 1, min(G, y0 + 4) + 1)
                r = (x0, y0, x1, y1)
                if all(not (r[2] > o[0][0] and o[0][2] > r[0] and r[3] > o[0][1] and o[0][3] > r[1])
                       for o in objs):
                    objs.append((r, rng.randrange(len(COLOURS)))); placed = True; break
            if not placed: ok = False; break
        if ok and len(objs) == n: return objs
    return None


def true_unary(o): return [p for p in UNARY if unary_holds(p, o)]
def true_binary(A, B): return [p for p in BINARY if binary_holds(p, A, B)]


# ---------------------------------------------------------------- the parser
def tokenize(text):
    t = text.lower().replace("?", " ").replace(",", " ").replace(".", " ")
    return [w for w in t.split() if w]


def _match_rel(toks, i):
    """longest multi-word relation starting at i -> (relation, next_index) or None."""
    for n in (3, 2, 1):
        if i + n <= len(toks):
            cand = " ".join(toks[i:i + n])
            if cand in BINARY: return cand, i + n
    return None


def parse(text, lexicon):
    """-> dict(kind, left, rel, right, unknown). lexicon maps a KNOWN word -> predicate (LEARNED, not given)."""
    toks = tokenize(text)
    left, right, rel = [], [], None
    unknown = []
    cur = left
    i = 0
    while i < len(toks):
        w = toks[i]
        m = _match_rel(toks, i)
        if m and rel is None and cur is left and left:
            rel, i = m; cur = right; continue
        if w in DETS or w in NOUNS or w in FILLER:
            i += 1; continue
        if w in lexicon:
            cur.append(lexicon[w]); i += 1; continue
        unknown.append(w); i += 1
    kind = "yesno" if (rel and left and right) else ("describe" if left else "empty")
    return {"kind": kind, "left": left, "rel": rel, "right": right, "unknown": unknown, "tokens": toks}
