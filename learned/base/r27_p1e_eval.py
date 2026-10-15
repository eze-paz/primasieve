"""R27 P1e evaluation with F2 (judge in context): realised answer vs the story's own sentence, both after story + question."""
import os, sys, json, statistics as st, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
from r27_fluency import judge_ctx, judge_ctx_many, judge_bits, sentence_form
from b6_rwkv import hit
items = [(s["text"], q, g) for s in json.load(open("val_all13.json", encoding="utf-8"))["stories"] for q, g in s["qs"]]
R = [r for r in json.load(open(sys.argv[1] if len(sys.argv) > 1 else "r27_p1_sentences.json", encoding="utf-8")) if r["s"] and r["story"]]
random.Random(0).shuffle(R); R = R[:60]
pre = lambda r: f"{items[r['i']][0]}\n\nQuestion: {r['q']}\nAnswer: "
a = [judge_ctx_many(pre(r), [r["s"]])[0] for r in R]
def before(r):
    t = items[r['i']][0]; k = t.find(r["story"]); return t[:k] if k > 0 else ""
b = [judge_ctx_many(before(r), [r["story"]])[0] if before(r).strip() else judge_bits(r["story"]) for r in R]
print(f"F2b realised (after story + question) {st.mean(a):.3f}, human sentence (after the text before it) {st.mean(b):.3f}; form {st.mean(sentence_form(r['s']) for r in R):.3f}; quoted {sum(1 for r in R if r['s'] == r['story'])}; gold {sum(1 for r in R if r['gold_span'] and hit(r['s'], items[r['i']][2]))} / {sum(1 for r in R if r['gold_span'])} over {len(R)}", flush=True)
