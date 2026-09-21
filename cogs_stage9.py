"""STAGE 9 RUN -- realization grammar + synonym classes from RAW TEXT, no paired supervision.
Pre-registered in cogs_stage9_prereg.md; gates G9a-G9g, kills K1-K4. Mechanism in core/form.py.

  data     _nldata/alice.txt (train = chapters I-IX, held-out = X-XII), WordNet 3.1 (_nldata/dict),
           Moby Thesaurus (_nldata/files/mthesaur.txt) -- all offline, read through emergence/kb_offline.
  claim    FORM only. Nothing here binds a word to a referent.

Usage:  python cogs_stage9.py"""
import os, sys, random, collections, math, re, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.form import sentences, FormGrammar, signatures, collide, merge_mdl, realize, corrupt
from core.verdict import attribute, ATTRIBUTED
from core.registry import selfcheck
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergence"))
from kb_offline import moby_index

HERE = os.path.dirname(os.path.abspath(__file__))
NLD = os.path.join(HERE, "_nldata")
T0 = time.time()


def say(s=""): print(s, flush=True)


# ---------------------------------------------------------------- data
def chapters():
    raw = open(os.path.join(NLD, "alice.txt"), encoding="utf-8").read()
    body = raw.split("*** START OF THE PROJECT GUTENBERG EBOOK", 1)[-1].split("*** END OF THE PROJECT GUTENBERG EBOOK", 1)[0]
    parts = re.split(r"\nCHAPTER [IVX]+\.\n", body)
    return parts[1:]                                        # parts[0] = front matter + table of contents


def wordnet_pos():
    """word -> set of POS letters, from the WordNet index files. Used ONLY by G9e, the external judge."""
    pos = collections.defaultdict(set)
    for fn, p in (("index.noun", "n"), ("index.verb", "v"), ("index.adj", "a"), ("index.adv", "r")):
        for line in open(os.path.join(NLD, "dict", fn), encoding="utf-8"):
            if line.startswith(" "): continue
            pos[line.split(" ", 1)[0].lower()].add(p)
    return pos


def wordnet_first_synsets():
    """word -> set of lemmas in its FIRST synset per POS (E-8's first-sense rule), from index.* + data.*."""
    first = collections.defaultdict(set)
    for fn, dn in (("index.noun", "data.noun"), ("index.verb", "data.verb"), ("index.adj", "data.adj"), ("index.adv", "data.adv")):
        data = {}
        for line in open(os.path.join(NLD, "dict", dn), encoding="utf-8"):
            if line.startswith(" "): continue
            f = line.split(" ")
            off, wcnt = f[0], int(f[3], 16)
            data[off] = {f[4 + 2 * i].lower() for i in range(wcnt)}
        for line in open(os.path.join(NLD, "dict", fn), encoding="utf-8"):
            if line.startswith(" "): continue
            f = line.rstrip("\n").split(" ")
            w, n_syn = f[0].lower(), int(f[2])
            offs = f[-n_syn:]
            first[w] |= data.get(offs[0], set())
    return first


def synonym_candidates(vocab, moby, wn_first):
    """pairs (a, b) in vocab with MUTUAL Moby synonymy AND WordNet first-sense agreement in BOTH directions."""
    out = set()
    for a in vocab:
        ma = set(moby.get(a, ()))
        for b in ma:
            if b != a and b in vocab and a in set(moby.get(b, ())) and b in wn_first.get(a, ()) and a in wn_first.get(b, ()):
                out.add((min(a, b), max(a, b)))
    return sorted(out)


# ---------------------------------------------------------------- one full induction + scoring
def induce(train, order="similar", log=None):
    g = FormGrammar(train)
    sig = signatures(train)
    dl0 = g.dl_total()
    n_coll = collide(g, sig)
    dl1 = g.dl_total()
    n_adopt, n_eval = merge_mdl(g, sig, order=order, rng=random.Random(9), log=log)
    return g, dict(dl0=dl0, dl_collide=dl1, dl_final=g.dl_total(), collisions=n_coll, adopted=n_adopt, evaluated=n_eval)


def score_heldout(g, held):
    gram = sum(g.dl_sentence(s) for s in held)
    uni = sum(1 + g.unigram(s) for s in held)              # same escape bit so the comparison is fair
    mem = sum(g.dl_memory(s) for s in held)
    cov = sum(1 for s in held if g.derive(s) is not None) / len(held)
    return dict(gram=gram, uni=uni, mem=mem, cov=cov, gain_uni=1 - gram / uni, gain_mem=1 - gram / mem)


