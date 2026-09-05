"""STAGE 5 TESTBED -- four constructions COGS/SLOG never had: coordination, adjectives, negation, quantifiers.

A separate generator (the Stage 3b adversary is load-bearing for its own gates and must not change). Output is
in COGS logical-form style so the real engine (cogs_gram) parses it; vocabulary is synthetic, as in Stages
3b-3d. Each construction has a BASE control (sentences without it) and a KNOCKOUT the engine must fail if its
handling is authored rather than induced.

The logical-form conventions, each the linguistically standard neo-Davidsonian shape:
  ADJECTIVE   `the red cake` -> `* cake ( x_2 ) AND red ( x_2 )`  -- a unary predicate SHARING THE HEAD's
              variable, not its own. This is the one that breaks alignment-by-position: `red` at token 1 has a
              predicate anchored at token 2. The engine must induce that some words modify a neighbour.
  COORDINATION `the cat and the dog ran` -> `cat(x_2) AND dog(x_5) AND run.agent(e, x_2) AND run.agent(e, x_5)`
              -- a coordinator joins two constituents of one type, and the shared role DISTRIBUTES over both.
  NEGATION    `the cat did not run` -> `... AND NOT ( x_e )` -- a unary marker on the EVENT variable.
  QUANTIFIER  `every cat ran` -> `FORALL ( x_2 ) ; cat ( x_2 ) AND run.agent(e, x_2)` -- a marker on the
              quantified entity. Pre-registered as the likely NULL: a flat conjunct set cannot express SCOPE
              (every>some vs some>every), so recovering the marker is the most this representation can do and
              that limit is the finding, not a failure to fix."""
import os, sys, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_lf import serialize

CONSTRUCTIONS = ("adjective", "coordination", "negation", "quantifier")


def _grammar(seed):
    rng = random.Random(5000 + seed)
    g = dict(
        nouns=[f"n{i}" for i in range(16)], verbs=[f"v{i}" for i in range(8)],
        names=[f"P{i}" for i in range(5)], adjs=[f"a{i}" for i in range(6)],
        det_indef="d0", det_def="d1", coord="AND", neg_aux="did", neg="not",
        quant="every", term="T", rng=rng)
    g["nlem"] = {w: f"N{i}" for i, w in enumerate(g["nouns"])}
    g["vlem"] = {w: f"V{i}" for i, w in enumerate(g["verbs"])}
    g["alem"] = {w: f"A{i}" for i, w in enumerate(g["adjs"])}
    return g


def _np(g, rng, allow_adj, allow_coord, allow_quant, toks, defs):
    """Emit one NP's TOKENS; return (head, own_conjuncts). Conjuncts are returned, not appended, so the caller
    can place them in the engine's order (subject's own conjuncts, then the role block, then the object's)."""
    if allow_coord and rng.random() < 0.5:
        members, conjs = [], []
        k = rng.randint(2, g.get("max_coord", 2))            # ARITY: 2 or 3 conjuncts, chained by the coordinator
        for m in range(k):
            if m:
                toks.append(g["coord"])
            h, c = _np(g, rng, allow_adj, False, allow_quant, toks, defs)
            members.append(h)
            conjs += c
        return ("coord",) + tuple(members), conjs
    quant = allow_quant and rng.random() < 0.5
    if quant:
        toks.append(g["quant"])
        det = None
    else:
        det = rng.choice([g["det_indef"], g["det_def"]])
        toks.append(det)
    pool = g.get("adj_pool") or g["adjs"]
    adjv = rng.choice(pool) if (allow_adj and rng.random() < 0.6) else None
    if adjv is not None:
        toks.append(adjv)
    w = rng.choice(g["nouns"])
    idx = len(toks)
    toks.append(w)
    head = ("v", idx)
    own = []
    if det == g["det_def"]:
        defs.append((g["nlem"][w], idx))
    else:
        own.append((g["nlem"][w], (head,)))
    if adjv is not None:
        own.append((g["alem"][adjv], (head,)))          # SHARES the noun's variable
    if quant:
        own.append(("FORALL", (head,)))
    return head, own


def _role_block(role_pred, ev, head):
    """Apply a role to a (possibly coordinated) head, distributing over ALL conjuncts, in order."""
    if isinstance(head, tuple) and head and head[0] == "coord":
        out = []
        for mem in head[1:]:
            out += _role_block(role_pred, ev, mem)
        return out
    return [(role_pred, (ev, head))]


