"""KB-GEOMETRY -- a language model's WEIGHTS as a designated knowledge source. ZERO LLM at run time, pure stdlib.

E-11 (em_weights*.py) read Qwen2.5-0.5B's embedding table as a world and found exact-up-to-eps structure with
knockouts at zero: morphology is a translation (plural 0.92, 3rd-person 0.94 nearest-neighbour accuracy; shuffled
pairs 0.000), synonyms sit in the top-10 neighbours 35% of the time (random words 0%), and the plural operator
INJECTED into the model's residual stream steers its next word to a plural on 14/20 prompts (random direction 0).

So the table is a lexicon with relational operators, and the engine can consult it the way it consults WordNet or
Wiktionary: as an ATTRIBUTED source. What it says is held on ITS word with a certificate (the neighbour list, the
neighbour verbatim in it), never as verified; the world or a corroborating source upgrades or retracts it. The
geometry is READ, not run: `_nldata/qwen_geometry.sqlite` is built once by `emergence/em_weights3.py` in the numpy
environment (like the Wiktionary index is built once from the download); this module is stdlib sqlite.

Reading rule (like MOBY's): a neighbour that IS an anchor word proposes that anchor's predicate; corroboration
only -- the source is loose (neighbours are also antonyms, co-hyponyms, spelling variants), so a bulk pass admits
its word only when a second source agrees, and the chat states the caveat when it is the only voice."""
import os, json, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.path.dirname(HERE), "_nldata", "qwen_geometry.sqlite")
SOURCE_ID = "WEIGHTS-qwen2.5-0.5b"
_CON = {}


def _con():
    if "c" not in _CON:
        _CON["c"] = sqlite3.connect(DB, check_same_thread=False) if os.path.exists(DB) else None
    return _CON["c"]


def neighbours(word):
    """[(neighbour, cosine)] by the model's own geometry, or None when the source is not built."""
    c = _con()
    if c is None: return None
    r = c.execute("select neighbours from nn where w=?", (word.lower(),)).fetchone()
    return json.loads(r[0]) if r else []


def apply_operator(word, op):
    """the form the model's geometry gives for `op` in {plural, 3sg, prog, past} applied to `word`, or None."""
    c = _con()
    if c is None: return None
    r = c.execute("select form from op where w=? and op=?", (word.lower(), op)).fetchone()
    return r[0] if r else None


def src_geometry(word, anchors=None):
    """kb_sources' source shape -> [(span, text)] | None. The TEXT is the neighbour list (what was read); a SPAN is
    one neighbour that is an anchor word (lemma equality, MOBY's rule), so the certificate check is exact."""
    nb = neighbours(word)
    if nb is None: return None
    text = ", ".join(f"{w} {c:.3f}" for w, c in nb)
    if anchors is None: return [(text, text)]
    return [(w, text) for w, c in nb if w in anchors]


def geometry_read(span, anchors):
    s = span.strip()
    return {anchors[s]} if s in anchors else set()
