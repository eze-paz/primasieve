"""The comprehension reader's data side (construct_prereg.md, statements_prereg.md): the crawl store in id form, mention
finding, typed construction keys, learning from the Wiktionary sentences, and READING a statement into checked
propositions. Never imported by core/ (core/constructions.py holds the counting, no word of any language)."""
import os, sys, json, sqlite3, collections, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core.reason import symbols
from core.resolve import segment
from core.constructions import Constructions, FORWARD, BACKWARD

CRAWL = os.path.join(HERE, "..", "_nldata", "wikidata_crawl.sqlite")
KAIKKI = os.path.join(HERE, "..", "_nldata", "kaikki_all.sqlite")
SAVED = os.path.join(HERE, "..", "_nldata", "constructions.json")


class Store:
    """the crawl in id form: label index, item claims, property labels, inverse properties, types"""
    def __init__(self, path=CRAWL):
        db = sqlite3.connect(path); self.lab = {}; self.claims = {}; self.inverse = {}
        for q, l in db.execute("select q, label from lab"):
            if l: self.lab[q] = l
        for q, l, cl in db.execute("select q, label, claims from ent"):
            if l: self.lab[q] = l
            if q.startswith("P"):
                for v in json.loads(cl).get("P1696", []):
                    if v.startswith("P"): self.inverse[q] = v; self.inverse.setdefault(v, q)
            if q.startswith("Q"):
                d = {}
                for p, vs in json.loads(cl).items():
                    items = {v for v in vs if v.startswith("Q")}
                    if items: d[p] = items
                self.claims[q] = d
        self.index = collections.defaultdict(set)
        for q, l in self.lab.items():
            if q.startswith("Q"):
                key = " ".join(symbols(l, "LN"))
                if key: self.index[key].add(q)

    def named(self, q):
        """a label with at least one letter or digit (the store holds labels made only of invisible marks)"""
        return any(ch.isalnum() for ch in self.lab.get(q, ""))

    def canon(self, p, d):
        q = self.inverse.get(p)
        if q is None or p <= q: return (p, d)
        return (q, BACKWARD if d == FORWARD else FORWARD)

    def types(self, A):
        return {t for a in sorted(A) for t in sorted(self.claims.get(a, {}).get("P31", ()))[:3]} or {"?"}

    def _relations(self, A, B):
        out = set()
        for a in A:
            for p, vs in self.claims.get(a, {}).items():
                if vs & B: out.add((p, FORWARD))
        for b in B:
            for p, vs in self.claims.get(b, {}).items():
                if vs & A: out.add((p, BACKWARD))
        return out

    def relations(self, A, B):
        return {self.canon(p, d) for p, d in self._relations(A, B)}

    def holds(self, A, B, p, d):
        return self.canon(p, d) in self.relations(A, B)

    def known(self, A, B, d):
        S = A if d == FORWARD else B
        return any(self.claims.get(s) for s in S)

    def contradicts(self, a, b, p, d):
        """the subject carries relation p (forward form) with values, none of them the object"""
        p, d = self.canon(p, d)
        S, O = (a, b) if d == FORWARD else (b, a)
        vals = {x for x in self.claims.get(S, {}).get(p, set()) if self.named(x)}    # an unnamed value cannot contradict anyone
        return bool(vals) and O not in vals


def mentions(syms, store, common):
    out, i = [], 0
    while i < len(syms):
        hit = None
        for L in (4, 3, 2, 1):
            if i + L > len(syms): continue
            key = " ".join(syms[i:i + L])
            if key in store.index and not (L == 1 and (key in common or not key.isalpha())):
                hit = (i, i + L, store.index[key]); break
        if hit: out.append(hit); i = hit[1]
        else: i += 1
    return out


def tokens(s, store, common):
    full = [t.lower() for t in segment(s) if unicodedata.category(t[0])[0] in "LNP"]
    pos = [k for k, t in enumerate(full) if unicodedata.category(t[0])[0] in "LN"]
    syms = [full[k] for k in pos]
    return syms, mentions(syms, store, common), (full, pos)


def instances(syms, ms, head, max_len=5, full=None):
    out = []
    pts = ([(0, 0, head)] if head else []) + ms
    for x in range(len(pts) - 1):
        a, b = pts[x], pts[x + 1]
        if full is None: run = syms[a[1]:b[0]]
        else:
            ft, pos = full
            lo = pos[a[1] - 1] + 1 if a[1] > 0 else 0; hi = pos[b[0]] if b[0] < len(pos) else len(ft)
            run = ft[lo:hi]
        if len(run) > max_len: continue
        out.append((tuple(run), a, b))
    return out


