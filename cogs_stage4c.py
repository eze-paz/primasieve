"""STAGE 4c RUN -- REFERENCE: a pronoun resolved by a discourse function LEARNED BY ELIMINATION.
Gates C1-C3 in cogs_stage3a_prereg.md.

COGS and SLOG have no pronouns, so the testbed is the adversary grammar (COGS structure) extended with a
two-sentence DISCOURSE: sentence A introduces a subject and an object; sentence B uses the synthetic pronoun
token PRO for one argument, whose referent is fixed by a hidden discourse rule of the world. SYNTHETIC, stated
as such. The grammar is the Stage 4 engine unchanged; what is learned here is (1) that PRO is a pronoun -- a
token whose gold argument is never its own position -- and (2) WHICH discourse function it denotes, by
dialog_s3's elimination: a candidate survives iff it reproduces the referent in EVERY training pair, and the
survivor set may go EMPTY (that is the engine reporting its hypothesis space is refuted, which is sound).

  C1  pronoun items: EM >= 0.95 on sentence B's logical form, CONFAB 0; the learned function is reported
  C2  SHUFFLED-REFERENT knockout: the survivor set must go EMPTY (dialog_s3's own knockout, re-run here)
  C3  no regression on pronoun-free items of the same grammar

Usage:  python cogs_stage4c.py"""
import os, sys, time, random, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_adversary import build, COGS_DEFAULT, GNP, GCL, render, sample_np
from cogs_gram import induce, generate, parse_sentence, strip_term, lf_of, clause_nodes, NAME
from cogs_lf import norm_lf, parse_lf, serialize
from core.verdict import summarize
from core.registry import selfcheck

PRO = "PRO"
DISCOURSE = {                      # candidate meanings of the pronoun; the world uses exactly one
    "LAST_SUBJECT": lambda subj, obj: subj,
    "LAST_OBJECT": lambda subj, obj: obj,
}


def make_pairs(g, n, fn_name, rng):
    """(sentence A, sentence B with PRO, gold LF of B with the referent resolved). B's variables are B's own
    token positions; a common-noun referent from A is written as A's variable with an `a` prefix (x _ a4) so
    the two index spaces cannot collide; a name referent is the name itself."""
    fr_tr = [f for f in g["frames"] if len(f["slots"]) == 1 and f["slots"][0][1] == "NP"][0]
    out = []
    for _ in range(n):
        # A: transitive, subject and object both realized
        a = GCL(fr_tr, rng.choice(g["verbs"]), None, [sample_np(g, rng, 0, set()), sample_np(g, rng, 0, set())])
        sa, lfa = render(g, a)
        subj, obj = a.slots[0], a.slots[1]

        def ref(node):
            return ("c", node.word) if node.kind == "NAME" else ("v", f"a{node.idx}")
        referent = DISCOURSE[fn_name](ref(subj), ref(obj))
        # B: transitive with PRO as the object (or subject, half the time)
        b = GCL(fr_tr, rng.choice(g["verbs"]), None, [sample_np(g, rng, 0, set()), sample_np(g, rng, 0, set())])
        which = rng.choice([0, 1])
        b.slots[which] = GNP("NAME", PRO, None, False)
        sb, lfb = render(g, b)
        # substitute the pronoun constant by the referent in the gold
        p = parse_lf(lfb)
        conj = [(pred, tuple(referent if (arg == ("c", PRO)) else arg for arg in args)) for pred, args in p[1]]
        out.append((sa, sb, serialize(p[0], conj)))
    return out


def induce_pronoun(lex, pairs):
    """A token is a PRONOUN if, in every sentence B containing it, exactly one gold argument is aligned to NO
    token of B, and the token itself is aligned to nothing. Returns the set of such tokens."""
    cand = collections.Counter()
    tot = collections.Counter()
    for sa, sb, lf in pairs:
        toks = strip_term(lex, sb)
        p = parse_lf(lf)
        foreign = [a for _, args in p[1] for a in args
                   if (a[0] == "c" and a[1] not in toks) or (a[0] == "v" and isinstance(a[1], str))]
        unknown = [w for w in set(toks) if w not in lex.cls]
        for w in unknown:
            tot[w] += 1
            if len(foreign) == 1:
                cand[w] += 1
    # decisive_purity, not equality: in 3 of 400 pairs the referent happened to ALSO be a token of B (a name
    # used twice), so the foreign argument vanished. The same tolerance every other lexical fact uses.
    return {w for w in cand if cand[w] >= 0.95 * tot[w] and tot[w] >= 10}