def shuffled(sents, rng):
    out = []
    for s in sents:
        t = list(s); rng.shuffle(t); out.append(t)
    return out


if __name__ == "__main__":
    selfcheck(__file__)
    rng = random.Random(9)
    say("STAGE 9 -- FORM from raw text: classes + skeletons under MDL, synonyms from attributed dictionaries.")
    say("Claim under test: FORM is learnable from text alone. MEANING is not claimed here.\n")

    ch = chapters()
    train = [s for c in ch[:9] for s in sentences(c)]
    held = [s for c in ch[9:] for s in sentences(c)]
    ntr_all = sum(len(sentences(c, 1, 10**6)) for c in ch[:9])
    say(f"  corpus: {len(ch)} chapters; train {len(train)} sentences of 2..12 symbols (of {ntr_all} total), held-out {len(held)}")

    g, st = induce(train, log=say)
    say(f"  induction: DL {st['dl0']:.0f} -> collide {st['dl_collide']:.0f} ({st['collisions']} collisions) -> MDL merges "
        f"{st['dl_final']:.0f} ({st['adopted']} adopted of {st['evaluated']} evaluated); K={g.K} classes, |S|={len(g.skel)} skeletons, V={g.V}   [{time.time()-T0:.0f}s]")

    # ---- G9a reproduction: every train sentence derives and realizes back to itself from its own fillers
    repro = sum(1 for s in train if g.derive(s) is not None)
    g9a = repro == len(train)
    say(f"\nG9a  SOUNDNESS: train sentences derived {repro}/{len(train)} = {repro/len(train):.4f}   [gate 1.000 -> {'PASS' if g9a else 'FAIL'}]")

    # ---- G9b MDL on held-out
    sc = score_heldout(g, held)
    g9b = sc["gain_uni"] >= 0.10 and sc["gram"] < sc["mem"]
    say(f"G9b  HELD-OUT MDL: grammar {sc['gram']:.0f} bits vs unigram {sc['uni']:.0f} (gain {sc['gain_uni']:+.3f}) vs memory {sc['mem']:.0f} "
        f"(gain {sc['gain_mem']:+.3f})   [gate >= +0.100 vs unigram AND < memory -> {'PASS' if g9b else 'FAIL'}]")
    say(f"G9g  COVERAGE (report): held-out sentences with a derivation {sc['cov']:.3f}   [predicted 0.25-0.50]")

    # ---- synonyms (G9f) with certificates
    moby = moby_index() or {}
    wn_first = wordnet_first_synsets()
    vocab = set(g.vocab)
    cands = synonym_candidates(vocab, moby, wn_first)
    syn, rejected, refused = collections.defaultdict(set), 0, 0
    for a, b in cands:
        text = ", ".join(moby.get(a, ()))
        claim, state, prov = attribute(b, "MOBY", text, b, lambda span: span)     # span verbatim in a's list
        if state != ATTRIBUTED: refused += 1; continue
        if g.cls[a] == g.cls[b]: syn[a].add(b); syn[b].add(a)                       # FORM test: same class
        else: rejected += 1
    n_acc = sum(len(v) for v in syn.values()) // 2
    rej_rate = rejected / max(len(cands), 1)
    say(f"\nG9f  SYNONYMS (report): dictionary candidates {len(cands)} (Moby mutual AND WordNet first-sense both ways, corpus words only); "
        f"FORM test rejected {rejected} ({rej_rate:.3f}), accepted {n_acc}, certificate refused {refused}")
    for a, b in cands[:12]:
        say(f"       {a} ~ {b}: {'accepted' if b in syn.get(a, ()) else 'REJECTED (different class)'}")

    # ---- G9c round trip on form; G9d corruption
    N = 1000
    ok = confab = 0
    for _ in range(N):
        sk, s = realize(g, rng, syn)
        back = g.derive(s)
        if back == sk: ok += 1
        else: confab += 1
    g9c = confab == 0
    say(f"\nG9c  ROUND TRIP ON FORM: {ok}/{N} realized sentences parse back to the same skeleton, CONFAB {confab}   [gate 1.000, 0 -> {'PASS' if g9c else 'FAIL'}]")
    caught = trials = 0
    for _ in range(200):
        sk, s = realize(g, rng)
        t = corrupt(g, s, rng)
        if t is None: continue
        trials += 1
        if g.derive(t) != sk: caught += 1
    g9d = trials and caught >= 0.95 * trials
    say(f"G9d  THE INVARIANT CAN FAIL: cross-class corruption caught {caught}/{trials} = {caught/max(trials,1):.3f}   [gate >= 0.95 -> {'PASS' if g9d else 'FAIL'}]")
    say("     note: with a hard class map both G9c and G9d hold by construction; the prereg predicted a first-run G9c failure on")
    say("     agreement -- that prediction was WRONG about this design and is recorded as a miss, not a pass.")

    # ---- G9e external check: class purity against WordNet POS
    pos = wordnet_pos()
    tot = pure = 0
    for c, ws in g.members.items():
        tagged = [w for w in ws if w in pos]
        if len(tagged) < 2: continue
        best = max("nvar", key=lambda p: sum(1 for w in tagged if p in pos[w]))
        hit = sum(1 for w in tagged if best in pos[w])
        tot += len(tagged); pure += hit
    purity = pure / max(tot, 1)
    g9e = purity >= 0.70
    say(f"\nG9e  EXTERNAL CHECK: class purity vs WordNet majority POS {pure}/{tot} = {purity:.3f} over classes with >= 2 tagged members   "
        f"[report; bar 0.70 -> {'MET' if g9e else 'NOT MET'}]")

    # ---- audit sample for a human read (E-8 rule 4): printed, not scored
    say("\n  AUDIT -- 12 realized sentences and 6 largest classes (my read is not a gate):")
    for _ in range(12):
        sk, s = realize(g, rng, syn); say("     " + " ".join(s))
    for c in sorted(g.members, key=lambda c: -len(g.members[c]))[:6]:
        ws = sorted(g.members[c]); say(f"     class {c} ({len(ws)}): {' '.join(ws[:14])}{' ...' if len(ws) > 14 else ''}")

    # ---- K1 shuffled word order: G9b must FAIL
    k1rng = random.Random(1)
    g1, _ = induce(shuffled(train, k1rng))
    sc1 = score_heldout(g1, shuffled(held, k1rng))
    k1_fails = not (sc1["gain_uni"] >= 0.10 and sc1["gram"] < sc1["mem"])
    say(f"\nK1   SHUFFLED WORD ORDER: held-out gain vs unigram {sc1['gain_uni']:+.3f}, vs memory {sc1['gain_mem']:+.3f}, coverage {sc1['cov']:.3f}   "
        f"[G9b must FAIL here -> {'CONTROL DISCRIMINATES' if k1_fails else 'CONTROL PASSES = RUN VOID'}]")

    # ---- K2 shuffled dictionary: synonym acceptance must fall to the form-test chance level
    heads = list(moby.keys()); vals = [moby[h] for h in heads]; random.Random(2).shuffle(vals)
    moby2 = dict(zip(heads, vals))
    cands2 = synonym_candidates(vocab, moby2, wn_first)
    acc2 = sum(1 for a, b in cands2 if g.cls[a] == g.cls[b])
    say(f"K2   SHUFFLED DICTIONARY: candidates {len(cands2)}, accepted {acc2}   [vs real {len(cands)} / {n_acc}]")

    # ---- K3 cost-order ablation: random merge order at the same budget
    g3, st3 = induce(train, order="random")
    sc3 = score_heldout(g3, held)
    say(f"K3   MERGE ORDER ABLATION: similar-first DL {st['dl_final']:.0f} / held-out gain {sc['gain_uni']:+.3f}  vs  random order DL {st3['dl_final']:.0f} / "
        f"held-out gain {sc3['gain_uni']:+.3f}   [report]")

    # ---- verdict
    void = not k1_fails
    allpass = g9a and g9b and g9c and g9d and not void
    say(f"\n[{time.time()-T0:.0f}s]")
    if void:
        say("STAGE 9 FORM FROM RAW TEXT: VOID -- K1 passed, the MDL oracle rewards something other than word order (K4).")
    elif allpass:
        say(f"STAGE 9 FORM FROM RAW TEXT: PASS (held-out MDL gain {sc['gain_uni']:+.3f}, coverage {sc['cov']:.3f}, CONFAB 0, POS purity {purity:.3f})")
    elif g9a and not g9b:
        say(f"STAGE 9 FORM FROM RAW TEXT: NULL -- reproduces train but held-out MDL gain {sc['gain_uni']:+.3f} (gate +0.100): memory, not form.")
    else:
        say("STAGE 9 FORM FROM RAW TEXT: FAIL")
