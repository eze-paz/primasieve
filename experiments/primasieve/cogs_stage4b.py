"""STAGE 4b RUN -- OPEN VOCABULARY as a tolerance-set verdict. Gates B1-B3 in cogs_stage3a_prereg.md.

An unseen word gets its CLASS from position (after a determiner -> entity; verb slot -> event; capitalized and
bare -> name) and its LEMMA from suffix rules induced from the lexicon's own surface/lemma pairs. Both are
guesses, so nothing is committed unless the sentence still has exactly ONE licensed reading, and an unseen
verb in a contested frame abstains rather than taking the plurality. unimorph_eng.tsv is used ONLY as an
oracle to score the morphology; it is never an input.

  B1  the 22 COGS gen items that abstained on unseen nouns (`monastery`, `gardner`): >= 18 correct, CONFAB 0
  B2  HELD-OUT VOCABULARY: 10% of noun types removed from train entirely (every sentence containing them),
      scored on the gen items that contain them. KILL: confabulation > 0.02.
  B3  in-vocabulary items unchanged (gen EM 0.9990).
  plus: morphology accuracy of the suffix rules vs the unimorph oracle, 5-fold over the verb lexicon.

Usage:  python cogs_stage4b.py"""
import os, sys, time, random, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_data import load, em
from cogs_gram import induce, generate, induce_lexicon, ENTITY, EVENT
from core.verdict import summarize
from core.registry import selfcheck

HERE = os.path.dirname(os.path.abspath(__file__))


def two_mode(m, rows):
    n = emc = cf = ab = 0
    for s, g, c in rows:
        p = generate(m, s)
        n += 1
        if p is None:
            ab += 1
        elif em(p, g):
            emc += 1
        else:
            cf += 1
    return n, emc, cf, ab


if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    tr, dev, test, gen = load()
    print("STAGE 4b -- OPEN VOCABULARY\n")

    m = induce(tr)
    lex = m[0]
    print(f"  suffix rules induced  EVENT {lex.rules[EVENT][:6]}  ENTITY {lex.rules[ENTITY][:4]}")

    # B1 -- the 22 known OOV abstains
    oov_rows = [r for r in gen if any(w not in lex.cls for w in r[0].split())]
    n, emc, cf, ab = two_mode(m, oov_rows)
    print(f"\nB1  gen items containing an unseen word: {n}")
    print("  " + summarize(n, em=emc, confab=cf, abstain=ab, label="open vocabulary"))
    b1 = emc >= 18 and cf == 0
    print(f"  [gate >= 18 correct, CONFAB 0 -> {'PASS' if b1 else 'FAIL'}]")
    lex.open_vocab = False
    n0, e0, c0, a0 = two_mode(m, oov_rows)
    lex.open_vocab = True
    print(f"  (closed-vocabulary engine on the same items: correct {e0}, abstain {a0})")

    # B3 -- in-vocabulary unchanged
    n, emc, cf, ab = two_mode(m, gen)
    print(f"\nB3  full gen: " + summarize(n, em=emc, confab=cf, abstain=ab))
    b3 = emc / n >= 0.9990 - 1e-9
    print(f"  [gate EM >= 0.9990 -> {'PASS' if b3 else 'FAIL'}]  (was 0.9990 with 22 abstentions)")

    # B2 -- held-out vocabulary
    rng = random.Random(4)
    nouns = sorted(w for w, c in lex.cls.items() if c == ENTITY)
    held = set(rng.sample(nouns, max(1, len(nouns) // 10)))
    tr2 = [r for r in tr if not any(w in held for w in r[0].split())]
    gen2 = [r for r in gen if any(w in held for w in r[0].split())]
    m2 = induce(tr2)
    n, emc, cf, ab = two_mode(m2, gen2)
    print(f"\nB2  held out {len(held)} noun types ({len(tr)-len(tr2)} train rows removed); "
          f"{len(gen2)} gen items contain one")
    print("  " + summarize(n, em=emc, confab=cf, abstain=ab, label="held-out vocabulary"))
    b2 = cf / max(n, 1) <= 0.02
    print(f"  [KILL if CONFAB > 0.02 -> {'PASS' if b2 else 'FAIL'}]")
    m2[0].open_vocab = False
    n0, e0, c0, a0 = two_mode(m2, gen2)
    print(f"  (closed-vocabulary engine on the same items: correct {e0}, abstain {a0})")

    # morphology vs the unimorph ORACLE, 5-fold over the verb lexicon
    uni = {}
    for l in open(os.path.join(HERE, "_nldata", "unimorph_eng.tsv"), encoding="utf-8"):
        q = l.rstrip("\n").split("\t")
        if len(q) == 3 and q[2] in ("V;PST", "V;V.PTCP;PST"):
            uni[q[1]] = q[0]
    verbs = sorted(w for w, c in lex.cls.items() if c == EVENT and w in lex.lemma)
    rng.shuffle(verbs)
    folds = [verbs[i::5] for i in range(5)]
    right = wrong = abst = 0
    for k in range(5):
        heldv = set(folds[k])
        sub = lambda: None
        sub.lemma = {w: lem for w, lem in lex.lemma.items() if w not in heldv}
        sub.cls = lex.cls
        sub.rules = {ENTITY: [], EVENT: []}
        from cogs_gram import _induce_suffix_rules
        _induce_suffix_rules(sub)
        lex_rules_backup = lex.rules
        lex.rules = sub.rules
        for w in heldv:
            if w not in uni:
                continue
            guess = lex.lemma_of(w, EVENT) if w not in lex.lemma or True else None
            g2 = None
            for sfx, lsfx, n_ in sub.rules[EVENT]:
                if sfx and w.endswith(sfx) and len(w) > len(sfx) + 1:
                    g2 = w[:len(w) - len(sfx)] + lsfx
                    break
            g2 = g2 or w
            if g2 == uni[w]:
                right += 1
            else:
                wrong += 1
        lex.rules = lex_rules_backup
    print(f"\nMORPHOLOGY vs unimorph oracle (5-fold, verbs): {right} right / {wrong} wrong = "
          f"{right/max(right+wrong,1):.3f} accuracy on {right+wrong} inflected verbs")
    print("  (irregulars -- ate, froze, gave -- are the wrong ones: no suffix rule reaches them, by design)")

    print(f"\n4b OPEN VOCABULARY: {'PASS' if (b1 and b2 and b3) else 'FAIL'}")
    print(f"total {time.time()-t0:.0f}s")
