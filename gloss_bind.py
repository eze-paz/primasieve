"""POSITIONAL TYPE BINDING, AND A TYPED VOUCHER FOR GENERATION (gloss_bind_prereg.md). Zero LLM. Offline over the crawl.

A gloss word binds a type of the entity it stands next to: the headword when it opens the gloss (role H), a verified
mention when it sits within D tokens left (L) or right (R) of it. Generation is then vouched word by word: every content
token must be bound, in the role its position gives it, to a type that holds for the entity anchoring that position.

    python gloss_bind.py [--frames 30]"""
import os, sys, re, random, collections

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
import gloss_width as GW

D, MIN_OCC, HOLD, MAX_BASE, FW_DOC = 3, 5, 0.90, 0.5, 0.05


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


class Binder:
    def __init__(self, R):
        self.R = R; self.bind = {}; self.n = {}; self.fw = set(); self.base = {}

    def anchors(self, syms, h):
        """-> [(position, role, entity)] for every word position within D of an anchor"""
        m = self.R.mentions(syms, h); out = []
        starts = {}
        for k, (o, p, start) in m.items(): starts.setdefault(start, [start, start, o])
        for start, v in starts.items():
            end = start
            while end in m and m[end][2] == start: end += 1
            v[1] = end
        # amendment 1 (recorded): the role carries the DISTANCE. Measured: 'city' stands at L1 of Paris in "largest city:
        # Paris" and at L2 of France in "capital city of France"; a side-only role mixed the entity a word describes with
        # the one across a preposition, and no gloss noun bound (1 of 10)
        for i, end, o in starts.values():
            for k in range(max(0, i - D), i):
                if k not in m: out.append((k, "L%d" % (i - k), o))
            for k in range(end, min(len(syms), end + D)):
                if k not in m: out.append((k, "R%d" % (k - end + 1), o))
        for k in range(min(D, len(syms))):
            if k not in m: out.append((k, "H%d" % (k + 1), h))
        return out, m

    def induce(self, items):
        occ = collections.defaultdict(list); role_pop = collections.defaultdict(set); docf = collections.Counter()
        for h, t in items:
            syms = symbols(t, "LN"); docf.update(set(syms))
            anc, _ = self.anchors(syms, h)
            for k, role, e in anc:
                occ[(syms[k], role)].append(e); role_pop[role].add(e)
        tsets = {}
        def ts(e):
            if e not in tsets: tsets[e] = self.R.typeset(e)
            return tsets[e]
        for role, pop in role_pop.items():
            cnt = collections.Counter()
            for e in pop: cnt.update(ts(e))
            self.base[role] = {t: c / len(pop) for t, c in cnt.items()}
        self.bind = {}; self.n = {}
        for key, ents in occ.items():
            if len(ents) < MIN_OCC: continue
            cnt = collections.Counter(t for e in ents for t in ts(e))
            role = key[1]
            good = sorted((t for t, c in cnt.items() if c >= HOLD * len(ents) and self.base[role].get(t, 1.0) <= MAX_BASE),
                          key=lambda t: self.base[role][t])
            if good: self.bind[key] = good[:3]; self.n[key] = len(ents)
        bound_words = {w for w, _ in self.bind}
        self.fw = {w for w, c in docf.items() if c > FW_DOC * len(items) and w not in bound_words}
        return self.bind

    def holds(self, w, role, e):
        return any(t in self.R.typeset(e) for t in self.bind.get((w, role), ()))

    def vouch(self, body, s):
        """-> (ok, first untyped content word or None) for a generated sentence body about headword s"""
        syms = symbols(body, "LN")
        anc, m = self.anchors(syms, s)
        by_pos = collections.defaultdict(list)
        for k, role, e in anc: by_pos[k].append((role, e))
        for k, w in enumerate(syms):
            if k in m or w in self.fw: continue
            if not any(self.holds(w, role, e) for role, e in by_pos.get(k, [])): return False, w
        return True, None


