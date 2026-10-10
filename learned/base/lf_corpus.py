"""R17 step 1: the silver logical-form corpus. The hand-rule event reader reads every sentence of the generated
stories; an event (agent, verb, patient) is kept when both fillers stand in the sentence, and marked verified when one
of them is a gold answer of the story. The real-text teacher pairs (r5_train.json) are added as a second source.
Run: python learned/base/lf_corpus.py  -> learned/base/lf_corpus.json"""
import os, sys, json, re, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT)
import battery
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")


def main(limit=3000):
    R = battery.door().events.reader
    stories = json.load(open(os.path.join(HERE, "stories_train_v2.json"), encoding="utf-8"))
    out = []; seen = kept = 0; T0 = time.time()
    for s in stories[:limit]:
        golds = {g.lower() for q, gs in s["qs"] for g in gs}
        for sent in SENT.split(s["text"]):
            seen += 1; R.last_agent = None; R.last_patient = None
            try: evs = R.read(sent)
            except Exception: continue
            for e in evs:
                a, p, v = e.get("agent") or "", e.get("patient") or "", e.get("verb") or ""
                if not (a and p and v) or e.get("status") != "realis" or a not in sent or p not in sent: continue
                verified = any(x in golds for x in (a.lower(), p.lower(), a.lower().replace("the ", ""), p.lower().replace("the ", "")))
                toks = re.findall(r"[A-Za-z']+", sent); pos = e.get("pos")
                out.append(dict(sentence=sent, agent=a, verb=v, patient=p, surface=toks[pos] if pos is not None and pos < len(toks) else None, verified=verified)); kept += 1
    r5 = json.load(open(os.path.join(HERE, "r5_train.json"), encoding="utf-8"))
    real = [dict(sentence=x["sentence"], q=x["q"], answer=x["answer"], verified=True, source="teacher") for x in r5 if x["answer"] != "unknown"]
    json.dump(dict(stories=out, real=real), open(os.path.join(HERE, "lf_corpus.json"), "w", encoding="utf-8"), indent=0)
    print(f"story sentences {seen}, events kept {kept} ({sum(e['verified'] for e in out)} verified); real-text teacher pairs {len(real)} ({time.time() - T0:.0f} s)")


if __name__ == "__main__":
    main()
