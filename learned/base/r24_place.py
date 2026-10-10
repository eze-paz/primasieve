"""R24-d: the place memory as a PREDICTION feature (R24_prereg.md). On top of the chunk learner (run 2d), the state keeps
for each person the last ENT that followed a place word in a sentence where that person was the subject, and the most
recent such place of anyone. At an ENT slot right after a place word, the filler is predicted by a learned mixture of
three rankings (recency / the subject's last place / anyone's last place). Kept only if held-out bits fall below run
2d. Then the comprehension probe: with no labels used in learning, the same state answers 'Where was X at the end?'
and 'Where did X start?' on val_timespace and on held-out generator stories.
Run: python learned/base/r24_place.py [--train 150000] [--held 5000]"""
import os, sys, json, math, random, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_books as B, r24_classes as C, r24_chunks as K
from b6_rwkv import hit

PLACE_WORDS = {"to", "at", "in", "into", "on", "near", "from", "toward", "towards", "by", "under", "behind", "across", "through"}
RANKINGS = ("recency", "subject_place", "any_place")


class PlaceState(T.State):
    def __init__(self):
        super().__init__(); self.place_of = {}; self.first_place_of = {}; self.any_place = []; self.subject = None

    def ranking(self, name):
        if name == "subject_place": return [self.place_of[self.subject]] if self.subject in self.place_of else []
        if name == "any_place": return self.any_place
        return super().ranking(name)

    def saw_place(self, key):
        if self.subject:
            self.place_of[self.subject] = key; self.first_place_of.setdefault(self.subject, key)
        if key in self.any_place: self.any_place.remove(key)
        self.any_place.insert(0, key)


class PlaceLM(K.ChunkLM):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.mix = collections.Counter(); self.prank = {r: collections.Counter() for r in RANKINGS}; self.use_place = True

    def learn_place(self, stories, names):
        """count, at ENT slots after a place word, which ranking has the filler at rank 0 and at which rank"""
        for text in stories:
            st = PlaceState()
            for s in T.SENT.split(text):
                toks = T.TOK.findall(s)
                if not toks: continue
                items = T.slotify(toks, names); st.subject = None
                for k, (sym, filler) in enumerate(items):
                    if sym == "PERSON" and st.subject is None and k <= 1: st.subject = filler[0]
                    if sym == "PRON" and st.subject is None and k == 0 and st.persons: st.subject = st.persons[0]   # the learner's own resolver: most recent
                    if sym == "ENT":
                        key = T.key_of(sym, filler)
                        if k and items[k - 1][0] in PLACE_WORDS:
                            for r in RANKINGS:
                                lst = st.ranking(r)
                                if key in lst: self.prank[r][lst.index(key)] += 1; self.mix[r] += (lst.index(key) == 0)
                                else: self.prank[r]["none"] += 1
                            st.saw_place(key)
                    if sym in ("PERSON", "ENT"): st.mention(sym, filler, first=(k == 0))

    def p_place_filler(self, key, st):
        z = sum(self.mix.values()) + 3.0; p = 0.0
        for r in RANKINGS:
            w = (self.mix[r] + 1.0) / z; c = self.prank[r]; R = sum(c.values()); lst = st.ranking(r)
            if key in lst: p += w * (c[lst.index(key)] + 0.5) / (R + 0.5 * T.K)
            else: p += w * (c["none"] + 0.5) / (R + 0.5 * T.K) / max(1, len(st.ents))
        return p

    def score(self, toks, names, st):
        items = self.symbols(T.slotify(toks, names)); syms = [sym for sym, _ in items]
        seg, lp = self.segment(syms); bits = -lp / math.log(2); full = all(len(ch) >= 2 for ch in seg); st.subject = None
        self.in_chunks += sum(len(ch) for ch in seg if len(ch) >= 2); self.n_syms += len(syms)
        for k, (sym, filler) in enumerate(items):
            pos = "first" if k == 0 else "later"
            if sym == "PERSON" and st.subject is None and k <= 1: st.subject = filler[0]
            if sym == "PRON" and st.subject is None and k == 0 and st.persons: st.subject = st.persons[0]
            if sym in ("PERSON", "ENT", "PRON") or sym.startswith("C"):
                after_place = sym == "ENT" and k and items[k - 1][0] in PLACE_WORDS
                if after_place and self.use_place:
                    key = T.key_of(sym, filler); new0, new1 = self.new[(sym, pos)]; p_new = (new0 + 1) / (new1 + 2)
                    pf = (1 - p_new) * self.p_place_filler(key, st) if key in st.ents else self.p_filler(sym, filler, st, pos)
                else: pf = self.p_filler(sym, filler, st, pos)
                pfl = 1.0
                for w in filler: pfl *= self.p_floor(w)
                bits += -math.log2((1 - T.FLOOR) * pf + T.FLOOR * pfl)
                if after_place: st.saw_place(T.key_of(sym, filler))
            if sym in ("PERSON", "ENT"): st.mention(sym, filler, first=(k == 0))
        return bits, len(toks), full


