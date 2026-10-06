"""The crawl store (65,263 entities) as an OFFLINE fetcher for core/research.py (breadth_prereg.md run 2): a name nothing
else read -> its best-known stored entities with their claims, labelled. Quoted ("store"). Never imported by core/."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kb_crawl import Crawl


class StoreFetcher:
    quotes = True
    name = "store"
    local = True                  # research3_prereg.md: an index on disk -- not rationed like a web lookup
    namesakes_ask = True          # near-equal namesakes are READINGS, not the first in the list

    def __init__(self, max_entities=4, max_values=8, closed=()):
        self.c = Crawl(); self.max_entities, self.max_values = max_entities, max_values
        self.closed = set(closed)                   # natural_prereg.md (7): a span of closed-class symbols only is never a name
        import collections
        sys.path.insert(0, os.path.join(HERE, ".."))
        from core.reason import symbols
        self.symbols = symbols; self.index = collections.defaultdict(set)      # labels as the reader sees them: "lenta.ru" -> "lenta ru"
        for q, l in self.c.db.execute("select q, label from ent where label is not null"):
            k = " ".join(symbols(l, "LN"))
            if k: self.index[k].add((q, l))

    def fetch(self, symbol):
        if all(t in self.closed for t in self.symbols(symbol, "LN")): return None
        ents = [(q, l, "") for q, l in sorted(self.index.get(" ".join(self.symbols(symbol, "LN")), ()))]
        if not ents: return None
        ranked = sorted(ents, key=lambda e: (-len(self.c.claims(e[0])), e[0]))[:self.max_entities]
        # research2_prereg.md run 2: a name means its best-known thing only when it is CLEARLY best known (at least twice
        # the claims of the next); otherwise every near-equal namesake is kept, and the world asks which one is meant
        self.last_guessed = False
        if len(ranked) > 1:
            top = len(self.c.claims(ranked[0][0])); nxt = len(self.c.claims(ranked[1][0]))
            if top >= 2 * max(1, nxt):
                ranked = ranked[:1]; self.last_guessed = True       # the referent is a GUESS (the best-known of several namesakes)
            else: ranked = [e for e in ranked if 2 * len(self.c.claims(e[0])) >= top]
        data = {}
        for q, label, _ in ranked:
            cl = {}
            for p, vs in self.c.claims(q).items():
                pl = self.c.label(p)
                vals = [self.c.label(v) for v in vs[:self.max_values]]
                vals = [v for v in vals if v and not (v[:1] == "Q" and v[1:].isdigit())]
                if pl and not pl.startswith("P") and vals: cl[pl] = vals
            if cl: data[q] = dict(label=label, aliases=[symbol], desc="", claims=cl)
        if data and self.last_guessed: data = {q: dict(e, referent_guessed=True) for q, e in data.items()}
        return ("graph", data) if data else None
