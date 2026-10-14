"""R27 P1 evaluation on the untouched answers: fluency of realised sentences vs bare spans vs the story's sentences."""
import os, sys, json, statistics as st, random
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
from r27_fluency import judge_bits, sentence_form
R = [r for r in json.load(open("r27_p1_sentences.json", encoding="utf-8")) if r["s"] and r["story"]]
random.Random(0).shuffle(R); R = R[:300]
def m(xs): return round(st.mean(xs), 3)
out = {}
for name, f in (("realised sentences", lambda r: r["s"]), ("bare answer spans", lambda r: r["a"]), ("story's own sentence", lambda r: r["story"])):
    out[name] = dict(judge=m([judge_bits(f(r)) for r in R]), form=m([sentence_form(f(r)) for r in R]))
    print(f"P1 {name}: {out[name]} over {len(R)}", flush=True)
print("gold kept:", sum(r["gold_sent"] for r in R if r["gold_span"]), "/", sum(r["gold_span"] for r in R))
for r in R[:15]: print("  ", r["q"], "->", r["s"])
