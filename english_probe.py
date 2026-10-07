"""ENGLISH PROBES -- runs tests/english_probes.json (ENGLISH_MAP.md) and scores the engine AND the predictions.

Story probes go through the event memory alone (core.events.EventMemory over kb_events.build, built once) and, for the
stories marked door=true, through the live door (chat.live_door, a NEW door per story); question probes go through ONE
live door, in order (setup turns first). Outcomes: RIGHT / WRONG / SILENT. Writes english_probe_results.json and
(re)writes the Results section of ENGLISH_MAP.md. Diagnostic only: nothing in core/ imports it.

    python english_probe.py [--em-only] [--max-door-stories 40]
"""
import os, sys, re, json, time, tempfile, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
T0 = time.time()
PROBES = os.path.join(HERE, "tests", "english_probes.json")
OUT = os.path.join(HERE, "english_probe_results.json")
MAP = os.path.join(HERE, "ENGLISH_MAP.md")
STORE = os.path.join(tempfile.gettempdir(), "english_probe_store.json")   # never the battery's store file (a battery may be running)

ABST = ("I could not find", "No world of mine", "I cannot", "Nothing I hold", "I found nothing", "Did you mean",
        "I do not know the word", "That is not something I can do", "What would help", "Say correct", "Say wrong",
        "Noted", "Understood", "Acknowledged", "Which did you mean", "Which reading do you want", "Say which one")
READS = ("It could be", "Two readings survive", "Either")
RECALL = ("From what you told me:", "By your account:", "As you told it:")
QUOTE = ("If you mean what", "If you are asking what", "Taking this as what", "The dictionary says", "By the dictionary", "As defined")
GUESS = ("My guess for", "I am guessing", "A guess, not a fact", "Probably")
SPLIT = re.compile(r"(?<=[.!?])\s+")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def norm(s):
    from core.reason import symbols
    return " ".join(symbols(str(s), "LN"))


def hit(text, gold, every=False):
    r = norm(text); gs = [g for g in gold if not g.startswith("@")]
    f = all if every else any
    return bool(gs) and f(norm(g) and norm(g) in r for g in gs)


def judge_em(got, gold, every=False):
    if got is None: return ("RIGHT", "abstained") if "@ABSTAIN" in gold else ("SILENT", "")
    ans = got[0]
    if hit(ans, gold, every): return "RIGHT", ""
    return "WRONG", "recall"


def judge_door(reply, gold, every=False, word=None):
    """-> (outcome, sub, answer text judged). A RECALL is judged on its answer only (its bracketed event is evidence, not
    the answer); abstention sentences are dropped before matching (they contain words such as 'no')."""
    sents = [s.strip() for s in SPLIT.split(reply.strip()) if s.strip()]
    rec = [s for s in sents if s.startswith(RECALL)]
    if rec:
        m = re.match(r"^(?:From what you told me:|By your account:|As you told it:)\s*(.*?)\s*\((.*)\)\.?$", rec[-1])
        text, sub = (m.group(1) if m else rec[-1]), "recall"
    else:
        keep = [s for s in sents if not any(a in s for a in ABST) and not s.startswith(READS)]
        text = " ".join(keep); low = text.lower()
        sub = ("guess" if any(text.startswith(g) or (" " + g) in text for g in GUESS) else
               "quote" if ("dictionary" in low or "(wordnet" in low or "(kaikki" in low or text.startswith(QUOTE)) else "fact")
    if "@ABSTAIN" in gold:
        if not text.strip(): return "RIGHT", "abstained", text
        return ("RIGHT", sub, text) if hit(text, gold, every) else ("WRONG", sub, text)
    if not text.strip(): return "SILENT", "", text
    if "@DICT" in gold:          # a definition of the word ASKED about (not of another word of the turn)
        m = re.search(r"what (\S+) is:", text); asked = (word or "").lower()
        ok = sub == "quote" and (m is None or m.group(1).lower() == asked)
        return ("RIGHT", "quote", text) if ok else ("WRONG", sub, text)
    if hit(text, gold, every): return "RIGHT", sub, text
    return "WRONG", sub, text


def asked_word(q):
    m = re.search(r"what does (\w+) mean|what is an? (\w+)", q.lower())
    return (m.group(1) or m.group(2)) if m else None


