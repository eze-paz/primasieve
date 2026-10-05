"""The dictionary's statements of sameness for core/synonyms.py (synonyms_prereg.md): Wiktionary synonym lists and
one-word definitions, made symmetric; cached so the live chat opens without the 20-second pass. Never imported by core/."""
import os, sys, json, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core.reason import symbols

KAIKKI = os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite")
CACHE = os.path.join(HERE, "..", "_nldata", "synonyms_same.json")


def dictionary_same(closed):
    """the dictionary's statements of sameness: Wiktionary synonym lists, and one-word definitions; made symmetric"""
    same = collections.defaultdict(set); db = sqlite3.connect(KAIKKI)
    for w, v in db.execute("select w, v from e"):
        if not w.isalpha(): continue
        e = json.loads(v)
        for x in e.get("syn", []):
            if x.isalpha() and x != w: same[w].add(x)
        for d in e.get("defs", []):
            ss = symbols(str(d), "LN"); opn = [t for t in ss if t not in closed]
            if len(ss) <= 2 and len(opn) == 1 and opn[0].isalpha() and opn[0] != w: same[w].add(opn[0])
    for w in list(same):
        for x in list(same[w]): same[x].add(w)
    return same


def load_same(closed):
    if os.path.exists(CACHE): return {k: set(v) for k, v in json.load(open(CACHE, encoding="utf-8")).items()}
    same = dictionary_same(closed)
    json.dump({k: sorted(v) for k, v in same.items()}, open(CACHE, "w", encoding="utf-8"))
    return same
