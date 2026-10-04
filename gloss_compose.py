"""SPECIFICITY, GLUE FROM FORM (H2), SUBGRAPH FRAMES (H1) -- gloss_compose_prereg.md. Zero LLM. Offline over the crawl.

    python gloss_compose.py [--frames 30]"""
import os, sys, re, math, random, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols, reason
from core.verdict import ATTRIBUTED, COMMIT
from core.kg import KGWorld
from core.seqform import ClassBigram
from core.registry import selfcheck
from kb_crawl import Crawl
import kg_multihop as KG
import realize as RZ
import gloss_scale as GS
import gloss_generate as GG
import gloss_width as GW
import gloss_bind as GB

THETA, K_FORM, FORM_S = 0.20, 48, 90
NLD = os.path.join(HERE, "_nldata")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


# ------------------------------------------------------------------------------------------------ Part S
class SpecBinder(GB.Binder):
    """Binder + the specificity rule: a word keeps type t only if it is diagnostic of t on its side"""

    def __init__(self, R, glue):
        super().__init__(R); self.glue = set(glue); self.spec = {}; self.recall = {}

    def induce(self, items):
        super().induce(items)
        need = {t for ts in self.bind.values() for t in ts}
        n_t = collections.Counter(); n_wt = collections.Counter(); tsets = {}
        for h, t in items:
            syms = symbols(t, "LN"); anc, _ = self.anchors(syms, h)
            inst = collections.defaultdict(set)                       # (entity, side) -> window words
            for k, role, e in anc: inst[(e, role[0])].add(syms[k])
            for (e, side), words in inst.items():
                if e not in tsets: tsets[e] = self.R.typeset(e) & need
                for tt in tsets[e]:
                    n_t[(side, tt)] += 1
                    for w in words:
                        if (w, side, tt) is not None: n_wt[(w, side, tt)] += 1
        self.spec = {}
        for (w, role), ts in self.bind.items():
            keep = []
            for tt in ts:
                r = n_wt[(w, role[0], tt)] / max(1, n_t[(role[0], tt)]); self.recall[(w, role, tt)] = r
                if r >= THETA: keep.append(tt)
            if keep: self.spec[(w, role)] = keep
        return self.spec

    def vouch(self, body, s, extra=()):
        """-> (ok, failing word). Every non-glue token outside a verified mention must contribute a diagnostic type that
        holds for its anchoring entity and that no earlier word contributed. `extra` = other entities whose mentions count."""
        syms = symbols(body, "LN"); anc, m = self.anchors(syms, s)
        for e in extra:
            m2 = self.R.mentions(syms, e)
            for k, v in m2.items(): m.setdefault(k, v)
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
            if not ok: return False, w
        return True, None


def content_of(body, glue):
    return [w for w in symbols(body, "LN") if w not in glue]


# ------------------------------------------------------------------------------------------------ Part H2
def glue_fill(content, glue, model, T, rng):
    """insert 0-2 glue words into each gap between content tokens, greedily left to right, by the form model's bits"""
    opts = [()] + [(g,) for g in glue] + [(g1, g2) for g1 in glue for g2 in glue]
    toks = [content[0]]
    for i in range(1, len(content)):
        scored = []
        for o in opts:
            cand = toks + list(o) + content[i:]
            bits, _ = model.sentence(cand)
            scored.append((bits / len(cand), o))      # amendment 1 (recorded): per token -- total bits always prefers no glue
        if T == 0: best = min(scored)[1]
        else:
            lo = min(b for b, _ in scored); ws = [math.exp(-(b - lo) * math.log(2) / T) for b, _ in scored]; r = rng.random() * sum(ws)
            best = scored[-1][1]
            for (b, o), w in zip(scored, ws):
                r -= w
                if r <= 0: best = o; break
        toks += list(best) + [content[i]]
    return toks


def bpt(model, toks):
    bits, _ = model.sentence(toks); return bits / max(1, len(toks))