def probe(M, names, stories, label):
    """'Where was X at the end?' -> X's last place; 'Where did X start?' -> X's first place; no labels used in learning"""
    matched = right = n = 0
    for s in stories:
        st = PlaceState()
        for sent in T.SENT.split(s["text"]):
            toks = T.TOK.findall(sent)
            if toks: M.score(toks, names, st)
        for q, gold in s["qs"]:
            n += 1; ql = q.lower().rstrip("?"); a = None
            if ql.startswith("where was ") and ql.endswith(" at the end"): who = q[10:-12].strip(); a = st.place_of.get(who)
            elif ql.startswith("where did ") and ql.endswith(" start"): who = q[10:-6].strip(); a = st.first_place_of.get(who)
            if a is not None: matched += 1; right += hit(a, gold)
    print(f"R24-d2 probe on {label}: matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f})", flush=True)
    return matched, right, n


def main():
    import data as D
    train_b, held_b = D.books(); random.Random(2).shuffle(held_b)
    train = B.paragraphs(train_b, K.arg("--train", 150000)); held = B.paragraphs(held_b, K.arg("--held", 5000)); T0 = time.time()
    classes, uni = C.induce_classes([s["text"] for s in train], k=200); frozen = {w for w, _ in uni.most_common(100)}
    names = T.mid_caps([s["text"] for s in train])
    M = PlaceLM(classes, frozen, 5000); M.learn([s["text"] for s in train], names); M.learn_place([s["text"] for s in train], names)
    seqs = M.seqs([s["text"] for s in train], names); M.fit(seqs); print(f"fitted in {(time.time() - T0) / 60:.1f} min", flush=True)
    print("learned mixture over rankings at place slots:", dict(M.mix), "| subject_place ranks:", dict(M.prank["subject_place"]), flush=True)
    res = {}
    for use in (False, True):
        M.use_place = use; bits = n = 0
        for s in held:
            st = PlaceState()
            for sent in T.SENT.split(s["text"]):
                toks = T.TOK.findall(sent)
                if not toks: continue
                b, k, _ = M.score(toks, names, st); bits += b; n += k
        res[use] = bits / n; print(f"held-out bits/token {'WITH' if use else 'without'} the place memory: {bits / n:.3f}", flush=True)
    print(f"R24-d1: {res[True]:.3f} vs {res[False]:.3f} -> {'PASS (kept)' if res[True] < res[False] else 'MISS (not kept)'}")
    M.use_place = True
    val = json.load(open("val_timespace.json", encoding="utf-8"))["stories"]; v = probe(M, names, val, "val_timespace (bar >= 8 matched at >= 0.75)")
    gen = json.load(open("r21_heldout.json", encoding="utf-8"))[:100]; g = probe(M, names, gen, "100 held-out generator stories")
    json.dump(dict(bits_with=res[True], bits_without=res[False], val=v, gen=g, mix=dict(M.mix)), open("r24_place_results.json", "w"))


if __name__ == "__main__":
    main()
