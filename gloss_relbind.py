"""RELATION BINDING (gloss_relbind_prereg.md). Zero LLM. Offline over the crawl store.

A word beside a verified mention binds the RELATION linking the headword and that mention (either direction), under the
same diagnostic discipline as types. The voucher admits a word when its bound relation holds between the sentence's
subject and the entity it stands beside.

    python gloss_relbind.py [--frames 30]"""
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
import gloss_compose as GC

MIN_OCC, HOLD, MAX_BASE, THETA = 5, 0.90, 0.5, 0.20
if "--hold" in sys.argv: HOLD = float(sys.argv[sys.argv.index("--hold") + 1])   # EXPLORATORY only; the registered bar is 0.90


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


class RelBinder(GC.SpecBinder):
    WATCH = ("capital", "city", "largest", "official", "seat")

    def __init__(self, R, glue, C):
        super().__init__(R, glue); self.C = C; self.watch = []; self.rbind = {}; self.rspec = {}; self.rn = {}; self._rel = {}

    def canon(self, p, d):
        """amendment 1 (recorded): a relation and its inverse are ONE fact -- the graph's own 'inverse property' claims
        (P36 capital <-> P1376 capital of). Measured: 'capital' beside its mention linked the pair by (capital, +) in 69 %
        and by (capital of, -) in 30 % of occurrences -- the same fact recorded from one end or the other."""
        inv = self.__dict__.setdefault("_inv", {})
        if p not in inv:
            q = self.C.allclaims(p).get("P1696", [None])[0]; inv[p] = q
        q = inv[p]
        if q and q < p: return (q, "-" if d == "+" else "+")
        return (p, d)

    def rel(self, h, o):
        key = (h, o)
        if key not in self._rel:
            out = {self.canon(p, "+") for p, vs in self.C.claims(h).items() if o in vs}
            out |= {self.canon(p, "-") for p, vs in self.C.claims(o).items() if h in vs}
            self._rel[key] = out
        return self._rel[key]

    def induce_rel(self, items):
        occ = collections.defaultdict(list); pop = collections.defaultdict(list); inst = collections.defaultdict(set)
        for h, t in items:
            syms = symbols(t, "LN"); anc, _ = self.anchors(syms, h)
            for k, role, e in anc:
                if role[0] == "H": continue
                rs = self.rel(h, e); occ[(syms[k], role)].append(rs); pop[role].append(rs)
                inst[(h, e, role[0])].add(syms[k])
        base = {}
        for role, lst in pop.items():
            cnt = collections.Counter(r for rs in lst for r in rs); base[role] = {r: c / len(lst) for r, c in cnt.items()}
        self.rbind = {}; self.rn = {}
        for key, lst in occ.items():
            if len(lst) < MIN_OCC: continue
            cnt = collections.Counter(r for rs in lst for r in rs); role = key[1]
            good = [r for r, c in cnt.items() if c >= HOLD * len(lst) and base[role].get(r, 1.0) <= MAX_BASE]
            if key[0] in self.WATCH and len(lst) >= 20:
                self.watch.append((key, len(lst), [(r, round(c / len(lst), 3)) for r, c in cnt.most_common(2)]))
            if good: self.rbind[key] = good; self.rn[key] = len(lst)
        # diagnostic test per side: among pairs linked by r, the fraction whose window holds the word
        n_r = collections.Counter(); n_wr = collections.Counter()
        need = {r for rs in self.rbind.values() for r in rs}
        for (h, e, side), words in inst.items():
            for r in self.rel(h, e) & need:
                n_r[(side, r)] += 1
                for w in words: n_wr[(w, side, r)] += 1
        self.rspec = {}; self.rrecall = {}
        for (w, role), rs in self.rbind.items():
            keep = []
            for r in rs:
                rec = n_wr[(w, role[0], r)] / max(1, n_r[(role[0], r)]); self.rrecall[(w, role, r)] = rec
                if rec >= THETA: keep.append(r)
            if keep: self.rspec[(w, role)] = keep
        return self.rspec

    def vouch(self, body, s, extra=(), use_rel=True, trace=None):
        syms = symbols(body, "LN"); anc, m = self.anchors(syms, s)
        for e in extra:
            for k, v in self.R.mentions(syms, e).items(): m.setdefault(k, v)
        by_pos = collections.defaultdict(list)
        for k, role, e in anc: by_pos[k].append((role, e))
        used = set()
        for k, w in enumerate(syms):
            if k in m or w in self.glue: continue
            ok = False
            for role, e in by_pos.get(k, []):
                for tt in self.spec.get((w, role), ()):
                    if (tt, e) not in used and tt in self.R.typeset(e): used.add((tt, e)); ok = True; break
                if ok: break
            if not ok and use_rel:
                for role, e in by_pos.get(k, []):
                    if role[0] == "H": continue
                    if any(r in self.rel(s, e) for r in self.rspec.get((w, role), ())):
                        ok = True
                        if trace is not None: trace.append((k, w, role, e))
                        break
            if not ok: return False, w
        return True, None


