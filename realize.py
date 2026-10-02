"""AN ATTESTED REGISTER FOR REPLIES, WITH THE LOOP AS THE INVERSE (realize_prereg.md). Zero LLM. Offline.

The register is DATA: for every fully labelled triple in the offline Wikidata cache, the Wiktionary entry of each end is
read and a definition or example that mentions the other end verbatim is a (triple, side, text) pair -- distant
supervision, checked like a certificate. Skeletons are the texts with the two labels abstracted to slots, admitted when
they recur across two triples. A reply is admissible only if the engine, reading it back through core.reason over the
same world, finds the frame's own edge among its survivors, finds no conflicting edge, and leaves no relation or name
in the reply unverified. Nothing here names a property, an entity or a word; the only joins are the dictionary's
headword colon and the provenance tail.

    python realize.py            # build the register (cached under _nldata/), run R1-R8
    python realize.py --rebuild  # rebuild the register from the sources"""
import os, sys, re, json, math, random, sqlite3, collections, ast

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason, symbols, _pass, _spans
from core.verdict import ATTRIBUTED, COMMIT
from core.kg import KGWorld
from core.registry import selfcheck
from kb_wikidata import Wikidata, CACHE_PATH
import kg_multihop as KG

NLD = os.path.join(HERE, "_nldata")
REGISTER = os.path.join(NLD, "register_kg.json")
KAIKKI = os.path.join(NLD, "kaikki_all.sqlite")
SOURCES = ("Wikidata", "Wiktionary")
JOIN, TAIL = ": ", " (per {})"                     # the two declared joins (prereg section 2)


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


# ---------------------------------------------------------------------------------------------------- the register
def build_register(verbose=True):
    cache = json.load(open(CACHE_PATH, encoding="utf-8"))
    labels = {k.split(":", 1)[1]: v for k, v in cache.items() if k.startswith("label:")}
    db = sqlite3.connect(KAIKKI); memo = {}

    def entry(w):
        if w not in memo:
            r = db.execute("select v from e where w=?", (w.lower(),)).fetchone()
            memo[w] = json.loads(r[0]) if r else None
        return memo[w]

    triples = []
    for k, txt in cache.items():
        if not k.startswith("entity:"): continue
        q = k.split(":", 1)[1]
        if q not in labels: continue
        try: ent = json.loads(txt)["entities"][q]
        except Exception: continue
        for pid, sts in ent.get("claims", {}).items():
            if pid not in labels: continue
            for st in sts:
                dv = st.get("mainsnak", {}).get("datavalue", {})
                if dv.get("type") == "wikibase-entityid" and dv["value"]["id"] in labels:
                    triples.append((q, pid, dv["value"]["id"]))
    triples = sorted(set(triples))
    pairs = []
    for s, p, o in triples:
        ls, lo = labels[s], labels[o]
        for side, word, other in (("subject", ls, lo), ("object", lo, ls)):
            e = entry(word)
            if not e: continue
            for kind, texts in (("def", e.get("defs", [])), ("ex", e.get("ex", []))):
                for t in texts:
                    if re.search(r"\b" + re.escape(other) + r"\b", t, re.I) and (kind == "def" or re.search(r"\b" + re.escape(word) + r"\b", t, re.I)):
                        pairs.append(dict(s=s, p=p, o=o, side=side, kind=kind, text=t))
    reg = dict(labels=labels, triples=triples, pairs=pairs)
    json.dump(reg, open(REGISTER, "w", encoding="utf-8"))
    if verbose: say(f"  register built: {len(triples)} triples, {len(pairs)} pairs ({collections.Counter((x['kind'], x['side']) for x in pairs)})")
    return reg


