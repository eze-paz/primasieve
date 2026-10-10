"""R24-g: a TIME layer. The state remembers, for each time phrase seen ('in the morning', 'at noon', 'in the evening',
'at night', 'at dawn'), where each person and thing was while that phrase was current. A statement that opens with a
time phrase and a comma ('At noon, the key was at the garden.') is anchored to that mark, and the slot after the place
word is predicted by a new ranking -- the thing's place at that mark -- mixed with the usual ones, weights learned by
counting. Nothing is labelled: the generator's 'Where was X at noon?' questions are restated as statements and the
learner is paid in bits when the time memory predicts them. Kept if held-out answer bits fall.
Run: python learned/base/r24_time.py"""
import os, sys, re, json, math, random, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_classes as C, r24_place as P, r24_qa as Q
from b6_rwkv import hit

MARKS = ("in the morning", "at noon", "in the evening", "at night", "at dawn", "the next morning")
P.RANKINGS = ("recency", "subject_place", "subject_first_place", "any_place", "mark_place")


ATTR = ("both", "subject", "object", "none"); RULE = collections.defaultdict(lambda: "both")     # per place word: whose place the phrase updates


class TimeState(Q.QAState):
    def __init__(self):
        super().__init__(); self.mark = None; self.at_mark = {}; self.anchor_mark = None; self.prep = None

    def ranking(self, name):
        if name == "mark_place":
            who = self.subject or self.obj; m = self.anchor_mark
            return [self.at_mark[(m, who)]] if m and who and (m, who) in self.at_mark else []
        return super().ranking(name)

    def saw_place(self, key):
        rule = RULE[self.prep] if self.prep else "both"
        targets = [w for w, on in ((self.subject, rule in ("both", "subject")), (getattr(self, "obj", None), rule in ("both", "object"))) if on and w and w != key]
        for who in targets:
            self.place_of[who] = key; self.first_place_of.setdefault(who, key)
            if self.mark: self.at_mark[(self.mark, who)] = key
        if key in self.any_place: self.any_place.remove(key)
        self.any_place.insert(0, key)


P.PlaceState = TimeState


def mark_of(sent):
    sl = sent.lower()
    for m in MARKS:
        if sl.startswith(m): return m
    return None


