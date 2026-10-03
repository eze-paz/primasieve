"""RESEARCH -- an unread symbol becomes a fetch, a fetch becomes a world (research_prereg.md). Zero LLM. Holds no word, no
source name, no world: it iterates the FETCHERS a session was given, and what a fetch returns is held in a world of a data
shape the loop already reads (core.triples / core.table), named by the source.

A fetcher exposes `name`, `quotes` (True when it quotes, False when it computes) and `fetch(symbol) -> (shape, data) |
None`, shape in {"triples", "records"}. The residue drives it: after a turn that left symbols unread, every unread span
(longest first) is offered to every fetcher once per session; nothing is fetched twice; a fetch that returned nothing is
remembered. FETCHED CONTENT IS READINGS, NEVER TEACHING: it enters no world's pairs, is never read as a question, a
command or a feedback word; it can only become what a world reads a span as, under the certificate check. Fetched data
is written to a file so that the store can re-attach it (S8) and so that the evidence is inspectable."""
import json
import os
import unicodedata

from .kg import KGWorld
from .table import Table, Records, TableWorld
from .triples import Triples


class Researcher:
    def __init__(self, fetchers, folder, df=None, budget=400):
        self.fetchers = list(fetchers); self.folder = folder; self.df = df; self.budget = budget
        self.tried = {}                 # (fetcher name, symbol) -> path | None
        self.attached = []              # (fetcher name, symbol, path)
        os.makedirs(folder, exist_ok=True)

    # ---- what a turn left unread: spans of symbols no non-quoting world read (longest first, no numerals) -------------
    def unread_spans(self, frame, maxlen=3):
        """spans no non-quoting world read, longest first; with a df, a span whose every symbol sits above the question's
        median definition frequency is not a name (the graph world's A1) and is not fetched"""
        syms = frame.get("syms", []); n = len(syms); df = self.df
        med = None
        if df is not None and n:
            vals = sorted(df(x) for x in syms); med = vals[len(vals) // 2]
        read = set()
        for r, w in zip(frame.get("readings", []), frame.get("reading_worlds", [])):
            if getattr(w, "quotes", False) or r[2] in ("U", "X"): continue
            if r[0] < n: read.update(range(r[0], min(r[1], n)))
        out = []
        for L in range(maxlen, 0, -1):
            for i in range(n - L + 1):
                span = range(i, i + L)
                if all(p not in read for p in span) and all(unicodedata.category(syms[p][0])[0] == "L" for p in span):
                    if med is not None and all(df(syms[p]) > med for p in span): continue
                    out.append(" ".join(syms[i:i + L]))
        return out

    # ---- fetch, write, attach ---------------------------------------------------------------------------------------------
    def research(self, session, frame):
        """-> [worlds attached this turn]. Budgeted; one fetch per (fetcher, symbol) per session."""
        new = []; taken = []
        for span in self.unread_spans(frame):
            if any(span in t for t in taken): continue          # a span inside a name that attached is that name's part, not a thing
            for f in self.fetchers:
                key = (f.name, span)
                if key in self.tried or len(self.tried) >= self.budget: continue
                got = None
                try: got = f.fetch(span)
                except Exception: got = None
                if not got: self.tried[key] = None; continue
                shape, data = got
                path = os.path.join(self.folder, f"{f.name}-{abs(hash(span)) % 10**8}.json")
                with open(path, "w", encoding="utf-8") as fh: json.dump(dict(shape=shape, symbol=span, source=f.name, data=data), fh, ensure_ascii=False, indent=1)
                self.tried[key] = path
                w = self.attach(session, path, f)
                if w is not None: new.append(w); self.attached.append((f.name, span, path)); taken.append(span)
        return new

    def attach(self, session, path, fetcher=None):
        d = json.load(open(path, encoding="utf-8"))
        name = d["source"]                        # the SOURCE's name: the ledger's record belongs to a source, not to one of its entities
        if any(getattr(w, "fetched", None) == path for w in session.worlds): return None
        if d["shape"] == "graph":
            w = KGWorld(FetchedGraph(d["data"], name), self.df, name=name)
        elif d["shape"] == "triples":
            src = Triples(path, name); src.data = d["data"]; src.props = sorted({p for e in d["data"].values() for p in e})
            src.text = {e: json.dumps(cl, sort_keys=True) for e, cl in d["data"].items()}
            w = KGWorld(src, self.df, name=name)
        elif d["shape"] == "records":
            w = TableWorld(Records([Table(c["headers"], c["rows"], cn) for cn, c in d["data"].items()]), name=name, df=self.df)
        else: return None
        w.attributed = bool(getattr(fetcher, "quotes", True)) if fetcher is not None else d.get("quotes", True)
        w.fetched = path
        session.worlds.append(w)
        return w

    # ---- persistence: the store keeps the fetched files and re-attaches them ---------------------------------------------
    def evidence(self): return [list(x) for x in self.attached]

    def absorb(self, session, ev):
        for fname, span, path in ev:
            if os.path.exists(path):
                self.tried[(fname, span)] = path
                if self.attach(session, path) is not None: self.attached.append((fname, span, path))
        return len(self.attached)


class FetchedGraph:
    """a small graph source over fetched entities: {qid: {label, aliases, desc, claims {property label: [value labels]}}}.
    Several entities may answer to one name (the graph world's own rule: the question's property decides among them)."""

    def __init__(self, data, name):
        self.data = data; self.name = name; self.log = []
        self.props = sorted({p for e in data.values() for p in e.get("claims", {})})
        self.text = {q: json.dumps(e.get("claims", {}), sort_keys=True) for q, e in data.items()}
        self.labels = {q: e["label"] for q, e in data.items()}

    def entities(self, label):
        self.log.append((self.name, "item", label)); l = label.lower()
        return [(q, e["label"], e.get("desc", "")) for q, e in self.data.items() if e["label"].lower() == l or l in [a.lower() for a in e.get("aliases", [])]]

    def properties(self, label):
        self.log.append((self.name, "property", label))
        return [(label, label)] if label in self.props else []

    def claims(self, q): return {p: list(v) for p, v in self.data.get(q, {}).get("claims", {}).items()}

    def claims_text(self, q): return self.text.get(q, "")

    def label(self, x): return self.labels.get(x, x)

    def labelled(self, x): return isinstance(x, str) and bool(x)

    def consulted(self): return list(self.log)


class WikidataFetcher:
    """the existing Wikidata source as a fetcher: the top entities found by a name (several: the question's property
    decides), each with its claims with every id replaced by its label (one hop; the next hop is the loop's composition
    across worlds). Quotes."""
    quotes = True

    def __init__(self, source, name="wikidata-research", max_values=8, max_entities=4):
        self.source, self.name, self.max_values, self.max_entities = source, name, max_values, max_entities

    def fetch(self, symbol):
        ents = self.source.entities(symbol)
        if not ents: return None
        data = {}
        for qid, label, desc in ents[:self.max_entities]:
            claims = self.source.claims(qid)
            if not claims: continue
            cl = {}
            for p, vals in claims.items():
                pl = str(self.source.label(p)); labs = [str(self.source.label(v)) for v in vals[:self.max_values]]
                if pl and labs: cl.setdefault(pl, []).extend(labs)
            if desc: cl["description"] = [str(desc)]
            data[qid] = dict(label=str(label), aliases=[symbol], desc=str(desc or ""), claims=cl)
        return ("graph", data) if data else None
