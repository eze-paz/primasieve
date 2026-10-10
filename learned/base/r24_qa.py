"""R24-e: the next-word game on stories FOLLOWED BY their questions restated as statements. Same learner and state as
R24-d (chunk constructions over classes, recency state, the subject's last / first place); nothing is labelled: the
answer sentences are just more text, and the only thing that can predict 'Rosa was at the garden.' is the memory of
where Rosa last went. Kept if held-out bits on answer sentences fall; comprehension = the learner's own argmax at the
answer slot, scored against the gold (which is the text's next words).
Run: python learned/base/r24_qa.py"""
import os, sys, json, math, random, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_classes as C, r24_chunks as K, r24_place as P
from b6_rwkv import hit

P.RANKINGS = ("recency", "subject_place", "subject_first_place", "any_place")


class QAState(P.PlaceState):
    def ranking(self, name):
        if name == "subject_first_place": return [self.first_place_of[self.subject]] if self.subject in self.first_place_of else []
        return super().ranking(name)


P.PlaceState = QAState          # the place learner's counting pass uses the state that knows the first-place ranking


def restate(q, gold):
    """the generator's question and its gold, as a statement; None for question kinds not restated here"""
    ql = q.lower().rstrip("?"); g = gold[0]
    def place(g): return g if g.startswith(("on the", "in the", "at the", "by the", "under the", "near the", "behind the")) else (f"at {g}" if g.startswith(("the ", "a ", "his ", "her ")) else f"at the {g}")
    if ql.startswith("where was ") and ql.endswith(" at the end"): return f"{q[10:-12].strip()[0].upper()}{q[10:-12].strip()[1:]} was {place(g)}."
    if ql.startswith("where did ") and ql.endswith(" start"): return f"{q[10:-6].strip()[0].upper()}{q[10:-6].strip()[1:]} started {place(g)}."
    return None


def with_answers(stories):
    out = []
    for s in stories:
        ans = [restate(q, g) for q, g in s["qs"]]; ans = [a for a in ans if a]
        if ans: out.append(dict(text=s["text"] + " " + " ".join(ans), n_story=len([x for x in T.SENT.split(s["text"]) if x.strip()]), qs=s["qs"]))
    return out


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data)
    train = with_answers(data[:7000]); held = with_answers(data[7000:]); T0 = time.time()
    classes, uni = C.induce_classes([s["text"] for s in train], k=100, min_count=5); frozen = {w for w, _ in uni.most_common(100)}
    names = T.mid_caps([s["text"] for s in train])
    M = P.PlaceLM(classes, frozen, 3000); M.prank = {r: collections.Counter() for r in P.RANKINGS}
    M.learn([s["text"] for s in train], names); M.learn_place([s["text"] for s in train], names)
    seqs = M.seqs([s["text"] for s in train], names); M.fit(seqs); print(f"fitted in {(time.time() - T0) / 60:.1f} min", flush=True)
    print("learned mixture over rankings at place slots:", dict(M.mix), flush=True)
    for ctx in (("was", "at"), ("started", "at")):
        if ctx in M.mix_ctx: print(f"   in context {ctx}: {dict(M.mix_ctx[ctx])}", flush=True)
    res = {}
    for use in (False, True):
        M.use_place = use; bits = n = ab = an = 0
        for s in held:
            st = QAState(); sents = [x for x in T.SENT.split(s["text"]) if x.strip()]
            for k, sent in enumerate(sents):
                toks = T.TOK.findall(sent)
                if not toks: continue
                b, kk, _ = M.score(toks, names, st); bits += b; n += kk
                if k >= s["n_story"]: ab += b; an += kk
        res[use] = (bits / n, ab / max(1, an)); print(f"held-out bits/token {'WITH' if use else 'without'} the place memory: all {bits / n:.3f} | answer sentences {ab / max(1, an):.3f}", flush=True)
    print(f"R24-e1: answer-sentence bits {res[True][1]:.3f} vs {res[False][1]:.3f} -> {'PASS' if res[True][1] < res[False][1] else 'MISS'}")
    M.use_place = True

    def predict_place(st, who, first=False):
        st.subject = who; st.first_place_of  # the learner's argmax over known ENTs at a place slot
        if not st.ents: return None
        return max(st.ents, key=lambda key: M.p_place_filler(key, st, ("was", "at")))

    for label, stories, bar in (("held-out generator stories", held, 0.80), ("val_timespace", [dict(text=s["text"], qs=s["qs"]) for s in json.load(open("val_timespace.json", encoding="utf-8"))["stories"]], 0.75)):
        ok = tot = 0
        for s in stories:
            st = QAState()
            for sent in [x for x in T.SENT.split(s["text"]) if x.strip()][: s.get("n_story", 10 ** 6)]:
                toks = T.TOK.findall(sent)
                if toks: M.score(toks, names, st)
            for q, gold in s["qs"]:
                ql = q.lower().rstrip("?")
                if ql.startswith("where was ") and ql.endswith(" at the end"):
                    who = q[10:-12].strip(); who = T.key_of('ENT', who.lower().split()) if who.split()[0].lower() in T.DET else who
                    a = predict_place(st, who); tot += 1; ok += (a is not None and hit(a, gold))
        print(f"R24-e{'2' if bar == 0.8 else '3'} on {label}: 'Where was X at the end' answered by the learner's own next-word argmax: {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= {bar})", flush=True)
    json.dump(dict(bits=res, mix=dict(M.mix)), open("r24_qa_results.json", "w"))


if __name__ == "__main__":
    main()
