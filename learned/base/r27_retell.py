"""R27 P2: retell a story -- content plan from the role reader's clauses, sentence plan, realisation. Run: py -3.12 r27_retell.py"""
import os, sys, re, json, random, time, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:]]; ARGV0 = list(sys.argv); sys.argv = [sys.argv[0]]
import r25_soft as S
T, E, R, B, D0, D, QR = S.T, S.E, S.R, S.B, S.D0, S.D, S.QR
os.chdir(HERE)
from r27_answer import past, cap
data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
train_b, _ = D0.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
D.ON = True; T.SPAN_STOP.update(D.verb_forms() - E.NOUNISH); QR.ARGV = ["x", "--pron-ref"]
LINK = ["", "Then", "Later", "After that", "Then", "Later"]
PRON = {"he", "she", "they", "it", "him", "her", "them"}
def gender(text, name):
    i = text.find(name)
    if i < 0: return None
    m = re.search(r"\b(he|she)\b", text[i + len(name):], re.I); return m.group(1).lower() if m else None
def plan(text):
    sents = []
    for x in T.SENT.split(text):
        if x.strip():
            cs, cf = R.construction(x, names); sents.append((cs, cf, list(R.LAST_RAWS)))
    rows = S.roles_of(sents); out = []; seen = set()
    for r in rows:
        if not r["subj"] or not r["verb"]: continue
        key = (str(r["subj"]).lower(), r["verb"], str(r["obj"]).lower() if r["obj"] else None)
        if key in seen: continue
        seen.add(key); out.append(r)
        if len(out) >= 6: break
    return out
NOMI = {"him": "he", "her": "she", "them": "they"}
def realise(text, rows):
    out = []; prev = None; said_time = set(); prev_subj_by_sent = {}
    for k, r in enumerate(rows):
        subj = str(r["subj"]); pred = (r.get("do") or "").strip()
        if not pred: continue
        if k > 0 and r["si"] == rows[k - 1]["si"] and pred.lower() in (rows[k - 1].get("do") or "").lower(): continue   # nested in the previous clause
        m_ = re.search(r"\b(was|were|had been|has been|is|are)\s+" + re.escape(pred.split()[0]) + r"\b", text, re.I)
        if m_: pred = m_.group(1) + " " + pred                                                  # keep the passive / progressive auxiliary
        if k > 0 and r["si"] == rows[k - 1]["si"] and re.search(r"\band\s+" + re.escape(pred.split()[0]) + r"\b", text, re.I): subj = prev   # shared subject after 'and'
        subj = NOMI.get(subj.lower(), subj)
        if prev and subj.lower() == prev.lower() and subj.lower() not in PRON:
            g = gender(text, subj); subj_s = g if g else subj
        else: subj_s = subj
        s = f"{subj_s} {pred}"
        if r["when"] and r["si"] not in said_time and str(r["when"]).lower() not in s.lower():
            w = str(r["when"]); s = f"{w[0].upper() + w[1:]}, {s[0].lower() + s[1:] if not s.split()[0][0].isupper() or s.split()[0].lower() in PRON else s}"; said_time.add(r["si"])
        n_out = len(out); link = "In the end" if (k == len(rows) - 1 and n_out >= 2) else LINK[min(n_out, len(LINK) - 1)]
        s = s.strip()
        if link: s = link + ", " + (s[0].lower() + s[1:] if s.split()[0].lower() in PRON | {"the", "a", "an", "one", "every", "until", "when", "after", "before", "on", "in", "at", "by", "during"} else s)
        out.append(cap(s).rstrip(".") + "."); prev = subj
    return " ".join(out)
if __name__ == "__main__":
    from r27_fluency import judge_bits, sentence_form, order_gain, entity_continuity
    st_ = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    texts = [s["text"] for s in st_]
    # story index ranges: the 2,510 questions map to 502 stories; untouched = val_fresh2 and val_fresh3..10 stories
    qn = 0; idx_un = []; idx_pr = []
    for k, s in enumerate(st_):
        (idx_un if (310 <= qn < 510 or qn >= 910) else idx_pr).append(k); qn += len(s["qs"])
    use = idx_un if "--untouched" in ARGV0 else idx_pr[:40]
    if "--n" in ARGV0: use = use[:int(ARGV0[ARGV0.index("--n") + 1])]
    res = []
    for k in use:
        rows = plan(texts[k]); out = realise(texts[k], rows) if rows else ""
        story6 = " ".join([x for x in T.SENT.split(texts[k]) if x.strip()][:6])
        res.append(dict(k=k, retell=out, story=story6, n=len(rows)))
    json.dump(res, open("r27_p2_retell.json" if "--untouched" in ARGV0 else "r27_p2_retell_practice.json", "w", encoding="utf-8"), indent=0)
    for r in res[:5]: print("STORY:", r["story"][:300], "\nRETELL:", r["retell"], "\n")
    if "--score" in ARGV0:
        good = [r for r in res if r["retell"].count(".") >= 3]
        for name, f in (("retelling", lambda r: r["retell"]), ("story first six sentences", lambda r: r["story"])):
            sc = [(judge_bits(f(r)), sentence_form(f(r)), order_gain(f(r)), entity_continuity(f(r))) for r in good]
            print(f"P2 {name}: judge {st.mean(x[0] for x in sc):.3f}, form {st.mean(x[1] for x in sc):.3f}, order gain {st.mean(x[2] for x in sc):.3f}, continuity {st.mean(x[3] for x in sc):.3f} over {len(good)}", flush=True)
