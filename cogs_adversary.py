"""STAGE 3b -- the GENERATOR-FAMILY CONTROL for the head-passing engine.

Stage 3a scored COGS gen EM 0.9990 but its own limitation note says the constituent SCHEMAS are authored:
`parse_np` wants a pre-nominal determiner and a right-attaching modifier, `parse_clause` wants the verb before
its post-arguments, `ev_np` splices the HEAD's lemma and exports the HEAD's variable, `ev_cl` exports the EVENT.
This module randomizes exactly those dimensions and reruns the SAME engine, which is the test that made Stage 2
a result instead of a replication of Nye 2020 / NQG 2021.

A grammar in the family is a synchronous CFG with variables, drawn from:
    np_branch  modifier right of its head noun (COGS) | head-final, left of it
    np_head    a modified NP exports the HEAD's variable (COGS) | the DEPENDENT's
    mod_pred   modifier predicate splices the HEAD's lemma (COGS) | the DEPENDENT's | no lemma at all
    mod_args   modifier arguments (head, dep) (COGS) | (dep, head)
    mid        constant middle segments ('nmod',) (COGS) | two of them | none
    det_pos    determiner before the noun (COGS) | after it
    verb_pos   verb before its post-arguments (COGS) | clause-final
    cl_head    a clause exports the EVENT variable (COGS) | its SUBJECT's
    def_style  definiteness as the `*` prefix list (COGS) | an inline marker predicate
plus a randomized synthetic lexicon, randomized frames, randomized role names and randomized role order, so
nothing leaks from COGS. Variables stay 0-based TOKEN POSITIONS -- that is COGS's representation convention,
not part of its grammar, and it is probed separately (see stage3b_probe_variable_convention).

Train/test is a DEPTH split, the analogue of Stage 2's length split and of COGS's own recursion categories:
train has modifier and embedding depth <= 1 and NEVER a modifier on the subject; test is modifier depth 2-6,
embedding depth 2-6, and a modifier on the SUBJECT -- a configuration absent from train."""
import os, sys, random, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_lf import serialize

COGS_DEFAULT = dict(np_branch="right", np_head="head", mod_pred="head_lemma", mod_args="head_dep",
                    mid=("nmod",), det_pos="pre", verb_pos="medial", cl_head="event", def_style="prefix")

DIMS = dict(np_branch=("right", "left"), np_head=("head", "dep"),
            mod_pred=("head_lemma", "dep_lemma", "bare"), mod_args=("head_dep", "dep_head"),
            mid=(("nmod",), ("rel", "of"), ()), det_pos=("pre", "post"),
            verb_pos=("medial", "final"), cl_head=("event", "subject"),
            def_style=("prefix", "inline"))


# ---------------------------------------------------------------- a grammar in the family
def make_grammar(seed, overrides=None):
    """overrides pins chosen dimensions. Pinning ALL of them to COGS_DEFAULT gives the sanity control; pinning
    all but one gives a SINGLE-DIMENSION KNOCKOUT, which is what makes a failure attributable -- a fully random
    draw differs on several dimensions at once and attributes nothing."""
    rng = random.Random(7000 + seed)
    g = {k: rng.choice(v) for k, v in DIMS.items()}
    if overrides:
        g.update(overrides)
    if g["mod_pred"] == "bare" and not g["mid"]:
        g["mid"] = ("nmod",)                       # a modifier predicate needs at least one naming segment
    g["nouns"] = [f"n{i}" for i in range(24)]
    g["nlem"] = {w: f"N{i}" for i, w in enumerate(g["nouns"])}
    g["verbs"] = [f"v{i}" for i in range(10)]
    g["vlem"] = {w: f"V{i}" for i, w in enumerate(g["verbs"])}
    g["names"] = [f"P{i}" for i in range(6)]
    g["rels"] = [f"p{i}" for i in range(3)]
    g["det_indef"], g["det_def"] = "d0", "d1"
    g["defmark"] = "DEFMARK"
    g["term"] = "T"
    roles = [f"r{i}" for i in range(4)]
    rng.shuffle(roles)
    # frames: (pre_marker, tuple of (marker, kind) for the non-subject slots) -> role tuple incl. the subject
    m0, m1, m2, cm = "m0", "m1", "m2", "c0"
    g["cmark"] = cm
    frames = [
        (None, ()),
        (None, (("", "NP"),)),
        (None, (("", "NP"), (m0, "NP"))),
        (m1, ((m2, "NP"),)),
        (None, ((cm, "CL"),)),
    ]
    g["frames"] = []
    for pre, slots in frames:
        rs = [roles[0]] + [roles[1 + i % 3] for i in range(len(slots))]
        perm = list(range(len(rs)))
        rng.shuffle(perm)
        g["frames"].append(dict(pre=pre, slots=slots, roles=tuple(rs[i] for i in perm)))
    return g


