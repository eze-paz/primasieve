"""A text model of the NARRATIVE training books (booktm_prereg.md): the same counts as core/textmodel.TextModel, learned from
the Gutenberg training books (never the held-out ones) instead of the dictionary-heavy text the main model read. Used by
the story learners for slot sharing. Never imported by core/."""
import os, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core.textmodel import TextModel

PATH = os.path.join(HERE, "..", "_nldata", "textmodel_books.json")
_TM = {}


def book_tm(n_books=120):
    if "tm" in _TM: return _TM["tm"]
    if os.path.exists(PATH): _TM["tm"] = TextModel.load(PATH); return _TM["tm"]
    import kb_events as KE
    sents = []
    for b in KE.books(False)[:n_books]:
        text = open(os.path.join(KE.GUT, b + ".txt"), encoding="utf-8", errors="replace").read()
        sents += [s for s in re.split(r"(?<=[.!?])\s+", text) if 3 <= len(s.split()) <= 80]
    tm = TextModel(); tm.learn(sents); tm.save(PATH); _TM["tm"] = tm
    return tm
