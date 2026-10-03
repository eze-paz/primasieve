"""READING GLOSSES, RUNG 2 -- TYPES and CONSTRUCTIONS (gloss_types_prereg.md). Zero LLM. Offline except the one data
step (--fetch-labels), which fills missing labels in the Wikidata cache through the API the cache already uses.

    python gloss_types.py --fetch-labels     # the data step (minutes; writes label:<qid> keys into the cache)
    python gloss_types.py                    # induce types and constructions, run T0-T6"""
import os, sys, re, json, time, random, sqlite3, collections, ast, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols, reason
from core.verdict import ATTRIBUTED, COMMIT
from core.kg import KGWorld
from core.registry import selfcheck
from kb_wikidata import Wikidata, CACHE_PATH, API, UA
import kg_multihop as KG
import realize as RZ

KAIKKI = os.path.join(HERE, "_nldata", "kaikki_all.sqlite")
MIN_N, MAX_BASE = 3, 0.5
EPS, MIN_N_TOL = 0.10, 5          # amendment 1 (recorded): a binding tolerates up to 10 % contrary headwords once it has >= 5 --
                                  # the alignment is distant supervision and one wrong-sense gloss killed every exact binding


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


# ------------------------------------------------------------------------------------------------ the data step
def fetch_labels(batch=50, pace=0.2):
    cache = json.load(open(CACHE_PATH, encoding="utf-8"))
    have = {k.split(":", 1)[1] for k in cache if k.startswith("label:")}
    ids = set()
    for k, txt in cache.items():
        if not k.startswith("entity:"): continue
        q = k.split(":", 1)[1]; ids.add(q)
        try: ent = json.loads(txt)["entities"][q]
        except Exception: continue
        for pid, sts in ent.get("claims", {}).items():
            ids.add(pid)
            for st in sts:
                dv = st.get("mainsnak", {}).get("datavalue", {})
                if dv.get("type") == "wikibase-entityid": ids.add(dv["value"]["id"])
    todo = sorted(ids - have); say(f"  labels to fetch: {len(todo)} of {len(ids)}")
    ctx = Wikidata(offline=True).ctx; got = 0; t0 = time.time()
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        url = API + urllib.parse.urlencode(dict(action="wbgetentities", ids="|".join(chunk), props="labels", languages="en", format="json"))
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30, context=ctx).read().decode("utf-8"))
        except Exception as e:
            say(f"  batch {i // batch} failed: {e!r}"); time.sleep(2); continue
        for q, ent in d.get("entities", {}).items():
            lab = ent.get("labels", {}).get("en", {}).get("value")
            if lab: cache[f"label:{q}"] = lab; got += 1
            else: cache[f"label:{q}"] = q                                   # no English label: the id stands (as Wikidata.label does)
        if (i // batch) % 100 == 0 and i: say(f"  ... {i + len(chunk)}/{len(todo)} ids, {got} labels, {time.time() - t0:.0f} s")
        time.sleep(pace)
    live = json.load(open(CACHE_PATH, encoding="utf-8"))                       # merge with whatever another process wrote meanwhile
    live.update({k: v for k, v in cache.items() if k.startswith("label:")})
    json.dump(live, open(CACHE_PATH, "w", encoding="utf-8"))
    say(f"  fetched {got} labels in {time.time() - t0:.0f} s; cache saved")


def fetch_classes(rounds=2, pace=0.15):
    """data step 2 (amendment 3, recorded): the claims of every class item reached by instance-of / subclass-of from the
    headwords, two rounds up, so a type can be closed under subclass-of ('big city' -> 'city' -> 'human settlement')."""
    src = Wikidata(offline=False); src.last = time.time()
    labels = {k.split(":", 1)[1]: v for k, v in src.cache.items() if k.startswith("label:")}
    items, _ = build_items(Wikidata(offline=True), labels)
    frontier = {o for h, _ in items for p in ("P31", "P279") for o in src.claims(h).get(p, [])}
    seen = set(); t0 = time.time(); n = 0
    for r in range(rounds):
        todo = sorted(c for c in frontier - seen if f"entity:{c}" not in src.cache)
        say(f"  round {r + 1}: {len(frontier - seen)} class ids, {len(todo)} to fetch")
        for i, c in enumerate(todo):
            src._entity(c); n += 1
            if i % 200 == 0 and i: say(f"    ... {i}/{len(todo)} ({time.time() - t0:.0f} s)"); src.save()
        seen |= frontier
        frontier = {o for c in list(frontier) for o in src.claims(c).get("P279", [])}
    src.save(); say(f"  fetched {n} class entities in {time.time() - t0:.0f} s; cache saved")


# ------------------------------------------------------------------------------------------------ the data
def build_items(src, labels):
    """-> [(headword qid, gloss text)]: every cached entity with claims, a label and a Wiktionary definition that mentions
    one of its claim objects by label (the alignment of realize.py, now over the whole cache)."""
    db = sqlite3.connect(KAIKKI); memo = {}

    def entry(w):
        if w not in memo:
            r = db.execute("select v from e where w=?", (w.lower(),)).fetchone(); memo[w] = json.loads(r[0]) if r else None
        return memo[w]
    items = set(); n_ent = n_lab = n_wikt = 0
    for q in src.cache:
        if not q.startswith("entity:"): continue
        h = q.split(":", 1)[1]; n_ent += 1
        if h not in labels or labels[h] == h: continue
        n_lab += 1
        e = entry(labels[h])
        if not e: continue
        n_wikt += 1
        objs = {o for vs in src.claims(h).values() for o in vs}
        names = sorted({labels[o] for o in objs if o in labels and labels[o] != o and len(labels[o]) > 2}, key=len, reverse=True)
        for t in e.get("defs", []):
            if any(re.search(r"\b" + re.escape(nm) + r"\b", t) for nm in names[:400]): items.add((h, t))
    return sorted(items), dict(entities=n_ent, labelled=n_lab, with_entry=n_wikt)


# ------------------------------------------------------------------------------------------------ the mechanism
class Rung2:
    def __init__(self, src, labels):
        self.src, self.labels = src, labels; self.common = set(); self.types = {}; self.n = {}; self.cons = {}; self.base = {}; self._relbase = {}

    def claims(self, h): return self.src.claims(h)
    def ancestors(self, c, depth=4):
        """c and its subclass-of ancestors over cached claims (amendment 3)"""
        memo = self.__dict__.setdefault("_anc", {})
        if c in memo: return memo[c]
        out = {c}; frontier = {c}
        for _ in range(depth):
            nxt = {o for x in frontier for o in self.claims(x).get("P279", [])} - out
            if not nxt: break
            out |= nxt; frontier = nxt
        memo[c] = out; return out

    def typeset(self, h):
        """(relation, value) pairs of the headword's claims, with instance-of values CLOSED under subclass-of: an entity
        typed 'big city' is also typed 'city' (amendment 3; measured: the 176 'city' glosses' headwords spread over
        'big city', 'city', 'largest city', 'city in the United States', and no one class reached a binding)"""
        memo = self.__dict__.setdefault("_ts", {})
        if h in memo: return memo[h]
        ts = {(p, o) for p, vs in self.claims(h).items() for o in vs}
        for o in self.claims(h).get("P31", []):
            ts |= {("P31", a) for a in self.ancestors(o)}
        memo[h] = ts; return ts

    def content(self, syms): return [k for k, w in enumerate(syms) if w not in self.common]

    def mentions(self, syms, h):
        """-> {position: relation-or-None} for verified mentions (objects of the headword's claims), longest label first"""
        rel = collections.defaultdict(set)
        for p, vs in self.claims(h).items():
            for o in vs: rel[o].add(p)
        out = {}
        for o, ps in sorted(rel.items(), key=lambda kv: -len(self.labels.get(kv[0], ""))):
            lab = self.labels.get(o)
            if not lab or lab == o: continue
            ls = symbols(lab, "L")
            if not ls: continue
            for i in range(len(syms) - len(ls) + 1):
                if syms[i:i + len(ls)] == ls and not any(k in out for k in range(i, i + len(ls))):
                    p = min(ps, key=lambda r: self.rel_base(r)) if ps else None
                    for k in range(i, i + len(ls)): out[k] = (o, p, i)
        return out

    def skeleton(self, syms, ments):
        out = []; i = 0
        while i < len(syms):
            if i in ments and ments[i][2] == i:
                o, p, start = ments[i]; out.append(("E", p)); i += 1
                while i in ments and ments[i][2] == start: i += 1
            else: out.append(syms[i]); i += 1
        return tuple(out)

    def induce(self, items):
        heads = {h for h, _ in items}
        df = collections.Counter()
        for h, t in items:
            for w in set(symbols(t, "L")): df[w] += 1
        self.common = {w for w, c in df.items() if c > len(items) / 2}
        cnt = collections.Counter()
        for h in heads:
            for t in self.typeset(h): cnt[t] += 1
        self.base = {t: c / len(heads) for t, c in cnt.items()}
        rc = collections.Counter()
        for h in heads:
            for p in set(self.claims(h)): rc[p] += 1
        self._relbase = {p: c / len(heads) for p, c in rc.items()}
        # types: a word -> every (relation, value) all its headwords carry
        occ = collections.defaultdict(list)
        for h, t in items:
            syms = symbols(t, "L"); ts = self.typeset(h)
            for w in {syms[k] for k in self.content(syms)}: occ[w].append(ts)
        self.types = {}; self.n = {}
        for w, sets in occ.items():
            if len(sets) < MIN_N: continue
            cnt_t = collections.Counter(t for ts in sets for t in ts)
            need = len(sets) if len(sets) < MIN_N_TOL else (1 - EPS) * len(sets)
            ts = sorted((t for t, c in cnt_t.items() if c >= need and self.base.get(t, 1.0) <= MAX_BASE), key=lambda t: self.base[t])
            if ts: self.types[w] = ts; self.n[w] = len(sets)
        # constructions (amendment 4, recorded): LOCAL windows of up to W tokens on each side of a mention slot, over
        # >= 3 headwords, with a truth condition that may TYPE THE FILLER -- 'city' in "capital and largest city: {E}"
        # predicates the filler, not the headword (measured: its headwords were countries). Whole-gloss skeletons
        # recurred 5-17 times; windows recur far more.
        by = collections.defaultdict(list)
        for h, t in items:
            for key, filler in self.windows(t, h):
                by[key].append((h, filler))
        self.cons = {}
        for key, occs in by.items():
            hs = {h for h, _ in occs}
            if len(hs) < MIN_N: continue
            cond = self.wcondition(key, occs)
            if cond is None: continue
            self.cons[key] = (len(hs), cond)
        return self.types, self.cons

    W = 3

    def windows(self, text, h):
        """-> [((left tuple, right tuple, relation), filler qid)] for every mention slot and every window size 1..W"""
        syms = symbols(text, "L"); m = self.mentions(syms, h); out = []
        starts = {v[2]: v for k, v in m.items() if v[2] == k}
        for i, (o, p, start) in starts.items():
            end = i
            while end in m and m[end][2] == start: end += 1
            for w in range(1, self.W + 1):
                left = tuple(syms[max(0, i - w):i]); right = tuple(syms[end:end + w])
                if not left and not right: continue
                out.append(((left, right, p if (p is not None and self.rel_base(p) <= MAX_BASE) else None), o))
        return out

    def wcondition(self, key, occs):
        """the condition of a window: its relation (if informative), the headword types its words bind, and the most
        specific type every filler shares (base-rate capped). Must hold for EVERY occurrence; None if vacuous or violated."""
        left, right, p = key
        types = tuple(self.types[w][0] for w in left + right if w in self.types)
        fsets = [self.typeset(f) for _, f in occs]
        shared = set.intersection(*fsets) if fsets else set()
        ftypes = sorted((t for t in shared if t[0] == "P31" and self.base.get(t, 1.0) <= MAX_BASE), key=lambda t: self.base[t])
        ftype = ftypes[0] if ftypes else None
        if p is None and not types and ftype is None: return None
        for h, f in occs:
            ts = self.typeset(h)
            if not all(t in ts for t in types): return None
            if p is not None and p not in self.claims(h): return None
        return (types, (p,) if p else (), ftype)

    def wsatisfies(self, h, f, cond):
        types, slots, ftype = cond; ts = self.typeset(h)
        return all(t in ts for t in types) and all(p in self.claims(h) for p in slots) and (ftype is None or ftype in self.typeset(f))

    def rel_base(self, p): return self._relbase.get(p, 1.0)

    def condition(self, sk):
        """the truth condition of a skeleton: the most specific bound type of each bound word, and each slot's relation.
        Amendment 2 (recorded): a slot relation counts only under the base-rate cap (a relation most entities carry, such
        as a namesake link at 0.61, verifies nothing), and a condition with no type and no slot is VACUOUS -- the shuffled
        knockout admitted 39 such constructions against 17 real ones."""
        types = tuple(self.types[w][0] for w in sk if isinstance(w, str) and w in self.types)
        slots = tuple(p for x in sk if isinstance(x, tuple) for p in [x[1]] if p is not None and self.rel_base(p) <= MAX_BASE)
        return types, slots

    def satisfies(self, h, m, cond, sk):
        types, slots = cond; ts = self.typeset(h); rels = set(self.claims(h))
        return all(t in ts for t in types) and all(p in rels for p in slots)

    def read(self, text, h, use=("names", "labels", "types", "cons")):
        syms = symbols(text, "L"); idx = self.content(syms)
        if not idx: return set(), set()
        ts = self.typeset(h); rels = set(self.claims(h)); plabels = {self.labels[p].lower() for p in rels if p in self.labels}
        m = self.mentions(syms, h) if "names" in use else {}
        ok = set()
        for k in idx:
            w = syms[k]
            if k in m: ok.add(k); continue
            if "labels" in use and w in plabels: ok.add(k); continue
            if "types" in use and any(t in ts for t in self.types.get(w, ())): ok.add(k)
        if "cons" in use:
            for key, f in self.windows(text, h):
                if key in self.cons and self.wsatisfies(h, f, self.cons[key][1]):
                    left, right, p = key
                    ok |= {k for k in idx if syms[k] in left + right}
        return ok, set(idx)

    # ---- the reader for realize.Inverse(strict=True): prepare per reply, then answer per word -------------------------
    def prepare(self, body, s, o):
        """a construction is matched over the whole reply (its skeleton with the reply's verified mentions abstracted),
        for either of the frame's two entities as headword; the words it covers are then accounted for per word"""
        self._okwords = set()
        syms = symbols(body, "L")
        for h in (s, o):
            for key, f in self.windows(body, h):
                if key in self.cons and self.wsatisfies(h, f, self.cons[key][1]): self._okwords |= set(key[0] + key[1])

    def __call__(self, w, ents):
        if any(t in self.typeset(e) for e in ents for t in self.types.get(w, ())): return True
        return w in getattr(self, "_okwords", ())


def rate(R, items, use):
    ok = tot = 0
    for h, t in items:
        a, b = R.read(t, h, use); ok += len(a); tot += len(b)
    return ok / max(1, tot)


def literals_in(fn_names):
    tree = ast.parse(open(__file__, encoding="utf-8").read()); out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in fn_names:
            body = node.body[1:] if (node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant)) else node.body
            for stmt in body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and "[" not in sub.value and "\\" not in sub.value: out.add(sub.value)
    return out