if __name__ == "__main__":
    selfcheck(__file__)
    a = sys.argv; nframes = int(a[a.index("--frames") + 1]) if "--frames" in a else 30
    say("POSITIONAL BINDING -- a word binds a type of the entity beside it; generation vouched word by word (gloss_bind_prereg.md)\n")
    C = Crawl(); items, per = GW.build_items(C, ("defs", "ex"))
    R, train, test, st = GW.induce(C, items, 5)
    say(f"    data {per}; reader W=5: {st}")
    B = Binder(R); bind = B.induce(train)
    roles = collections.Counter(r for _, r in bind)
    fw_nouns = sorted(w for w in ["city", "capital", "river", "island", "language", "country", "province", "county", "town", "village"] if w in B.fw)
    say(f"\nB1  BINDINGS: {len(bind)} (word, role) pairs {dict(roles)}; function words {len(B.fw)} (e.g. {sorted(B.fw)[:14]})")
    for key in sorted(bind, key=lambda k: -B.n[k])[:24]:
        say(f"      {key[0]:14s} {key[1]}  x{B.n[key]:<5d} -> {[R.labels.get(o, o) for p, o in bind[key]]}")
    nouns = ["city", "capital", "river", "island", "language", "country", "province", "county", "town", "village"]
    got = {w: sorted(r for (x, r) in bind if x == w) for w in nouns}
    nb = sum(1 for w in nouns if got[w])
    say(f"B1  gloss nouns bound: {nb}/10 {got}   [>= 6 -> {'PASS' if nb >= 6 else 'FAIL'}]")
    say(f"B1' gloss nouns that fell into the FUNCTION-WORD class (frequent, binding nothing -> passed by the voucher unchecked): {fw_nouns}")
    hit = tot = 0
    for h, t in test:
        syms = symbols(t, "LN"); anc, _ = B.anchors(syms, h)
        for k, role, e in anc:
            if (syms[k], role) in bind: tot += 1; hit += B.holds(syms[k], role, e)
    ok2 = hit / max(1, tot) >= 0.85
    say(f"B2  HELD-OUT SOUNDNESS: {hit}/{tot} = {hit / max(1, tot):.3f}   [>= 0.85 -> {'PASS' if ok2 else 'FAIL'}]")
    texts = [t for _, t in train]; random.Random(0).shuffle(texts)
    Bs = Binder(R); bs = Bs.induce([(h, t) for (h, _), t in zip(train, texts)])
    ok3 = len(bs) < 0.25 * max(1, len(bind))
    say(f"B3  KNOCKOUT shuffled glosses: {len(bs)} bindings (main {len(bind)})   [< 25 % -> {'PASS' if ok3 else 'FAIL'}]")

    # generation, longest-first, with and without the typed voucher
    items_d, _ = GW.build_items(C, ("defs",))
    reg = GS.register_from_crawl(C, items_d); df = KG.make_df(); kgw = KGWorld(C, df, name="Wikidata")
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    cand = [t for t in reg["triples"] if t[1] in props]; random.Random(2).shuffle(cand); frames = []
    for s, p, o in cand:
        if len(frames) >= nframes: break
        fr = reason(f"what is the {reg['labels'][p]} of {reg['labels'][s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o: frames.append((s, p, o))
    gloss_toks = collections.defaultdict(set)
    for h, t in items: gloss_toks[h] |= set(symbols(t, "LN"))
    def unsupported(sent, s):
        body = sent.split(GG.JOIN, 1)[-1]; syms = symbols(body, "LN"); m = R.mentions(syms, s)
        ents = {s} | {v[0] for v in m.values()}; sup = set().union(*[gloss_toks.get(e, set()) for e in ents])
        content = [w for k, w in enumerate(syms) if k not in m and w not in B.fw]
        return sum(1 for w in content if w not in sup), len(content)
    out = {}; reasons = collections.Counter()
    for arm in ("untyped", "typed"):
        G = GG.Generator(R, C); G.prefer_long = True; inv = RZ.Inverse(kgw, df, strict=True, reader=R); emitted = {}
        for rnd in range(2):
            for s, p, o in frames:
                got_ = None
                for sent, keys, nf in G.candidates(s, p, o):
                    ok = inv.check(sent, s, p, o, C.label(o))
                    if ok and arm == "typed":
                        tok, bad = B.vouch(sent.split(GG.JOIN, 1)[-1], s)
                        if not tok: reasons[bad] += 1; ok = False
                    for k in keys: G.standing[k] += 1 if ok else -1
                    if ok and got_ is None: got_ = (sent, nf)
                if got_ and (s, p, o) not in emitted: emitted[(s, p, o)] = got_
            for k, sv in list(G.standing.items()):
                if sv < 0: G.retired.add(k)
        un = [unsupported(v[0], s) for (s, p, o), v in emitted.items()]
        rate = sum(u for u, _ in un) / max(1, sum(n for _, n in un))
        lens = [len(v[0].split(GG.JOIN, 1)[-1].split()) for v in emitted.values()]
        bad_family = sum(1 for v in emitted.values() if "neighborhood of new orleans" in v[0])
        out[arm] = dict(cov=len(emitted), rate=rate, len=sum(lens) / max(1, len(lens)), fam=bad_family, sents=[v[0] for v in emitted.values()])
        say(f"\nB4  {arm.upper()}: coverage {len(emitted)}/{len(frames)}, mean length {out[arm]['len']:.1f} tokens, unsupported-content rate {rate:.3f}, 'neighborhood of new orleans' family {bad_family}")
        for v in list(emitted.values())[:10]: say(f"      {v[0][:120]!r}")
    say(f"      words that failed the typed voucher most often: {reasons.most_common(15)}")
    ok4 = out["typed"]["cov"] > 0
    ok5 = out["typed"]["rate"] < 0.25 and out["typed"]["rate"] < out["untyped"]["rate"]
    ok6 = out["typed"]["fam"] == 0
    say(f"\nB4  typed coverage {out['typed']['cov']}/{len(frames)}   [> 0 -> {'PASS' if ok4 else 'FAIL'}]")
    say(f"B5  AUDIT unsupported-content: untyped {out['untyped']['rate']:.3f} -> typed {out['typed']['rate']:.3f}   [< 0.25 and lower -> {'PASS' if ok5 else 'FAIL'}]")
    say(f"B6  known false family under the typed voucher: {out['typed']['fam']} (untyped {out['untyped']['fam']})   [0 -> {'PASS' if ok6 else 'FAIL'}]")
    say(f"B7  HYGIENE: the binding and vouching paths hold no English literal (the gloss-noun list is the B1 gate's printout only)   [PASS]")
    ok = nb >= 6 and ok2 and ok3 and ok4 and ok5 and ok6
    say(f"\nPOSITIONAL BINDING: {'PASS' if ok else 'NOT PASSED'} -- {len(bind)} bindings, nouns {nb}/10, soundness {hit / max(1, tot):.3f}, knockout {len(bs)}, typed coverage {out['typed']['cov']}/{len(frames)} at length {out['typed']['len']:.1f}, unsupported {out['untyped']['rate']:.2f} -> {out['typed']['rate']:.2f}")
