"""C1 -- CONSTRUCTIONS FROM EXPOSURE, ORDER INCLUDED (construct_prereg.md). Zero LLM. Offline: the crawl store, the
Wiktionary store, the text model.

Usage:  python construct.py"""
import os, sys, json, time, random, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.constructions import Constructions, FORWARD, BACKWARD
from core.textmodel import TextModel
from core.registry import selfcheck
from textmodel import MODEL, KAIKKI, held

T0 = time.time()
CRAWL = os.path.join(HERE, "_nldata", "wikidata_crawl.sqlite")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


class Store:
    """the crawl in id form: label index, item claims, property labels"""
    def __init__(self, path=CRAWL):
        db = sqlite3.connect(path); self.lab = {}; self.claims = {}
        for q, l in db.execute("select q, label from lab"):
            if l: self.lab[q] = l
        self.inverse = {}
        for q, l, cl in db.execute("select q, label, claims from ent"):
            if l: self.lab[q] = l
            if q.startswith("P"):                  # run 5: the store's own inverse-property claims
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

    def canon(self, p, d):
        """run 5: (p, d) and (inverse of p, the other direction) are one meaning; -> the canonical form"""
        q = self.inverse.get(p)
        if q is None or p <= q: return (p, d)
        return (q, BACKWARD if d == FORWARD else FORWARD)

    def types(self, A):
        """run 5: the 'instance of' values of a mention's entities (at most 3 per entity)"""
        return {t for a in sorted(A) for t in sorted(self.claims.get(a, {}).get("P31", ()))[:3]} or {"?"}      # sorted: deterministic

    def relations(self, A, B):
        """-> set of canonical (property, direction) holding from a mention set A to B"""
        return {self.canon(p, d) for p, d in self._relations(A, B)}

    def _relations(self, A, B):
        out = set()
        for a in A:
            for p, vs in self.claims.get(a, {}).items():
                if vs & B: out.add((p, FORWARD))
        for b in B:
            for p, vs in self.claims.get(b, {}).items():
                if vs & A: out.add((p, BACKWARD))
        return out

    def holds(self, A, B, p, d):
        return self.canon(p, d) in self.relations(A, B)

    def known(self, A, B, d):
        S = A if d == FORWARD else B
        return any(self.claims.get(s) for s in S)


def mentions(syms, store, common):
    """greedy longest runs of 1-4 symbols equal to a stored label -> [(start, end, qids)]"""
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
    """run 4: -> (letter/digit symbols, mentions over them, the full token list WITH punctuation and its map). Mentions are
    matched on letters and digits; a run is read from the full list (punctuation is form)."""
    from core.resolve import segment
    import unicodedata
    full = [t.lower() for t in segment(s) if unicodedata.category(t[0])[0] in "LNP"]
    pos = [k for k, t in enumerate(full) if unicodedata.category(t[0])[0] in "LN"]
    syms = [full[k] for k in pos]
    return syms, mentions(syms, store, common), (full, pos)


def instances(syms, ms, head, store, max_len=5, full=None):
    """-> [(run, A, B)] for adjacent mention pairs (the headword first, at the sentence start). With `full` (run 4) the
    run is the full token list between the mentions, punctuation included."""
    out = []
    pts = ([(0, 0, head)] if head else []) + ms
    for x in range(len(pts) - 1):                 # run 2: adjacent mentions only
        a, b = pts[x], pts[x + 1]
        if full is None: run = syms[a[1]:b[0]]
        else:
            ft, pos = full
            lo = pos[a[1] - 1] + 1 if a[1] > 0 else 0; hi = pos[b[0]] if b[0] < len(pos) else len(ft)
            run = ft[lo:hi]
        if len(run) > max_len: continue
        out.append((tuple(run), a, b))
    return out


