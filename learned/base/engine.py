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
        if reader:
            import battery; self.R = battery.door().events.reader
        from reader_check import parse_q, match
        self.parse_q, self.match = parse_q, match

    def load_text(self, text): self.store = Store(text)

    def _reader_answer(self, question, hits):
        p = self.parse_q(question)
        if p is None or self.R is None: return None
        role, verb, other = p; other_role = "patient" if role == "agent" else "agent"
        for i, h in hits:
            for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", h):
                try: evs = [e for e in self.R.read(s) if e.get("agent") and e.get("patient")]
                except Exception: evs = []
                for e in evs:
                    v_ok = verb is None or (self.R.verbs.get(verb.lower()) == e["verb"] or verb.lower().startswith(e["verb"][:4]))
                    o_ok = self.match(other, e[other_role]) or any(w in e[other_role].lower().split() for w in other.lower().split() if len(w) > 3)
                    if v_ok and o_ok: return e[role], (i, h)
        return None

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