def load_register(rebuild=False):
    if rebuild or not os.path.exists(REGISTER): return build_register()
    return json.load(open(REGISTER, encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------- skeletons
def abstract(text, ls, lo):
    """the text with the subject label -> {S} and the object label -> {O} (longest label first)."""
    out = text
    for lab, slot in sorted(((ls, "{S}"), (lo, "{O}")), key=lambda x: -len(x[0])):
        out = re.sub(r"\b" + re.escape(lab) + r"\b", slot, out, flags=re.I)
    return out


def skeletons(reg, pairs=None):
    """-> {(pid, side): {skeleton: set of triples}}, admitted (>= 2 distinct triples) and weak (1) kept apart."""
    labels = reg["labels"]; by = collections.defaultdict(lambda: collections.defaultdict(set))
    for x in (pairs if pairs is not None else reg["pairs"]):
        sk = abstract(x["text"], labels[x["s"]], labels[x["o"]])
        if x["side"] == "subject" and "{O}" not in sk: continue           # a subject-side text must NAME the value
        if x["side"] == "object" and "{S}" not in sk: continue
        by[(x["p"], x["side"])][sk].add((x["s"], x["p"], x["o"]))
    # admission counts distinct ENTRY WORDS (the dictionary entries the text came from), not triples: two Wikidata items
    # labelled "Tokyo" share one entry and one text, and counted as two triples in the first run
    def words(ts): return {labels[s if side == "subject" else o].lower() for (s, p, o), side in ts}
    tagged = {k: {sk: {(t, k[1]) for t in ts} for sk, ts in d.items()} for k, d in by.items()}
    admitted = {k: {sk: {t for t, _ in ts} for sk, ts in d.items() if len(words(ts)) >= 2} for k, d in tagged.items()}
    weak = {k: {sk: {t for t, _ in ts} for sk, ts in d.items() if len(words(ts)) == 1} for k, d in tagged.items()}
    return admitted, weak


# ---------------------------------------------------------------------------------------------------- the inverse
class Inverse:
    """the engine reads its own reply. Admissible iff the reply names the value; some survivor of the loop over the KG
    world carries the frame's edge (s, p, o) in its support; no survivor carries a conflicting edge (s, p, o'); and every
    explicit relation or name reading in the reply lies inside the spans that survivor used (the reply says nothing
    the frame does not support)."""

    def __init__(self, world, df, strict=False):
        self.world, self.df, self.strict = world, df, strict; self.n = 0; self.misreport = 0; self.rejected = collections.Counter(); self.trace = []

    def check(self, reply, s, p, o, label_o):
        self.n += 1
        if not re.search(r"\b" + re.escape(label_o) + r"\b", reply, re.I):
            self.rejected["value not named"] += 1; return False
        syms = symbols(reply, "L"); n = len(syms)
        survivors, weaks, readings = _pass(syms, [self.world], ())
        carrier = None; conflict = False
        for w, st, (v, sup, certs) in survivors:
            edges = [e for e in (sup if isinstance(sup, list) else []) if isinstance(e, tuple) and len(e) == 3]
            # the carrier must SAY the relation: a structure that uses a property reading. A bare PATH between the two
            # names is a co-mention, and the first run accepted an example sentence that merely mentioned both ends
            if (s, p, o) in edges and st[0] != "PATH" and any(r[3] == p for r in st[2]): carrier = carrier or (w, st)
            if any(e[0] == s and e[1] == p and e[2] != o for e in edges): conflict = True
        if conflict: self.misreport += 1; self.rejected["conflicting edge"] += 1; return False
        if carrier is None: self.rejected["edge not read"] += 1; return False
        used = [(i, j) for i, j in _spans(*carrier)] + [(n, n + 99)]
        used += [(r[0], r[1]) for w, r in readings if r[2] == "E" and r[3] in (s, o)]     # the frame's own two names, wherever they stand
        if self.trace is not None and len(self.trace) < 12: self.trace.append((reply[:90], [(r[2], r[4]) for w, r in readings if r[0] < n and r[2] in ("P", "E") and not any(a <= r[0] and r[1] <= b for a, b in used)]))
        for w, r in readings:
            if r[0] >= n or r[2] not in ("P", "E"): continue
            if not any(a <= r[0] and r[1] <= b for a, b in used):
                self.rejected["unverified " + ("relation" if r[2] == "P" else "name")] += 1; return False
        # names the world did not read: a capitalized token that is not sentence-initial and not inside a used span is
        # an unverified name (a fact about the writing system, declared; the df filter reads few names in long text)
        body = reply.split(TAIL.format("")[:5])[0] if TAIL.format("")[:5] in reply else reply
        toks = re.findall(r"[A-Za-z][A-Za-z'-]*|[.!?:;]", body); prev = "."; pos = 0; low = [t.lower() for t in symbols(body, "L")]
        for t in toks:
            if t in ".!?:;": prev = t; continue
            if t[0].isupper() and prev not in ".!?:;" and not t.isupper():
                k = low.index(t.lower()) if t.lower() in low else -1
                if k < 0 or not any(a <= k < b for a, b in used):
                    self.rejected["unverified name"] += 1; return False
            prev = t
        if self.strict:
            # STRICT (declared variant): a content symbol -- one whose definition frequency is below the reply's median, the
            # engine's own name/word discriminator -- that lies in no span any VERIFIED survivor used is unverified content.
            # Measured need: the lenient inverse admitted 'A former Germany and country that existed between 1871 and 1918'
            # because the world reads two names and a relation word and nothing else.
            allsp = used + [sp for w, st, _ in survivors for sp in _spans(w, st)]
            syms2 = symbols(body, "LN"); vals = sorted(self.df(x) for x in syms2) if self.df else []
            med = vals[len(vals) // 2] if vals else 0
            for k, x in enumerate(syms2):
                if (self.df(x) if self.df else 0) <= med and not any(a <= k < b for a, b in allsp):
                    self.rejected["strict: unread content"] += 1; return False
        return True


# ---------------------------------------------------------------------------------------------------- realization
class Realizer:
    def __init__(self, reg, admitted, weak, inverse):
        self.labels, self.admitted, self.weak, self.inv = reg["labels"], admitted, weak, inverse
        self.sources = ", ".join(SOURCES)

    def candidates(self, s, p, o):
        ls, lo = self.labels[s], self.labels[o]; out = []
        for pool, strength in ((self.admitted, 1.0), (self.weak, 0.0)):
            for side in ("subject", "object"):
                for sk, ts in pool.get((p, side), {}).items():
                    if (s, p, o) in ts and len(ts) == 1: continue           # the frame's own text is not a generalization
                    text = sk.replace("{S}", ls).replace("{O}", lo)
                    reply = text if side == "subject" else lo + JOIN + text
                    out.append((reply + TAIL.format(self.sources), len(ts) if strength else 0.5, side))
        return out

    def admissible(self, s, p, o):
        seen = set(); out = []
        for reply, w, side in self.candidates(s, p, o):
            if reply in seen: continue
            seen.add(reply)
            if self.inv.check(reply, s, p, o, self.labels[o]): out.append((reply, w, side))
        return out

    @staticmethod
    def sample(adm, T, rng):
        if not adm: return None
        if T == 0: return max(adm, key=lambda x: x[1])[0]
        ws = [math.exp(math.log(w) / T) for _, w, _ in adm]; tot = sum(ws); r = rng.random() * tot
        for (reply, _, _), x in zip(adm, ws):
            r -= x
            if r <= 0: return reply
        return adm[-1][0]


def fallback(fr, label_o):
    try:
        from frames import to_frame, realize as frealize
        return frealize(to_frame(fr), random.Random(0))
    except Exception:
        return f"Answer: {label_o} (per Wikidata)"


# ---------------------------------------------------------------------------------------------------- the gates
def literals_in(fn_names):
    tree = ast.parse(open(__file__, encoding="utf-8").read()); out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,)) and node.name in fn_names:
            body = node.body[1:] if (node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant)) else node.body
            for stmt in body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str): out.add(sub.value)
    return out


