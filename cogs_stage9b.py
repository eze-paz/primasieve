"""STAGE 9b RUN -- COMPOSITIONAL form: phrase-level units under the same MDL code (cogs_stage9b_prereg.md).
Mechanism: core/form.py PhraseGrammar + grow_phrases. Data and baselines as Stage 9.

Usage:  python cogs_stage9b.py"""
import os, sys, random, collections, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.form import sentences, signatures, collide, PhraseGrammar, grow_phrases, realize_phrase, corrupt
from core.verdict import attribute, ATTRIBUTED, COMMIT, ABSTAIN
from core.registry import selfcheck
from cogs_stage9 import chapters, wordnet_pos, wordnet_first_synsets, synonym_candidates, shuffled
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergence"))
from kb_offline import moby_index

T0 = time.time()
BUDGET_MAIN, BUDGET_ABL = 75, 40


def say(s=""): print(s, flush=True)


def induce(train, budget, use_units=True, cand_random=40, log=None):
    g = PhraseGrammar(train)
    sig = signatures(train)
    # collision-extend first (same SignatureBank step as Stage 9), through PhraseGrammar.merge
    from core.generate import SignatureBank
    bank, n = SignatureBank(), 0
    for w in g.vocab:
        key = frozenset(sig[w].items())
        if not bank.add(w, key):
            a, b = g.cls[bank.hit(key)], g.cls[w]
            if a != b: g.merge(a, b); n += 1
    st = grow_phrases(g, sig, budget, use_units=use_units, cand_random=cand_random, rng=random.Random(9), log=log)
    st["collisions"] = n
    return g, st


def score(g, held):
    gram = sum(g.dl_sentence(s) for s in held)
    uni = sum(1 + g.unigram(s) for s in held)
    mem = sum(g.dl_memory(s) for s in held)
    known = [s for s in held if all(w in g.cls for w in s)]
    tok = sum(len(s) for s in known)
    covered = 0
    for s in known:
        n, segs = g.segment(g.seq(s))
        seg = sorted(segs)[0]
        covered += sum(len(sym) for sym in seg if len(sym) > 1)
    return dict(gram=gram, uni=uni, mem=mem, gain_uni=1 - gram / uni, gain_mem=1 - gram / mem,
                known=len(known) / len(held), unit_cov=covered / max(tok, 1))


