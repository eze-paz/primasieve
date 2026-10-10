"""R24-h: the whole learned stack on the hand-written validation stories (val_timespace, 30 questions). Every layer is
the one the next-word game built: constructions over induced classes, the recency state and the 'he = latest person'
resolver, the place memory with learned attribution per place word, the time marks, the holder memory with learned
verb rules. A question is turned into the statement prefix the learner was trained on (the only hand-written part,
the question layer, as in R20) and the answer is the learner's own argmax at the slot. Reference: hand world 20 / 30
matched, 19 right; R20 induced world 21 / 30, 19 right.
Run: python learned/base/r24_probe.py"""
import os, sys, json, math, random, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
sys.argv = [sys.argv[0], "--run3"]
import r24_tlm as T, r24_classes as C, r24_place as P, r24_qa as Q, r24_time as R, r24_hold as H
from b6_rwkv import hit


def fit_all():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); T0 = time.time()
    train = R.with_answers(data[:7000]); names = T.mid_caps([s["text"] for s in train])
    classes, uni = C.induce_classes([s["text"] for s in train], k=100, min_count=5); frozen = {w for w, _ in uni.most_common(100)}
    M = R.TimeLM(classes, frozen, 3000); M.prank = {r: collections.Counter() for r in P.RANKINGS}
    M.learn([s["text"] for s in train], names); M.learn_place([s["text"] for s in train], names); M.fit(M.seqs([s["text"] for s in train], names))
    rules = json.load(open("r24_time_results.json")).get("rules") or {}
    R.RULE.update(rules)
    if rules:
        M.prank = {r: collections.Counter() for r in P.RANKINGS}; M.mix = collections.Counter(); M.mix_ctx = collections.defaultdict(collections.Counter); M.prank_ctx = collections.defaultdict(collections.Counter)
        M.learn_place([s["text"] for s in train], names)
    htrain = H.with_answers(data[:7000]); hnames = T.mid_caps([s["text"] for s in htrain]); tr = [H.reduce(s["text"], hnames) for s in htrain]
    HM = H.HolderLM(); HM.rule.update(json.load(open("r24_hold_results.json"))["rules"]); HM.count(tr)
    print(f"fitted all layers in {(time.time() - T0) / 60:.1f} min; attribution rules {dict(R.RULE)}", flush=True)
    return M, names, HM, hnames


def answer(M, names, HM, hnames, text, q):
    """the learner's own argmax for the question's statement prefix; None = no layer speaks"""
    ql = q.lower().rstrip("?"); st = R.TimeState(); sents = [x for x in T.SENT.split(text) if x.strip()]
    for sent in sents:
        toks = T.TOK.findall(sent)
        if toks: M.score(toks, names, st, sent)
    def ent(x):
        x = x.strip(); return T.key_of("ENT", x.lower().split()) if x.split()[0].lower() in T.DET else x
    def place(ctx, who, mark=None, first=False):
        st.anchor_mark = mark; st.subject = who if who[:1].isupper() else None; st.obj = who if not who[:1].isupper() else None
        cands = [k for k in st.ents if k != who]
        return max(cands, key=lambda key: M.p_place_filler(key, st, ctx)) if cands else None
    if ql.startswith("where was ") and ql.endswith(" at the end"): return place(("was", "at"), ent(q[10:-12]))
    if ql.startswith("where did ") and ql.endswith(" start"): return place(("started", "at"), ent(q[10:-6]))
    for m in R.MARKS:
        if ql.startswith("where was ") and ql.endswith(" " + m): return place(("mark", "at"), ent(q[10:-(len(m) + 1)]), mark=m)
    # holder questions through the holder learner
    sents_h = H.reduce(text, hnames); obs, holder, first_holder = HM.replay(sents_h); persons = []
    for _, _, _, mentions in sents_h:
        for kind, key in mentions:
            if kind == "PERSON":
                if key in persons: persons.remove(key)
                persons.insert(0, key)
    def who_with(ctx, thing, rankings):
        cands = persons + (["Nobody"] if ctx[0] == "right" else [])
        return max(cands, key=lambda k: HM.p(ctx, k, rankings, persons)) if cands else None
    def rk(thing, extra=None):
        return {"recency": persons, "subject": [], "holder": [holder[thing] if holder.get(thing) else "Nobody"] if thing in holder else [],
                "first_holder": [first_holder[thing]] if thing in first_holder else [], "after_event": extra or [], "next_after_event": []}
    if ql.startswith("who had ") and ql.endswith(" at the end"): t = ent(q[8:-12]); return who_with(("was", "with"), t, rk(t))
    if ql.startswith("who had ") and ql.endswith(" first"): t = ent(q[8:-6]); return who_with(("first", "with"), t, rk(t))
    if ql.startswith("who had ") and " after " in ql:
        t = ent(q[8:].rstrip("?").split(" after ")[0]); ev = q[8:].rstrip("?").split(" after ", 1)[1].split()
        who, verb = ev[0], (ev[1] if len(ev) > 1 else "")
        # the holder right after / the next holder after that event, from the holder learner's own timeline
        timeline = []; hold2 = {}
        for subj, events, _, mentions in sents_h:
            for v, o, rec, es in events:
                if es == "PRON": es = persons[0] if persons else None
                if not (es and o) or o == "IT": continue
                r = HM.rule[v]
                if r == "hold": hold2[o] = es
                elif r == "release": hold2[o] = None
                elif r == "give" and rec: hold2[o] = rec
                timeline.append((es, v, o, hold2.get(o)))
        idx = [i for i, (sj, v, th, h) in enumerate(timeline) if sj == who and (v == verb or v.startswith(verb[:3]))]
        if not idx: return None
        later = [h for (sj, v, th, h) in timeline[idx[-1] + 1:] if h]
        return later[0] if later else None
    return None


def main():
    M, names, HM, hnames = fit_all()
    val = json.load(open("val_timespace.json", encoding="utf-8"))["stories"]; matched = right = n = 0
    for s in val:
        for q, gold in s["qs"]:
            n += 1; a = answer(M, names, HM, hnames, s["text"], q)
            if a is not None: matched += 1; right += hit(a, gold)
            print(f"  {'OK ' if a is not None and hit(a, gold) else 'XX ' if a is not None else '-- '} {q} | gold {gold} | learned {a}")
    print(f"R24-h: the learned stack alone on val_timespace: matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f}); hand world 20 / 19, R20 induced world 21 / 19")
    json.dump(dict(matched=matched, right=right, n=n), open("r24_probe_results.json", "w"))


if __name__ == "__main__":
    main()