class TimeLM(P.PlaceLM):
    """the place learner with time marks: a sentence that starts with a mark sets the current mark; a sentence that
    starts with a mark AND a comma is a statement anchored to that mark (its slots use the mark ranking)"""
    def _enter(self, st, sent):
        m = mark_of(sent); st.anchor_mark = None
        if m:
            if sent[len(m):len(m) + 1] == ",": st.anchor_mark = m                     # 'At noon, the key was at the garden.'
            else: st.mark = m                                                         # 'At noon Rosa took the key to the garden.'

    def learn_place(self, stories, names):
        for text in stories:
            st = TimeState()
            for s in T.SENT.split(text):
                toks = T.TOK.findall(s)
                if not toks: continue
                self._enter(st, s); items = T.slotify(toks, names); st.subject = None; st.obj = None
                for k, (sym, filler) in enumerate(items):
                    if sym == "PERSON": st.subject = filler[0]
                    if sym == "PRON" and filler[0] in ("he", "she", "him", "his", "her") and st.persons: st.subject = st.persons[0]
                    if sym == "PRON" and filler[0] in ("it", "them") and st.things: st.obj = st.things[0]
                    if sym == "ENT":
                        key = T.key_of(sym, filler)
                        if not (k and items[k - 1][0] in P.PLACE_WORDS): st.obj = key; st.things.insert(0, key) if key not in st.things else st.things.insert(0, st.things.pop(st.things.index(key)))
                        if k and items[k - 1][0] in P.PLACE_WORDS:
                            st.prep = items[k - 1][0]; ctx = ("mark", items[k - 1][0]) if st.anchor_mark else tuple(x for x, _ in items[max(0, k - 2):k])
                            for r in P.RANKINGS:
                                lst = st.ranking(r)
                                if not lst: continue
                                if key in lst: self.prank[r][lst.index(key)] += 1; self.prank_ctx[(ctx, r)][lst.index(key)] += 1; self.mix[r] += (lst.index(key) == 0); self.mix_ctx[ctx][r] += (lst.index(key) == 0)
                                else: self.prank[r]["none"] += 1; self.prank_ctx[(ctx, r)]["none"] += 1
                            st.saw_place(key)
                    if sym in ("PERSON", "ENT"): st.mention(sym, filler, first=(k == 0))

    def score(self, toks, names, st, sent=None):
        if sent is not None: self._enter(st, sent)
        raw = T.slotify(toks, names); items = self.symbols(raw); syms = [sym for sym, _ in items]
        seg, lp = self.segment(syms); bits = -lp / math.log(2); full = all(len(ch) >= 2 for ch in seg); st.subject = None; st.obj = None
        self.in_chunks += sum(len(ch) for ch in seg if len(ch) >= 2); self.n_syms += len(syms)
        for k, (sym, filler) in enumerate(items):
            pos = "first" if k == 0 else "later"
            if sym == "PERSON": st.subject = filler[0]
            if sym == "PRON" and filler[0] in ("he", "she", "him", "his", "her") and st.persons: st.subject = st.persons[0]
            if sym == "PRON" and filler[0] in ("it", "them") and st.things: st.obj = st.things[0]
            if sym == "ENT" and not (k and raw[k - 1][0] in P.PLACE_WORDS):
                st.obj = T.key_of(sym, filler); st.things.insert(0, st.obj) if st.obj not in st.things else st.things.insert(0, st.things.pop(st.things.index(st.obj)))
            if sym in ("PERSON", "ENT", "PRON") or sym.startswith("C"):
                after_place = sym == "ENT" and k and raw[k - 1][0] in P.PLACE_WORDS
                if after_place and self.use_place:
                    key = T.key_of(sym, filler); new0, new1 = self.new[(sym, pos)]; p_new = (new0 + 1) / (new1 + 2); st.prep = raw[k - 1][0]
                    ctx = ("mark", raw[k - 1][0]) if st.anchor_mark else tuple(x for x, _ in raw[max(0, k - 2):k])
                    pf = (1 - p_new) * self.p_place_filler(key, st, ctx) if key in st.ents else self.p_filler(sym, filler, st, pos)
                else: pf = self.p_filler(sym, filler, st, pos)
                pfl = 1.0
                for w in filler: pfl *= self.p_floor(w)
                bits += -math.log2((1 - T.FLOOR) * pf + T.FLOOR * pfl)
                if after_place: st.saw_place(T.key_of(sym, filler))
            if sym in ("PERSON", "ENT"): st.mention(sym, filler, first=(k == 0))
        return bits, len(toks), full


def restate(q, gold):
    r = Q.restate(q, gold)
    if r: return r
    ql = q.lower().rstrip("?"); g = gold[0]
    for m in MARKS:
        if ql.startswith("where was ") and ql.endswith(" " + m):
            who = q[10:-(len(m) + 1)].strip(); g = gold[-1]                           # the LAST alternative: the state at the end of that time (the generator lists earlier places first)
            if not g.startswith(("on the", "in the", "at the", "by the", "under the", "near the", "the ")): g = "the " + g
            g2 = g if not g.startswith("the ") else f"at {g}"
            return f"{m.capitalize()}, {who} was {g2}."                               # 'At noon, the key was at the gate.'
    return None


