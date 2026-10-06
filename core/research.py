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
    def __init__(self, fetchers, folder, df=None, budget=400, per_turn=None):
        self.fetchers = list(fetchers); self.folder = folder; self.df = df; self.budget = budget
        self.per_turn = per_turn      # at most this many fetch attempts in one turn (a story sentence is full of unread words)
        self.tried = {}                 # (fetcher name, symbol) -> path | None
        self.attached = []              # (fetcher name, symbol, path)
        os.makedirs(folder, exist_ok=True)

    # ---- what a turn left unread: spans of symbols no non-quoting world read (longest first, no numerals) -------------
    def weak_spans(self, frame, maxlen=3):
        """research2_prereg.md: for a turn nothing answered -- spans read only by NON-content readings (an entity, a filter
        value) or by fetched worlds, longest first, letters only"""
        syms = frame.get("syms", []); n = len(syms); strong = set()
        for r, w in zip(frame.get("readings", []), frame.get("reading_worlds", [])):
            if getattr(w, "quotes", False) or getattr(w, "fetched", None) or r[0] >= n: continue
            if r[2] in getattr(w, "content_kinds", set()): strong.update(range(r[0], min(r[1], n)))
        med = None
        if self.df is not None and n:
            vals = sorted(self.df(x) for x in syms); med = vals[len(vals) // 2]
        out = []
        for L in range(maxlen, 0, -1):
            for i in range(n - L + 1):
                span = range(i, i + L)
                if all(p not in strong for p in span) and all(unicodedata.category(syms[p][0])[0] == "L" for p in span):
                    if med is not None and all(self.df(syms[p]) > med for p in span): continue
                    out.append(" ".join(syms[i:i + L]))
        return out

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
    def research(self, session, frame, weak=False):
        """-> [worlds attached this turn]. Budgeted; one fetch per (fetcher, symbol) per session. With `weak`
        (research2_prereg.md), the spans of weak_spans are offered after the unread ones."""
        new = []; taken = []; tries = 0
        # research3_prereg.md: a LOCAL fetcher (an index on disk) is not rationed like the web -- no budget, no per-turn
        # cap, spans up to 6 symbols; online fetchers keep every limit
        local = [f for f in self.fetchers if getattr(f, "local", False)]
        online = [f for f in self.fetchers if not getattr(f, "local", False)]
        spans = self.unread_spans(frame)
        if weak: spans += [x for x in self.weak_spans(frame) if x not in spans]
        lspans = self.unread_spans(frame, maxlen=6) if local else []
        if local and weak: lspans += [x for x in self.weak_spans(frame, maxlen=6) if x not in lspans]
        plan = [(sp, local, True) for sp in lspans] + [(sp, online, False) for sp in spans]
        for span, fs, is_local in plan:
            if not is_local and self.per_turn is not None and tries >= self.per_turn: break
            if any(span in t for t in taken): continue          # a span inside a name that attached is that name's part, not a thing
            for f in fs:
                key = (f.name, span)
                if key in self.tried or (not is_local and len([k for k in self.tried if k[0] in self._online_names()]) >= self.budget): continue
                if not is_local: tries += 1
                got = None
                try: got = f.fetch(span)
                except Exception: got = None
                if not got: self.tried[key] = None; continue
                shape, data = got
                path = os.path.join(self.folder, f"{f.name}-{abs(hash(span)) % 10**8}.json")
                with open(path, "w", encoding="utf-8") as fh: json.dump(dict(shape=shape, symbol=span, source=f.name, data=data, namesakes_ask=bool(getattr(f, "namesakes_ask", False))), fh, ensure_ascii=False, indent=1)
                self.tried[key] = path
                w = self.attach(session, path, f)
                if w is not None: new.append(w); self.attached.append((f.name, span, path)); taken.append(span)
        return new

    def _online_names(self): return {f.name for f in self.fetchers if not getattr(f, "local", False)}

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
        if d["shape"] == "graph" and any(e.get("referent_guessed") for e in d["data"].values()):
            w.conjectured = lambda st: True    # the name has other namesakes; this one is the best-known -- an answer through it is a guess
        if getattr(fetcher, "namesakes_ask", False) or d.get("namesakes_ask"):
            # the fetcher kept only near-equal namesakes: no order among them (READINGS), and below any world's own order --
            # a constant 0 OUTRANKED the fixture's search order (its keys are negative), so a replica "Statue of Liberty"
            # chained through a fetched world beat the real one (research2_prereg.md run 2's defect)
            w.rank_key = lambda st: -10 ** 6
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
