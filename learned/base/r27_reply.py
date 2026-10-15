"""R27 P3: a reply paragraph to a question -- the answer sentence plus up to two related story clauses (R27_prereg.md).
Run: py -3.12 r27_reply.py [--untouched] [--n N] [--score]"""
import os, sys, re, json, random, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
ARGV0 = list(sys.argv)
import r27_retell as RT                                                                     # loads the role reader stack
from r27_answer import sentence, cap
from b6_rwkv import hit
os.chdir(HERE)
STOP = {"the", "a", "an", "of", "to", "in", "on", "at", "and", "was", "were", "did", "do", "does", "is", "are", "who", "what", "where", "when", "why", "how", "her", "his", "he", "she", "they", "it", "with", "for", "by", "from", "had", "has"}
def words(t): return {w.lower() for w in re.findall(r"[A-Za-z']+", t) if w.lower() not in STOP and len(w) > 2}
def clause_text(r): return f"{r['subj']} {r.get('do') or ''}".strip()
def reply(text, q, a):
    if not a: return "The story does not say."
    s1 = sentence(q, a, text) or cap(a) + "."
    rows = []
    sents = []
    for x in RT.T.SENT.split(text):
        if x.strip():
            cs, cf = RT.R.construction(x, RT.names); sents.append((cs, cf, list(RT.R.LAST_RAWS)))
    allr = [r for r in RT.S.roles_of(sents) if r["subj"] and r.get("do")]
    for k in range(1, len(allr)):                                                              # a verb after 'and' shares the previous clause's subject
        r, p_ = allr[k], allr[k - 1]
        if r["si"] == p_["si"] and re.search(r"\band\s+" + re.escape(r["do"].split()[0]) + r"\b", text, re.I): r["subj"] = p_["subj"]
    allr = [r for r in allr if not any(o is not r and o["si"] == r["si"] and r["do"].lower() in o["do"].lower() and len(o["do"]) > len(r["do"]) for o in allr)]   # no nested clauses
    S_ = [x for x in RT.T.SENT.split(text) if x.strip()]
    ans_si = next((k for k, x in enumerate(S_) if a.lower() in x.lower()), None)
    qverbs = {RT.D.verb_base(w.lower()) for w in re.findall(r"[A-Za-z]+", q) if RT.D.verb_base(w.lower())} - {"be", "have", "do"}
    key = words(q) | words(a)
    scored = sorted(((len(words(clause_text(r)) & key), -abs((r["si"] - ans_si) if ans_si is not None else 0), r) for r in allr if a.lower() not in clause_text(r).lower() and r["si"] != ans_si and (RT.D.verb_base(r["verb"]) or r["verb"]) not in qverbs), key=lambda x: (-x[0], -x[1]))
    support = [r for sc, _, r in scored if sc > 0][:2]
    support.sort(key=lambda r: r["si"])
    out = [s1]
    for r in support:
        subj = RT.NOMI.get(str(r["subj"]).lower(), str(r["subj"])); pred = r["do"].strip()
        link = "Before that" if (ans_si is not None and r["si"] < ans_si) else "After that" if (ans_si is not None and r["si"] > ans_si) else "Also"
        s = f"{subj} {pred}"; s = f"{link}, " + (s[0].lower() + s[1:] if s.split()[0].lower() in RT.PRON | {"the", "a", "an"} else s)
        if s.lower().rstrip(".") not in " ".join(out).lower(): out.append(s.rstrip(".") + ".")
    return " ".join(out)
if __name__ == "__main__":
    st_ = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; items = [(s["text"], q, g) for s in st_ for q, g in s["qs"]]
    pol = json.load(open("r26_best_policy_answers.json", encoding="utf-8"))
    idx = (list(range(310, 510)) + list(range(910, 2510))) if "--untouched" in ARGV0 else (list(range(310)) + list(range(510, 910)))
    idx = [i for i in idx if pol[i]]; random.Random(0).shuffle(idx)
    if "--n" in ARGV0: idx = idx[:int(ARGV0[ARGV0.index("--n") + 1])]
    R = []
    for i in idx:
        t, q, g = items[i]; rp = reply(t, q, pol[i]); s1 = sentence(q, pol[i], t)
        R.append(dict(i=i, q=q, reply=rp, one=s1, story=" ".join([x for x in RT.T.SENT.split(t) if x.strip()][:4]), gold_one=bool(s1 and hit(s1, g)), gold_reply=bool(hit(rp, g))))
    json.dump(R, open("r27_p3_replies.json" if "--untouched" in ARGV0 else "r27_p3_replies_practice.json", "w", encoding="utf-8"), indent=0)
    for r in R[:8]: print("Q:", r["q"], "\nA:", r["reply"], "\n")
    if "--score" in ARGV0:
        from r27_fluency import judge_bits, sentence_form, entity_continuity
        print("gold kept:", sum(r["gold_reply"] for r in R if r["gold_one"]), "/", sum(r["gold_one"] for r in R))
        multi = [r for r in R if r["reply"].count(".") >= 2]
        for name, f in (("reply paragraphs", lambda r: r["reply"]), ("story first four sentences", lambda r: r["story"])):
            sc = [(judge_bits(f(r)), sentence_form(f(r)), entity_continuity(f(r))) for r in multi]
            print(f"P3 {name}: judge {st.mean(x[0] for x in sc):.3f}, form {st.mean(x[1] for x in sc):.3f}, continuity {st.mean(x[2] for x in sc if x[2] == x[2]):.3f} over {len(multi)}", flush=True)
