"""R27 P8: human summaries vs P2d vs P8 (aggregation) on the same 20 stories."""
import os, sys, json, re, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
from r27_fluency import judge_bits, sentence_form, order_gain, entity_continuity
H = {r["k"]: r["summary"] for r in json.load(open("r27_human_summaries.json", encoding="utf-8"))}
D = {r["k"]: r["retell"] for r in json.load(open("r27_p2d_retell.json", encoding="utf-8"))}
E = {r["k"]: r["retell"] for r in json.load(open("r27_p2e_retell.json", encoding="utf-8"))}
ks = [k for k in H if k in D and k in E and D[k].count(".") >= 3]
for name, src in (("human summaries", H), ("P2d retelling", D), ("P8 aggregated retelling", E)):
    sc = [(judge_bits(src[k]), sentence_form(src[k]), order_gain(src[k]), entity_continuity(src[k])) for k in ks]
    print(f"P8 {name}: judge {st.mean(x[0] for x in sc):.3f}, form {st.mean(x[1] for x in sc):.3f}, order gain {st.mean(x[2] for x in sc if x[2] == x[2]):.3f}, continuity {st.mean(x[3] for x in sc if x[3] == x[3]):.3f} over {len(ks)}", flush=True)
