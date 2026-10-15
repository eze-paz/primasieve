"""R27 P9: summary from whole story sentences (sentence-level content plan + pronouns). Run: py -3.12 r27_summarise.py"""
import os, sys, re, json, collections, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ARGV0 = list(sys.argv); sys.argv = [sys.argv[0], "--p2e"]
import r27_retell as RT
os.chdir(HERE)
def summarise(text, k=4):
    S = [x for x in RT.T.SENT.split(text) if x.strip()]
    names = collections.Counter(w for w in re.findall(r"\b[A-Z][a-z]{2,}\b", text) if w not in ("The", "One", "Every", "When", "After", "Before", "Then", "Later", "She", "He", "They", "It", "Her", "His", "That", "This", "There", "In", "On", "At", "By", "As", "But", "And", "So"))
    main = names.most_common(1)[0][0] if names else None
    sc = []
    for i, s in enumerate(S):
        cs, cf = RT.R.construction(s, RT.names); n = sum(1 for r in RT.S.roles_of([(cs, cf, list(RT.R.LAST_RAWS))]) if r["subj"] and r["verb"])
        sc.append((n + (1 if main and main in s else 0), -i, i))
    keep = sorted(i for _, _, i in sorted(sc, reverse=True)[:k])
    out = []; prev_name = None
    for i in keep:
        s = S[i].strip(); first = s.split()[0].strip(",")
        if prev_name and first == prev_name:
            g = RT.gender(text, first)
            if g: s = g.capitalize() + s[len(first):]
        prev_name = first if first[0].isupper() and first in names else None
        out.append(s)
    return " ".join(out)
if __name__ == "__main__":
    from r27_fluency import judge_bits, sentence_form, order_gain, entity_continuity
    st_ = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    H = {r["k"]: r["summary"] for r in json.load(open("r27_human_summaries.json", encoding="utf-8"))}
    out = {k: summarise(st_[k]["text"]) for k in H}
    json.dump(out, open("r27_p9_summaries.json", "w", encoding="utf-8"), indent=0)
    for k in list(H)[:2]: print("OURS:", out[k], "\nHUMAN:", H[k], "\n")
    for name, src in (("P9 sentence-level summary", out), ("human summaries", H)):
        sc = [(judge_bits(src[k]), sentence_form(src[k]), order_gain(src[k]), entity_continuity(src[k])) for k in H]
        print(f"P9 {name}: judge {st.mean(x[0] for x in sc):.3f}, form {st.mean(x[1] for x in sc):.3f}, order gain {st.mean(x[2] for x in sc if x[2] == x[2]):.3f}, continuity {st.mean(x[3] for x in sc if x[3] == x[3]):.3f}", flush=True)
