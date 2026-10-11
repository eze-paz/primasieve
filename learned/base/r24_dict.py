"""R24-ap: a dictionary the learner may consult at reading time (WordNet 3.1 database files in _nldata/dict).
Word knowledge is a source, like search: the learner looks a word up only when its own learned lexicon is silent.
Used for: whether an unknown word is mainly a verb (by WordNet's tagged-sense counts per part of speech), the base
form of an irregular verb (verb.exc: 'lent' -> 'lend'), and the base form of a regular one (WordNet's own suffix rules).
Off unless ON is set by the caller."""
import os, collections

HERE = os.path.dirname(os.path.abspath(__file__)); DICT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_nldata", "dict")
ON = False
IDX = {}            # (pos, lemma) -> tagged-sense count (how often that sense was seen in WordNet's tagged corpus)
EXC = {}            # irregular verb form -> base
VERB_SUFFIX = [("ies", "y"), ("es", "e"), ("es", ""), ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", ""), ("s", "")]


def load():
    if IDX: return
    for pos, f in (("v", "index.verb"), ("n", "index.noun"), ("a", "index.adj"), ("r", "index.adv")):
        for line in open(os.path.join(DICT, f), encoding="utf-8", errors="replace"):
            if line.startswith(" "): continue
            p = line.split(); lemma = p[0]; pcnt = int(p[3]); tag = int(p[5 + pcnt])
            IDX[(pos, lemma)] = tag
    for line in open(os.path.join(DICT, "verb.exc"), encoding="utf-8", errors="replace"):
        p = line.split()
        if len(p) >= 2: EXC.setdefault(p[0], p[1])


def verb_base(w):
    """the verb base of a word form, or None if the dictionary does not know it as a verb"""
    load(); w = w.lower()
    if w in EXC: return EXC[w]
    if ("v", w) in IDX: return w
    for suf, rep in VERB_SUFFIX:
        if w.endswith(suf) and ("v", w[: -len(suf)] + rep) in IDX: return w[: -len(suf)] + rep
    return None


def mainly_verb(w):
    """True when the dictionary knows the word as a verb and, for a bare form, its verb senses are tagged more often
    than its noun / adjective senses ('spin', 'lend' yes; 'doctor', 'dusk', 'open' no)"""
    load(); w = w.lower(); b = verb_base(w)
    if b is None: return False
    if b != w: return True                                                   # an inflected form of a verb: 'spun', 'packed'
    v = IDX.get(("v", w), 0)
    return v > max(IDX.get(("n", w), 0), IDX.get(("a", w), 0), IDX.get(("r", w), 0))


def verb_forms():
    """every word form the dictionary reads as mainly a verb: the base forms and their irregular forms"""
    load(); out = {l for (pos, l) in IDX if pos == "v" and "_" not in l and mainly_verb(l)}
    out |= {f for f, b in EXC.items() if b in out}
    return out
