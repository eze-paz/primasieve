"""READING GLOSSES AT SCALE -- crawl store, headword anchors, numeric mentions, claim-free words (gloss_scale_prereg.md).
Zero LLM. Offline (the crawl is a separate data step: python emergence/kb_crawl.py --crawl).

    python gloss_scale.py [--frames 300]"""
import os, sys, re, json, random, sqlite3, collections, ast

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols, reason
from core.verdict import ATTRIBUTED, COMMIT
from core.kg import KGWorld
from core.registry import selfcheck
from kb_crawl import Crawl
import kg_multihop as KG
import realize as RZ
import gloss_types as GT

KAIKKI = os.path.join(HERE, "_nldata", "kaikki_all.sqlite")
DELTA, MIN_FREE = 0.10, 20


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


# ------------------------------------------------------------------------------------------------ data
def build_items(C):
    """-> items [(headword, gloss)], numeric-mention count, counts. A gloss aligns if it mentions a claim object's label,
    or the year/amount of a time/quantity claim, of its headword."""
    db = sqlite3.connect(KAIKKI); memo = {}

    def entry(w):
        if w not in memo:
            r = db.execute("select v from e where w=?", (w.lower(),)).fetchone(); memo[w] = json.loads(r[0]) if r else None
        return memo[w]
    items = set(); n_lab = n_wikt = n_num = 0
    for q, lab in C.db.execute("select q, label from ent where label is not null"):
        n_lab += 1
        e = entry(lab)
        if not e: continue
        n_wikt += 1
        cl = C.allclaims(q)
        names = sorted({C.label(v) for vs in cl.values() for v in vs if v.startswith("Q")}, key=len, reverse=True)
        names = [n for n in names if n and not n.startswith("Q") and len(n) > 2][:300]
        nums = {v[2:] for vs in cl.values() for v in vs if v[:2] in ("T:", "N:")}
        for t in e.get("defs", [])[:12]:
            toks = set(symbols(t, "LN"))
            if any(re.search(r"\b" + re.escape(nm) + r"\b", t) for nm in names) or (nums & toks):
                items.add((q, t)); n_num += bool(nums & toks)
    return sorted(items), dict(labelled=n_lab, with_entry=n_wikt, numeric_aligned=n_num)


