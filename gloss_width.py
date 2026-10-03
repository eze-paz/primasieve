"""WINDOW WIDTH AGAINST DATA, AND A DIFFERENT REGISTER (gloss_width_prereg.md). Zero LLM. Offline over the crawl store.

    python gloss_width.py [--frames 30]"""
import os, sys, re, json, random, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols, reason
from core.verdict import ATTRIBUTED, COMMIT
from core.kg import KGWorld
from core.registry import selfcheck
from kb_crawl import Crawl
import kg_multihop as KG
import realize as RZ
import gloss_scale as GS
import gloss_generate as GG

NLD = os.path.join(HERE, "_nldata")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def build_items(C, kinds=("defs",)):
    """as gloss_scale.build_items, with the example sentences as a second register"""
    db = sqlite3.connect(GS.KAIKKI); memo = {}

    def entry(w):
        if w not in memo:
            r = db.execute("select v from e where w=?", (w.lower(),)).fetchone(); memo[w] = json.loads(r[0]) if r else None
        return memo[w]
    items = set(); per = collections.Counter()
    for q, lab in C.db.execute("select q, label from ent where label is not null"):
        e = entry(lab)
        if not e: continue
        cl = C.allclaims(q)
        names = sorted({C.label(v) for vs in cl.values() for v in vs if v.startswith("Q")}, key=len, reverse=True)
        names = [n for n in names if n and not n.startswith("Q") and len(n) > 2][:300]
        nums = {v[2:] for vs in cl.values() for v in vs if v[:2] in ("T:", "N:")}
        for kind in kinds:
            for t in (e.get(kind, []) or [])[:12]:
                toks = set(symbols(t, "LN"))
                if any(re.search(r"\b" + re.escape(nm) + r"\b", t) for nm in names) or (nums & toks):
                    if kind == "ex" and not re.search(r"\b" + re.escape(lab) + r"\b", t): continue    # an example must mention its headword
                    items.add((q, t)); per[kind] += 1
    return sorted(items), dict(per)


