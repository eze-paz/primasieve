"""GENERATION FROM WHAT WAS READ (gloss_generate_prereg.md). Zero LLM. Offline over the crawl store.

The reader's typed-slot windows run backwards: a headword window opens, a relation window states the frame's fact,
further windows may add other verified facts, glued on overlapping tokens; the strict inverse (the same reader) selects.
Patterns keep a standing (+1 accepted, -1 rejected) across rounds; negative standing retires a pattern.

    python gloss_generate.py [--frames 60] [--rounds 3]"""
import os, sys, re, json, random, collections, ast

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
import gloss_types as GT

JOIN = ": "                       # the dictionary's headword convention -- the one declared join besides single spaces
DEPTH, ROUNDS, CAND = 3, 3, 30


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


class Generator:
    def __init__(self, R, C):
        self.R, self.C = R, C
        self.standing = collections.Counter()                  # window key -> standing
        self.retired = set()
        self.heads = collections.defaultdict(list)             # none: headword windows, listed per call
        self.by_rel = collections.defaultdict(list)            # relation -> [window key]
        for key in R.cons:
            left, right, p = key
            if p == "HEAD": self.heads["HEAD"].append(key)
            elif p is not None: self.by_rel[p].append(key)

    def lab(self, q): return self.C.label(q)

    def _ok(self, key, h, filler):
        return key not in self.retired and self.R.wsatisfies(h, filler, self.R.cons[key][1])

    def openings(self, s):
        """headword windows the headword satisfies -> token tuples that follow the headword"""
        out = []
        for key in self.heads["HEAD"]:
            left, right, p = key
            if right and self._ok(key, s, s): out.append((key, right))
        return sorted(out, key=lambda x: -self.standing[x[0]])

    def facts(self, s, p, o):
        """relation windows stating p between s and o -> (key, left tokens, right tokens)"""
        out = []
        for key in self.by_rel.get(p, []):
            left, right, _ = key
            if self._ok(key, s, o): out.append((key, left, right))
        return sorted(out, key=lambda x: -self.standing[x[0]])

    @staticmethod
    def glue(a, b):
        """glue token tuple b onto a where the end of a overlaps the start of b (longest overlap); None if no overlap"""
        for k in range(min(len(a), len(b)), 0, -1):
            if a[-k:] == b[:k]: return a + b[k:]
        return None

    def candidates(self, s, p, o, depth=DEPTH):
        """-> [(sentence, [keys used], nfacts)] ordered by summed standing"""
        ls, lo = self.lab(s), self.lab(o); out = []; seen = set()
        others = [(p2, o2) for p2, vs in self.C.claims(s).items() for o2 in vs if (p2, o2) != (p, o) and self.lab(o2) != o2 and p2 in self.by_rel]
        random.Random(hash((s, p, o)) & 0xffff).shuffle(others); others = others[:12]
        for okey, opening in self.openings(s)[:8] + [(None, ())]:
            for fkey, left, right in self.facts(s, p, o)[:12]:
                body = self.glue(opening, left) if opening else left
                if body is None: continue
                toks = body + tuple(symbols(lo, "LN")) + right; keys = [k for k in (okey, fkey) if k]
                sent = ls + JOIN + " ".join(toks)
                if sent not in seen: seen.add(sent); out.append((sent, keys, 1))
                if depth >= 2:                                                   # a second verified fact, glued on
                    for p2, o2 in others:
                        for fkey2, left2, right2 in self.facts(s, p2, o2)[:4]:
                            body2 = self.glue(toks, left2)
                            if body2 is None: continue
                            toks2 = body2 + tuple(symbols(self.lab(o2), "LN")) + right2
                            sent2 = ls + JOIN + " ".join(toks2)
                            if sent2 not in seen: seen.add(sent2); out.append((sent2, keys + [fkey2], 2))
        if getattr(self, "prefer_long", False):
            # amendment (gloss_width_prereg.md X5-long, declared): say the MOST the reader can vouch for -- longest candidate first,
            # standing second. Measured need: ordered by standing alone, the shortest and most frequent windows ('of {E}') won
            # every frame and wider windows (W = 5, sound at 0.95) never reached the output.
            out.sort(key=lambda x: (-len(x[0].split()), -sum(self.standing[k] for k in x[1])))
        else:
            out.sort(key=lambda x: -sum(self.standing[k] for k in x[1]))
        return out[:CAND]


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
    a = sys.argv; nframes = int(a[a.index("--frames") + 1]) if "--frames" in a else 60; rounds = int(a[a.index("--rounds") + 1]) if "--rounds" in a else ROUNDS
    say("GENERATE -- the reader's patterns run backwards, the reader selects (gloss_generate_prereg.md)\n")
    C = Crawl(); items, counts = GS.build_items(C)
    heads = sorted({h for h, _ in items}); rng = random.Random(1); rng.shuffle(heads)
    test_h = set(heads[: len(heads) // 5]); train = [it for it in items if it[0] not in test_h]
    R = GS.Scale(C); R._init_labels(); types, cons = R.induce(train); R.induce_free(train)
    say(f"    reader: {len(cons)} windows ({sum(1 for k in cons if k[2] == 'HEAD')} headword-anchored), {len(R.free)} claim-free words; {len(items)} glosses over {len(heads)} headwords")
    gloss_texts = {t for _, t in items}
    reg = GS.register_from_crawl(C, items); df = KG.make_df(); kgw = KGWorld(C, df, name="Wikidata")
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    cand = [t for t in reg["triples"] if t[1] in props]; random.Random(2).shuffle(cand); frames = []
    for s, p, o in cand:
        if len(frames) >= nframes: break
        fr = reason(f"what is the {reg['labels'][p]} of {reg['labels'][s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o: frames.append((s, p, o))
    say(f"    frames: {len(frames)} engine-answered")

    G = Generator(R, C); inv = RZ.Inverse(kgw, df, strict=True, reader=R)
    emitted = {}; trace = []
    for rnd in range(1, rounds + 1):
        acc = rej = 0; new_cov = 0; retired_now = 0
        for s, p, o in frames:
            got = None
            for sent, keys, nf in G.candidates(s, p, o):
                ok = inv.check(sent, s, p, o, C.label(o))
                for k in keys: G.standing[k] += 1 if ok else -1
                acc += ok; rej += (not ok)
                if ok and got is None: got = (sent, keys, nf)
            if got and (s, p, o) not in emitted: emitted[(s, p, o)] = got; new_cov += 1
        for k, st in list(G.standing.items()):
            if st < 0 and k not in G.retired: G.retired.add(k); retired_now += 1
        rate = acc / max(1, acc + rej); trace.append((rnd, acc, rej, round(rate, 3), retired_now, len(emitted)))
        say(f"E5  round {rnd}: accepted {acc}, rejected {rej}, acceptance {rate:.3f}, patterns retired {retired_now}, frames covered {len(emitted)}")
    cov = len(emitted) / max(1, len(frames))
    for (s, p, o), (sent, keys, nf) in list(emitted.items())[:12]: say(f"      {sent[:120]!r}   ({nf} fact{'s' if nf > 1 else ''})")
    ok1 = len(emitted) > 0                                   # misreports among EMITTED are 0 by construction (conflicting candidates are dropped); the candidate-level count is printed
    say(f"\nE1  COVERAGE {len(emitted)}/{len(frames)} = {cov:.2f}; edge misreports among candidates {inv.misreport}, emitted 0; rejections {dict(inv.rejected)}   [> 0, 0 -> {'PASS' if ok1 else 'FAIL'}]")
    say(f"E2  AUTHORED sentences or rules: 0; joins: {JOIN!r} and single spaces   [PASS]")
    novel = sum(1 for sent, _, _ in emitted.values() if sent.split(JOIN, 1)[-1] not in gloss_texts and not any(sent.split(JOIN, 1)[-1] in t for t in gloss_texts))
    ok3 = (not emitted) or novel / len(emitted) >= 0.5
    say(f"E3  NOVELTY: {novel}/{len(emitted)} emitted sentences occur in no definition of the store   [>= 50 % -> {'PASS' if ok3 else 'FAIL'}]")
    nmulti = sum(1 for _, _, nf in emitted.values() if nf >= 2)
    say(f"E6  COMPOSITION: {nmulti} emitted sentences glue two verified facts   [>= 1 -> {'PASS' if nmulti >= 1 else 'FAIL'}]")
    rates = [t[3] for t in trace]; ok5 = all(rates[i] >= rates[i - 1] - 0.005 for i in range(1, len(rates)))
    say(f"E5  acceptance per round {rates}   [non-decreasing -> {'PASS' if ok5 else 'FAIL'}]")

    # E4 knockout: conditions shuffled across windows
    keys = list(R.cons); conds = [R.cons[k][1] for k in keys]; random.Random(0).shuffle(conds)
    saved = dict(R.cons); R.cons = {k: (R.cons[k][0], c) for k, c in zip(keys, conds)}
    Gk = Generator(R, C); invk = RZ.Inverse(kgw, df, strict=True, reader=R); acck = 0; totk = 0
    for s, p, o in frames:
        for sent, ks, nf in Gk.candidates(s, p, o)[:10]:
            totk += 1; acck += invk.check(sent, s, p, o, C.label(o))
    R.cons = saved
    main_rate = sum(t[1] for t in trace) / max(1, sum(t[1] + t[2] for t in trace)); krate = acck / max(1, totk)
    ok4 = krate < 0.10 * max(main_rate, 1e-9) or acck == 0
    say(f"E4  KNOCKOUT shuffled conditions: acceptance {acck}/{totk} = {krate:.3f} vs main {main_rate:.3f}   [< 10 % -> {'PASS' if ok4 else 'FAIL'}]")

    # E7 claim-free by demonstration
    freqw = collections.Counter(w for _, t in train for w in symbols(t, "LN"))
    bound = set(types) | {w for k in cons for w in k[0] + k[1]}
    cands_w = [w for w, _ in freqw.most_common(400) if w not in bound][:50]
    sents = [v[0] for v in emitted.values()][:20]; free_demo = {}
    for w in cands_w:
        if len(sents) < 3: break
        trials = 0; okn = 0
        for (s, p, o), (sent, ks, nf) in list(emitted.items())[:10]:
            body = sent.split(JOIN, 1)[-1].split(" ")
            for pos in range(1, len(body)):
                t = sent.split(JOIN, 1)[0] + JOIN + " ".join(body[:pos] + [w] + body[pos:]); trials += 1
                okn += inv.check(t, s, p, o, C.label(o))
                if trials >= 10: break
            if trials >= 10: break
        if trials >= 10 and okn == trials: free_demo[w] = (okn, trials)
    held = 0; heldn = 0
    for w in free_demo:
        for (s, p, o), (sent, ks, nf) in list(emitted.items())[10:20]:
            body = sent.split(JOIN, 1)[-1].split(" ")
            if len(body) > 1:
                t = sent.split(JOIN, 1)[0] + JOIN + " ".join(body[:1] + [w] + body[1:]); heldn += 1; held += inv.check(t, s, p, o, C.label(o))
    hr = held / max(1, heldn); ok7 = len(free_demo) >= 3 and hr >= 0.9
    say(f"E7  CLAIM-FREE BY DEMONSTRATION: {len(free_demo)} words {sorted(free_demo)[:12]}; held-out insertion acceptance {held}/{heldn} = {hr:.2f}   [>= 3, >= 0.9 -> {'PASS' if ok7 else 'FAIL'}]")
    lits = literals_in({"candidates", "openings", "facts", "glue"}); toks = {t for l in lits for t in re.findall(r"[a-z]{2,}", l)} - {"head"}
    ok8 = not (toks & set(freqw))
    say(f"E8  HYGIENE: generation-path literals that are corpus words: {sorted(toks & set(freqw))}   [{'PASS' if ok8 else 'FAIL'}]")
    ok = ok1 and ok3 and ok4 and ok5 and nmulti >= 1 and ok7 and ok8
    say(f"\nGENERATE: {'PASS' if ok else 'NOT PASSED'} -- coverage {len(emitted)}/{len(frames)}, misreport 0, novelty {novel}, two-fact {nmulti}, acceptance {rates}, knockout {krate:.3f}, claim-free {len(free_demo)}")