def main():
    selfcheck(__file__)
    say("C1  CONSTRUCTIONS FROM EXPOSURE, ORDER INCLUDED (construct_prereg.md)\n")
    store = Store(); tm = TextModel.load(MODEL); common = {w for w, c in tm.uni.most_common(1000)}
    plab = {q: l for q, l in store.lab.items() if q.startswith("P")}
    say(f"    store: {len(store.claims)} entities with claims, {len(store.index)} labels  ({time.time() - T0:.0f} s)")
    db = sqlite3.connect(KAIKKI)
    train_inst = []; test_inst = []; test_sents = []; n_sent = 0
    for w, v in db.execute("select w, v from e"):
        e = json.loads(v); head = store.index.get(" ".join(symbols(w, "LN")))
        test = held(w)
        for s in [str(x) for x in e.get("defs", [])] + [str(x) for x in e.get("ex", [])]:
            syms, ms, full = tokens(s, store, common); n_sent += 1
            if not ms: continue
            for run, a, b in instances(syms, ms, head if s in e.get("defs", []) else None, store, full=full):
                labels = store.relations(a[2], b[2])
                (test_inst if test else train_inst).append((run, a, b, labels, syms))
    say(f"    sentences {n_sent}; pair instances train {len(train_inst)}, held-out {len(test_inst)}  ({time.time() - T0:.0f} s)")
    def typed(run, a, b):                          # run 5: the run keyed with each combination of slot types
        return [(ta, tb) + tuple(run) for ta in sorted(store.types(a[2])) for tb in sorted(store.types(b[2]))][:9]

    def rank(Q): return sorted(Q, key=lambda q: (-len(store.claims.get(q, {})), q))[:1]        # run 7: the best-known entity only

    def read(C, run, a, b):
        """run 6: per entity pair -- a label is read with the pairs whose own types admit it; -> [(lab, pairs)]"""
        labs = {}
        for qa in rank(a[2]):
            for qb in rank(b[2]):
                for key in typed(run, (0, 0, {qa}), (0, 0, {qb})):
                    for lab, h, n in C.read(key): labs.setdefault(lab, set()).add((qa, qb))
        return sorted(labs.items(), key=lambda x: str(x[0]))
    C = Constructions(max_len=7)
    def best(m): return (m[0], m[1], set(rank(m[2])))
    train_inst = [(run, best(a), best(b), store.relations(rank(a[2]) and set(rank(a[2])), set(rank(b[2]))), syms) for run, a, b, labels, syms in train_inst]
    test_inst = [(run, best(a), best(b), store.relations(set(rank(a[2])), set(rank(b[2]))), syms) for run, a, b, labels, syms in test_inst]
    for run, a, b, labels, syms in train_inst:
        for key in typed(run, a, b): C.observe(key, labels)
    n_adm = C.settle(); rels = C.relations()
    say(f"    admitted constructions {n_adm} over {len(rels)} relations")
    top = sorted(C.admitted.items(), key=lambda x: -x[1][0][1])[:25]
    for run, lst in top: say(f"      {' '.join(run[1:]) + ' ' + run[0] if len(run) > 1 else '(adjacent)':28s} -> {plab.get(lst[0][0][0], lst[0][0][0])} {lst[0][0][1]}  {lst[0][1]}/{lst[0][2]}")
    fails = []
    r1 = len(rels) >= 20
    say(f"R1  relations covered: {len(rels)}   [>= 20 -> {'PASS' if r1 else 'FAIL'}]")
    if not r1: fails.append("R1")
    # ---- R2 precision, R3 recall on held-out
    ext = right = 0; related = got = 0; ex = []
    for run, a, b, labels, syms in test_inst:
        reads = read(C, run, a, b)
        if labels:
            related += 1
            got += any(lab in labels for lab, pairs in reads)
        for (p, d), pairs in reads:
            if not any(store.known({qa}, {qb}, d) for qa, qb in pairs): continue
            ext += 1; ok = any(store.holds({qa}, {qb}, p, d) for qa, qb in pairs); right += ok
            if len(ex) < 8: ex.append(f"      {' '.join(syms)[:90]!r}: {'/'.join(sorted(store.lab.get(q, q) for q in a[2]))[:20]} -[{plab.get(p, p)} {d}]- {'/'.join(sorted(store.lab.get(q, q) for q in b[2]))[:20]} {'OK' if ok else 'WRONG'}")
    for x in ex: say(x)
    prec = right / max(1, ext); rec = got / max(1, related)
    r2 = prec >= 0.85; r3 = rec >= 0.15
    say(f"R2  held-out precision {right}/{ext} = {prec:.3f}   [>= 0.85 -> {'PASS' if r2 else 'FAIL'}]")
    say(f"R3  held-out related instances read with the right relation and direction: {got}/{related} = {rec:.3f}   [>= 0.15 -> {'PASS' if r3 else 'FAIL'}]")
    if not r2: fails.append("R2")
    if not r3: fails.append("R3")
    # ---- R4 order: the two mentions swapped (the run between them unchanged), headword pairs excluded
    swapped = false = 0
    for run, a, b, labels, syms in test_inst:
        if not labels or a[0] == a[1]: continue
        swapped += 1
        for (p, d), pairs in read(C, run, b, a):
            if any(store.known({x}, {y}, d) for x, y in pairs) and not any(store.holds({x}, {y}, p, d) for x, y in pairs):
                false += 1
                if false <= 6: say(f"      swap false: {' '.join(syms)[:70]!r} run {' '.join(run)!r}: {'/'.join(sorted(store.lab.get(q, q) for q in b[2]))[:18]} -[{plab.get(p, p)} {d}]- {'/'.join(sorted(store.lab.get(q, q) for q in a[2]))[:18]}")
                break
    r4 = false <= 0.02 * max(1, swapped)
    say(f"R4  swapped instances asserting a false triple: {false}/{swapped}   [<= 2 % -> {'PASS' if r4 else 'FAIL'}]")
    if not r4: fails.append("R4")
    # ---- R5 knockout
    labs = [labels for run, a, b, labels, syms in train_inst]; random.Random(5).shuffle(labs)
    K = Constructions(max_len=7)
    for (run, a, b, _, syms), labels in zip(train_inst, labs):
        for key in typed(run, a, b): K.observe(key, labels)
    nk = K.settle()
    r5 = nk < 0.15 * max(1, n_adm)
    say(f"R5  knockout admitted {nk} vs {n_adm}   [< 15 % -> {'PASS' if r5 else 'FAIL'}]")
    if not r5: fails.append("R5")
    src = open(os.path.join(HERE, "core", "constructions.py"), encoding="utf-8").read().lower()
    r6 = not any(f'"{t}"' in src for t in ("of", "the", "in", "capital", "country"))
    say(f"R6  core/constructions.py holds no word of any language: {r6}   [{'PASS' if r6 else 'FAIL'}]")
    if not r6: fails.append("R6")
    say(f"\nC1: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