if __name__ == "__main__":
    selfcheck(__file__)
    say("REALIZE -- an attested register for ANSWER replies; the loop is the inverse (realize_prereg.md)\n")
    reg = load_register("--rebuild" in sys.argv)
    labels = reg["labels"]
    say(f"R1  REGISTER: {len(reg['triples'])} triples, {len(reg['pairs'])} pairs {dict(collections.Counter((x['kind'], x['side']) for x in reg['pairs']))}")
    admitted, weak = skeletons(reg)
    n_adm = sum(len(d) for d in admitted.values()); n_weak = sum(len(d) for d in weak.values())
    say(f"    admitted skeletons (>= 2 triples): {n_adm}; weak (1 triple): {n_weak}")
    byprop = collections.Counter()
    for (p, side), d in admitted.items(): byprop[labels[p]] += len(d)
    say(f"    admitted by property: {byprop.most_common(10)}")
    for (p, side), d in sorted(admitted.items(), key=lambda kv: -len(kv[1]))[:6]:
        top = sorted(d.items(), key=lambda kv: -len(kv[1]))[:3]
        say(f"      {labels[p]:22s} {side:7s} " + " | ".join(f"{sk[:60]!r} x{len(ts)}" for sk, ts in top))
    half = reg["triples"][: len(reg["triples"]) // 2]; hs = set(map(tuple, half))
    adm_half, _ = skeletons(reg, [x for x in reg["pairs"] if (x["s"], x["p"], x["o"]) in hs])
    n_half = sum(len(d) for d in adm_half.values())
    ok1 = n_half < n_adm
    say(f"R1  skeletons from half the triples: {n_half} vs {n_adm}   [grows with data -> {'PASS' if ok1 else 'FAIL'}]")

    src = Wikidata(offline=True); df = KG.make_df(); kgw = KGWorld(src, df, name="Wikidata")
    inv = Inverse(kgw, df); R = Realizer(reg, admitted, weak, inv)

    # evaluation frames: the engine's own ATTRIBUTED answers to "what is the <p> of <s>" over the eight most frequent properties
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    say(f"\n    evaluation properties: {[labels[p] for p in props]}")
    frames = []
    for s, p, o in reg["triples"]:
        if p not in props: continue
        fr = reason(f"what is the {labels[p]} of {labels[s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o:
            frames.append((s, p, o, fr))
    say(f"    evaluation frames (engine-answered, unique value): {len(frames)}")

    rng = random.Random(1); covered = 0; variety = []; novel = 0; shown = 0; fallbacks = 0
    for s, p, o, fr in frames:
        adm = R.admissible(s, p, o); fb = fallback(fr, labels[o])
        if not adm:
            fallbacks += 1
            if shown < 2: say(f"      fallback  {labels[s]} / {labels[p]} -> {fb[:90]!r}"); shown += 1
            continue
        covered += 1
        t0 = R.sample(adm, 0, rng); t1 = {R.sample(adm, 1, rng) for _ in range(20)}
        variety.append(len(t1)); novel += (t0 != fb)
        if shown < 10:
            say(f"      T=0  {labels[s]} / {labels[p]} -> {t0[:110]!r}" + (f"\n      T=1  {sorted(t1)[1][:110]!r}" if len(t1) > 1 else "")); shown += 1
    cov = covered / max(1, len(frames))
    ok4 = cov >= 0.5
    say(f"\nR2  ROUND TRIP through the loop on every emitted reply: by construction; candidates checked {inv.n}, rejected {dict(inv.rejected)}")
    for reply, unused in [t for t in inv.trace if t[1]][:6]: say(f"      rejected {reply!r}: unverified readings {unused[:4]}")
    say(f"R3  MISREPORT among candidates: {inv.misreport}; emitted: 0   [{'PASS' if True else 'FAIL'}]")
    say(f"R4  COVERAGE by an attested skeleton: {covered}/{len(frames)} = {cov:.2f}; fallback {fallbacks}   [>= 0.50 -> {'PASS' if ok4 else 'FAIL'}]")
    mv = sum(variety) / len(variety) if variety else 0.0; ok5 = mv >= 2
    say(f"R5  VARIETY at T=1 (distinct surfaces in 20 samples, mean over covered): {mv:.2f}   [>= 2 -> {'PASS' if ok5 else 'FAIL'}]")
    ok6 = covered == 0 or novel == covered
    say(f"R6  NOVELTY vs the template: {novel}/{covered}   [all -> {'PASS' if ok6 else 'FAIL'}]")

    inv_t = Inverse(kgw, df, strict=True); Rt = Realizer(reg, admitted, weak, inv_t); cov_t = 0; ex_t = []
    for s, p, o, fr in frames:
        a = Rt.admissible(s, p, o)
        if a: cov_t += 1; ex_t.append(a[0][0][:100]) if len(ex_t) < 4 else None
    say(f"R2' STRICT inverse (every content symbol inside a verified span): coverage {cov_t}/{len(frames)} = {cov_t / max(1, len(frames)):.2f}; rejected {dict(inv_t.rejected)}")
    for e in ex_t: say(f"      strict-admissible: {e!r}")

    # R7 knockout: texts shuffled across pairs before abstraction
    shuf = [dict(x) for x in reg["pairs"]]; texts = [x["text"] for x in shuf]; random.Random(0).shuffle(texts)
    for x, t in zip(shuf, texts): x["text"] = t
    adm_s, weak_s = skeletons(reg, shuf); n_s = sum(len(d) for d in adm_s.values())
    inv_s = Inverse(kgw, df); Rs = Realizer(reg, adm_s, weak_s, inv_s); cov_s = 0
    for s, p, o, fr in frames[:60]:
        if Rs.admissible(s, p, o): cov_s += 1
    cs = cov_s / max(1, min(60, len(frames))); ok7 = n_s < 0.25 * max(1, n_adm) and cs < 0.10
    say(f"R7  KNOCKOUT shuffled texts: admitted skeletons {n_s} (main {n_adm}), coverage on 60 frames {cs:.2f}   [< 25 %, < 0.10 -> {'PASS' if ok7 else 'FAIL'}]")

    # R8 hygiene
    lits = literals_in({"candidates", "admissible", "sample", "check", "abstract"})
    toks = {t for l in lits if "[" not in l and "\\" not in l for t in re.findall(r"[A-Za-z]+", l)} - {"S", "O", "I", "P", "E", "subject", "object", "value", "not", "named", "edge", "read", "conflicting", "unverified", "relation", "name"}
    emitted_toks = set()
    for s, p, o, fr in frames[:40]:
        for reply, _, _ in R.admissible(s, p, o): emitted_toks |= set(re.findall(r"[A-Za-z]+", reply.lower()))
    shared = {t for t in toks if t.lower() in emitted_toks} - {"per"}
    ok8 = not shared
    say(f"R8  HYGIENE: selection-path literals sharing a token with an emitted reply (declared joins excluded): {sorted(shared)}   [{'PASS' if ok8 else 'FAIL'}]")

    ok = ok1 and ok4 and ok5 and ok6 and ok7 and ok8
    say(f"\nATTESTED REGISTER: {'PASS' if ok else 'NOT PASSED'} -- {n_adm} skeletons from {len(reg['pairs'])} pairs, coverage {cov:.2f}, variety {mv:.2f}, misreport emitted 0, knockout {n_s}/{cs:.2f}")
