"""R27 G3: retellings written by our own model vs human summaries and the story-wording retelling."""
import os, sys, json, re, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ARGV0_ = list(sys.argv); sys.argv = [sys.argv[0], "--g2b"]
import r27_gen as G
os.chdir(HERE)
from r27_fluency import judge_bits, sentence_form, order_gain
stories = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
H = {r["k"]: r["summary"] for r in json.load(open("r27_human_summaries.json", encoding="utf-8"))}
E = {r["k"]: r["retell"] for r in json.load(open("r27_p2e_retell.json", encoding="utf-8"))}
P = {k: G.paragraph_mix(stories[k]["text"], clause="--clause" in ARGV0_) for k in H}
json.dump(P, open("r27_g5_outputs.json", "w", encoding="utf-8"), indent=0)
for k in list(H)[:4]: print("OURS:", P[k], "\nHUMAN:", H[k], "\n")
def grams(t): w = [x.lower() for x in re.findall(r"[A-Za-z']+", t)]; return [tuple(w[i:i + 3]) for i in range(len(w) - 2)]
ks = [k for k in H if P[k].count(".") >= 2]
nov = st.mean(sum(1 for g in grams(P[k]) if g not in set(grams(stories[k]["text"]))) / max(1, len(grams(P[k]))) for k in ks)
for name, src in (("G5 counts+network own-words retelling", P), ("human summaries", H), ("P8 story-wording retelling", E)):
    sc = [(judge_bits(src[k]), sentence_form(src[k]), order_gain(src[k])) for k in ks]
    print(f"G3 {name}: judge {st.mean(x[0] for x in sc):.3f}, form {st.mean(x[1] for x in sc):.3f}, order gain {st.mean(x[2] for x in sc if x[2] == x[2]):.3f} over {len(ks)}", flush=True)
print(f"G3 novelty of our retellings: {nov:.3f}")
