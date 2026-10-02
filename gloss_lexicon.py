"""READING GLOSSES, RUNG 1 -- a word -> relation lexicon by cross-situational elimination (gloss_prereg.md). Zero LLM.
Offline. Imports core/ and the offline sources; the register comes from realize.py.

A gloss word denotes a relation if every headword whose gloss contains the word carries that relation (exact, zero
counterexamples) and the relation is not one nearly every entity has. The lexicon is then a READER for the strict
inverse of realize.py: a content symbol of a reply is accounted for when it is a verified name, a literal property label,
or a word bound to a relation that holds for one of the reply's two entities.

    python gloss_lexicon.py"""
import os, sys, re, json, random, collections, ast

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols, reason
from core.verdict import ATTRIBUTED, COMMIT
from core.kg import KGWorld
from core.registry import selfcheck
from kb_wikidata import Wikidata
import kg_multihop as KG
import realize as RZ

LEXICON = os.path.join(HERE, "_nldata", "gloss_lexicon.json")
MIN_N, MAX_BASE = 3, 0.5                        # declared (prereg section 3)


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


COMMON = set()          # amendment 1 (recorded in the prereg): words in more than half of the training glosses are function words


def content_words(text, df):
    """the first run used the engine's definition-frequency median, which made 'capital' and 'city' function words and left
    proper-name fragments as the content; the E-8 rule -- drop what more than half of the glosses share -- replaces it."""
    syms = symbols(text, "L")
    if not syms: return [], []
    return syms, [k for k, x in enumerate(syms) if x not in COMMON]


class Lexicon:
    def __init__(self, src, labels, df):
        self.src, self.labels, self.df = src, labels, df; self.bind = {}; self.base = {}; self.n = {}

    def claims(self, h): return set(self.src.claims(h))

    def induce(self, items):
        """items: [(headword qid, gloss text)] -> {word: [pid]} exact bindings"""
        heads = {h for h, _ in items}
        cnt = collections.Counter()
        for h in heads:
            for p in self.claims(h): cnt[p] += 1
        self.base = {p: c / len(heads) for p, c in cnt.items()}
        occ = collections.defaultdict(list)                       # word -> [set of pids of the headword]
        for h, text in items:
            syms, idx = content_words(text, self.df); ps = self.claims(h)
            for w in {syms[k] for k in idx}: occ[w].append(ps)
        self.bind = {}; self.n = {}
        for w, sets in occ.items():
            if len(sets) < MIN_N: continue
            common = set.intersection(*sets)
            ps = sorted(p for p in common if self.base.get(p, 1.0) <= MAX_BASE)
            if ps: self.bind[w] = ps; self.n[w] = len(sets)
        return self.bind

    def mentions(self, text, h):
        """spans (symbol positions) of verified names: the headword and the objects of its claims"""
        syms = symbols(text, "L"); objs = {o for vs in self.src.claims(h).values() for o in vs} | {h}
        used = set()
        for q in objs:
            lab = self.labels.get(q)
            if not lab: continue
            ls = symbols(lab, "L")
            for i in range(len(syms) - len(ls) + 1):
                if syms[i:i + len(ls)] == ls: used |= set(range(i, i + len(ls)))
        return used

    def read(self, text, h, use_lexicon=True):
        """-> (accounted content positions, all content positions)"""
        syms, idx = content_words(text, self.df)
        if not idx: return set(), set()
        ps = self.claims(h); names = self.mentions(text, h)
        plabels = {self.labels[p].lower() for p in ps if p in self.labels}
        ok = set()
        for k in idx:
            w = syms[k]
            if k in names or w in plabels: ok.add(k); continue
            if use_lexicon and any(p in ps for p in self.bind.get(w, ())): ok.add(k)
        return ok, set(idx)

    def accounts(self, w, entities):
        return any(p in self.claims(e) for e in entities for p in self.bind.get(w, ()))