def a_heads(lex, model, sa):
    """Subject and object heads of sentence A, in A's index space, prefixed with `a`."""
    lex_, sch, mid, roles, vc = model
    ps = parse_sentence(lex_, sch, strip_term(lex_, sa), want=1)
    if not ps:
        return None
    node = ps[0]
    heads = clause_nodes(lex_, sch, mid, node)[0][1]
    if len(heads) < 2:
        return None

    def tag(h):
        return ("c", h[1]) if h[0] == "c" else ("v", f"a{h[1]}")
    return tag(heads[0]), tag(heads[1])


def resolve(lf_b, fn_name, subj, obj):
    p = parse_lf(lf_b)
    r = DISCOURSE[fn_name](subj, obj)
    conj = [(pred, tuple(r if arg == ("c", PRO) else arg for arg in args)) for pred, args in p[1]]
    return serialize(p[0], conj)


def learn_discourse(model, pairs):
    """Elimination: a function survives iff it reproduces the gold in EVERY training pair it can be tested on."""
    lex = model[0]
    surv = set(DISCOURSE)
    tested = 0
    for sa, sb, gold in pairs:
        ah = a_heads(lex, model, sa)
        lfb = generate(model, sb)
        if ah is None or lfb is None:
            continue
        tested += 1
        keep = {fn for fn in surv if resolve(lfb, fn, *ah) == norm_lf(gold)}
        surv = keep
        if not surv:
            break
    return surv, tested


if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    g, tr, te = build(100, overrides=dict(COGS_DEFAULT))
    rng = random.Random(77)
    TRUE_FN = "LAST_OBJECT"
    train_pairs = make_pairs(g, 400, TRUE_FN, rng)
    test_pairs = make_pairs(g, 400, TRUE_FN, rng)
    print(f"STAGE 4c -- REFERENCE. Adversary grammar (COGS structure) + two-sentence discourse with the pronoun "
          f"token {PRO}; the world's hidden rule is {TRUE_FN}. {len(train_pairs)} train / {len(test_pairs)} "
          f"test pairs. SYNTHETIC.\n")
    model = induce(tr)
    lex = model[0]

    pron = induce_pronoun(lex, train_pairs)
    print(f"  induced PRONOUN tokens: {sorted(pron)}   (a token whose gold argument is never its own position)")
    for w in pron:
        lex.cls[w] = NAME                       # a pronoun is a name whose constant is resolved by discourse
    surv, tested = learn_discourse(model, train_pairs)
    print(f"  discourse function by ELIMINATION over {tested} pairs: survivors {sorted(surv)}")

    # C1
    n = emc = cf = ab = 0
    if len(surv) == 1:
        fn = next(iter(surv))
        for sa, sb, gold in test_pairs:
            ah = a_heads(lex, model, sa)
            lfb = generate(model, sb)
            n += 1
            if ah is None or lfb is None:
                ab += 1
            elif resolve(lfb, fn, *ah) == norm_lf(gold):
                emc += 1
            else:
                cf += 1
    else:
        n, ab = len(test_pairs), len(test_pairs)
    print(f"\nC1  " + summarize(n, em=emc, confab=cf, abstain=ab, label="pronoun items"))
    c1 = n and emc / n >= 0.95 and cf == 0
    print(f"  [gate EM >= 0.95, CONFAB 0 -> {'PASS' if c1 else 'FAIL'}]   learned: {sorted(surv)}")

    # C2 -- shuffled referents must EMPTY the survivor set
    shuf = []
    for sa, sb, gold in train_pairs:
        ah = a_heads(lex, model, sa)
        if ah is None:
            continue
        wrong = resolve(generate(model, sb) or "", TRUE_FN, ah[1], ah[0]) if generate(model, sb) else gold
        shuf.append((sa, sb, wrong if rng.random() < 0.5 else gold))
    surv2, tested2 = learn_discourse(model, shuf)
    print(f"\nC2  shuffled-referent knockout: survivors {sorted(surv2)} after {tested2} pairs   "
          f"[gate EMPTY -> {'PASS' if not surv2 else 'FAIL'}]")

    # C3 -- pronoun-free items of the same grammar
    n3 = sum(1 for s, lf, c in te)
    ok3 = sum(1 for s, lf, c in te if generate(model, s) == norm_lf(lf))
    print(f"\nC3  pronoun-free test items: EM {ok3/n3:.3f}   [gate 1.000 -> {'PASS' if ok3 == n3 else 'FAIL'}]")

    print(f"\n4c REFERENCE: {'PASS' if (c1 and not surv2 and ok3 == n3) else 'FAIL'}")
    print(f"total {time.time()-t0:.0f}s")
