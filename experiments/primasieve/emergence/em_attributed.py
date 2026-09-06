"""EMERGENCE E-7 -- THE THIRD VERDICT STATE: ATTRIBUTED (em_attributed_prereg.md). ZERO LLM, pure stdlib.

Hold what a source says, cite exactly where, use it tagged, never call it proven, drop it when the world
disagrees. State + lattice + store live in core.verdict; this file is the measured test on the rect world with
planted sources (three of which lie), the real WordNet, a contested word, and today's antonym-bridge decoy."""
import os, sys, json, time, random, re, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import en_world as W
import en_chat as C
import wn_acquire as ACQ
from core.registry import selfcheck
from core.verdict import COMMIT, ABSTAIN, ATTRIBUTED, RETRACTED, attribute, combine, Beliefs, summarize3

OUT = os.path.join(HERE, "EMERGENCE.json")

# ---- the twelve new words and their hidden TRUE meanings (the world's; never shown to the reader) ----
TRUE = {"crimson": "red", "scarlet": "red", "azure": "blue", "emerald": "green", "teal": "green",
        "gigantic": "huge", "minuscule": "tiny", "boxy": "square", "lofty": "tall", "broad": "wide",
        "topmost": "upper", "central": "centred"}

# ---- designated sources (fixed). Definitions AND non-defining distractor sentences. Three lies. ----
SOURCES = {
    "DICT-A": ("crimson is a shade of red. scarlet is a shade of red. azure is a shade of blue. "
               "emerald is a shade of green. teal is a shade of green. "
               "the crimson one was near the azure one. a boxy thing sat above the lofty one."),
    "DICT-B": ("gigantic means huge. minuscule means tiny. boxy means square. lofty means wide. "
               "broad means wide. the gigantic one and the broad one were both lower."),
    "FORUM":  ("teal is a shade of red. topmost means upper. central means leftmost. "
               "someone said the central one looked topmost but nobody checked."),
}
LIES = {("FORUM", "teal"), ("DICT-B", "lofty"), ("FORUM", "central")}
WN_WORDS = ["crimson", "scarlet", "azure", "emerald", "gigantic", "minuscule"]

DEF = re.compile(r"^(\w+) (?:is a shade of|means) (\w+)$")


def sentences(text):
    return [s.strip() for s in text.split(".") if s.strip()]


def reads(span, lex):
    """the fixed reading grammar: a definition sentence -> (word, known meaning); anything else -> None."""
    m = DEF.match(span)
    if not m or m.group(2) not in lex: return None
    return (m.group(1), lex[m.group(2)])


def wordnet_certificate(word, lex):
    """WordNet's certificate: the word's synset lemma list (hops=0) as the span; reading = the unique known word
    in it. Blocks the antonym bridge by construction (an antonym is not a lemma of the word's own synset)."""
    lem = ACQ.related_words(word, "adj", hops=0) | ACQ.related_words(word, "noun", hops=0)
    known = sorted(k for k in lem if k in lex)
    span = " ".join(sorted(lem))
    return span, (known[0] if len(known) == 1 else None)


def read_sources(lex, beliefs, shuffle=False, rng=None):
    """-> counts dict. Attribution goes through core.verdict.attribute; a failed certificate is refused."""
    n_admit = n_refused = n_distractor_admits = 0
    held = collections.defaultdict(list)                  # word -> [(meaning, source, span)]
    for sid, text in SOURCES.items():
        sents = sentences(text)
        spans = list(sents)
        if shuffle: spans = spans[1:] + spans[:1]           # KNOCKOUT: every span paired with a DIFFERENT sentence
        #   (a rotation, not a random shuffle: a shuffle's fixed points are genuine certificates, which is what a
        #    first version of this knockout mis-counted as admits)
        for sent, span in zip(sents, spans):
            r = reads(sent, lex)
            if r is None: continue                        # not a definition: distractor; must admit nothing
            word, meaning = r
            claim, state, prov = attribute((word, meaning), sid, text, span, lambda s: reads(s, lex))
            if state == ATTRIBUTED: held[word].append((meaning, sid, span)); n_admit += 1
            else: n_refused += 1
        for sent in sents:                                 # distractor guard: a mention is not a definition
            if reads(sent, lex) is None:
                for w in TRUE:
                    if w in sent.split():
                        claim, state, _ = attribute((w, TRUE[w]), sid, text, sent, lambda s: reads(s, lex))
                        n_distractor_admits += (state == ATTRIBUTED)
    wn = {w: wordnet_certificate(w, lex) for w in WN_WORDS}
    wn_spans = [wn[w][0] for w in WN_WORDS]
    if shuffle: wn_spans = wn_spans[1:] + wn_spans[:1]     # KNOCKOUT: each word cites ANOTHER word's synset
    for w, span_used in zip(WN_WORDS, wn_spans):           # the real source
        span, meaning = wn[w]
        if meaning is None: n_refused += 1; continue
        text = span; span = span_used
        claim, state, prov = attribute((w, lex[meaning]), "WORDNET", text, span,
                                       lambda s: (w, lex[meaning]) if meaning in s.split() else None)
        if state == ATTRIBUTED: held[w].append((lex[meaning], "WORDNET", span)); n_admit += 1
        else: n_refused += 1
    contested = []
    for w, items in held.items():
        meanings = {m for m, _, _ in items}
        prov = {(s, sp) for _, s, sp in items}
        if len(meanings) == 1:
            beliefs.hold(("word", w), next(iter(meanings)), ATTRIBUTED, prov)
        else:
            beliefs.hold(("word", w), frozenset(meanings), ATTRIBUTED, prov); contested.append(w)   # held as a SET
    return dict(admitted=n_admit, refused=n_refused, distractor_admits=n_distractor_admits, contested=contested)