def differs(g):
    return sorted(k for k in DIMS if g[k] != COGS_DEFAULT[k])


# ---------------------------------------------------------------- sampling derivations
class GNP:
    __slots__ = ("kind", "word", "lemma", "definite", "mod", "idx")

    def __init__(self, kind, word, lemma, definite, mod=None):
        self.kind, self.word, self.lemma, self.definite, self.mod = kind, word, lemma, definite, mod
        self.idx = None                        # rel = (relator_word, inner GNP), filled as `mod`


class GCL:
    __slots__ = ("frame", "verb", "vlemma", "slots", "idx")

    def __init__(self, frame, verb, vlemma, slots):
        self.frame, self.verb, self.vlemma, self.slots = frame, verb, vlemma, slots
        self.idx = None


def sample_np(g, rng, depth, used=None):
    # proper names are drawn WITHOUT replacement inside a clause: two slots sharing one name would share one
    # constant head, collapsing the (event, argument) -> role map that role induction reads off the gold form
    if depth == 0 and rng.random() < 0.25:
        avail = [x for x in g["names"] if used is None or x not in used]
        if avail:
            w = rng.choice(avail)
            if used is not None:
                used.add(w)
            return GNP("NAME", w, None, False)
    w = rng.choice(g["nouns"])
    node = GNP("ENTITY", w, g["nlem"][w], rng.random() < 0.5)
    if depth > 0:
        node.mod = (rng.choice(g["rels"]), sample_np(g, rng, depth - 1, used))
    return node


def sample_cl(g, rng, mod_depth, emb_depth, subj_mod=False):
    if emb_depth > 0:
        fr = g["frames"][4]
    elif mod_depth > 0 and not subj_mod:
        # a requested modifier depth must actually be REALIZED: the intransitive frame has no non-subject NP
        # slot to hang it on, so choosing it would have quietly put depth-0 items in the deep test set
        fr = rng.choice([f for f in g["frames"][:4] if any(k == "NP" for _, k in f["slots"])])
    else:
        fr = rng.choice(g["frames"][:4])
    used = set()
    slots = [sample_np(g, rng, mod_depth if subj_mod else 0, used)]
    nonsubj = [i for i, (_, k) in enumerate(fr["slots"]) if k == "NP"]
    pick = rng.choice(nonsubj) if (nonsubj and not subj_mod) else None
    for i, (m, kind) in enumerate(fr["slots"]):
        if kind == "CL":
            slots.append(sample_cl(g, rng, mod_depth if emb_depth == 1 else 0, emb_depth - 1))
        else:
            slots.append(sample_np(g, rng, mod_depth if i == pick else 0, used))
    return GCL(fr, rng.choice(g["verbs"]), None, slots)


# ---------------------------------------------------------------- rendering: tokens and logical form
def render_np(g, node, toks):
    if node.kind == "NAME":
        node.idx = len(toks)
        toks.append(node.word)
        return
    head = [node.word]
    det = g["det_def"] if node.definite else g["det_indef"]
    unit_pre = [det] + head if g["det_pos"] == "pre" else head + [det]
    if node.mod is None:
        node.idx = len(toks) + (1 if g["det_pos"] == "pre" else 0)
        toks.extend(unit_pre)
        return
    rel, inner = node.mod
    if g["np_branch"] == "right":
        node.idx = len(toks) + (1 if g["det_pos"] == "pre" else 0)
        toks.extend(unit_pre)
        toks.append(rel)
        render_np(g, inner, toks)
    else:                                                    # head-final NP: [inner] [relator] [det noun]
        render_np(g, inner, toks)
        toks.append(rel)
        node.idx = len(toks) + (1 if g["det_pos"] == "pre" else 0)
        toks.extend(unit_pre)