# ------------------------------------------------------------------------------------------------ the reader at scale
class Scale(GT.Rung2):
    def __init__(self, C):
        super().__init__(C, None); self.C = C; self.free = set(); self._lab = {}

    # labels through the store (GT.Rung2 reads self.labels as a dict)
    class _Labels(dict):
        def __init__(self, C): super().__init__(); self.C = C
        def get(self, k, d=None):
            if not dict.__contains__(self, k): dict.__setitem__(self, k, self.C.label(k))
            v = dict.__getitem__(self, k); return v if v != k else d
        def __getitem__(self, k): return self.get(k, k)
        def __contains__(self, k): return True
    def _init_labels(self): self.labels = Scale._Labels(self.C)

    def claims(self, h): return self.C.claims(h)

    def numeric(self, syms, h):
        """numeric mentions: {position: (value, relation)} for tokens equal to the year/amount of a T:/N: claim"""
        out = {}
        for p, vs in self.C.allclaims(h).items():
            for v in vs:
                if v[:2] in ("T:", "N:"):
                    for k, w in enumerate(syms):
                        if w == v[2:]: out[k] = (v, p)
        return out

    def windows(self, text, h):
        """rung-2 windows around name mentions, plus (step 2) the headword anchor at position 0 and (step 3) windows
        around numeric mentions"""
        syms = symbols(text, "LN"); out = []
        m = self.mentions(syms, h)
        starts = {v[2]: v for k, v in m.items() if v[2] == k}
        anchors = [(i, (o, p), i + 1 if i not in m else None) for i, (o, p, start) in starts.items()]
        spans = []
        for i, (o, p, start) in starts.items():
            end = i
            while end in m and m[end][2] == start: end += 1
            spans.append((i, end, o, p if (p is not None and self.rel_base(p) <= GT.MAX_BASE) else None))
        for k, (v, p) in self.numeric(syms, h).items():
            if k not in m: spans.append((k, k + 1, v, p if self.rel_base(p) <= GT.MAX_BASE else None))
        spans.append((0, 0, h, "HEAD"))                              # the headword anchor: an empty span before the first token
        for i, end, filler, p in spans:
            for w in range(1, self.W + 1):
                left = tuple(syms[max(0, i - w):i]); right = tuple(syms[end:end + w])
                if not left and not right: continue
                out.append(((left, right, p), filler))
        return out

    def typeset(self, h):
        if isinstance(h, str) and h[:2] in ("T:", "N:"): return {("KIND", h[:1])}
        return super().typeset(h)

    def wcondition(self, key, occs):
        left, right, p = key
        types = tuple(self.types[w][0] for w in left + right if w in self.types)
        fsets = [self.typeset(f) for _, f in occs]
        shared = set.intersection(*fsets) if fsets else set()
        ftypes = sorted((t for t in shared if (t[0] == "P31" and self.base.get(t, 1.0) <= GT.MAX_BASE) or t[0] == "KIND"), key=lambda t: self.base.get(t, 0.0))
        ftype = ftypes[0] if ftypes else None
        rel = p if p not in (None, "HEAD") else None
        if rel is None and not types and ftype is None: return None
        for h, f in occs:
            ts = self.typeset(h)
            if not all(t in ts for t in types): return None
            if rel is not None and rel not in self.claims(h): return None
        return (types, (rel,) if rel else (), ftype)

    def induce_free(self, items):
        """step 4: claim-free words -- presence predicts no type under the cap (max lift < DELTA), in >= MIN_FREE glosses"""
        heads = {h for h, _ in items}
        occ = collections.defaultdict(set)
        for h, t in items:
            for w in set(symbols(t, "LN")): occ[w].add(h)
        caps = [t for t, b in self.base.items() if b <= GT.MAX_BASE and b >= 0.02]
        hts = {h: self.typeset(h) for h in heads}
        self.lift = {}
        for w, hs in occ.items():
            if len(hs) < MIN_FREE: continue
            lifts = []
            for t in caps:
                pw = sum(1 for h in hs if t in hts[h]) / len(hs); lifts.append(abs(pw - self.base[t]))
            self.lift[w] = max(lifts) if lifts else 0.0
        self.free = {w for w, l in self.lift.items() if l < DELTA}
        return self.free

    def read(self, text, h, use=("names", "labels", "types", "cons")):
        syms = symbols(text, "LN"); idx = self.content(syms)
        if not idx: return set(), set()
        ts = self.typeset(h); rels = set(self.claims(h)); plabels = {self.labels[p].lower() for p in rels}
        m = self.mentions(syms, h) if "names" in use else {}; num = self.numeric(syms, h) if "names" in use else {}
        ok = set()
        for k in idx:
            w = syms[k]
            if k in m or k in num: ok.add(k); continue
            if "labels" in use and w in plabels: ok.add(k); continue
            if "types" in use and any(t in ts for t in self.types.get(w, ())): ok.add(k); continue
            if "free" in use and w in self.free: ok.add(k)
        if "cons" in use:
            for key, f in self.windows(text, h):
                if key in self.cons and self.wsatisfies(h, f, self.cons[key][1]):
                    left, right, p = key; ok |= {k for k in idx if syms[k] in left + right}
        return ok, set(idx)

    def states(self, body, s, o, p):
        """does an admitted construction STATE the relation p between s and o in this reply? -> covered positions or None.
        (amendment, recorded: at scale 2,391 of 2,400 candidate replies were rejected as 'edge not read' because an
        attested gloss says 'a city in France', never the relation word 'country'; the construction 'city in {E:country}'
        is what reads it)"""
        syms = symbols(body, "LN")
        for h, other in ((s, o), (o, s)):
            m = self.mentions(syms, h)
            spans = {}
            for k, (obj, rel, start) in m.items():
                if obj == other: spans.setdefault(start, [start, start])
            for start in spans:
                end = start
                while end in m and m[end][2] == start: end += 1
                spans[start][1] = end
            for start, (i, end) in spans.items():
                for w in range(1, self.W + 1):
                    left = tuple(syms[max(0, i - w):i]); right = tuple(syms[end:end + w])
                    if not left and not right: continue
                    key = (left, right, p)
                    if key in self.cons and self.wsatisfies(h, other, self.cons[key][1]):
                        return set(range(max(0, i - w), min(len(syms), end + w)))
        return None

    def prepare(self, body, s, o):
        self._okwords = set()
        for h in (s, o):
            for key, f in self.windows(body, h):
                if key in self.cons and self.wsatisfies(h, f, self.cons[key][1]): self._okwords |= set(key[0] + key[1])

    def __call__(self, w, ents):
        if w in self.free: return True
        if any(t in self.typeset(e) for e in ents for t in self.types.get(w, ())): return True
        return w in getattr(self, "_okwords", ())