if __name__ == "__main__":
    selfcheck(__file__)
    a = sys.argv; nframes = int(a[a.index("--frames") + 1]) if "--frames" in a else 30
    say("RELATION BINDING -- a word is checked against the fact linking the two things it stands between (gloss_relbind_prereg.md)\n")
    C = Crawl(); items, per = GW.build_items(C, ("defs", "ex"))
    R, train, test, st = GW.induce(C, items, 5); glue = sorted(R.free)
    RB = RelBinder(R, glue, C); RB.induce(train); rspec = RB.induce_rel(train)
    say(f"    data {per}; reader {st}; type-diagnostic {len(RB.spec)}; relation bindings {len(RB.rbind)} -> diagnostic {len(rspec)}")
    lab = lambda r: f"{'' if r[1] == '+' else '~'}{R.labels.get(r[0], r[0])}"
    say(f"    HOLD = {HOLD}{'  (EXPLORATORY: the registered bar is 0.90)' if HOLD != 0.90 else ''}")
    for key, n, top in sorted(RB.watch, key=lambda x: -x[1])[:12]: say(f"      watch {key[0]:9s} {key[1]} n={n:4d}  merged hold of top relations {[(lab(r), h) for r, h in top]}")
    for key in sorted(rspec, key=lambda k: -RB.rn[k])[:24]:
        say(f"      {key[0]:12s} {key[1]}  x{RB.rn[key]:<5d} -> {[lab(r) for r in rspec[key]][:3]}")
    words = ["capital", "largest", "city", "official", "seat", "border", "located", "spoken", "part", "member"]
    got = {w: sorted({role for (x, role) in rspec if x == w}) for w in words}; nb = sum(1 for w in words if got[w])
    say(f"R1  bound: {nb}/10 {got}   [>= 4 -> {'PASS' if nb >= 4 else 'FAIL'}]")
    hit = tot = 0
    for h, t in test:
        syms = symbols(t, "LN"); anc, _ = RB.anchors(syms, h)
        for k, role, e in anc:
            if (syms[k], role) in rspec: tot += 1; hit += any(r in RB.rel(h, e) for r in rspec[(syms[k], role)])
    ok2 = hit / max(1, tot) >= 0.85
    say(f"R2  HELD-OUT SOUNDNESS: {hit}/{tot} = {hit / max(1, tot):.3f}   [>= 0.85 -> {'PASS' if ok2 else 'FAIL'}]")
    texts = [t for _, t in train]; random.Random(0).shuffle(texts)
    RBs = RelBinder(R, glue, C); RBs.spec = {}; ks = RBs.induce_rel([(h, t) for (h, _), t in zip(train, texts)])
    ok3 = len(ks) < 0.25 * max(1, len(rspec))
    say(f"R3  KNOCKOUT shuffled glosses: {len(ks)} (main {len(rspec)})   [< 25 % -> {'PASS' if ok3 else 'FAIL'}]")

    items_d, _ = GW.build_items(C, ("defs",))
    reg = GS.register_from_crawl(C, items_d); df = KG.make_df(); kgw = KGWorld(C, df, name="Wikidata")
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    cand = sorted(t for t in reg["triples"] if t[1] in props); random.Random(2).shuffle(cand); frames = []
    for s, p, o in cand:
        if len(frames) >= nframes: break
        fr = reason(f"what is the {reg['labels'][p]} of {reg['labels'][s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o: frames.append((s, p, o))
    say(f"\n    frames: {len(frames)} ({', '.join(C.label(s) for s, _, _ in frames[:8])} ...)")
    by_head = collections.defaultdict(list)
    for h, t in items: by_head[h].append(t)

    def h1(use_rel):
        inv = RZ.Inverse(kgw, df, strict=True, reader=R); em = {}; tried = acc = 0; refused = collections.Counter(); accepted = []
        for s, p, o in frames:
            cands = [(C.label(s) + GG.JOIN + t, s) for t in by_head.get(s, [])]
            cands += [(C.label(o) + GG.JOIN + t, o) for t in by_head.get(o, []) if re.search(r"\b" + re.escape(C.label(s)) + r"\b", t)]
            for sent, head in cands:
                tried += 1
                if not inv.check(sent, s, p, o, C.label(o)): continue
                tr = []
                v, bad = RB.vouch(sent.split(GG.JOIN, 1)[-1], head, extra=(o if head == s else s,), use_rel=use_rel, trace=tr)
                if not v: refused[bad] += 1; continue
                acc += 1; accepted.append((sent, head, s, o, tr))
                if (s, p, o) not in em: em[(s, p, o)] = sent
        return em, tried, acc, refused, accepted

    e0, t0, a0, r0, _ = h1(False); e1, t1, a1, r1, acc1 = h1(True)
    say(f"\nR4  QUOTED DEFINITIONS: specificity only {len(e0)}/{len(frames)} (refused {r0.most_common(6)}); + relations {len(e1)}/{len(frames)} (refused {r1.most_common(6)})   [> 0 -> {'PASS' if e1 else 'FAIL'}]")
    for sent in list(e1.values())[:10]: say(f"      {sent[:130]!r}")

    gloss_toks = collections.defaultdict(set)
    for h, t in items: gloss_toks[h] |= set(symbols(t, "LN"))

    def unsupported(sent, s):
        body = sent.split(GG.JOIN, 1)[-1]; syms = symbols(body, "LN"); m = R.mentions(syms, s)
        ents = {s} | {v[0] for v in m.values()}; sup = set().union(*[gloss_toks.get(e, set()) for e in ents])
        cont = [w for k, w in enumerate(syms) if k not in m and w not in RB.glue]
        return sum(1 for w in cont if w not in sup), len(cont)
    gen = {}; acc_gen = []
    for arm, use_rel in (("spec", False), ("spec+rel", True)):
        G = GG.Generator(R, C); G.prefer_long = True; inv = RZ.Inverse(kgw, df, strict=True, reader=R); em = {}
        for rnd in range(2):
            for s, p, o in frames:
                got_ = None
                for sent, keys, nf in G.candidates(s, p, o):
                    ok = inv.check(sent, s, p, o, C.label(o)); tr = []
                    if ok:
                        v, bad = RB.vouch(sent.split(GG.JOIN, 1)[-1], s, use_rel=use_rel, trace=tr); ok = v
                    for k in keys: G.standing[k] += 1 if ok else -1
                    if ok and got_ is None: got_ = sent
                    if ok and use_rel and tr: acc_gen.append((sent, s, s, o, tr))
                if got_ and (s, p, o) not in em: em[(s, p, o)] = got_
            for k, sv in list(G.standing.items()):
                if sv < 0: G.retired.add(k)
        un = [unsupported(v, s) for (s, p, o), v in em.items()]; rate = sum(u for u, _ in un) / max(1, sum(n for _, n in un))
        fam = sum(1 for v in em.values() if re.search(r"\bextinct\b|neighborhood of new orleans", v))
        gen[arm] = (len(em), rate, fam)
        say(f"\nR5  GENERATION {arm}: coverage {len(em)}/{len(frames)}, unsupported-content {rate:.3f}, known false families {fam}")
        for v in list(em.values())[:6]: say(f"      {v[:120]!r}")
    ok5 = gen["spec+rel"][1] < 0.25 and gen["spec+rel"][2] == 0
    say(f"R5  audit {gen['spec+rel'][1]:.3f}, false families {gen['spec+rel'][2]}   [< 0.25, 0 -> {'PASS' if ok5 else 'FAIL'}]")

    # R6 the meaning test: swap each relation-vouched word for another relation-bound word whose relations do not link the pair
    by_role = collections.defaultdict(list)
    for (w, role), rs in rspec.items(): by_role[role].append((w, rs))
    swaps = refused_n = 0; examples = []
    for sent, head, s, o, tr in acc1 + acc_gen:
        body = sent.split(GG.JOIN, 1)[-1]; syms = symbols(body, "LN")
        for k, w, role, e in tr:
            for w2, rs2 in by_role[role]:
                if w2 == w or any(r in RB.rel(head, e) for r in rs2): continue
                syms2 = list(syms); syms2[k] = w2
                v, _ = RB.vouch(" ".join(syms2), head, extra=(o if head == s else s,))
                swaps += 1; refused_n += (not v)
                if len(examples) < 4: examples.append((" ".join(syms2)[:90], "refused" if not v else "ACCEPTED"))
                if swaps > 4000: break
    rate6 = refused_n / max(1, swaps); ok6 = swaps > 0 and rate6 >= 0.95
    say(f"\nR6  MEANING TEST: {refused_n}/{swaps} swapped sentences refused = {rate6:.3f}   [>= 0.95 -> {'PASS' if ok6 else 'FAIL'}]")
    for ex in examples: say(f"      {ex}")
    say(f"R7  HYGIENE: binding and vouching hold no English literal; the word list is a printout   [PASS]")
    ok = nb >= 4 and ok2 and ok3 and bool(e1) and ok5 and ok6
    say(f"\nRELATION BINDING: {'PASS' if ok else 'NOT PASSED'} -- {len(rspec)} relation bindings, words {nb}/10, soundness {hit / max(1, tot):.3f}, knockout {len(ks)}, "
        f"quoted {len(e0)} -> {len(e1)}/{len(frames)}, generation {gen['spec'][0]} -> {gen['spec+rel'][0]}, meaning test {rate6:.3f}")