def rescore():
    """re-judge the stored replies of english_probe_results.json with the current judge (no engine run)"""
    P = json.load(open(PROBES, encoding="utf-8")); res = json.load(open(OUT, encoding="utf-8"))
    qs = {q["id"]: q for q in P["questions"]}
    for r in res["door"] + res["questions"]:
        q = qs.get(r["id"], {})
        r["outcome"], r["sub"], r["judged"] = judge_door(r["reply"], r["gold"], q.get("gold_all", False), asked_word(q.get("q", "")))
        r["held"] = r["outcome"][0] == r["pred"]
    res["rescored"] = time.strftime("%Y-%m-%d %H:%M")
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    write_results(P, res)
    say("rescored; Results section rewritten")


def main():
    if "--rescore" in sys.argv: return rescore()
    P = json.load(open(PROBES, encoding="utf-8"))
    em_only = "--em-only" in sys.argv
    maxd = int(sys.argv[sys.argv.index("--max-door-stories") + 1]) if "--max-door-stories" in sys.argv else 40
    from core.textmodel import TextModel
    import kb_events as KE
    from core.events import EventMemory
    tm = TextModel.load(os.path.join(HERE, "_nldata", "textmodel.json"))
    say("building the event reader (kb_events.build) once ...")
    built = KE.build({w for w, c in tm.uni.most_common(200)}, tm.uni)
    R = built[0]
    say(f"  built in {time.time() - T0:.0f} s; subjects {sorted(getattr(R, 'subjects', []))} markers {sorted(R.to_marker)} "
        f"auxiliaries {sorted(R.auxiliaries)[:20]}")
    KE.build = lambda *a, **k: built          # every door below reuses it (live_door calls KE.build)
    res = dict(engine_commit=os.popen(f'git -C "{HERE}" rev-parse --short HEAD').read().strip(),
               note="engine = working tree at this commit WITH the uncommitted iteration-16 reader changes (core/events.py, "
                    "emergence/kb_events.py) of the parallel loop session",
               em=[], door=[], questions=[])
    # ---- 1. event memory alone, every story
    for s in P["stories"]:
        M = EventMemory(R)
        for sent in SPLIT.split(s["text"]): M.ingest(sent)
        for q in s["qs"]:
            got = M.ask(q["q"]); out, sub = judge_em(got, q["gold"])
            res["em"].append(dict(id=q["id"], phen=q["phen"], q=q["q"], gold=q["gold"], pred=q["pred"], outcome=out, sub=sub,
                                  answer=(got[0] if got else None),
                                  event=(" ".join(str(x) for x in (got[1]["agent"], got[1]["verb"], got[1]["patient"]) if x) if got else None),
                                  held=out[0] == q["pred"]))
    n = len(res["em"]); say(f"event memory: {sum(r['outcome'] == 'RIGHT' for r in res['em'])}/{n} right, "
                            f"predictions held {sum(r['held'] for r in res['em'])}/{n}  ({time.time() - T0:.0f} s)")
    if not em_only:
        import chat as CH

        def door():
            if os.path.exists(STORE): os.remove(STORE)
            return CH.live_door(False, False, STORE, None, 3)
        # ---- 2. live door, the stories marked door=true (a new door per story)
        for s in [s for s in P["stories"] if s["door"]][:maxd]:
            D = door()
            for sent in SPLIT.split(s["text"]): D.turn(sent)
            for q in s["qs"]:
                r = D.turn(q["q"]); out, sub, text = judge_door(r["reply"], q["gold"])
                whole = hit(r["reply"], q["gold"])         # what a whole-reply scorer (battery.hit) would credit
                res["door"].append(dict(id=q["id"], phen=q["phen"], q=q["q"], gold=q["gold"], pred=q["pred_door"], outcome=out, sub=sub,
                                        reply=r["reply"], judged=text, recall=bool(r.get("recall")), whole_reply_hit=whole,
                                        held=out[0] == q["pred_door"]))
            say(f"  door story {s['sid']}: " + ", ".join(f"{x['outcome'][0]}" for x in res["door"][-len(s['qs']):]) + f"  ({time.time() - T0:.0f} s)")
        # ---- 3. question probes, one door
        D = door()
        for q in P["questions"]:
            for t in q["setup"]: D.turn(t)
            r = D.turn(q["q"]); out, sub, text = judge_door(r["reply"], q["gold"], q.get("gold_all", False), asked_word(q.get("q", "")))
            res["questions"].append(dict(id=q["id"], phen=q["phen"], q=q["q"], gold=q["gold"], pred=q["pred"], outcome=out, sub=sub,
                                         reply=r["reply"], judged=text, held=out[0] == q["pred"]))
            say(f"  {q['id']} {out[0]} (pred {q['pred']}) {q['q'][:50]!r} -> {r['reply'][:110]!r}")
    res["time_s"] = round(time.time() - T0)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    write_results(P, res)
    say(f"written {OUT} and the Results section of ENGLISH_MAP.md  ({res['time_s']} s)")


