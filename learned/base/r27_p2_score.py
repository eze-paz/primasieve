"""R27 P2 scoring of saved retellings (r27_p2_retell.json): judge, form, order gain, continuity, faithfulness."""
import os, sys, json, re, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
from r27_fluency import judge_bits, sentence_form, order_gain, entity_continuity
texts = [s["text"] for s in json.load(open("val_all13.json", encoding="utf-8"))["stories"]]
R = [r for r in json.load(open("r27_p2_retell.json", encoding="utf-8")) if r["retell"].count(".") >= 3][:20]
def faith(r):
    S = [re.sub(r"^(Then|Later|After that|In the end|Before that|Also), ", "", s).rstrip(".") for s in re.split(r"(?<=\.)\s+", r["retell"]) if s.strip()]
    t = texts[r["k"]].lower(); ok = 0
    for s in S:
        w = s.split(); pred = " ".join(w[1:]).lower() if len(w) > 1 else s.lower()
        ok += any(pred[-k:] in t for k in (len(pred),)) or " ".join(w[-3:]).lower() in t
    return ok / max(1, len(S))
for name, f in (("retelling", lambda r: r["retell"]), ("story first six sentences", lambda r: r["story"])):
    sc = [(judge_bits(f(r)), sentence_form(f(r)), order_gain(f(r)), entity_continuity(f(r))) for r in R]
    print(f"P2 {name}: judge {st.mean(x[0] for x in sc):.3f}, form {st.mean(x[1] for x in sc):.3f}, order gain {st.mean(x[2] for x in sc if x[2] == x[2]):.3f}, continuity {st.mean(x[3] for x in sc if x[3] == x[3]):.3f} over {len(R)}", flush=True)
print(f"P2 faithfulness (retelling sentences whose wording is found in the story): {st.mean(faith(r) for r in R):.3f}")
for r in R[:3]: print("RETELL:", r["retell"])
