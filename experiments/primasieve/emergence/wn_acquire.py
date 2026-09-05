"""ACQUIRE -- a wide external knowledge source, used ONLY as a PROPOSER. The world stays the verifier.

Owner asked for "a very wide source of searchable data it can use during conversation". WordNet is already in
the repo (117,953 noun entries + adjectives, fully offline), so no internet is needed.

THE ARCHITECTURAL POINT, and it is the one thing this project has measured repeatedly: an external knowledge
source has NO verifier behind it. Wire it in as a decider and every soundness property measured here
evaporates. So it is wired in as a PROPOSER only:

    unknown word  ->  WordNet PROPOSES candidate meanings  ->  the engine ASKS  ->  confirmed or rejected
                      (wide, unverified)                       (sound)             (lexicon grows)

That is exactly the shape the joint null with sandpie-91 vindicated: a proposer earns its keep when it knows
something the verifier's own search cannot reach. Here it plainly does -- no amount of scene-elimination will
ever tell the engine that "scarlet" is a kind of red, because "scarlet" never appears in its training data.
WordNet supplies the candidate; the conversation supplies the proof. WordNet never decides anything.

A proposal is NEVER silently accepted. If the user does not confirm it, the word stays unknown and the engine
keeps abstaining on it.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DICT = os.path.join(os.path.dirname(HERE), "_nldata", "dict")
_CACHE = {}


def _index(pos):
    """word -> [synset offsets], parsed once."""
    key = f"index.{pos}"
    if key in _CACHE: return _CACHE[key]
    idx = {}
    p = os.path.join(DICT, key)
    if os.path.exists(p):
        for line in open(p, encoding="latin-1"):
            if line.startswith(" "): continue
            f = line.split()
            if len(f) < 4: continue
            w = f[0]
            offs = [x for x in f if len(x) == 8 and x.isdigit()]
            if offs: idx[w] = offs
    _CACHE[key] = idx
    return idx


def _data(pos):
    """synset offset -> (lemmas, pointer offsets), parsed once."""
    key = f"data.{pos}"
    if key in _CACHE: return _CACHE[key]
    out = {}
    p = os.path.join(DICT, key)
    if os.path.exists(p):
        for line in open(p, encoding="latin-1"):
            if line.startswith(" "): continue
            head = line.split("|")[0].split()
            if len(head) < 4: continue
            off = head[0]
            try: wcount = int(head[3], 16)
            except ValueError: continue
            lemmas = []
            i = 4
            for _ in range(wcount):
                if i >= len(head): break
                lemmas.append(head[i].split("(")[0].lower().replace("_", " "))
                i += 2
            ptrs = [t for t in head[i:] if len(t) == 8 and t.isdigit()]
            out[off] = (lemmas, ptrs)
    _CACHE[key] = out
    return out


def related_words(word, pos="adj", hops=1):
    """every lemma in the word's synsets, plus one hop along pointers (similar-to, etc.)."""
    idx, dat = _index(pos), _data(pos)
    offs = list(idx.get(word.lower(), []))
    seen, out = set(), set()
    frontier = offs
    for _ in range(hops + 1):
        nxt = []
        for o in frontier:
            if o in seen or o not in dat: continue
            seen.add(o)
            lem, ptrs = dat[o]
            out.update(lem)
            nxt.extend(ptrs)
        frontier = nxt
    out.discard(word.lower())
    return out