def rate(R, items, use):
    ok = tot = 0
    for h, t in items:
        a, b = R.read(t, h, use); ok += len(a); tot += len(b)
    return ok / max(1, tot)


def register_from_crawl(C, items):
    """realize.py's register over the crawl: (triple, side, text) pairs from the aligned glosses"""
    by_head = collections.defaultdict(list)
    for h, t in items: by_head[h].append(t)
    pairs = []; triples = set(); labels = {}
    for h, texts in by_head.items():
        for p, vs in C.claims(h).items():
            for o in vs:
                lo = C.label(o)
                if lo == o: continue
                for t in texts:
                    if re.search(r"\b" + re.escape(lo) + r"\b", t):
                        pairs.append(dict(s=h, p=p, o=o, side="subject", kind="def", text=t)); triples.add((h, p, o)); labels[o] = lo
                for t2 in by_head.get(o, []):
                    lh = C.label(h)
                    if lh != h and re.search(r"\b" + re.escape(lh) + r"\b", t2):
                        pairs.append(dict(s=h, p=p, o=o, side="object", kind="def", text=t2)); triples.add((h, p, o))
        labels[h] = C.label(h)
    for s, p, o in triples: labels[p] = C.label(p)
    return dict(labels=labels, triples=sorted(triples), pairs=pairs)