if __name__ == "__main__":
    selfcheck(__file__)
    rng = random.Random(9)
    say("STAGE 9b -- COMPOSITIONAL FORM: recurring class sub-sequences adopted as units under the two-part MDL code.")
    say("Claim under test: form compresses raw text only when sub-sentence units recur and compose. MEANING not claimed.\n")
    ch = chapters()
    train = [s for c in ch[:9] for s in sentences(c)]
    held = [s for c in ch[9:] for s in sentences(c)]
    say(f"  corpus: train {len(train)} sentences (2..12 symbols), held-out {len(held)}")

    g, st = induce(train, BUDGET_MAIN, log=say)
    say(f"  induction: {st['collisions']} collisions; {st['merges']} class merges + {st['units']} units adopted of {st['evaluated']} evaluated "
        f"in {st['rounds']} rounds; K={g.K}, |P|={len(g.units)}, DL={st['dl']:.0f}; budget {'SPENT' if st['spent'] else 'not spent'}   [{time.time()-T0:.0f}s]")

    # G9b-1 soundness: every train sentence derives; realizing its own segmentation with its own words is identity
    der = sum(1 for s in train if g.derive(s)[0] is not None)
    g1 = der == len(train)
    say(f"\nG9b-1  SOUNDNESS: train sentences derive {der}/{len(train)}   [gate 1.000 -> {'PASS' if g1 else 'FAIL'}]")

    sc = score(g, held)
    g2 = sc["gain_uni"] >= 0.10 and sc["gram"] < sc["mem"]
    say(f"G9b-2  HELD-OUT MDL: grammar {sc['gram']:.0f} bits vs unigram {sc['uni']:.0f} (gain {sc['gain_uni']:+.3f}) vs memory {sc['mem']:.0f} "
        f"(gain {sc['gain_mem']:+.3f})   [gate >= +0.100 AND < memory -> {'PASS' if g2 else 'FAIL'}]")
    say(f"G9b-7  STRUCTURE: held-out sentences fully known {sc['known']:.3f}; TOKENS covered by multi-token units {sc['unit_cov']:.3f}   [predicted 0.30-0.50]; "
        f"units {len(g.units)}, mean length {sum(map(len, g.units))/max(len(g.units),1):.2f}")

    # synonyms G9b-6
    moby = moby_index() or {}
    wn_first = wordnet_first_synsets()
    cands = synonym_candidates(set(g.vocab), moby, wn_first)
    syn, rejected = collections.defaultdict(set), 0
    for a, b in cands:
        claim, state, prov = attribute(b, "MOBY", ", ".join(moby.get(a, ())), b, lambda span: span)
        if state != ATTRIBUTED: continue
        if g.cls[a] == g.cls[b]: syn[a].add(b); syn[b].add(a)
        else: rejected += 1
    n_acc = sum(len(v) for v in syn.values()) // 2
    say(f"G9b-6  SYNONYMS: candidates {len(cands)}, FORM test accepted {n_acc}, rejected {rejected}   "
        + ("; ".join(f"{a}~{b}" for a, b in cands if b in syn.get(a, ())) or "(none accepted)"))

    # G9b-3 round trip on form (segmentation ambiguity is real now)
    N = 1000; ok = confab = abstain = 0
    for _ in range(N):
        seg, s = realize_phrase(g, rng, syn)
        state, segs = g.derive(s)
        if state == COMMIT:
            if segs == {seg}: ok += 1
            else: confab += 1
        else: abstain += 1
    g3 = confab == 0
    say(f"\nG9b-3  ROUND TRIP ON FORM: unique parse == generating segmentation {ok}/{N}, ABSTAIN (tie) {abstain}, CONFAB {confab}   [gate CONFAB 0 -> {'PASS' if g3 else 'FAIL'}]")
    caught = trials = 0
    for _ in range(200):
        seg, s = realize_phrase(g, rng)
        t = corrupt(g, s, rng)
        if t is None: continue
        trials += 1
        state, segs = g.derive(t)
        if segs is None or seg not in segs: caught += 1
    g4 = trials and caught >= 0.95 * trials
    say(f"G9b-4  THE INVARIANT CAN FAIL: cross-class corruption caught {caught}/{trials} = {caught/max(trials,1):.3f}   [gate >= 0.95 -> {'PASS' if g4 else 'FAIL'}]")

    # G9b-5 purity
    pos = wordnet_pos(); tot = pure = 0
    for c, ws in g.members.items():
        tagged = [w for w in ws if w in pos]
        if len(tagged) < 2: continue
        best = max("nvar", key=lambda p: sum(1 for w in tagged if p in pos[w]))
        pure += sum(1 for w in tagged if best in pos[w]); tot += len(tagged)
    purity = pure / max(tot, 1)
    say(f"G9b-5  EXTERNAL CHECK: POS purity vs WordNet {pure}/{tot} = {purity:.3f}   [bar 0.70 -> {'MET' if purity >= 0.70 else 'NOT MET'}]")

    # audit
    say("\n  AUDIT -- 10 realized sentences; 12 most frequent units (class members abbreviated):")
    for _ in range(10):
        seg, s = realize_phrase(g, rng, syn); say("     " + " ".join(s))
    ucount = collections.Counter()
    for s in train:
        n, segs = g.segment(g.seq(s))
        for sym in sorted(segs)[0]:
            if len(sym) > 1: ucount[sym] += 1
    for u, c in ucount.most_common(12):
        say(f"     x{c:<3} " + " | ".join("/".join(sorted(g.members[k])[:4]) + ("/.." if len(g.members[k]) > 4 else "") for k in u))
    for c in sorted(g.members, key=lambda c: -len(g.members[c]))[:5]:
        ws = sorted(g.members[c]); say(f"     class {c} ({len(ws)}): {' '.join(ws[:14])}{' ...' if len(ws) > 14 else ''}")

    # K5 units disabled (the phrase arm's own ablation)
    g5, st5 = induce(train, BUDGET_MAIN, use_units=False)
    sc5 = score(g5, held)
    share = (sc["gain_uni"] - sc5["gain_uni"]) / sc["gain_uni"] if sc["gain_uni"] > 0 else float("nan")
    k5 = sc["gain_uni"] > 0 and share >= 0.5
    say(f"\nK5   UNITS DISABLED: held-out gain {sc5['gain_uni']:+.3f} (K={g5.K}) vs with units {sc['gain_uni']:+.3f}; units' share of the gain {share:.2f}   "
        f"[>= 0.50 -> {'UNITS CARRY THE GAIN' if k5 else 'UNITS DO NOT CARRY THE GAIN'}]   [{time.time()-T0:.0f}s]")

    # K1 shuffled order
    k1rng = random.Random(1)
    g1s, _ = induce(shuffled(train, k1rng), BUDGET_ABL)
    sc1 = score(g1s, shuffled(held, k1rng))
    k1_fails = not (sc1["gain_uni"] >= 0.10 and sc1["gram"] < sc1["mem"])
    say(f"K1   SHUFFLED WORD ORDER: held-out gain {sc1['gain_uni']:+.3f}, unit coverage {sc1['unit_cov']:.3f}   "
        f"[must FAIL G9b-2 -> {'fails' if k1_fails else 'PASSES = RUN VOID'}{'' if g2 else '; uninformative since the real run also fails'}]")

    # K2 shuffled dictionary
    heads = list(moby.keys()); vals = [moby[h] for h in heads]; random.Random(2).shuffle(vals)
    cands2 = synonym_candidates(set(g.vocab), dict(zip(heads, vals)), wn_first)
    say(f"K2   SHUFFLED DICTIONARY: candidates {len(cands2)} (real {len(cands)})")

    # K3 similar-only candidates
    g3s, st3 = induce(train, BUDGET_ABL, cand_random=0)
    sc3 = score(g3s, held)
    say(f"K3   CANDIDATE ORDER: similar+random DL {st['dl']:.0f} / gain {sc['gain_uni']:+.3f}  vs  similar-only DL {st3['dl']:.0f} / gain {sc3['gain_uni']:+.3f}   [report; budgets {BUDGET_MAIN}s vs {BUDGET_ABL}s]")

    say(f"\n[{time.time()-T0:.0f}s]")
    void = g2 and not k1_fails
    if void:
        say("STAGE 9b COMPOSITIONAL FORM: VOID -- shuffled order also passes the MDL gate.")
    elif g1 and g2 and g3 and g4 and k5:
        say(f"STAGE 9b COMPOSITIONAL FORM: PASS (held-out gain {sc['gain_uni']:+.3f}, units' share {share:.2f}, unit coverage {sc['unit_cov']:.3f}, CONFAB 0)")
    elif g1 and g2 and g3 and g4:
        say(f"STAGE 9b COMPOSITIONAL FORM: MDL PASS BUT NOT THIS CLAIM -- gain {sc['gain_uni']:+.3f} comes from classes, units' share {share:.2f}")
    elif g1 and not g2:
        say(f"STAGE 9b COMPOSITIONAL FORM: NULL -- held-out gain {sc['gain_uni']:+.3f} (gate +0.100); unit coverage {sc['unit_cov']:.3f}")
    else:
        say("STAGE 9b COMPOSITIONAL FORM: FAIL")