def best(store, Q):
    """construct_prereg.md run 7: the one entity a mention denotes -- the one the store knows most about (ties by id)"""
    return sorted(Q, key=lambda q: (-len(store.claims.get(q, {})), q))[:1]


def typed(store, run, A, B):
    return [(ta, tb) + tuple(run) for ta in sorted(store.types(A)) for tb in sorted(store.types(B))][:9]


def save(C, path=SAVED):
    json.dump([[list(k), [[list(lab), h, n] for lab, h, n in v]] for k, v in C.admitted.items()], open(path, "w", encoding="utf-8"))


def load(path=SAVED):
    C = Constructions(max_len=7)
    C.admitted = {tuple(k): [(tuple(lab), h, n) for lab, h, n in v] for k, v in json.load(open(path, encoding="utf-8"))}
    return C


class Reader:
    """reads a statement into propositions over the store and checks each (statements_prereg.md)"""
    def __init__(self, store, C, common):
        self.store, self.C, self.common = store, C, common

    def propositions(self, text, head=None):
        """-> [dict(run, a, b, lab, pairs)]: lab = (relation, direction); pairs = the (entity, entity) whose own types
        admit the construction (disambiguation by construction)"""
        syms, ms, full = tokens(text, self.store, self.common)
        out = []
        for run, a, b in instances(syms, ms, head, full=full):
            labs = collections.defaultdict(set)
            rank = lambda Q: best(self.store, Q)                    # construct_prereg.md run 7: a name means its best-known thing
            for qa in rank(a[2]):
                for qb in rank(b[2]):
                    for key in typed(self.store, run, {qa}, {qb}):
                        for lab, h, n in self.C.read(key): labs[lab].add((qa, qb))
            for lab, pairs in labs.items():
                out.append(dict(run=run, a=a, b=b, lab=lab, pairs=sorted(pairs), syms=syms))
        return out

    def check(self, text, head=None):
        """-> (verdict, [(proposition, verdict)]) ; verdict in SUPPORTED / CONTRADICTED / UNKNOWN / UNREAD"""
        props = self.propositions(text, head); res = []
        for pr in props:
            p, d = pr["lab"]
            if any(self.store.holds({qa}, {qb}, p, d) for qa, qb in pr["pairs"]): v = "SUPPORTED"
            elif pr["pairs"] and all(self.store.contradicts(qa, qb, p, d) for qa, qb in pr["pairs"]): v = "CONTRADICTED"
            else: v = "UNKNOWN"
            res.append((pr, v))
        vs = [v for _, v in res]
        if not res: return "UNREAD", res
        if "CONTRADICTED" in vs: return "CONTRADICTED", res
        if all(v == "SUPPORTED" for v in vs): return "SUPPORTED", res        # run 2: every proposition, not one
        return "UNKNOWN", res


def book_sentences(paths):
    """novelgrammar_prereg.md: the sentences of the given book files"""
    import re as _re
    for p in paths:
        text = open(p, encoding="utf-8", errors="replace").read()
        for s in _re.split(r"(?<=[.!?])\s+", text):
            if 3 <= len(s.split()) <= 80: yield " ".join(s.split())


def learn(store, common, held=None, least=3, share=0.8, books=(), shuffle_books=None):
    """C1 run 5's learner over the Wiktionary sentences (training headwords only when `held` is given), and, with
    `books`, over those books' sentences too (novelgrammar_prereg.md); `shuffle_books` (a Random) shuffles the books'
    relation labels before counting -- the knockout"""
    C = Constructions(least=least, share=share, max_len=7); db = sqlite3.connect(KAIKKI)
    if books:
        inst = []
        for s in book_sentences(books):
            syms, ms, full = tokens(s, store, common)
            if len(ms) < 2: continue
            for run, a, b in instances(syms, ms, None, full=full):
                A, B = set(best(store, a[2])), set(best(store, b[2]))
                inst.append((typed(store, run, A, B), store.relations(A, B)))
        if shuffle_books is not None:
            labs = [l for k, l in inst]; shuffle_books.shuffle(labs); inst = [(k, l) for (k, _), l in zip(inst, labs)]
        for keys, labels in inst:
            for key in keys: C.observe(key, labels)
    for w, v in db.execute("select w, v from e"):
        if held is not None and held(w): continue
        e = json.loads(v); head = store.index.get(" ".join(symbols(w, "LN")))
        defs = [str(x) for x in e.get("defs", [])]
        for s in defs + [str(x) for x in e.get("ex", [])]:
            syms, ms, full = tokens(s, store, common)
            if not ms: continue
            for run, a, b in instances(syms, ms, head if s in defs else None, full=full):
                A, B = set(best(store, a[2])), set(best(store, b[2]))
                labels = store.relations(A, B)
                for key in typed(store, run, A, B): C.observe(key, labels)
    C.settle()
    return C