if __name__ == "__main__":
    selfcheck(__file__)
    a = sys.argv; nframes = int(a[a.index("--frames") + 1]) if "--frames" in a else 30
    say("COMPOSE -- specificity rule, glue from form (H2), subgraph frames (H1) (gloss_compose_prereg.md)\n")
    C = Crawl(); items, per = GW.build_items(C, ("defs", "ex"))
    R, train, test, st = GW.induce(C, items, 5)
    glue = sorted(R.free)
    say(f"    data {per}; reader W=5 {st}; glue (claim-free set) {glue}")
    SB = SpecBinder(R, glue); spec = SB.induce(train)
    say(f"    bindings {len(SB.bind)} -> diagnostic {len(spec)} (THETA {THETA})")
    for w in ("extinct", "city", "capital", "language", "neighborhood", "island", "county", "spoken", "largest"):
        rows = [(role, [R.labels.get(o, o) for p, o in ts][:2]) for (x, role), ts in spec.items() if x == w]
        refused = [(role, round(SB.recall.get((w, role, ts[0]), 0), 3)) for (x, role), ts in SB.bind.items() if x == w and (x, role) not in spec]
        say(f"      {w:12s} diagnostic {rows[:3]}  refused (role, recall) {refused[:3]}")

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
        cont = [w for k, w in enumerate(syms) if k not in m and w not in SB.glue]
        return sum(1 for w in cont if w not in sup), len(cont)

    # ---- Part S
    out = {}
    for arm in (("spec",) if "--h1-only" in a else ("untyped", "spec")):
        G = GG.Generator(R, C); G.prefer_long = True; inv = RZ.Inverse(kgw, df, strict=True, reader=R); emitted = {}; why = collections.Counter()
        for rnd in range(2):
            for s, p, o in frames:
                got = None
                for sent, keys, nf in G.candidates(s, p, o):
                    ok = inv.check(sent, s, p, o, C.label(o))
                    if ok and arm == "spec":
                        v, bad = SB.vouch(sent.split(GG.JOIN, 1)[-1], s)
                        if not v: why[bad] += 1; ok = False
                    for k in keys: G.standing[k] += 1 if ok else -1
                    if ok and got is None: got = sent
                if got and (s, p, o) not in emitted: emitted[(s, p, o)] = got
            for k, sv in list(G.standing.items()):
                if sv < 0: G.retired.add(k)
        un = [unsupported(v, s) for (s, p, o), v in emitted.items()]
        rate = sum(u for u, _ in un) / max(1, sum(n for _, n in un))
        false_fam = sum(1 for v in emitted.values() if re.search(r"\bextinct\b|neighborhood of new orleans", v))
        out[arm] = dict(emitted=emitted, rate=rate, fam=false_fam)
        say(f"\nS   {arm.upper()}: coverage {len(emitted)}/{len(frames)}, unsupported-content {rate:.3f}, known false family {false_fam}")
        for v in list(emitted.values())[:10]: say(f"      {v[:120]!r}")
        if arm == "spec": say(f"      refused most often: {why.most_common(14)}")
    if "--h1-only" in a: out["untyped"] = dict(emitted={}, rate=1.0, fam=0)
    ok_s1 = out["spec"]["fam"] == 0
    ok_s2 = out["spec"]["rate"] < 0.25 and out["spec"]["rate"] < out["untyped"]["rate"]
    say(f"\nS1  known false sentences under specificity: {out['spec']['fam']} (untyped {out['untyped']['fam']})   [0 -> {'PASS' if ok_s1 else 'FAIL'}]")
    say(f"S2  unsupported-content: untyped {out['untyped']['rate']:.3f} -> spec {out['spec']['rate']:.3f}   [< 0.25, lower -> {'PASS' if ok_s2 else 'FAIL'}]")
    say(f"S3  coverage under specificity: {len(out['spec']['emitted'])}/{len(frames)}")

    ok_g1 = ok_g2 = ok_g3 = False; mh2 = mgw = mre = 0.0
    if "--h1-only" not in a:
        # ---- Part H2
        rng = random.Random(5)
        ex_items = [t for h, t in items if t not in {tt for _, tt in items_d}]
        ex_items_sorted = sorted(set(ex_items)); random.Random(7).shuffle(ex_items_sorted)
        held_real = ex_items_sorted[: len(ex_items_sorted) // 10]; held_set = set(held_real)
        form_train = [symbols(t, "LN") for _, t in items if t not in held_set]
        form_train = [s for s in form_train if 2 <= len(s) <= 40]
        gen_model = ClassBigram(form_train, K_FORM); r1 = gen_model.exchange(FORM_S)
        judge_train = []
        for corpus in ("alice.txt", "brent_phono.txt"):
            try:
                for l in open(os.path.join(NLD, corpus), encoding="utf-8", errors="replace"):
                    ws = symbols(l, "LN")
                    if 2 <= len(ws) <= 40: judge_train.append(ws)
            except FileNotFoundError: pass
        judge = ClassBigram(judge_train, K_FORM); r2 = judge.exchange(FORM_S)
        say(f"\nH2  form model: {len(form_train)} sentences, {r1['moves']} moves; independent judge: {len(judge_train)} sentences (Alice + Brent), {r2['moves']} moves")
        g1 = g2 = n = 0; rows = []
        inv2 = RZ.Inverse(kgw, df, strict=True, reader=R)
        for (s, p, o), sent in out["spec"]["emitted"].items():
            body = sent.split(GG.JOIN, 1)[-1]; cont = content_of(body, SB.glue)
            subj = symbols(C.label(s), "LN")
            if not cont: continue
            n += 1
            t0 = glue_fill(subj + cont, glue, gen_model, 0, rng)
            h2 = " ".join(t0)
            g1 += content_of(h2, SB.glue) == subj + cont
            ok = inv2.check(h2 + RZ.TAIL.format(", ".join(RZ.SOURCES)), s, p, o, C.label(o)); g2 += ok
            shuffled = subj + cont[:]; rng.shuffle(shuffled)
            rand_glue = []
            for w in shuffled: rand_glue += [w] + ([rng.choice(glue)] if rng.random() < 0.5 else [])
            glued_window = symbols(C.label(s), "LN") + symbols(body, "LN")
            rows.append((bpt(judge, t0), bpt(judge, glued_window), bpt(judge, rand_glue), h2, sent, ok))
        real = [bpt(judge, symbols(t, "LN")) for t in held_real[:300] if 2 <= len(symbols(t, "LN")) <= 40]
        mh2 = sum(r[0] for r in rows) / max(1, len(rows)); mgw = sum(r[1] for r in rows) / max(1, len(rows)); msh = sum(r[2] for r in rows) / max(1, len(rows)); mre = sum(real) / max(1, len(real))
        for r in rows[:10]: say(f"      H2 {r[3][:80]!r:84s} <- {r[4][:60]!r}  {'accepted' if r[5] else 'REJECTED'}")
        ok_g1 = n > 0 and g1 == n; ok_g2 = n > 0 and g2 >= 0.9 * n; ok_g3 = mh2 < mgw and mh2 < msh
        gap = (mh2 - mre) / max(1e-9, (msh - mre))
        say(f"G1  meaning preserved: {g1}/{n}   [100 % -> {'PASS' if ok_g1 else 'FAIL'}]")
        say(f"G2  strict inverse accepts the H2 reply: {g2}/{n}   [>= 90 % -> {'PASS' if ok_g2 else 'FAIL'}]")
        say(f"G3  independent judge bits/token: H2 {mh2:.2f}, glued windows {mgw:.2f}, shuffled+random glue {msh:.2f}, real held-out examples {mre:.2f}   [H2 below both -> {'PASS' if ok_g3 else 'FAIL'}]")
        say(f"G4  gap to real as a fraction of shuffled-to-real: {gap:.2f}   [printed; predicted 0.3-0.6]")

    # ---- Part H1
    by_head = collections.defaultdict(list)
    for h, t in items: by_head[h].append(t)

    def h1_candidates(s, o):
        out_ = []
        for t in by_head.get(s, []): out_.append((C.label(s) + GG.JOIN + t, s))
        lab_s = C.label(s)
        for t in by_head.get(o, []):
            if re.search(r"\b" + re.escape(lab_s) + r"\b", t): out_.append((C.label(o) + GG.JOIN + t, o))
        return out_

    def h1_run(source_of):
        inv3 = RZ.Inverse(kgw, df, strict=True, reader=R); emitted = {}; tried = 0; acc = 0; stage = collections.Counter(); badw = collections.Counter()
        for i, (s, p, o) in enumerate(frames):
            s2, o2 = source_of(i)
            for sent, head in h1_candidates(s2, o2):
                tried += 1
                before = dict(inv3.rejected)
                if not inv3.check(sent, s, p, o, C.label(o)):
                    d = {k: v - before.get(k, 0) for k, v in inv3.rejected.items() if v - before.get(k, 0) > 0}
                    stage["inverse: " + (next(iter(d)) if d else "?")] += 1; continue
                other = o if head == s else s
                v, bad = SB.vouch(sent.split(GG.JOIN, 1)[-1], head, extra=(other,))
                if not v: stage["voucher"] += 1; badw[bad] += 1; continue
                acc += 1
                if (s, p, o) not in emitted: emitted[(s, p, o)] = (sent, head)
        h1_run.stage, h1_run.badw = stage, badw
        return emitted, tried, acc

    em1, tr1, ac1 = h1_run(lambda i: (frames[i][0], frames[i][2]))
    say(f"\nH1  rejections by stage: {dict(h1_run.stage)}; words the voucher refused: {h1_run.badw.most_common(12)}")
    for s_, p_, o_ in frames[:6]:
        for sent, head in h1_candidates(s_, o_)[:2]: say(f"      candidate {sent[:120]!r}")
    shift = lambda i: (frames[(i + 7) % len(frames)][0], frames[(i + 7) % len(frames)][2])
    emk, trk, ack = h1_run(shift)
    facts = []
    for (s, p, o), (sent, head) in em1.items():
        body = sent.split(GG.JOIN, 1)[-1]; syms = symbols(body, "LN")
        ents = {v[0] for v in R.mentions(syms, s).values()} | {v[0] for v in R.mentions(syms, o).values()}
        facts.append(len(ents | {o}))
    gloss_texts = {t for _, t in items}
    novel = sum(1 for (sent, head) in em1.values() if sent.split(GG.JOIN, 1)[-1] not in gloss_texts)
    say(f"\nH1  subgraph frames: coverage {len(em1)}/{len(frames)} (candidates {tr1}, accepted {ac1})")
    for (s, p, o), (sent, head) in list(em1.items())[:10]: say(f"      {sent[:130]!r}")
    mf = sum(facts) / max(1, len(facts)); rate_main = ac1 / max(1, tr1); rate_k = ack / max(1, trk)
    ok_f1 = len(em1) > len(out["spec"]["emitted"]); ok_f2 = mf >= 2; ok_f3 = rate_k < 0.10 * max(rate_main, 1e-9) or ack == 0
    say(f"F1  coverage {len(em1)} vs specificity-generated {len(out['spec']['emitted'])}   [higher -> {'PASS' if ok_f1 else 'FAIL'}]")
    say(f"F2  verified facts per reply: mean {mf:.2f}   [>= 2 -> {'PASS' if ok_f2 else 'FAIL'}]")
    say(f"F3  KNOCKOUT (another frame's sentences): acceptance {ack}/{trk} = {rate_k:.4f} vs main {rate_main:.4f}   [< 10 % -> {'PASS' if ok_f3 else 'FAIL'}]")
    say(f"F4  novelty: {novel}/{len(em1)} not verbatim in the store   [printed; predicted ~0]")
    say(f"\nCOMPOSE: S {'PASS' if ok_s1 and ok_s2 else 'NOT PASSED'} (coverage {len(out['spec']['emitted'])}/{len(frames)}, unsupported {out['spec']['rate']:.2f}); "
        f"H2 {'PASS' if ok_g1 and ok_g2 and ok_g3 else 'NOT PASSED'} (judge {mh2:.2f} vs windows {mgw:.2f}, real {mre:.2f}); "
        f"H1 {'PASS' if ok_f1 and ok_f2 and ok_f3 else 'NOT PASSED'} (coverage {len(em1)}/{len(frames)}, facts {mf:.2f}, knockout {rate_k:.3f})")