# ---------------------------------------------------------------- SPEECH ACTS
# An earlier version of this engine refused "hello" as an unknown word. That was wrong, and the reason it was
# wrong is worth stating: the soundness discipline exists to stop the engine COMMITTING TO FALSE CLAIMS ABOUT
# THE WORLD. A greeting makes no claim -- there are no truth conditions to get wrong -- so the discipline
# simply does not apply, and refusing was over-application, not rigour.
#
# WordNet already classifies these: "hello" is in noun.communication with the gloss "an expression of
# greeting". So the act TYPE is looked up, not hardcoded per word. What IS supplied is the small map from a
# gloss phrase to an act type below; that generalises to any word WordNet glosses the same way (howdy,
# hiya, farewell, cheers all work without being listed), but it is my mapping and not induced.
LEX_COMMUNICATION = 10
# Patterns read OFF the actual glosses in this WordNet build, not invented:
#   hello    "an expression of greeting"
#   welcome  "a greeting or reception"
#   goodbye  "a farewell remark"
#   farewell "an acknowledgment or expression of goodwill at parting"
#   thanks   "an acknowledgment of appreciation"
#   sorry    "feeling or expressing regret or sorrow ..."   (an ADJECTIVE, so adjectives are checked too)
ACT_PATTERNS = [
    ("greeting", ["greeting"]),
    ("farewell", ["farewell", "at parting", "leave-taking", "departing politely"]),
    ("thanks", ["acknowledgment of appreciation", "gratitude"]),
    ("apology", ["regret", "apology"]),
]


def _synsets_with_gloss(word, pos):
    """(lex_filenum, gloss) for each synset of the word."""
    idx = _index(pos)
    offs = set(idx.get(word.lower(), []))
    if not offs: return []
    out = []
    p = os.path.join(DICT, f"data.{pos}")
    if not os.path.exists(p): return []
    for line in open(p, encoding="latin-1"):
        if line[:8] in offs:
            head, _, gloss = line.partition("|")
            f = head.split()
            if len(f) > 1:
                try: out.append((int(f[1]), gloss.strip()))
                except ValueError: pass
    return out


def speech_act(word):
    """Is this word a conversational move rather than a claim? -> (act_type, gloss) or None.

    Looked up, not listed: any word WordNet glosses this way qualifies. Nouns are restricted to the
    communication lexicographer file; adjectives are checked too because "sorry" is glossed as an adjective
    ("feeling or expressing regret"), which the noun-only first version missed."""
    for pos, restrict in (("noun", True), ("adj", False)):
        for lex, gloss in _synsets_with_gloss(word, pos):
            if restrict and lex != LEX_COMMUNICATION: continue
            g = gloss.lower()
            for act, pats in ACT_PATTERNS:
                if any(pt in g for pt in pats):
                    return act, gloss.split(";")[0].strip()
    return None


def propose(word, known_words, pos_order=("adj", "noun"), hops=1):
    """PROPOSE candidate known-words for an unknown word. Returns [(known_word, via_pos)] -- never commits.

    hops=1 follows one pointer (needed for adjectives: scarlet is "similar to" red, not a synonym of it).
    hops=0 is SAME-SYNSET ONLY, i.e. strict synonymy. Verbs need the strict setting: at hops=1 WordNet's
    polysemy produced junk bridges -- "can" -> remove (via canning) and "find" -> grow (via "come to be") --
    which would have had the engine asking to learn function words as actions. Measured: at hops=0, erase and
    expand still bridge correctly while can/find/hello propose nothing."""
    props = []
    for pos in pos_order:
        rel = related_words(word, pos, hops=hops)
        for kw in known_words:
            if kw in rel and kw not in [p[0] for p in props]:
                props.append((kw, pos))
    return props


if __name__ == "__main__":
    known = ["red", "blue", "green", "yellow", "purple", "orange",
             "square", "wide", "tall", "tiny", "small", "big", "huge"]
    print("ACQUIRE: WordNet PROPOSES a meaning for a word the engine never learned.")
    print("It never decides -- the engine still has to ask, and an unconfirmed proposal is discarded.\n")
    print(f"  {'unknown word':16s} {'WordNet proposes':38s} status")
    for w in ["scarlet", "crimson", "azure", "emerald", "enormous", "minuscule", "gigantic",
              "flibbertigibbet", "quantum"]:
        p = propose(w, known)
        shown = ", ".join(f"{k} (via {v})" for k, v in p[:3]) if p else "-"
        status = "-> ask the user to confirm" if p else "-> nothing proposed; stays unknown, keeps abstaining"
        print(f"  {w:16s} {shown:38s} {status}")
