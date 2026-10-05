"""ATTACHMENT -- which thing a word is about (gloss_attach_prereg.md). Zero LLM. Offline over the crawl store.

Four rules decide which mention a word attaches to: skip the headword's own class words (A1), skip namesake mentions (A2),
attach each gloss to the sense of the headword it actually describes (A3), and attach only to the nearest anchor (A4).
Binding, vouching and every bar are gloss_relbind's.

    python gloss_attach.py [--frames 30] [--frames-only]"""
import os, sys, subprocess

if os.environ.get("PYTHONHASHSEED") != "0":                      # T8: a fixed string-hash seed, so set order is stable
    env = dict(os.environ, PYTHONHASHSEED="0")
    sys.exit(subprocess.call([sys.executable] + sys.argv, env=env))

import re, json, random, sqlite3, collections, hashlib
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
import gloss_relbind as GR

D = 3


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


# ------------------------------------------------------------------------------------------------ A3: the headword's sense
def build_items_sense(C, kinds=("defs", "ex")):
    """as gloss_width.build_items, but a gloss goes to the ONE stored entity of that name it has the most verified mentions
    for (ties drop it). Returns items and counts (glosses kept, dropped as ties, entities sharing a name)."""
    db = sqlite3.connect(GS.KAIKKI); by_label = collections.defaultdict(list)
    for q, lab in C.db.execute("select q, label from ent where label is not null"): by_label[lab].append(q)
    items = []; ties = shared = 0
    for lab, qs in sorted(by_label.items()):
        r = db.execute("select v from e where w=?", (lab.lower(),)).fetchone()
        if not r: continue
        e = json.loads(r[0]); shared += len(qs) > 1
        names = {}
        for q in qs:
            cl = C.allclaims(q)
            nm = sorted({C.label(v) for vs in cl.values() for v in vs if v.startswith("Q")}, key=len, reverse=True)
            nm = [n for n in nm if n and not n.startswith("Q") and len(n) > 2][:300]
            nums = {v[2:] for vs in cl.values() for v in vs if v[:2] in ("T:", "N:")}
            names[q] = (nm, nums)
        for kind in kinds:
            for t in (e.get(kind, []) or [])[:12]:
                if kind == "ex" and not re.search(r"\b" + re.escape(lab) + r"\b", t): continue
                toks = set(symbols(t, "LN")); score = {}
                for q, (nm, nums) in names.items():
                    sc = sum(1 for n in nm if re.search(r"\b" + re.escape(n) + r"\b", t)) + len(nums & toks)
                    if sc: score[q] = sc
                if not score: continue
                best = max(score.values()); top = [q for q, v in score.items() if v == best]
                if len(top) > 1: ties += 1; continue
                items.append((top[0], t))
    return sorted(set(items)), dict(glosses=len(set(items)), ties_dropped=ties, names_shared=shared)


# ------------------------------------------------------------------------------------------------ A1, A2, A4
class AttachBinder(GR.RelBinder):
    def __init__(self, R, glue, C, a1=True, a2=True, a4=True):
        super().__init__(R, glue, C); self.a1, self.a2, self.a4 = a1, a2, a4; self.namesake = set()

    def classes(self, h):
        cl = self.C.claims(h); return set(cl.get("P31", [])) | set(cl.get("P279", []))

    def valid_anchor(self, h, o):
        if self.a1 and o in self.classes(h): return False
        if self.a2 and self.namesake and not (self.rel(h, o) - self.namesake): return False
        return True

    def anchors(self, syms, h):
        m = self.R.mentions(syms, h); starts = {}
        for k, (o, p, start) in m.items(): starts.setdefault(start, [start, start, o])
        for start, v in starts.items():
            end = start
            while end in m and m[end][2] == start: end += 1
            v[1] = end
        spans = sorted(starts.values())
        anchors = [(i, end, o) for i, end, o in spans if self.valid_anchor(h, o)]
        out = []
        for k in range(len(syms)):
            if k in m: continue
            right = [(i - k, o) for i, end, o in anchors if 0 < i - k <= D]       # the anchor is to the right: role L(dist)
            left = [(k - end + 1, o) for i, end, o in anchors if 0 < k - end + 1 <= D]
            if self.a4:
                right = sorted(right)[:1]; left = sorted(left)[:1]
            for dist, o in right: out.append((k, "L%d" % dist, o))
            for dist, o in left: out.append((k, "R%d" % dist, o))
            if k < D: out.append((k, "H%d" % (k + 1), h))
        return out, m

    def learn_namesake(self, items):
        """A2's relation set: relations whose base rate over all mention pairs exceeds 0.5 (namesake links)"""
        cnt = collections.Counter(); n = 0
        for h, t in items:
            syms = symbols(t, "LN"); m = self.R.mentions(syms, h)
            for o in {v[0] for v in m.values()}:
                n += 1; cnt.update(self.rel(h, o))
        self.namesake = {r for r, c in cnt.items() if c > 0.5 * max(1, n)}
        return self.namesake