def induce(C, items, W):
    heads = sorted({h for h, _ in items}); rng = random.Random(1); rng.shuffle(heads)
    test_h = set(heads[: len(heads) // 5]); train = [it for it in items if it[0] not in test_h]; test = [it for it in items if it[0] in test_h]
    R = GS.Scale(C); R._init_labels(); R.W = W; types, cons = R.induce(train); R.induce_free(train)
    ch = ct = 0
    for h, t in test:
        for key, f in R.windows(t, h):
            if key in cons: ct += 1; ch += R.wsatisfies(h, f, cons[key][1])
    texts = [t for _, t in train]; random.Random(0).shuffle(texts)
    Rs = GS.Scale(C); Rs._init_labels(); Rs.W = W; _, cs_ = Rs.induce([(h, t) for (h, _), t in zip(train, texts)])
    r = GS.rate(R, test, ("names", "labels", "types", "cons", "free"))
    return R, train, test, dict(windows=len(cons), soundness=round(ch / max(1, ct), 3), checked=ct, knockout=len(cs_), reading=round(r, 3))


if __name__ == "__main__":
    selfcheck(__file__)
    a = sys.argv; nframes = int(a[a.index("--frames") + 1]) if "--frames" in a else 30
    say("WIDTH AND REGISTER -- window width against data; definitions vs example sentences (gloss_width_prereg.md)\n")
    C = Crawl()
    items_d, per_d = build_items(C, ("defs",)); items_de, per_de = build_items(C, ("defs", "ex"))
    say(f"    registers: definitions {per_d}; definitions+examples {per_de}; items {len(items_d)} / {len(items_de)}")
    results = {}; readers = {}
    for name, items, W in ((("E", items_de, 5),) if "--long" in a else (("A", items_d, 3), ("B", items_d, 5), ("C", items_d, 7), ("D", items_de, 3), ("E", items_de, 5))):
        R, train, test, st = induce(C, items, W); results[name] = st; readers[name] = (R, train, test)
        say(f"X1  {name} W={W} {'defs' if items is items_d else 'defs+ex'}: windows {st['windows']}, held-out soundness {st['soundness']} ({st['checked']} checked), knockout {st['knockout']}, reading {st['reading']}")
    if "--long" in a: results.setdefault("A", results["E"]); results.setdefault("B", results["E"]); results.setdefault("C", results["E"]); readers.setdefault("A", readers["E"]); readers.setdefault("D", readers["E"])
    fB = results["B"]["windows"] / max(1, results["A"]["windows"]); fC = results["C"]["windows"] / max(1, results["A"]["windows"])
    say(f"X2  WIDTH: W=5 admits {fB:.2f} of W=3's windows, W=7 admits {fC:.2f}   [predicted < 0.25, < 0.05]")
    kA = set(readers["A"][0].cons); kD = set(readers["D"][0].cons); new = kD - kA
    shapesA = {(k[0], k[1]) for k in kA}; shapesD = {(k[0], k[1]) for k in kD}
    say(f"X3  REGISTER: examples add {len(new)} windows at W=3 ({len(shapesD - shapesA)} new shapes)   [>= 500 -> {'PASS' if len(new) >= 500 else 'FAIL'}]")
    RD = readers["D"][0]
    for key in sorted(new, key=lambda k: -RD.cons[k][0])[:10]:
        left, right, p = key
        say(f"      x{RD.cons[key][0]:<4d} {' '.join(left)} {{E{':' + RD.labels.get(p, p) if p and p != 'HEAD' else ('HEAD' if p == 'HEAD' else '')}}} {' '.join(right)}")
    say(f"X4  READING per config: " + ", ".join(f"{n} {results[n]['reading']}" for n in results))

    # X5 generation on D and E
    reg = GS.register_from_crawl(C, items_d); df = KG.make_df(); kgw = KGWorld(C, df, name="Wikidata")
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    cand = [t for t in reg["triples"] if t[1] in props]; random.Random(2).shuffle(cand); frames = []
    for s, p, o in cand:
        if len(frames) >= nframes: break
        fr = reason(f"what is the {reg['labels'][p]} of {reg['labels'][s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o: frames.append((s, p, o))
    for name in (("E-long",) if "--long" in a else ("D", "E")):
        R = readers[name[0]][0]; G = GG.Generator(R, C); G.prefer_long = name.endswith("long"); inv = RZ.Inverse(kgw, df, strict=True, reader=R); emitted = {}
        for rnd in range(2):
            for s, p, o in frames:
                got = None
                for sent, keys, nf in G.candidates(s, p, o):
                    ok = inv.check(sent, s, p, o, C.label(o))
                    for k in keys: G.standing[k] += 1 if ok else -1
                    if ok and got is None: got = (sent, keys, nf)
                if got and (s, p, o) not in emitted: emitted[(s, p, o)] = got
            for k, st in list(G.standing.items()):
                if st < 0: G.retired.add(k)
        lens = [len(v[0].split(GG.JOIN, 1)[-1].split()) for v in emitted.values()]
        say(f"X5  {name} (W={R.W}): coverage {len(emitted)}/{len(frames)}, two-fact {sum(1 for v in emitted.values() if v[2] >= 2)}, mean length {sum(lens) / max(1, len(lens)):.1f} tokens, misreports emitted 0 ({inv.misreport} candidates dropped)")
        for v in list(emitted.values())[:8]: say(f"      {v[0][:120]!r}")

    # X6 form overlap with narrative text
    def toks_of(path):
        try: return set(w for l in open(path, encoding="utf-8", errors="replace") for w in symbols(l, "LN"))
        except FileNotFoundError: return set()
    def ngrams(path, n):
        out = set()
        try:
            for l in open(path, encoding="utf-8", errors="replace"):
                ws = symbols(l, "LN")
                for i in range(len(ws) - n + 1): out.add(tuple(ws[i:i + n]))
        except FileNotFoundError: pass
        return out
    for corpus in ("alice.txt", "brent_phono.txt"):
        path = os.path.join(NLD, corpus); grams = {n: ngrams(path, n) for n in (1, 2, 3)}
        hit = tot = 0
        for (left, right, p) in RD.cons:
            for side in (left, right):
                if side: tot += 1; hit += tuple(side) in grams.get(len(side), set())
        say(f"X6  form overlap with {corpus}: {hit}/{tot} = {hit / max(1, tot):.3f} of the reader's window sides occur as n-grams there   [no claim]")
    ok = all(results[n]["soundness"] >= 0.85 for n in results if results[n]["windows"] >= 50) and len(new) >= 500
    say(f"\nWIDTH AND REGISTER: {'PASS' if ok else 'NOT PASSED'} -- W5/W3 {fB:.2f}, W7/W3 {fC:.2f}, examples add {len(new)} windows")