def with_answers(stories):
    out = []
    for s in stories:
        ans = [a for a in (restate(q, g) for q, g in s["qs"]) if a]
        if ans: out.append(dict(text=s["text"] + " " + " ".join(ans), n_story=len([x for x in T.SENT.split(s["text"]) if x.strip()]), qs=s["qs"]))
    return out


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data)
    train = with_answers(data[:7000]); held = with_answers(data[7000:]); T0 = time.time()
    classes, uni = C.induce_classes([s["text"] for s in train], k=100, min_count=5); frozen = {w for w, _ in uni.most_common(100)}
    names = T.mid_caps([s["text"] for s in train])
    M = TimeLM(classes, frozen, 3000); M.prank = {r: collections.Counter() for r in P.RANKINGS}
    M.learn([s["text"] for s in train], names); M.learn_place([s["text"] for s in train], names)
    seqs = M.seqs([s["text"] for s in train], names); M.fit(seqs); print(f"fitted in {(time.time() - T0) / 60:.1f} min", flush=True)

    def answer_bits(stories):
        ab = an = 0
        for s in stories:
            st = TimeState(); sents = [x for x in T.SENT.split(s["text"]) if x.strip()]
            for k, sent in enumerate(sents):
                toks = T.TOK.findall(sent)
                if not toks: continue
                b, kk, _ = M.score(toks, names, st, sent)
                if k >= s["n_story"]: ab += b; an += kk
        return ab / max(1, an)
    sub = train[:1500]; preps = ["to", "by", "near", "under", "on", "at", "in", "from", "into", "behind"]
    def refit():
        M.prank = {r: collections.Counter() for r in P.RANKINGS}; M.mix = collections.Counter(); M.mix_ctx = collections.defaultdict(collections.Counter); M.prank_ctx = collections.defaultdict(collections.Counter)
        M.learn_place([s["text"] for s in train], names)
    base = answer_bits(sub); print(f"   attribution all 'both': answer bits {base:.3f}", flush=True)
    for rnd in range(2):
        changed = 0
        for w in preps:
            best = (answer_bits(sub), RULE[w]); cur = RULE[w]
            for a in ATTR:
                if a == cur: continue
                RULE[w] = a; refit(); b = answer_bits(sub)
                if b < best[0] - 1e-4: best = (b, a)
            RULE[w] = best[1]; refit(); changed += (best[1] != cur)
        print(f"   round {rnd + 1}: {changed} attribution rules changed; answer bits {answer_bits(sub):.3f}; rules {dict(RULE)}", flush=True)
        if not changed: break
    for ctx in (("mark", "at"), ("mark", "on"), ("was", "at")):
        if ctx in M.mix_ctx: print(f"   learned mixture in context {ctx}: {dict(M.mix_ctx[ctx])}", flush=True)

    def run(use_mark):
        bits = n = ab = an = 0
        for s in held:
            st = TimeState(); sents = [x for x in T.SENT.split(s["text"]) if x.strip()]
            for k, sent in enumerate(sents):
                toks = T.TOK.findall(sent)
                if not toks: continue
                if not use_mark: st.at_mark = {}                                       # ablation: the time memory is emptied before every sentence
                b, kk, _ = M.score(toks, names, st, sent); bits += b; n += kk
                if k >= s["n_story"] and mark_of(sent): ab += b; an += kk
        return bits / n, ab / max(1, an)
    without = run(False); withm = run(True)
    print(f"held-out bits/token: all {withm[0]:.3f} vs {without[0]:.3f} without the time memory | time-anchored answer sentences {withm[1]:.3f} vs {without[1]:.3f}")
    print(f"R24-g1: {'PASS' if withm[1] < without[1] else 'MISS'} (time memory {'kept' if withm[1] < without[1] else 'not kept'})")
    ok = tot = 0
    for s in held:
        st = TimeState(); sents = [x for x in T.SENT.split(s["text"]) if x.strip()]
        for sent in sents[:s["n_story"]]:
            toks = T.TOK.findall(sent)
            if toks: M.score(toks, names, st, sent)
        for q, gold in s["qs"]:
            ql = q.lower().rstrip("?")
            for m in MARKS:
                if ql.startswith("where was ") and ql.endswith(" " + m):
                    who = q[10:-(len(m) + 1)].strip(); who = T.key_of("ENT", who.lower().split()) if who.split()[0].lower() in T.DET else who
                    st.anchor_mark = m; st.subject = None; st.obj = who
                    a = max(st.ents, key=lambda key: M.p_place_filler(key, st, ("mark", "at"))) if st.ents else None
                    tot += 1; ok += (a is not None and hit(a, gold))
    print(f"R24-g2: 'Where was X <time>' by the learner's own argmax on held-out generator stories: {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= 0.80)")
    json.dump(dict(bits=(withm, without), g2=(ok, tot)), open("r24_time_results.json", "w"))


if __name__ == "__main__":
    main()