def capital_share(B, items, word="capital"):
    """best share, over L positions, of a word's occurrences whose anchored pair is linked by a capital relation"""
    caps = {r for r in {("P1376", "+"), ("P1376", "-"), ("P36", "+"), ("P36", "-")}}
    caps = {B.canon(p, d) for p, d in caps}
    per = collections.defaultdict(lambda: [0, 0])
    for h, t in items:
        syms = symbols(t, "LN"); anc, _ = B.anchors(syms, h)
        for k, role, e in anc:
            if syms[k] == word and role[0] == "L":
                per[role][1] += 1; per[role][0] += bool(B.rel(h, e) & caps)
    best = max(((g / n, role, n) for role, (g, n) in per.items() if n >= 20), default=(0.0, "-", 0))
    return best


if __name__ == "__main__":
    selfcheck(__file__)
    a = sys.argv; nframes = int(a[a.index("--frames") + 1]) if "--frames" in a else 30
    say("ATTACHMENT -- which thing a word is about (gloss_attach_prereg.md); PYTHONHASHSEED=0\n")
    C = Crawl()
    items_d, _ = GW.build_items(C, ("defs",))
    reg = GS.register_from_crawl(C, items_d); df = KG.make_df(); kgw = KGWorld(C, df, name="Wikidata")
    freq = collections.Counter(x["p"] for x in reg["pairs"]).most_common(8); props = [p for p, _ in freq]
    cand = sorted(t for t in reg["triples"] if t[1] in props); random.Random(2).shuffle(cand); frames = []
    for s, p, o in cand:
        if len(frames) >= nframes: break
        fr = reason(f"what is the {reg['labels'][p]} of {reg['labels'][s]}", [kgw], df, cats="L")
        if fr["kind"] in (ATTRIBUTED, COMMIT) and len(fr["answers"]) == 1 and fr["answers"][0][0] == o: frames.append((s, p, o))
    fh = hashlib.sha1(repr(frames).encode()).hexdigest()[:12]
    say(f"T8  frames hash {fh}: {', '.join(C.label(s) for s, _, _ in frames[:10])} ...")
    if "--frames-only" in a: sys.exit(0)

    items_raw, per_raw = GW.build_items(C, ("defs", "ex")); items, per = build_items_sense(C)
    say(f"    A3 sense attachment: raw {len(items_raw)} glosses {per_raw}; sense-attached {per}")
    R, train, test, st = GW.induce(C, items, 5); glue = sorted(R.free)
    say(f"    reader {st}")

    # T2 ablation on the sense-attached data (A3 on), then A3 off with all other rules
    rows = []
    for name, a1, a2, a4 in (("no rules", False, False, False), ("A1", True, False, False), ("A1+A2", True, True, False), ("A1+A2+A4", True, True, True)):
        B = AttachBinder(R, glue, C, a1, a2, a4)
        if a2: B.learn_namesake(train)
        rows.append((name + " (+A3)", capital_share(B, train)))
    Rr, train_r, test_r, _ = GW.induce(C, items_raw, 5)
    Br = AttachBinder(Rr, sorted(Rr.free), C); Br.learn_namesake(train_r)
    rows.insert(0, ("A1+A2+A4 without A3 (raw senses)", capital_share(Br, train_r)))
    Bn = AttachBinder(Rr, sorted(Rr.free), C, False, False, False); rows.insert(0, ("no rules, raw senses (gloss_relbind)", capital_share(Bn, train_r)))
    say("\nT2  ABLATION -- 'capital' before a place, share matching a capital link (best position, n >= 20):")
    for name, (share, role, n) in rows: say(f"      {name:40s} {share:.3f}  at {role} (n={n})")
    t1 = rows[-1][1][0]; ok1 = t1 >= 0.90
    say(f"T1  all four rules: {t1:.3f}   [>= 0.90 -> {'PASS' if ok1 else 'FAIL'}]")

    # full rules: bindings and the downstream gates
    B = AttachBinder(R, glue, C); B.learn_namesake(train); B.induce(train); rspec = B.induce_rel(train)
    say(f"\n    namesake relations (A2): {sorted(R.labels.get(p, p) + d for p, d in B.namesake)}")
    lab = lambda r: f"{'' if r[1] == '+' else '~'}{R.labels.get(r[0], r[0])}"
    say(f"    type-diagnostic {len(B.spec)}; relation bindings {len(B.rbind)} -> diagnostic {len(rspec)}")
    for key in sorted(rspec, key=lambda k: -B.rn[k])[:20]: say(f"      {key[0]:12s} {key[1]}  x{B.rn[key]:<5d} -> {[lab(r) for r in rspec[key]][:3]}")
    words = ["capital", "largest", "city", "official", "seat", "border", "located", "spoken", "part", "member"]
    got = {w: sorted({role for (x, role) in rspec if x == w}) for w in words}; nb = sum(1 for w in words if got[w])
    say(f"T3  relation words bound: {nb}/10 {got}   [>= 3 -> {'PASS' if nb >= 3 else 'FAIL'}]")
    hit = tot = 0
    for h, t in test:
        syms = symbols(t, "LN"); anc, _ = B.anchors(syms, h)
        for k, role, e in anc:
            if (syms[k], role) in rspec: tot += 1; hit += any(r in B.rel(h, e) for r in rspec[(syms[k], role)])
    texts = [t for _, t in train]; random.Random(0).shuffle(texts)
    Bs = AttachBinder(R, glue, C); Bs.namesake = B.namesake; Bs.spec = {}; ks = Bs.induce_rel([(h, t) for (h, _), t in zip(train, texts)])
    sound = hit / max(1, tot); ok4 = sound >= 0.85 and len(ks) < 0.25 * max(1, len(rspec))
    say(f"T4  held-out soundness {hit}/{tot} = {sound:.3f}; knockout {len(ks)} of {len(rspec)}   [>= 0.85, < 25 % -> {'PASS' if ok4 else 'FAIL'}]")

    by_head = collections.defaultdict(list)
    for h, t in items: by_head[h].append(t)
    inv = RZ.Inverse(kgw, df, strict=True, reader=R); quoted = {}; refused = collections.Counter(); acc_q = []
    for s, p, o in frames:
        cands = [(C.label(s) + GG.JOIN + t, s) for t in by_head.get(s, [])]
        cands += [(C.label(o) + GG.JOIN + t, o) for t in by_head.get(o, []) if re.search(r"\b" + re.escape(C.label(s)) + r"\b", t)]
        for sent, head in cands:
            before = dict(inv.rejected)
            if not inv.check(sent, s, p, o, C.label(o)):
                d = [k for k, v in inv.rejected.items() if v > before.get(k, 0) and k != "stated by construction"]
                refused["the reader: " + (d[0] if d else "?")] += 1; continue
            tr = []
            v, bad = B.vouch(sent.split(GG.JOIN, 1)[-1], head, extra=(o if head == s else s,), trace=tr)
            if not v: refused[bad] += 1; continue
            acc_q.append((sent, head, s, o, tr))
            if (s, p, o) not in quoted: quoted[(s, p, o)] = sent
    ok5 = len(quoted) > 0
    say(f"\nT5  QUOTED DEFINITIONS accepted: {len(quoted)}/{len(frames)}; words refused {refused.most_common(8)}   [> 0 -> {'PASS' if ok5 else 'FAIL'}]")
    for sent in list(quoted.values())[:10]: say(f"      {sent[:130]!r}")

    gloss_toks = collections.defaultdict(set)
    for h, t in items: gloss_toks[h] |= set(symbols(t, "LN"))
    G = GG.Generator(R, C); G.prefer_long = True; inv2 = RZ.Inverse(kgw, df, strict=True, reader=R); gen = {}; acc_g = []
    for rnd in range(2):
        for s, p, o in frames:
            got_ = None
            for sent, keys, nf in G.candidates(s, p, o):
                ok = inv2.check(sent, s, p, o, C.label(o)); tr = []
                if ok: ok, _ = B.vouch(sent.split(GG.JOIN, 1)[-1], s, trace=tr)
                for k in keys: G.standing[k] += 1 if ok else -1
                if ok and got_ is None: got_ = sent
                if ok and tr: acc_g.append((sent, s, s, o, tr))
            if got_ and (s, p, o) not in gen: gen[(s, p, o)] = got_
        for k, sv in list(G.standing.items()):
            if sv < 0: G.retired.add(k)
    un = 0; nc = 0
    for (s, p, o), v in gen.items():
        body = v.split(GG.JOIN, 1)[-1]; syms = symbols(body, "LN"); m = R.mentions(syms, s)
        sup = set().union(*[gloss_toks.get(e, set()) for e in ({s} | {x[0] for x in m.values()})])
        cont = [w for k, w in enumerate(syms) if k not in m and w not in B.glue]; un += sum(1 for w in cont if w not in sup); nc += len(cont)
    rate = un / max(1, nc); fam = sum(1 for v in gen.values() if re.search(r"\bextinct\b|neighborhood of new orleans", v))
    ok7 = rate < 0.25 and fam == 0
    say(f"\nT7  GENERATION: coverage {len(gen)}/{len(frames)}, unsupported-content {rate:.3f}, known false families {fam}   [< 0.25, 0 -> {'PASS' if ok7 else 'FAIL'}]")
    for v in list(gen.values())[:6]: say(f"      {v[:120]!r}")

    by_role = collections.defaultdict(list)
    for (w, role), rs in rspec.items(): by_role[role].append((w, rs))
    swaps = refused_n = 0; examples = []
    for sent, head, s, o, tr in acc_q + acc_g:
        syms = symbols(sent.split(GG.JOIN, 1)[-1], "LN")
        for k, w, role, e in tr:
            for w2, rs2 in by_role[role]:
                if w2 == w or any(r in B.rel(head, e) for r in rs2): continue
                syms2 = list(syms); syms2[k] = w2
                v, _ = B.vouch(" ".join(syms2), head, extra=(o if head == s else s,)); swaps += 1; refused_n += (not v)
                if len(examples) < 5: examples.append((" ".join(syms2)[:90], "refused" if not v else "ACCEPTED"))
    r6 = refused_n / max(1, swaps); ok6 = swaps > 0 and r6 >= 0.95
    say(f"\nT6  MEANING TEST: {refused_n}/{swaps} swapped sentences refused = {r6:.3f}   [>= 0.95 -> {'PASS' if ok6 else ('NOT TESTABLE' if swaps == 0 else 'FAIL')}]")
    for ex in examples: say(f"      {ex}")
    # T6' (added after T6 proved untestable; registered in the prereg before this run): keep the words and the mention,
    # change the SUBJECT to another entity for which the mention is still verified (some other claim links them) but the
    # bound relation does not. The binder must refuse the word. Positive control: the true subject, accepted.
    holders = collections.defaultdict(set)                     # e -> entities with any claim pointing at e
    for (q,) in C.db.execute("select q from ent"):
        for vs in C.claims(q).values():
            for v in vs: holders[v].add(q)
    # run 2 computed this with the same predicate it filtered on (circular; retracted). Run 3: the FULL voucher on the actual
    # words -- the fragment from the word through its anchor mention -- once with the true subject, once with each swap.
    pos = posn = neg = negn = 0; ex2 = []
    for h, t in test:
        syms = symbols(t, "LN"); anc, m = B.anchors(syms, h)
        for k, role, e in anc:
            key = (syms[k], role)
            if key not in rspec or role[0] != "L": continue
            rs = rspec[key]
            if not any(r in B.rel(h, e) for r in rs): continue
            i0 = k + int(role[1:])                                       # the anchor mention starts here
            end = i0
            while end in m and m[end][2] == m[i0][2]: end += 1
            frag = " ".join(syms[k:end])
            posn += 1; pos += B.vouch(frag, h)[0]
            for h2 in sorted(holders.get(e, set()) - {h})[:20]:
                if any(r in B.rel(h2, e) for r in rs): continue        # the relation holds for h2 too: not a counter-case
                negn += 1; okv, bad = B.vouch(frag, h2); neg += (not okv)
                if len(ex2) < 6: ex2.append((C.label(h2), frag, "refused at " + repr(bad) if not okv else "ACCEPTED"))
    r6b = neg / max(1, negn)
    say(f"\nT6' SUBJECT-SWAP MEANING TEST: {neg}/{negn} swapped subjects refused = {r6b:.3f}; true subjects accepted {pos}/{posn}   [>= 0.95 -> {'PASS' if negn and r6b >= 0.95 else 'FAIL'}]")
    for h2, frag, verdict in ex2: say(f"      {frag!r} said of {h2!r}: {verdict}")
    ok6 = ok6 or (negn > 0 and r6b >= 0.95)
    ok = ok1 and nb >= 3 and ok4 and ok5 and ok6 and ok7
    say(f"\nATTACHMENT: {'PASS' if ok else 'NOT PASSED'} -- capital {t1:.3f}, words {nb}/10, soundness {sound:.3f}, quoted {len(quoted)}/{len(frames)}, meaning test {r6:.3f} on {swaps}, generation {len(gen)}/{len(frames)} audit {rate:.3f}, frames {fh}")