def write_results(P, res):
    ph = {p["id"]: p for p in P["phenomena"]}
    fams = []
    for p in P["phenomena"]:
        if p["family"] not in fams: fams.append(p["family"])
    door_ids = {r["id"] for r in res["door"]}
    live = res["door"] + res["questions"] + [r for r in res["em"] if r["id"] not in door_ids]    # the outcome that counts per probe
    allpred = res["em"] + res["door"] + res["questions"]
    L = []; w = L.append

    def tally(rows):
        c = collections.Counter(r["outcome"] for r in rows); return c["RIGHT"], c["WRONG"], c["SILENT"]

    def acc(rows): return f"{sum(r['held'] for r in rows)}/{len(rows)}" if rows else "--"
    w("## 6. Results (english_probe.py)")
    w("")
    w(f"Run {time.strftime('%Y-%m-%d %H:%M')}, HEAD {res['engine_commit']} (engine code = cdbf193b; the map commit added only its own files) **with the uncommitted iteration-16 reader "
      f"changes** (core/events.py, emergence/kb_events.py) of the parallel loop session; {res.get('time_s', '?')} s. "
      "A probe's counted outcome is the live door's where it ran there, else the event memory's.")
    w("")
    w("| run | probes | RIGHT | WRONG | SILENT | predictions held |")
    w("|---|---|---|---|---|---|")
    for name, rows in (("event memory, all stories", res["em"]), ("live door, door stories", res["door"]),
                       ("live door, question probes", res["questions"]), ("counted (live where run)", live), ("all predictions", allpred)):
        r_, w_, s_ = tally(rows); w(f"| {name} | {len(rows)} | {r_} | {w_} | {s_} | {acc(rows)} |")
    w("")
    conf = collections.Counter((r["pred"], r["outcome"][0]) for r in allpred)
    w("Prediction vs outcome (all runs; rows = predicted, columns = observed):")
    w("")
    w("| predicted | RIGHT | WRONG | SILENT |")
    w("|---|---|---|---|")
    for p_ in "RWS": w(f"| {dict(R='RIGHT', W='WRONG', S='SILENT')[p_]} | {conf[(p_, 'R')]} | {conf[(p_, 'W')]} | {conf[(p_, 'S')]} |")
    w("")
    # per phenomenon
    byp = collections.defaultdict(list)
    for r in live: byp[r["phen"]].append(r)
    bypa = collections.defaultdict(list)
    for r in allpred: bypa[r["phen"]].append(r)
    pri = {}
    for pid, rows in byp.items():
        r_, w_, s_ = tally(rows); n = len(rows)
        wq = sum(1 for r in rows if r["outcome"] == "WRONG" and r.get("sub") in ("quote", "guess"))
        pri[pid] = ph[pid]["freq_value"] * (2 * (w_ - wq) + wq + s_) / n      # an off-target hedged quotation or labelled guess weighs as a silence
    w("### Per family")
    w("")
    w("| family | phenomena | probes | RIGHT | WRONG | SILENT | predictions held | mean frequency | priority (sum) |")
    w("|---|---|---|---|---|---|---|---|---|")
    for f in sorted(fams, key=lambda f: -sum(pri.get(p["id"], 0) for p in P["phenomena"] if p["family"] == f)):
        ids = [p["id"] for p in P["phenomena"] if p["family"] == f]
        rows = [r for i in ids for r in byp.get(i, [])]; rows_a = [r for i in ids for r in bypa.get(i, [])]
        r_, w_, s_ = tally(rows)
        mf = sum(ph[i]["freq_value"] for i in ids) / len(ids)
        w(f"| {f} | {len(ids)} | {len(rows)} | {r_} | {w_} | {s_} | {acc(rows_a)} | {mf:.3f} | {sum(pri.get(i, 0) for i in ids):.3f} |")
    w("")
    w("### Priority ranking (frequency x (2 x wrong share + silent share), counted outcomes)")
    w("")
    w("A WRONG that is an off-target dictionary quotation in a hedged frame (\"If you are asking what X is: ... Otherwise "
      "say wrong\") or a labelled guess weighs 1, like a silence; a WRONG stated as fact or recalled from the story weighs 2.")
    w("")
    w("| rank | phenomenon | family | frequency | probes | R/W/S | priority | component |")
    w("|---|---|---|---|---|---|---|---|")
    for k, (pid, v) in enumerate(sorted(pri.items(), key=lambda x: -x[1])[:30], 1):
        r_, w_, s_ = tally(byp[pid])
        w(f"| {k} | {pid} -- {ph[pid]['name']} | {ph[pid]['family']} | {ph[pid]['freq_value']:.3f} | {len(byp[pid])} | {r_}/{w_}/{s_} | {v:.3f} | {ph[pid]['component']} |")
    w("")
    allw = [r for r in live if r["outcome"] == "WRONG"]
    wrong = [r for r in allw if r.get("sub") not in ("quote", "guess")]
    wq = [r for r in allw if r.get("sub") in ("quote", "guess")]
    w(f"### WRONG outcomes: {len(allw)} counted -- {len(wrong)} stated as fact or recalled (honesty risks, listed), "
      f"{len(wq)} off-target hedged quotations or labelled guesses")
    w("")
    w("Off-target quotations (the door quoted a gloss of some word of the question instead of answering or abstaining): "
      + ", ".join(f"{r['id']}" for r in wq) + ".")
    w("")
    w("| id | phenomenon | question | gold | said | kind |")
    w("|---|---|---|---|---|---|")
    for r in wrong:
        said = r.get("judged") if "judged" in r else f"{r.get('answer')} ({r.get('event')})"
        w(f"| {r['id']} | {r['phen']} | {r['q']} | {', '.join(r['gold'])} | {str(said)[:120].replace('|', '/')} | {r.get('sub', '')} |")
    w("")
    w("Kinds: recall = the story memory's answer; fact = a world's answer stated as fact; quote = an off-target dictionary "
      "quotation; guess = a labelled guess.")
    w("")
    inflated = [r for r in res["door"] if r["whole_reply_hit"] and r["outcome"] != "RIGHT"]
    w(f"**Scoring note:** {len(inflated)} door story replies that are NOT right would be credited by a scorer that searches "
      "the whole reply (battery.hit), because a RECALL reply prints the event in brackets or an abstention contains the gold "
      "word: " + "; ".join(f"{r['id']} {r['q']!r} -> {r['reply'][:80]!r}" for r in inflated[:8]) + ("" if inflated else "none."))
    w("")
    miss = [r for r in allpred if not r["held"]]
    w(f"### Predictions that failed ({len(miss)} of {len(allpred)})")
    w("")
    w("| id | run | phenomenon | question | predicted | observed | what was said |")
    w("|---|---|---|---|---|---|---|")
    runs = {id(r): n for n, rows in (("memory", res["em"]), ("door", res["door"]), ("question", res["questions"])) for r in rows}
    for r in miss:
        said = r.get("reply") or f"{r.get('answer')} ({r.get('event')})"
        w(f"| {r['id']} | {runs[id(r)]} | {r['phen']} | {r['q']} | {dict(R='RIGHT', W='WRONG', S='SILENT')[r['pred']]} | {r['outcome']} | {str(said)[:110].replace('|', '/')} |")
    w("")
    txt = open(MAP, encoding="utf-8").read()
    i = txt.find("## 6. Results")
    txt = (txt[:i] if i >= 0 else txt.rstrip() + "\n\n") + "\n".join(L) + "\n"
    open(MAP, "w", encoding="utf-8").write(txt)


if __name__ == "__main__":
    main()
