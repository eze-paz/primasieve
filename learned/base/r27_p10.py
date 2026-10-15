"""R27 P10: summarising long passages -- P9 selection vs lead-5 vs clause retelling, against human summaries."""
import os, sys, re, json, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ARGV0 = list(sys.argv); sys.argv = [sys.argv[0], "--p2e"]
import r27_retell as RT
from r27_summarise import summarise
os.chdir(HERE)
import r24_dict as Dct
P = json.load(open("r27_long_passages.json", encoding="utf-8")); H = {r["k"]: r["summary"] for r in json.load(open("r27_long_human_summaries.json", encoding="utf-8"))}
STOP = set("the a an and or but of to in on at by for with from was were is are be been had has have did do does he she it they his her their its him them i you we my your our this that these those as so then there when while not no".split())
def cw(t): return {(Dct.verb_base(w) or w) for w in (x.lower() for x in re.findall(r"[A-Za-z']+", t)) if w not in STOP and len(w) > 2}
def cover(sys_t, k): h = cw(H[k]); return len(h & cw(sys_t)) / max(1, len(h))
S = {"P9 selection (k=5)": {}, "lead-5": {}, "clause retelling": {}}
for p in P:
    t = p["text"]; sents = [x for x in RT.T.SENT.split(t) if x.strip()]
    S["P9 selection (k=5)"][p["k"]] = summarise(t, 5); S["lead-5"][p["k"]] = " ".join(sents[:5]); S["clause retelling"][p["k"]] = RT.realise(t, RT.plan(t))
json.dump(S, open("r27_p10_outputs.json", "w", encoding="utf-8"), indent=0)
from r27_fluency import judge_bits, sentence_form, order_gain
for name, src in list(S.items()) + [("human summaries", H)]:
    ks = [p["k"] for p in P]
    print(f"P10 {name}: coverage {st.mean(cover(src[k], k) for k in ks):.3f}, words {st.mean(len(src[k].split()) for k in ks):.0f}, judge {st.mean(judge_bits(src[k]) for k in ks):.3f}, form {st.mean(sentence_form(src[k]) for k in ks):.3f}", flush=True)
