"""The guesser's data step (guess_prereg.md): the crawl store in LABEL form, the rules learned from it (saved, so the
chat opens without relearning), and the store's label table for the session's claims. Never imported by core/."""
import os, sys, json, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core.guesser import Guesser, text_cues

DB = os.path.join(HERE, "..", "_nldata", "wikidata_crawl.sqlite")
RULES = os.path.join(HERE, "..", "_nldata", "guesser_rules_text.json")      # facts + names + definitions (guess_text_prereg.md)
KAIKKI = os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite")
TARGETS = ["country", "instance of", "country of citizenship", "sex or gender", "occupation", "continent",
           "country of origin", "language of work or name"]


def labels(path=DB):
    db = sqlite3.connect(path); lab = {}
    for q, l in db.execute("select q, label from lab"): lab[q] = l
    for q, l in db.execute("select q, label from ent"):
        if l: lab[q] = l
    return lab


def load_entities(path=DB, lab=None):
    """-> [(qid, label, {property label: [value labels]})] for every item entity of the crawl"""
    lab = lab if lab is not None else labels(path)
    out = []
    for q, l, cl in sqlite3.connect(path).execute("select q, label, claims from ent"):
        if not q.startswith("Q") or not l: continue
        claims = {}
        for p, vs in json.loads(cl).items():
            pl = lab.get(p)
            if pl: claims[pl] = [lab.get(v, v) for v in vs]
        out.append((q, l, claims))
    return out


_kdb = None


def definitions(word, k=3):
    """the first k Wiktionary definitions of a word, joined ('' when the store or the entry is absent)"""
    global _kdb
    if not os.path.exists(KAIKKI): return ""
    if _kdb is None: _kdb = sqlite3.connect(KAIKKI)
    r = _kdb.execute("select v from e where w=?", (str(word).lower(),)).fetchone()
    return " ".join(json.loads(r[0]).get("defs", [])[:k]) if r else ""


def build_guesser(rules=RULES, path=DB):
    """-> a Guesser with the label table injected; None when the crawl store is absent"""
    if not os.path.exists(path): return None
    lab = labels(path)
    if os.path.exists(rules): G = Guesser.load(rules)
    else:
        G = Guesser(TARGETS); G.learn([(l, dict(c, **text_cues(definitions(l)))) for _, l, c in load_entities(path, lab)]); G.save(rules)
    G.labels = lab
    return G