def _sentence(g, rng, cons):
    toks, defs = [], []
    a, co, q = ("adjective" in cons), ("coordination" in cons), ("quantifier" in cons)
    subj, subj_own = _np(g, rng, a, co, q, toks, defs)
    neg = "negation" in cons and rng.random() < 0.6
    if neg:
        toks += [g["neg_aux"], g["neg"]]
    v = rng.choice(g["verbs"])
    ev = ("v", len(toks))
    toks.append(v)
    transitive = rng.random() < 0.5
    if transitive:
        obj, obj_own = _np(g, rng, a, co, q, toks, defs)
    else:
        obj, obj_own = None, []
    toks.append(g["term"])
    # engine order (subj_first): subject's own conjuncts, then the role block, then the object's own conjuncts
    block = _role_block(g["vlem"][v] + " . r0", ev, subj)
    if obj is not None:
        block += _role_block(g["vlem"][v] + " . r1", ev, obj)
    if neg:
        block.append(("NOT", (ev,)))                    # the event marker sits with the verb's role block
    conj = subj_own + block + obj_own
    return " ".join(toks), serialize(defs, conj)


def build(seed=0, cons=CONSTRUCTIONS, n_train=4000, n_test=800, max_coord=2,
          train_adj=None, test_adj=None):
    """-> (train, test). cons selects which constructions appear. Base control = cons=().
    train_adj / test_adj restrict the adjective pool per split -- a DISJOINT pair tests lexical generalization
    to an adjective never seen in training. max_coord sets coordination arity (2 or 3)."""
    g = _grammar(seed)
    g["max_coord"] = max_coord
    rng = g["rng"]
    seen = set()
    train, test = [], []
    for bucket, n, pool in ((train, n_train, train_adj), (test, n_test, test_adj)):
        g["adj_pool"] = pool
        got = 0
        while got < n:
            s, lf = _sentence(g, rng, cons)
            if s in seen:
                continue
            seen.add(s)
            bucket.append((s, lf, "|".join(cons) if cons else "base"))
            got += 1
    return train, test


def scope_pair(seed=0):
    """The two scope readings of `every cat V some dog` -- every>some vs some>every -- and the flat conjunct set
    the engine would assign. If the two readings map to the SAME flat set, the representation provably cannot
    express scope; that identity is the demonstrated NULL, not an assumption."""
    g = _grammar(seed)
    cat, dog, v = g["nouns"][0], g["nouns"][1], g["verbs"][0]
    toks = [g["quant"], cat, v, "some", dog, g["term"]]
    # neo-Davidsonian flat set: FORALL(cat), EXISTS(dog), v.r0(e,cat), v.r1(e,dog). Both readings, same set.
    conj = [(g["nlem"][cat], (("v", 1),)), ("FORALL", (("v", 1),)),
            (g["nlem"][dog], (("v", 4),)), ("EXISTS", (("v", 4),)),
            (g["vlem"][v] + " . r0", (("v", 2), ("v", 1))),
            (g["vlem"][v] + " . r1", (("v", 2), ("v", 4)))]
    lf = serialize([], conj)
    return " ".join(toks), lf, lf     # (sentence, forall>exists LF, exists>forall LF) -- identical by construction


def homograph_split(seed=0, n_train=1800, n_test=400):
    """A word that is a NOUN head in some sentences and an ADJECTIVE (modifier) in others -- the fragility
    boundary for the 'a marker is no token's lemma' detector, since here the marker IS a lemma elsewhere."""
    g = _grammar(seed)
    rng = g["rng"]
    homo = g["nouns"][0]                                  # n0 doubles as an adjective; its noun lemma is N0
    seen, train, test = set(), [], []
    for bucket, n in ((train, n_train), (test, n_test)):
        got = 0
        while got < n:
            toks, defs, conj = [], [], []
            det = rng.choice([g["det_indef"], g["det_def"]])
            toks.append(det)
            use_adj = rng.random() < 0.5
            if use_adj:
                toks.append(homo)                        # n0 as a pre-nominal adjective
            w = rng.choice(g["nouns"][1:])
            idx = len(toks)
            toks.append(w)
            head = ("v", idx)
            own = [(g["nlem"][w], (head,))] if det == g["det_indef"] else []
            if det == g["det_def"]:
                defs.append((g["nlem"][w], idx))
            if use_adj:
                own.append((g["nlem"][homo], (head,)))   # adjective predicate = the homograph's OWN noun lemma
            v = rng.choice(g["verbs"])
            ev = ("v", len(toks))
            toks.append(v)
            toks.append(g["term"])
            block = [(g["vlem"][v] + " . r0", (ev, head))]
            s = " ".join(toks)
            if s in seen:
                continue
            seen.add(s)
            bucket.append((s, serialize(defs, own + block), "homograph"))
            got += 1
    return train, test