def render_cl(g, node, toks):
    fr = node.frame
    render_np(g, node.slots[0], toks)
    verb_unit = ([fr["pre"]] if fr["pre"] else []) + [node.verb]
    if g["verb_pos"] == "medial":
        node.idx = len(toks) + len(verb_unit) - 1
        toks.extend(verb_unit)
    posts = []
    for (m, kind), sub in zip(fr["slots"], node.slots[1:]):
        if m:
            posts.append(m)
        start = len(toks) + len(posts)
        buf = []
        (render_cl if kind == "CL" else render_np)(g, sub, buf)
        posts.extend(buf)
        _shift(sub, start - 0)                                # buf indices were 0-based; rebase them
    toks.extend(posts)
    if g["verb_pos"] == "final":
        node.idx = len(toks) + len(verb_unit) - 1
        toks.extend(verb_unit)
    node.vlemma = g["vlem"][node.verb]


def _shift(node, off):
    if isinstance(node, GNP):
        node.idx += off
        if node.mod:
            _shift(node.mod[1], off)
    else:
        node.idx += off
        for s in node.slots:
            _shift(s, off)


def lf_np(g, node, defs, conj):
    """-> the head this NP exports (the head-passing contract, under this grammar's schema)."""
    if node.kind == "NAME":
        own, own_head = [], ("c", node.word)
    else:
        own_head = ("v", node.idx)
        own = []
        if node.definite and g["def_style"] == "prefix":
            defs.append((node.lemma, node.idx))
        else:
            own.append((node.lemma, (own_head,)))
            if node.definite:
                own.append((g["defmark"], (own_head,)))
    if node.mod is None:
        conj.extend(own)
        return own_head
    rel, inner = node.mod
    inner_conj = []
    ihead = lf_np(g, inner, defs, inner_conj)
    if g["mod_pred"] == "head_lemma":
        pieces = (node.lemma,) + tuple(g["mid"]) + (rel,)
    elif g["mod_pred"] == "dep_lemma":
        pieces = ((inner.lemma or inner.word),) + tuple(g["mid"]) + (rel,)
    else:
        pieces = tuple(g["mid"]) + (rel,)
    args = (own_head, ihead) if g["mod_args"] == "head_dep" else (ihead, own_head)
    modc = (" . ".join(pieces), args)
    conj.extend(own + [modc] + inner_conj)
    return own_head if g["np_head"] == "head" else ihead


def lf_cl(g, node, defs, conj):
    ev = ("v", node.idx)
    heads = []
    subconj = []
    for kind, sub in zip(["NP"] + [k for _, k in node.frame["slots"]], node.slots):
        c = []
        heads.append((lf_cl if kind == "CL" else lf_np)(g, sub, defs, c))
        subconj.append(c)
    block = [(node.vlemma + " . " + r, (ev, h)) for r, h in zip(node.frame["roles"], heads)]
    conj.extend(subconj[0] + block + [x for c in subconj[1:] for x in c])
    return ev if g["cl_head"] == "event" else heads[0]


def render(g, node):
    toks = []
    render_cl(g, node, toks)
    toks.append(g["term"])
    defs, conj = [], []
    lf_cl(g, node, defs, conj)
    return " ".join(toks), serialize(defs, conj)


# ---------------------------------------------------------------- the depth split
def build(seed, n_train=4000, n_test=250, overrides=None):
    g = make_grammar(seed, overrides)
    rng = random.Random(20000 + seed)
    train, test = [], []
    seen = set()
    for _ in range(n_train):                            # train: depth <= 1, NEVER a modifier on the subject
        md, ed = rng.choice([0, 1]), rng.choice([0, 1])
        s, lf = render(g, sample_cl(g, rng, md, ed))
        if s in seen:
            continue
        seen.add(s)
        train.append((s, lf, "in_distribution"))
    vocab = {w for s, _, _ in train for w in s.split()}
    for cat, kw in (("mod_recursion", dict(mod_depth=None, emb_depth=0)),
                    ("emb_recursion", dict(mod_depth=0, emb_depth=None)),
                    ("subj_mod", dict(mod_depth=None, emb_depth=0, subj_mod=True))):
        got = 0
        for _ in range(n_test * 40):
            if got >= n_test:
                break
            kk = dict(kw)
            d = rng.randint(2, 6) if cat != "subj_mod" else rng.randint(1, 3)
            if kk["mod_depth"] is None:
                kk["mod_depth"] = d
            if kk["emb_depth"] is None:
                kk["emb_depth"] = d
            s, lf = render(g, sample_cl(g, rng, **kk))
            if s in seen or not set(s.split()) <= vocab:
                continue
            seen.add(s)
            test.append((s, lf, cat))
            got += 1
    return g, train, test