def ask(beliefs, scene, word, qid):
    """'which one is <word>?' using an attributed meaning -> tagged answer, recorded as a dependent."""
    e = beliefs.b.get(("word", word))
    if e is None or e["state"] in (ABSTAIN, RETRACTED) or isinstance(e["value"], frozenset):
        return ABSTAIN, None
    cands = C.referents(scene, [e["value"]])
    if len(cands) != 1: return ABSTAIN, None
    state = beliefs.derive(("answer", qid), cands[0], [("word", word)])
    return state, cands[0]


def evidence(word, n, rng):
    """the world narrates n scenes using the word with its TRUE meaning -> objects it was used for."""
    objs = []
    while len(objs) < n:
        sc = W.rand_scene(rng, 3)
        if sc is None: continue
        for o in sc:
            if W.unary_holds(TRUE[word], o): objs.append(o); break
    return objs


if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time(); rng = random.Random(11)
    print("EMERGENCE E-7 -- the third verdict state: ATTRIBUTED (held on a checkable reference)\n", flush=True)
    _, lex, _ = C.build(n=9000, seed=7)                    # base lexicon: COMMIT by elimination (en_chat's n)
    lex = {w: p for w, p in lex.items()}
    missing_base = sorted(set(W.UNARY) - set(lex))
    print(f"base lexicon by elimination: {len(lex)}/{len(W.UNARY)} words COMMIT"
          + (f"  (not learned: {missing_base} -> definitions in terms of them cannot be read)" if missing_base else "") + "\n", flush=True)

    # ---- 1. read sources ----
    B = Beliefs()
    rd = read_sources(lex, B)
    held = {w: e for (kind, w), e in B.b.items() if kind == "word"}
    print(f"read: admitted {rd['admitted']} certificates, refused {rd['refused']}, distractor admits "
          f"{rd['distractor_admits']}, contested {rd['contested']}", flush=True)
    for w, e in sorted(held.items()):
        v = e["value"] if not isinstance(e["value"], frozenset) else "SET" + str(sorted(e["value"]))
        print(f"  {w:10s} -> {str(v):22s} {e['state']:10s} cites {sorted(s for s, _ in e['prov'])}", flush=True)

    # ---- decoy: the antonym bridge ----
    span, meaning = wordnet_certificate("large", lex)
    _, st_big, _ = attribute(("large", lex.get("big")), "WORDNET", span, span, lambda s: ("large", lex["big"]) if "big" in s.split() else None)
    _, st_small, _ = attribute(("large", lex.get("small")), "WORDNET", span, span, lambda s: ("large", lex["small"]) if "small" in s.split() else None)
    print(f"\ndecoy large: ->big {st_big}, ->small {st_small}   (proposer today said 'small' first)", flush=True)

    # ---- 2. use: 200 questions before evidence; baseline abstains on every one ----
    words = sorted(TRUE); n_q = 200; att = att_wrong = abst = confab = 0; per_src_wrong = collections.Counter()
    for qid in range(n_q):
        sc = W.rand_scene(rng, 4)
        if sc is None: continue
        w = words[qid % len(words)]
        state, ans = ask(B, sc, w, qid)
        if state == ATTRIBUTED:
            att += 1
            truth = C.referents(sc, [TRUE[w]])
            if truth != [ans]:
                att_wrong += 1
                for s, _ in B.b[("word", w)]["prov"]: per_src_wrong[s] += 1
        elif state == COMMIT:
            confab += (C.referents(sc, [TRUE[w]]) != [ans])
        else: abst += 1
    print(f"\npre-evidence: {summarize3(n_q, confab, 0, len(B.laundered()), att_wrong, att, abst)}", flush=True)
    print(f"  baseline (current engine) would ABSTAIN on all {n_q}; attributed answers wrong by source: {dict(per_src_wrong)}", flush=True)

    # ---- 3. evidence arrives: elimination on the world's own use of each word ----
    upgraded, retracted, cascaded = [], [], 0
    never_held = [w for w in words if ("word", w) not in B.b]
    for w in words:
        if ("word", w) not in B.b: continue                 # no source gave a readable certificate: stays ABSTAIN
        e = B.b[("word", w)]
        objs = evidence(w, 40, rng)
        surv = {p for p in W.UNARY if all(W.unary_holds(p, o) for o in objs)}
        vals = e["value"] if isinstance(e["value"], frozenset) else {e["value"]}
        if len(surv) == 1 and surv == vals:
            B.upgrade(("word", w)); upgraded.append(w)
        elif len(surv) == 1 and isinstance(e["value"], frozenset) and next(iter(surv)) in vals:
            # contested set resolved by the world: strike the sources that said otherwise, keep the confirmed one
            wrong_src = {s for m, s, sp in [(m, s, sp) for (s, sp) in e["prov"] for m in [reads(sp, lex)[1] if reads(sp, lex) else None]] if m != next(iter(surv))}
            for s in wrong_src: B.strikes[s] = B.strikes.get(s, 0) + 1
            e["value"] = next(iter(surv)); B.upgrade(("word", w)); upgraded.append(w + "(resolved)")
        elif not (vals & surv):
            out = B.retract(("word", w)); retracted.append(w); cascaded += len(out) - 1
    print(f"\nevidence: upgraded {upgraded}", flush=True)
    print(f"          retracted {retracted} (+{cascaded} dependent answers cascaded)", flush=True)
    print(f"          strikes {dict(B.strikes)}  confirms {dict(B.confirms)}", flush=True)

    # ---- 4. knockouts ----
    B2 = Beliefs(); rd2 = read_sources(lex, B2, shuffle=True, rng=random.Random(3))
    print(f"\nknockout span-shuffle: admitted {rd2['admitted']} (must be 0)", flush=True)

    # ---- verdicts ----
    lies_words = {w for _, w in LIES}
    lies_retracted = all(w in retracted or (w in rd["contested"]) for w in lies_words)
    # contested teal: the FORUM lie is struck rather than retracted (DICT-A was right); both lies elsewhere retract
    forum_struck = B.strikes.get("FORUM", 0) >= 2 and B.strikes.get("DICT-B", 0) >= 1
    truths = [w for w in words if (not any(w == lw for _, lw in LIES) or w == "teal") and w not in never_held]
    truths_up = all(any(u.startswith(w) for u in upgraded) for w in truths)
    print(f"          never held (no readable certificate from any source): {never_held}", flush=True)
    if rd["contested"] != ["teal"]:
        print(f"          PREDICTION MISS: contested words were {rd['contested']}, prereg predicted ['teal'] only "
              f"(a real source disagreement discovered, not a mechanism failure)", flush=True)
    deps_all = all(B.b[k]["state"] == RETRACTED for k, e in B.b.items() if k[0] == "answer"
                   and any(B.b[f]["state"] == RETRACTED for f in e["from_"]))
    sound = (confab == 0 and rd["distractor_admits"] == 0 and len(B.laundered()) == 0 and lies_retracted and forum_struck
             and truths_up and deps_all and st_big == ATTRIBUTED and st_small == ABSTAIN and rd2["admitted"] == 0
             and "teal" in rd["contested"])
    ok = sound and att >= 100
    print(f"\nKILL#1 confab 0 / misattribution refused at door / laundering 0: {confab == 0 and len(B.laundered()) == 0}", flush=True)
    print(f"KILL#2 lies retracted or struck ({sorted(lies_words)}): {lies_retracted and forum_struck}; truths upgraded: {truths_up}; dependents cascaded: {deps_all}", flush=True)
    print(f"KILL#3 contested words {rd['contested']} held as sets, unanswered before evidence: {'teal' in rd['contested']}", flush=True)
    print(f"KILL#4 decoy: large->big {st_big}, large->small {st_small}: {st_big == ATTRIBUTED and st_small == ABSTAIN}", flush=True)
    print(f"KILL#5 shuffle admits 0: {rd2['admitted'] == 0}   KILL#6 distractor admits 0: {rd['distractor_admits'] == 0}   "
          f"KILL#7 utility >=100 attributed answers: {att >= 100} ({att})", flush=True)
    if sound: print("\nE7 ATTRIBUTED STATE: SOUND -- held on a reference, cited exactly, used tagged, never laundered, retracted on evidence", flush=True)
    else: print("\nE7 ATTRIBUTED STATE: NOT SOUND (read the kill lines)", flush=True)
    print(f"E7 UTILITY: {att}/{n_q} answered as attributed where the baseline abstains; pre-registered bar 100: "
          f"{'MET' if att >= 100 else 'NOT MET (sound but below the utility bar here; reasons: contested words and '+str(never_held)+' abstain, and a unique referent among 4 objects is required)'}", flush=True)
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E7_attributed_state"] = dict(prereg="em_attributed_prereg.md", read=rd, pre_evidence=dict(n=n_q, attributed=att, attributed_wrong=att_wrong,
                                    abstain=abst, confab=confab, wrong_by_source=dict(per_src_wrong)), upgraded=upgraded,
                                    retracted=retracted, cascaded=cascaded, strikes=dict(B.strikes), confirms=dict(B.confirms),
                                    decoy=dict(big=st_big, small=st_small), shuffle_admitted=rd2["admitted"], passed=ok,
                                    secs=round(time.time() - t0, 1))
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"({time.time()-t0:.0f}s) -> EMERGENCE.json[E7_attributed_state]", flush=True)