if __name__ == "__main__":
    selfcheck(__file__)
    if "--fetch-labels" in sys.argv:
        say("DATA STEP -- labels for every entity and claim object in the cache"); fetch_labels(); sys.exit(0)
    if "--fetch-classes" in sys.argv:
        say("DATA STEP 2 -- claims of the class items, two rounds of subclass-of"); fetch_classes(); sys.exit(0)
    say("GLOSS TYPES -- rung 2: types and constructions (gloss_types_prereg.md)\n")
    src = Wikidata(offline=True); df = KG.make_df()
    labels = {k.split(":", 1)[1]: v for k, v in src.cache.items() if k.startswith("label:")}
    items, counts = build_items(src, labels)
    heads = sorted({h for h, _ in items}); rng = random.Random(1); rng.shuffle(heads)
    test_h = set(heads[: len(heads) // 5]); train = [it for it in items if it[0] not in test_h]; test = [it for it in items if it[0] in test_h]
    say(f"T0  DATA: {counts}; aligned (headword, gloss) texts {len(items)} over {len(heads)} headwords (rung 1 had 312 over 158); train {len(train)} / test {len(test)}")

    R = Rung2(src, labels); types, cons = R.induce(train)
    say(f"\nT1  TYPE LEXICON: {len(types)} bound words; function words {sorted(R.common)}; constructions admitted {len(cons)}")
    for w in sorted(types, key=lambda w: -R.n[w])[:30]:
        say(f"      {w:14s} x{R.n[w]:<4d} -> {[(labels.get(p, p), labels.get(o, o)) for p, o in types[w][:3]]}")
    expect = ["city", "capital", "river", "island", "language", "country", "province"]
    bound_exp = [w for w in expect if w in types]
    say(f"T1  gloss nouns bound (prediction P2): {bound_exp}   [>= 5 of 7 -> {'PASS' if len(bound_exp) >= 5 else 'FAIL'}]")
    for (left, right, p), (n, cond) in sorted(cons.items(), key=lambda kv: -kv[1][0])[:12]:
        say(f"      construction x{n}: {' '.join(left)} {{E{':' + labels.get(p, p) if p else ''}}} {' '.join(right)}  <- headword types {[labels.get(o, o) for q, o in cond[0]][:2]} filler type {labels.get(cond[2][1], cond[2][1]) if cond[2] else None}")

    r0 = rate(R, test, ("names", "labels")); r1 = rate(R, test, ("names", "labels", "types")); r2 = rate(R, test, ("names", "labels", "types", "cons"))
    ok2 = r2 - r0 >= 0.15
    say(f"\nT2  HELD-OUT READING: names+labels {r0:.2f}; +types {r1:.2f}; +constructions {r2:.2f}; lift {r2 - r0:+.2f}   [>= +0.15 -> {'PASS' if ok2 else 'FAIL'}]")
    hit = tot = 0
    for h, t in test:
        syms = symbols(t, "L"); ts = R.typeset(h)
        for w in {syms[k] for k in R.content(syms)}:
            if w in types: tot += 1; hit += any(x in ts for x in types[w])
    ch = ct = 0
    for h, t in test:
        for key, f in R.windows(t, h):
            if key in cons: ct += 1; ch += R.wsatisfies(h, f, cons[key][1])
    pt = hit / max(1, tot); pc = ch / max(1, ct)
    ok3 = pt >= 0.8 and (ct == 0 or pc >= 0.8)
    say(f"T3  HELD-OUT SOUNDNESS: types {hit}/{tot} = {pt:.2f}; constructions {ch}/{ct} = {pc:.2f}   [>= 0.80 -> {'PASS' if ok3 else 'FAIL'}]")
    texts = [t for _, t in train]; random.Random(0).shuffle(texts)
    Rs = Rung2(src, labels); ts_, cs_ = Rs.induce([(h, t) for (h, _), t in zip(train, texts)])
    rs0 = rate(Rs, test, ("names", "labels")); rs2 = rate(Rs, test, ("names", "labels", "types", "cons"))
    ok4 = len(ts_) < 0.25 * max(1, len(types)) and len(cs_) < 0.25 * max(1, len(cons)) and rs2 - rs0 < 0.05
    say(f"T4  KNOCKOUT shuffled glosses: types {len(ts_)} (main {len(types)}), constructions {len(cs_)} (main {len(cons)}), held-out lift {rs2 - rs0:+.2f}   [< 25 %, < 0.05 -> {'PASS' if ok4 else 'FAIL'}]")

    # T5: the strict inverse of realize.py with this reader
    reg = RZ.load_register(); kgw = KGWorld(src, df, name="Wikidata"); admitted, weak = RZ.skeletons(reg)
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    frames = []
    for s, p, o in reg["triples"]:
        if p not in props: continue
        fr = reason(f"what is the {reg['labels'][p]} of {reg['labels'][s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o: frames.append((s, p, o))
    inv = RZ.Inverse(kgw, df, strict=True, reader=R); Rz = RZ.Realizer(reg, admitted, weak, inv); c = 0; shown = 0
    for s, p, o in frames:
        a = Rz.admissible(s, p, o)
        if a:
            c += 1
            if shown < 6: say(f"      strict+rung2: {a[0][0][:110]!r}"); shown += 1
    cov = c / max(1, len(frames)); ok5 = cov >= 0.10
    say(f"T5  STRICT INVERSE with the rung-2 reader: coverage {c}/{len(frames)} = {cov:.2f}; strict rejections {inv.rejected.get('strict: unread content', 0)}   [>= 0.10 -> {'PASS' if ok5 else 'FAIL'}]")
    lits = literals_in({"induce", "read", "mentions", "skeleton", "condition", "satisfies", "prepare", "__call__", "content"})
    toks = {t for l in lits for t in re.findall(r"[A-Za-z]+", l)} - {"E", "L", "names", "labels", "types", "cons"}
    ok6 = not (toks & set(types))
    say(f"T6  HYGIENE: path literals that are bound words: {sorted(toks & set(types))}   [{'PASS' if ok6 else 'FAIL'}]")
    ok = len(bound_exp) >= 5 and ok2 and ok3 and ok4 and ok5 and ok6
    say(f"\nGLOSS TYPES: {'PASS' if ok else 'NOT PASSED'} -- {len(types)} types words, {len(cons)} constructions, held-out reading {r0:.2f} -> {r2:.2f}, soundness {pt:.2f}/{pc:.2f}, strict coverage {c}/{len(frames)}")