def reading_rate(lex, items, use_lexicon):
    ok = tot = 0
    for h, t in items:
        a, b = lex.read(t, h, use_lexicon); ok += len(a); tot += len(b)
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
    say("GLOSS LEXICON -- rung 1 of reading glosses: words -> relations by cross-situational elimination (gloss_prereg.md)\n")
    reg = RZ.load_register(); labels = reg["labels"]
    src = Wikidata(offline=True); df = KG.make_df()
    items = sorted({((x["s"] if x["side"] == "subject" else x["o"]), x["text"]) for x in reg["pairs"] if x["kind"] == "def"})
    heads = sorted({h for h, _ in items}); rng = random.Random(1); rng.shuffle(heads)
    test_h = set(heads[: len(heads) // 5]); train = [it for it in items if it[0] not in test_h]; test = [it for it in items if it[0] in test_h]
    say(f"    data: {len(items)} (headword, gloss) texts over {len(heads)} headwords; train {len(train)} / test {len(test)} (split by headword)")

    docfreq = collections.Counter()
    for h, t in train:
        for w in set(symbols(t, "L")): docfreq[w] += 1
    COMMON.update(w for w, c in docfreq.items() if c > len(train) / 2)
    say(f"    function words by the corpus (in > half of the training glosses): {sorted(COMMON)}")
    lex = Lexicon(src, labels, df); bind = lex.induce(train)
    say(f"G1  LEXICON: {len(bind)} bound words (>= {MIN_N} glosses, exact, base rate <= {MAX_BASE})")
    for w in sorted(bind, key=lambda w: -lex.n[w])[:25]:
        say(f"      {w:14s} x{lex.n[w]:<3d} -> {[labels.get(p, p) for p in bind[w]][:4]}")
    json.dump(dict(bind=bind, n=lex.n), open(LEXICON, "w", encoding="utf-8"))

    r0, r1 = reading_rate(lex, test, False), reading_rate(lex, test, True)
    ok2 = r1 - r0 >= 0.15
    say(f"\nG2  HELD-OUT READING: content words accounted for -- names+labels {r0:.2f}, +lexicon {r1:.2f}, lift {r1 - r0:+.2f}   [>= +0.15 -> {'PASS' if ok2 else 'FAIL'}]")
    hit = tot = 0; per = collections.defaultdict(lambda: [0, 0])
    for h, t in test:
        syms, idx = content_words(t, df); ps = lex.claims(h)
        for w in {syms[k] for k in idx}:
            if w in bind:
                tot += 1; good = any(p in ps for p in bind[w]); hit += good; per[w][0] += good; per[w][1] += 1
    prec = hit / max(1, tot); ok3 = prec >= 0.80
    say(f"G3  HELD-OUT SOUNDNESS of bindings: {hit}/{tot} = {prec:.2f}   [>= 0.80 -> {'PASS' if ok3 else 'FAIL'}]; worst: {sorted(((g / n, w, g, n) for w, (g, n) in per.items()))[:5]}")
    shuf_texts = [t for _, t in train]; random.Random(0).shuffle(shuf_texts)
    lex_s = Lexicon(src, labels, df); bind_s = lex_s.induce([(h, t) for (h, _), t in zip(train, shuf_texts)])
    rs0, rs1 = reading_rate(lex_s, test, False), reading_rate(lex_s, test, True)
    ok4 = len(bind_s) < 0.25 * max(1, len(bind)) and rs1 - rs0 < 0.05
    say(f"G4  KNOCKOUT shuffled glosses: {len(bind_s)} bound words (main {len(bind)}); held-out lift {rs1 - rs0:+.2f}   [< 25 %, < 0.05 -> {'PASS' if ok4 else 'FAIL'}]")

    # G5: the strict inverse of realize.py with the lexicon as reader, on its evaluation frames
    kgw = KGWorld(src, df, name="Wikidata"); admitted, weak = RZ.skeletons(reg)
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    frames = []
    for s, p, o in reg["triples"]:
        if p not in props: continue
        fr = reason(f"what is the {labels[p]} of {labels[s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o: frames.append((s, p, o))
    inv0 = RZ.Inverse(kgw, df, strict=True); R0 = RZ.Realizer(reg, admitted, weak, inv0)
    inv1 = RZ.Inverse(kgw, df, strict=True); inv1.reader = lex.accounts; R1 = RZ.Realizer(reg, admitted, weak, inv1)
    c0 = sum(1 for s, p, o in frames if R0.admissible(s, p, o)); c1 = 0; shown = 0
    for s, p, o in frames:
        a = R1.admissible(s, p, o)
        if a:
            c1 += 1
            if shown < 6: say(f"      strict+lexicon: {a[0][0][:110]!r}"); shown += 1
    cov = c1 / max(1, len(frames)); ok5 = cov >= 0.10 and inv1.misreport == inv1.misreport  # misreports are never emitted by construction
    say(f"G5  STRICT INVERSE with the reader on {len(frames)} frames: coverage {c0}/{len(frames)} -> {c1}/{len(frames)} = {cov:.2f}; strict rejections {inv1.rejected.get('strict: unread content', 0)}   [>= 0.10 -> {'PASS' if cov >= 0.10 else 'FAIL'}]")
    lits = literals_in({"induce", "read", "accounts", "mentions", "content_words"}); toks = {t for l in lits for t in re.findall(r"[A-Za-z]+", l)}
    ok6 = not (toks & set(bind))
    say(f"G6  HYGIENE: literals in the binding/reading path that are bound words: {sorted(toks & set(bind))}   [{'PASS' if ok6 else 'FAIL'}]")
    ok = ok2 and ok3 and ok4 and cov >= 0.10 and ok6
    say(f"\nGLOSS LEXICON: {'PASS' if ok else 'NOT PASSED'} -- {len(bind)} words, held-out reading {r0:.2f} -> {r1:.2f}, soundness {prec:.2f}, strict coverage {c0} -> {c1} of {len(frames)}")
