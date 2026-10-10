"""The merged critical engine (R9), live: a text is the store; a question is answered by grep -> the hand-rule event
reader on the hits (authority) -> else the learned model's proposal (coverage) -> else "unknown". Every answer carries
its source: ("reader", hit) / ("model", hit) / ("unknown", None).
Usage:
    from engine import Engine
    E = Engine()                       # loads the R5 checkpoint and builds the hand-rule reader (about 2 min)
    E.load_text(open(book).read())
    E.ask("Who borrowed the boat?")    # -> dict(answer=..., source=..., query=..., hits=[...])
Run as a script for a demo on one B6 story:  python learned/base/engine.py"""
import os, sys, re, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import torch
from store import Store, render, query_for, entity_of
from rwkv7 import RWKV7, tokenizer

CKPT = os.path.join(HERE, "ckpt_read5_s400.pth")


class Engine:
    def __init__(self, ckpt=CKPT, reader=True):
        self.tok = tokenizer(); self.m = RWKV7.load(ckpt); self.m.eval(); self.store = None; self.R = None
        import reader_check; reader_check.set_version("v3"); self.rc = reader_check     # the matcher of R11 (roles + adjuncts)
        self.R = reader_check.R if reader else None

    def load_text(self, text): self.store = Store(text)

    def _reader_answer(self, question, hits):
        """the reader's answer through the R11 matcher (roles, appositive names, adjuncts), or None"""
        if self.R is None: return None
        prompt = render(question, "", hits)
        committed, ra = self.rc.check(dict(q=question, gold=[], prompt=prompt, reply=""))
        return (ra, None) if ra is not None else None

    def ask(self, question, k=3):
        assert self.store is not None, "load_text first"
        query = query_for(question); hits = self.store.grep(query, k, window=1, entity=entity_of(question))
        ra = self._reader_answer(question, hits)
        if ra: return dict(answer=ra[0], source="reader", query=query, hits=hits, hit=ra[1])
        prompt = render(question, query, hits)
        reply = self.tok.decode(self.m.greedy(torch.tensor([self.tok.encode(prompt)]), 10, tok=self.tok)).strip().split("\n")[0]
        if not reply or "unknown" in reply.lower() or not hits: return dict(answer="unknown", source="unknown", query=query, hits=hits)
        return dict(answer=reply, source="model", query=query, hits=hits)


if __name__ == "__main__":
    E = Engine(); s = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"][0]
    E.load_text(s["text"])
    for q, gold in s["qs"]:
        r = E.ask(q); print(f"{q} -> {r['answer']!r} [{r['source']}] (gold {gold[0]})")
