"""R27 P7: replies to 'Tell me about X' -- the clauses about X, realised as a retelling. Run: py -3.12 r27_about.py [--score]"""
import os, sys, re, json, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ARGV0 = list(sys.argv); sys.argv = [sys.argv[0], "--p2d"]
import r27_retell as RT
os.chdir(HERE)
PRONS = {"he", "she", "they", "him", "her", "them"}
def about(text, x):
    sents = []
    for s_ in RT.T.SENT.split(text):
        if s_.strip():
            cs, cf = RT.R.construction(s_, RT.names); sents.append((cs, cf, list(RT.R.LAST_RAWS)))
    rows = [r for r in RT.S.roles_of(sents) if r["subj"] and r.get("do")]
    xl = x.lower(); g = RT.gender(text, x); keep = []
    for r in rows:
        subj = str(r["subj"]).lower(); obj = str(r["obj"]).lower() if r["obj"] else ""
        if xl in subj or xl in obj or xl in (r.get("do") or "").lower() or (g and subj == g): keep.append(r)
        if len(keep) >= 5: break
    for r in keep:
        if g and str(r["subj"]).lower() == g: r["subj"] = x                                     # restore the name; the realiser re-pronominalises
    return RT.realise(text, keep) if keep else f"The story does not say much about {x}."
if __name__ == "__main__":
    st_ = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; qn = 0; un = []
    for k, s in enumerate(st_):
        if 310 <= qn < 510 or qn >= 910: un.append(k)
        qn += len(s["qs"])
    out = []
    for k in un[:40]:
        t = st_[k]["text"]; m = re.search(r"\b([A-Z][a-z]{2,})\b", t[1:]); 
        names = [w for w in re.findall(r"\b[A-Z][a-z]{2,}\b", t) if w.lower() not in RT.S.QW and w not in ("The", "One", "Every", "When", "After", "Before", "In", "On", "At", "By", "Then", "Later", "That", "This", "There", "Her", "His", "Its")]
        if not names: continue
        x = names[0]; rep = about(t, x)
        ref = " ".join(s for s in RT.T.SENT.split(t) if s.strip() and (x in s or re.search(r"\b(he|she)\b", s, re.I)))
        out.append(dict(k=k, x=x, reply=rep, ref=ref))
    json.dump(out, open("r27_p7_about.json", "w", encoding="utf-8"), indent=0)
    for r in out[:4]: print("ABOUT", r["x"], ":", r["reply"])
    if "--score" in ARGV0:
        from r27_fluency import judge_bits, sentence_form
        def rel(r):
            S = [s for s in re.split(r"(?<=[.!?])\s+", r["reply"]) if s.strip()]; g = RT.gender(st_[r["k"]]["text"], r["x"]) or "#"
            return sum(1 for s in S if r["x"].lower() in s.lower() or re.search(rf"\b({g}|him|her)\b", s, re.I)) / max(1, len(S))
        def faith(r):
            t = st_[r["k"]]["text"].lower(); S = [re.sub(r"^(In the end), ", "", s).rstrip(".") for s in re.split(r"(?<=\.)\s+", r["reply"]) if s.strip()]
            return sum(1 for s in S if " ".join(s.split()[-3:]).lower() in t) / max(1, len(S))
        R = [r for r in out if not r["reply"].startswith("The story does not")][:25]
        print(f"P7 relevance {st.mean(rel(r) for r in R):.3f}, faithfulness {st.mean(faith(r) for r in R):.3f}, judge reply {st.mean(judge_bits(r['reply']) for r in R):.3f} vs reference {st.mean(judge_bits(r['ref']) for r in R if r['ref']):.3f}, form {st.mean(sentence_form(r['reply']) for r in R):.3f} over {len(R)}", flush=True)