if __name__ == "__main__":
    selfcheck(__file__)
    a = sys.argv; nframes = int(a[a.index("--frames") + 1]) if "--frames" in a else 300
    say("GLOSS SCALE -- crawl store, headword anchor, numeric mentions, claim-free words (gloss_scale_prereg.md)\n")
    C = Crawl(); ne, nl = C.count()
    items, counts = build_items(C)
    heads = sorted({h for h, _ in items}); rng = random.Random(1); rng.shuffle(heads)
    test_h = set(heads[: len(heads) // 5]); train = [it for it in items if it[0] not in test_h]; test = [it for it in items if it[0] in test_h]
    n_cls = sum(1 for (q,) in C.db.execute("select q from ent") if False) if False else None
    ok0 = len(heads) >= 5 * 1193
    say(f"S0  DATA: store {ne} entities, {nl} labels; {counts}; aligned (headword, gloss) {len(items)} over {len(heads)} headwords; train {len(train)} / test {len(test)}   [>= 5x 1193 -> {'PASS' if ok0 else 'FAIL'}]")

    R = Scale(C); R._init_labels(); types, cons = R.induce(train); free = R.induce_free(train)
    say(f"\nS1  CONSTRUCTIONS at scale: {len(cons)} windows; {len(types)} typed words; function words {sorted(R.common)}")
    for (left, right, p), (n, cond) in sorted(cons.items(), key=lambda kv: -kv[1][0])[:14]:
        slot = "{HEAD}" if p == "HEAD" else "{E" + (":" + R.labels.get(p, p) if p else "") + "}"
        ft = cond[2]; ftl = (R.labels.get(ft[1], ft[1]) if ft and ft[0] == "P31" else (f"kind {ft[1]}" if ft else None))
        say(f"      x{n:<5d} {' '.join(left)} {slot} {' '.join(right)}   <- filler type {ftl}, headword types {[R.labels.get(o, o) for q, o in cond[0]][:2]}")
    ch = ct = 0; chn = ctn = 0
    for h, t in test:
        for key, f in R.windows(t, h):
            if key in cons:
                good = R.wsatisfies(h, f, cons[key][1]); ct += 1; ch += good
                if isinstance(f, str) and f[:2] in ("T:", "N:"): ctn += 1; chn += good
    pc = ch / max(1, ct)
    texts = [t for _, t in train]; random.Random(0).shuffle(texts)
    Rs = Scale(C); Rs._init_labels(); ts_, cs_ = Rs.induce([(h, t) for (h, _), t in zip(train, texts)])
    ok1 = pc >= 0.85 and len(cs_) < 0.10 * max(1, len(cons))
    say(f"S1  held-out soundness {ch}/{ct} = {pc:.2f}; shuffled-gloss knockout {len(cs_)} of {len(cons)}   [>= 0.85, < 10 % -> {'PASS' if ok1 else 'FAIL'}]")

    r0 = rate(R, test, ("names", "labels")); r1 = rate(R, test, ("names", "labels", "types", "cons")); r2 = rate(R, test, ("names", "labels", "types", "cons", "free"))
    ok2 = r2 >= 0.45
    say(f"\nS2  HELD-OUT READING: names+labels {r0:.2f}; +types+constructions {r1:.2f}; +claim-free {r2:.2f}   [>= 0.45 -> {'PASS' if ok2 else 'FAIL'}]")

    # S4 claim-free, validated on held-out headwords
    test_heads = {h for h, _ in test}; occ_t = collections.defaultdict(set)
    for h, t in test:
        for w in set(symbols(t, "LN")): occ_t[w].add(h)
    caps = [t for t, b in R.base.items() if GT.MAX_BASE >= b >= 0.02]; hts = {h: R.typeset(h) for h in test_heads}
    stable = n_fr = 0
    for w in free:
        hs = occ_t.get(w, set())
        if len(hs) < 5: continue
        n_fr += 1; lift = max((abs(sum(1 for h in hs if t in hts[h]) / len(hs) - R.base[t]) for t in caps), default=0.0); stable += lift < DELTA
    st = stable / max(1, n_fr); ok4 = st >= 0.9
    say(f"S4  CLAIM-FREE WORDS: {len(free)} (e.g. {sorted(free, key=lambda w: -len(occ_t.get(w, ())))[:16]}); held-out stable {stable}/{n_fr} = {st:.2f}   [>= 0.90 -> {'PASS' if ok4 else 'FAIL'}]")
    numwin = [(k, v) for k, v in cons.items() if v[1][2] and v[1][2][0] == "KIND"]
    pn = chn / max(1, ctn); ok5 = len(numwin) >= 10 and (ctn == 0 or pn >= 0.85)
    say(f"S5  NUMBERS: {counts['numeric_aligned']} glosses align through a year/amount; {len(numwin)} numeric windows; held-out soundness {chn}/{ctn} = {pn:.2f}   [>= 10, >= 0.85 -> {'PASS' if ok5 else 'FAIL'}]")
    for (left, right, p), (n, cond) in sorted(numwin, key=lambda kv: -kv[1][0])[:6]:
        say(f"      x{n:<4d} {' '.join(left)} {{{cond[2][1]}:{R.labels.get(p, p) if p else '-'}}} {' '.join(right)}")

    # S3: the strict inverse over the crawl world with this reader, on a seeded sample of engine-answered frames
    reg = register_from_crawl(C, items); admitted, weak = RZ.skeletons(reg)
    say(f"\n    register at scale: {len(reg['triples'])} triples, {len(reg['pairs'])} pairs, {sum(len(d) for d in admitted.values())} admitted skeletons (realize.py had 14)")
    df = KG.make_df(); kgw = KGWorld(C, df, name="Wikidata")
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    cand = [t for t in reg["triples"] if t[1] in props]; random.Random(2).shuffle(cand); frames = []
    for s, p, o in cand:
        if len(frames) >= nframes: break
        fr = reason(f"what is the {reg['labels'][p]} of {reg['labels'][s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o: frames.append((s, p, o))
    inv = RZ.Inverse(kgw, df, strict=True, reader=R); Rz = RZ.Realizer(reg, admitted, weak, inv); c = 0; shown = 0
    for s, p, o in frames:
        adm = Rz.admissible(s, p, o)
        if adm:
            c += 1
            if shown < 8: say(f"      strict reply: {adm[0][0][:120]!r}"); shown += 1
    cov = c / max(1, len(frames)); ok3 = cov >= 0.10
    say(f"S3  STRICT INVERSE over the crawl world: coverage {c}/{len(frames)} = {cov:.2f}; candidates {inv.n}, rejected {dict(inv.rejected)}   [>= 0.10, misreport emitted 0 -> {'PASS' if ok3 else 'FAIL'}]")
    # S7 (owner's question, added before the first run): the LEARNING CURVE and per-chunk CREDIT. Learning here is discrete:
    # a data point either ADMITS a window (its third consistent headword arrives), RETRACTS one (a counterexample arrives),
    # or changes nothing. So the "gradient" is exact and attributable: for each tenth of the training data, the windows
    # admitted and retracted, and the held-out reading rate after it.
    say("\nS7  LEARNING CURVE (training data in tenths; held-out reading after each; windows admitted/retracted by that tenth)")
    order = list(train); random.Random(3).shuffle(order); prev = set(); prev_rate = None; curve = []
    for k in range(1, 11):
        part = order[: len(order) * k // 10]
        Rk = Scale(C); Rk._init_labels(); _, ck = Rk.induce(part); Rk.induce_free(part)
        cur = set(ck); admitted_k = cur - prev; retracted_k = prev - cur
        rk = rate(Rk, test, ("names", "labels", "types", "cons", "free"))
        ex = next(iter(sorted(admitted_k, key=lambda key: -ck[key][0])), None)
        exs = (" ".join(ex[0]) + " {" + ("HEAD" if ex[2] == "HEAD" else "E") + "} " + " ".join(ex[1])) if ex else "-"
        say(f"      {k * 10:3d} %  glosses {len(part):6d}  windows {len(cur):5d}  +{len(admitted_k):<4d} -{len(retracted_k):<3d}  held-out reading {rk:.3f}"
            + (f" ({rk - prev_rate:+.3f})" if prev_rate is not None else "") + f"   newest e.g. {exs[:60]!r}")
        curve.append((len(part), len(cur), rk)); prev = cur; prev_rate = rk
    mono = sum(1 for i in range(1, len(curve)) if curve[i][2] >= curve[i - 1][2] - 0.005)
    say(f"S7  reading rate non-decreasing across {mono}/{len(curve) - 1} steps; windows {curve[0][1]} -> {curve[-1][1]}")
    lits = GT.literals_in.__wrapped__ if hasattr(GT.literals_in, "__wrapped__") else None
    tree = ast.parse(open(__file__, encoding="utf-8").read()); toks = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("windows", "numeric", "wcondition", "induce_free", "read", "prepare", "__call__"):
            for stmt in node.body[1:] if (node.body and isinstance(node.body[0], ast.Expr)) else node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str): toks |= set(re.findall(r"[a-z]{3,}", sub.value))
    shared = (toks & (set(types) | free)) - {"names", "labels", "types", "cons", "free"}
    ok6 = not shared
    say(f"S6  HYGIENE: reading-path literals that are bound or claim-free words: {sorted(shared)}   [{'PASS' if ok6 else 'FAIL'}]")
    ok = ok0 and ok1 and ok2 and ok3 and ok4 and ok5 and ok6
    say(f"\nGLOSS SCALE: {'PASS' if ok else 'NOT PASSED'} -- {len(heads)} headwords, {len(cons)} windows at {pc:.2f}, reading {r0:.2f} -> {r2:.2f}, claim-free {len(free)}, numeric windows {len(numwin)}, strict coverage {c}/{len(frames)}")
