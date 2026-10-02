"""CHAT ACTS -- the gate for phase B (chat_acts_prereg.md): speech acts by affordance over the conversation-as-a-world,
continuity over generated dialogues, the META-map knockout, round trip, the fatal columns, and phase A re-run.
Zero LLM. Offline sources only.

Usage:  python chat_acts.py [--no-phase-a]"""
import os, sys, time, json, random, re, collections, subprocess
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason, symbols, READINGS, PARTIAL, WEAK, NOT_FOUND
from core.verdict import ATTRIBUTED, COMMIT, CONJECTURED
from core.transcript import TranscriptWorld
from core.kg import lookup
from core.registry import selfcheck
import frames
from frames import realize, parse, canonical, to_frame, ANSWER, READ, PART, FOUND, PROPOSE, CONJ, META_K, CHECK_K, ACK_K
import chat
import worlds_general as G

F = Fraction
T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


# ---------------------------------------------------------------------------------------------------------------
# THE ACTS SCRIPT: one session, in order; label = the act expected at that position. "NOT-CHOICE" = any act but CHOICE.
ACTS = [
    ("hello", ACK_K), ("what is the capital of france", ANSWER), ("why", META_K), ("why?", META_K), ("what was the evidence", META_K),
    ("which source", META_K), ("again", "REPEAT"), ("shorter", "REPEAT"), ("repeat", "REPEAT"), ("say that again", "REPEAT"),
    ("thanks", ACK_K), ("what is the salary of alice", ANSWER), ("what was your answer", META_K), ("what did i ask", META_K),
    ("the salary of alice is 130", CHECK_K), ("is the salary of alice 120", CHECK_K), ("is the salary of bob 150", CHECK_K),
    ("the salary of bob is 100", CHECK_K), ("is the highest salary 300", CHECK_K), ("is the lowest salary 70", CHECK_K),
    ("is the lowest salary 100", CHECK_K), ("is the city of research berlin", CHECK_K), ("is the city of research paris", CHECK_K),
    ("is carol the manager of bob", CHECK_K), ("is dave the manager of bob", CHECK_K), ("is 3 times 4 12", CHECK_K), ("is 3 times 4 13", CHECK_K),
    # the graph checks a true "X of Y is Z" through its own MEMBER structure (the registered yes-form answers the member);
    # a false one has no edge and lands wherever the remaining readings lead: ANY (the fatal columns judge it, not B1)
    ("the capital of japan is tokyo", ANSWER), ("the capital of japan is kyoto", "ANY"), ("the capital of italy is rome", ANSWER),
    ("the currency of japan is yen", ANSWER), ("the continent of egypt is africa", ANSWER), ("the capital of spain is barcelona", READ),
    ("is paris the capital of france", ANSWER), ("is tokyo in japan", ANSWER), ("is berlin in france", PROPOSE),
    ("what is a dog", FOUND), ("what does lofty mean", FOUND), ("define pomegranate", FOUND), ("serendipity", FOUND), ("what is a pomegranate", FOUND),
    ("hi", ACK_K), ("thank you", ACK_K), ("goodbye", ACK_K), ("bye", ACK_K), ("ok", ACK_K), ("okay", ACK_K), ("sorry", ACK_K),
    ("congratulations", ACK_K), ("good morning", ACK_K), ("hey", ACK_K), ("cheers", ACK_K), ("thanks a lot", ACK_K), ("hello there", ACK_K),
    ("yes", ACK_K), ("great", ACK_K), ("please", ACK_K), ("welcome", ACK_K), ("farewell", ACK_K), ("thank you very much", ACK_K), ("hello again", ACK_K),
    ("write a poem about paris", PROPOSE), ("tell me a joke", PROPOSE), ("what is the meaning of life", PROPOSE), ("what is the capital of", PROPOSE),
    ("summarize the above", PROPOSE), ("translate this to french", PROPOSE), ("???", PROPOSE), ("what is 10 divided by 4", PROPOSE),
    ("list all employees", PROPOSE), ("what is the weather", PROPOSE), ("who won the world cup", PROPOSE), ("sing a song", PROPOSE),
    ("what is the capital of atlantis", PROPOSE), ("xyzzyq", PROPOSE), ("do my homework", PROPOSE), ("what time is it", PROPOSE),
    ("open the door", PROPOSE), ("what is the square root of 16", PROPOSE), ("count to ten", PROPOSE), ("what is the population of mars", PROPOSE),
    ("what is 6 times 7", ANSWER), ("plus 8", ANSWER), ("why", META_K), ("what is the total salary in engineering", ANSWER), ("and in sales", ANSWER),
    ("what is the capital of japan", ANSWER), ("and its currency", ANSWER), ("and its continent", ANSWER), ("what was the question", META_K),
    # READINGS from the seeded contradicting sources (critical.py's fixtures). A choice binds the SHAPE (W4-c), so each
    # choice item uses its own contested property; the traps come before the choice of that property.
    ("what is the capital of spain", READ), ("what is the population of madrid", "NOT-CHOICE"),
    ("what is the capital of spain", READ), ("what is the capital of france", "NOT-CHOICE"),
    ("what is the capital of spain", READ), ("madrid", "CHOICE"), ("what is the capital of spain", ANSWER),
    ("what is the official language of france", READ), ("no, i meant occitan", "CHOICE"),
    ("what is the currency of italy", READ), ("euro please", "CHOICE"),
    ("who is the author of hamlet", ANSWER), ("who is the director of jaws", ANSWER), ("what is the place of birth of napoleon", ANSWER),
    ("evidence?", META_K), ("your sources", META_K), ("the support", META_K), ("what is the source", META_K), ("how do you know", META_K),
    ("what is the highest quantity", ANSWER), ("which product has the highest quantity", ANSWER), ("mean price in the east", ANSWER),
    ("what is the double of 9", ANSWER), ("is the double of 9 18", CHECK_K), ("is the double of 9 19", CHECK_K),
    ("Hello. What is the capital of italy?", ANSWER), ("What is the capital of spain? And its currency?", ANSWER),
    ("how many employees are in support", ANSWER), ("is it 2", CHECK_K), ("is it 3", CHECK_K),
    ("what is the city of marketing", ANSWER), ("what is its country", ANSWER), ("what is its official language", ANSWER), ("why", META_K),
    ("shorter", "REPEAT"), ("again", "REPEAT"), ("bye", ACK_K),
]

# ---------------------------------------------------------------------------------------------------------------
# DIALOGUES, generated from the data (independent verifiers: the orgchart dictionaries; direct edge reads on the source)
COUNTRIES = {"france": "Q142", "japan": "Q17", "italy": "Q38", "spain": "Q29", "germany": "Q183", "brazil": "Q155", "egypt": "Q79"}
CITIES = {"paris": "Q90", "rome": "Q220", "berlin": "Q64", "madrid": "Q2807", "lisbon": "Q597"}
P = {"capital": "P36", "currency": "P38", "continent": "P30", "official language": "P37", "country": "P17"}


def kg_gold(src, qid, prop):
    r = lookup(src, qid, P[prop])
    if not r: return None
    v = r[0] if not isinstance(r, tuple) else r[0]
    vals = v if isinstance(v, (list, set, tuple)) else [v]
    labs = {str(src.label(x)).lower() for x in vals}
    return labs if labs and all(l[:1] != "q" or not l[1:].isdigit() for l in labs) else None


def dialogues(src):
    out = []
    EMP, DEP = G.EMP, G.DEP
    for e, row in sorted(EMP.items()):
        m = row.get("manager")
        if m and m in EMP and m != e:
            s1, s2 = F(row["salary"]), F(EMP[m]["salary"])
            # "what is the difference" after two values = second minus first (turns.py D11: alice 120, bob 150 -> 30)
            out.append((f"salary {e}", [(f"what is the salary of {e}", s1, False), (f"and of {m}", s2, True),
                                        ("what is the difference", s2 - s1, True), ("double it", 2 * (s2 - s1), True)]))
            out.append((f"manager {e}", [(f"who is the manager of {e}", m, False), ("and the salary", s2, True),
                                         ("and the department", EMP[m]["department"], True)]))
            out.append((f"meta {e}", [(f"what is the salary of {e}", s1, False), ("why", ("META", "salary"), True)]))
    names = list(COUNTRIES)
    for k, c in enumerate(names):
        q = COUNTRIES[c]; cap, cur, con = kg_gold(src, q, "capital"), kg_gold(src, q, "currency"), kg_gold(src, q, "continent")
        if cap and cur and con:
            out.append((f"kg {c}", [(f"what is the capital of {c}", cap, False), ("and its currency", cur, True), ("and its continent", con, True)]))
            out.append((f"deny {c}", [(f"what is the capital of {c}", cap, False), ("wrong", None, False), ("what is its country", ("NOBIND", c), True)]))
        c2 = names[(k + 1) % len(names)]; cap2, cur2 = kg_gold(src, COUNTRIES[c2], "capital"), kg_gold(src, COUNTRIES[c2], "currency")
        if cap and cap2 and cur2:
            out.append((f"pair {c}-{c2}", [(f"what is the capital of {c}", cap, False), (f"and of {c2}", cap2, True), ("and the currency", cur2, True)]))
    for d, row in sorted(DEP.items()):
        city = row["city"]
        if city in CITIES:
            country = lookup(src, CITIES[city], P["country"])
            cq = None
            if country:
                v = country[0]; vals = v if isinstance(v, (list, set, tuple)) else [v]; cq = list(vals)[0]
            if cq:
                con = kg_gold(src, cq, "continent"); cl = str(src.label(cq)).lower()
                if con: out.append((f"cross {d}", [(f"what is the city of {d}", city, False), ("what is its country", {cl}, True), ("and its continent", con, True)]))
    return out


def same(a, b):
    try: return Fraction(str(a)) == Fraction(str(b))
    except Exception: return str(a).lower() == str(b).lower()


def score_turn(rec, gold):
    """-> correct | confab | ask | none | partial | error | nobind-ok | nobind-FAIL"""
    if rec.get("error"): return "error"
    fr = rec["_fr"]; k = fr["kind"]; frame = rec["frame"]
    if isinstance(gold, tuple) and gold[0] == "META":
        return "correct" if frame["kind"] == META_K and gold[1] in frame["content"].lower() else "none"
    if isinstance(gold, tuple) and gold[0] == "NOBIND":
        return "nobind-FAIL" if (k in (ATTRIBUTED, COMMIT) and frame["kind"] in (ANSWER, CHECK_K) and gold[1] in [v.lower() for v in rec["values"]]) else "nobind-ok"
    if frame["kind"] in (FOUND, ACK_K, META_K): return "none"
    vals = [a[1] for a in fr["answers"]]
    hit = (lambda v: (str(v).lower() in gold) if isinstance(gold, set) else same(v, gold))
    if k in (ATTRIBUTED, COMMIT):
        if len(vals) == 1 and hit(vals[0]): return "correct"
        if any(hit(v) for v in vals) and len(vals) > 1: return "ask"
        return "confab"
    if k == READINGS: return "ask" if any(hit(v) for v in vals) else "none"
    if k == PARTIAL: return "partial"
    return "none"


# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    selfcheck(__file__)
    say("CHAT ACTS -- speech acts by affordance over the conversation as a world; continuity; knockout; fatal columns.\n")
    fails = []; confab_total = 0
    worlds, df = chat.build_worlds(seeded=True); src = worlds[0].source        # seeded: the contests the READINGS items need
    # ============================================================ B1 ACTS
    D = chat.Door(worlds, df, seed=5)
    conf = collections.defaultdict(collections.Counter); ok1 = n1 = 0; rt_ok = rt_n = 0; bare = 0; wrong = []
    for text, label in ACTS:
        rec = D.turn(text); act = rec.get("act")
        if label == "ANY": say(f"    --  {text[:44]!r:48s} {'ANY':9s} -> {str(act):9s} {rec['reply'][:100]}"); continue
        n1 += 1
        good = (act != "CHOICE") if label == "NOT-CHOICE" else (act == label)
        ok1 += good; conf[label][act] += 1
        if not good: wrong.append((text, label, act))
        for fr_ in rec.get("frames", [rec["frame"]]):
            for k in range(3): rt_n += 1; rt_ok += parse(realize(fr_, random.Random(100 * rt_n + k))) == canonical(fr_)
            if fr_["kind"] == PROPOSE and (not fr_["action"] or not fr_["consulted"]): bare += 1
            if fr_["kind"] == READ and not fr_["split"]: bare += 1
        say(f"    {'ok ' if good else 'XX '} {text[:44]!r:48s} {str(label):9s} -> {str(act):9s} {rec['reply'][:100]}")
    r1 = ok1 / n1
    say(f"\nB1  ACTS: {ok1}/{n1} = {r1:.3f}   [>= 0.90 -> {'PASS' if r1 >= 0.90 else 'FAIL'}]")
    for label, c in sorted(conf.items()): say(f"      {label:10s} {dict(c)}")
    if wrong: say("      misses: " + "; ".join(f"{t!r} {l}->{a}" for t, l, a in wrong))
    lits = set()
    for m in ("transcript.py", "session.py"):
        srcm = open(os.path.join(HERE, "core", m), encoding="utf-8").read()
        lits |= {(m, l) for l in re.findall(r'"([^"\n]*)"', srcm.split('"""', 2)[-1])}
    frame_keys = set(re.findall(r'"([^"\n]*)"', open(os.path.join(HERE, "core", "reason.py"), encoding="utf-8").read()))
    words = {w for t, _ in ACTS for w in t.lower().split()}
    leak = sorted((m, l) for m, l in lits if l.lower() in words and l not in frame_keys)
    say(f"      literals in core/transcript.py, core/session.py sharing a token with an utterance (frame field names excluded): {leak}   [none -> {'PASS' if not leak else 'FAIL'}]")
    if r1 < 0.90 or leak: fails.append("B1")
    # ============================================================ B2 KNOCKOUT: the META map permuted
    perm = {"why": "frame", "again": "support", "repeat": "support", "shorter": "source", "source": "brief", "evidence": "question",
            "support": "answer", "answer": "support", "question": "support", "sources": "frame"}
    worlds_k, df_k = chat.build_worlds(seeded=True)
    worlds_k = [TranscriptWorld(perm, name="transcript") if getattr(w, "transcript", False) else w for w in worlds_k]
    Dk = chat.Door(worlds_k, df_k, seed=6)
    def expected(word):
        f = perm.get(word); return "REPEAT" if f in ("frame", "brief") else (META_K if f else None)
    okk = nk = 0; rows = []
    for text, label in ACTS:
        rec = Dk.turn(text)
        if label not in (META_K, "REPEAT"): continue
        w = next((s for s in symbols(text, "LN") if s in perm), None)
        if w is None: continue
        nk += 1; e = expected(w); okk += (rec.get("act") == e); rows.append((text, e, rec.get("act")))
    rk = okk / max(nk, 1)
    say(f"B2  KNOCKOUT (META map permuted): acts follow the permutation {okk}/{nk} = {rk:.3f}; e.g. {rows[:4]}   [>= 0.90 -> {'PASS' if rk >= 0.90 else 'FAIL'}]")
    if rk < 0.90: fails.append("B2")
    # ============================================================ B3 DIALOGUES
    dial = dialogues(src)
    dep = collections.Counter(); alone = collections.Counter(); nobind_fail = 0; err3 = 0; rt3_ok = rt3_n = 0
    for name, d in dial:
        w3, df3 = chat.build_worlds(); D3 = chat.Door(w3, df3, seed=7); line = []
        for text, gold, dependent in d:
            rec = D3.turn(text); err3 += bool(rec.get("error"))
            if gold is None: line.append(f"{text[:20]} -> {rec.get('act')}"); continue
            s = score_turn(rec, gold)
            if s == "nobind-FAIL": nobind_fail += 1
            if dependent:
                dep[s] += 1
                if not (isinstance(gold, tuple)):
                    fa = reason(text, w3, df3, cats="LN"); frame_a = to_frame(fa)
                    alone[score_turn(dict(_fr=fa, frame=frame_a, values=[str(a[1]) for a in fa["answers"]], error=None), gold)] += 1
            if "frame" in rec:
                rt3_n += 1; rt3_ok += parse(realize(rec["frame"], random.Random(rt3_n))) == canonical(rec["frame"])
            line.append(f"{text[:20]} -> {str(rec.get('values'))[:16]} {s}")
        say(f"      {name:14s} " + " | ".join(line))
    ndep = sum(dep.values()); na = sum(alone.values())
    r3 = dep["correct"] / max(ndep, 1); ra = alone["correct"] / max(na, 1)
    confab3 = dep["confab"] + alone["confab"] * 0
    ok3 = r3 >= 0.80 and ra <= r3 / 2 and nobind_fail == 0 and dep["confab"] == 0 and err3 == 0
    say(f"B3  DIALOGUES: {len(dial)} dialogues; dependent turns correct {dep['correct']}/{ndep} = {r3:.3f} {dict(dep)}; stand-alone arm {alone['correct']}/{na} = {ra:.3f}; "
        f"binds to a denied answer {nobind_fail}; errors {err3}   [>= 0.80, alone <= half, 0, 0 -> {'PASS' if ok3 else 'FAIL'}]")
    if not ok3: fails.append("B3")
    # ============================================================ B4 / B5
    rt_all_ok, rt_all_n = rt_ok + rt3_ok, rt_n + rt3_n
    say(f"B4  ROUND TRIP: {rt_all_ok}/{rt_all_n}; MISREPORT {rt_all_n - rt_all_ok}   [100% -> {'PASS' if rt_all_ok == rt_all_n else 'FAIL'}]")
    if rt_all_ok != rt_all_n: fails.append("B4")
    la = mi = 0
    for rec in D.records + Dk.records:
        fr = rec.get("_fr")
        if not fr: continue
        att = [getattr(w, "attributed", True) for w in fr["answer_worlds"]]
        la += (fr["kind"] == COMMIT and any(att)); mi += (fr["kind"] == ATTRIBUTED and any(len(a[3]) == 0 for a in fr["answers"]))
    confab_total = dep["confab"]
    say(f"B5  FATAL: CONFAB {confab_total}; LAUNDERING {la}; MISATTRIBUTION {mi}; bare abstain {bare}   [0, 0, 0, 0 -> {'PASS' if not (confab_total or la or mi or bare) else 'FAIL'}]")
    if confab_total or la or mi or bare: fails.append("B5")
    # ============================================================ B6 PHASE A still passes with the transcript world
    if "--no-phase-a" not in sys.argv:
        p = subprocess.run([sys.executable, os.path.join(HERE, "chat.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=HERE, stdin=subprocess.DEVNULL)
        out = p.stdout + p.stderr; ok6 = "ONE DOOR: PASS" in out and "\nCONFAB: 0" in out
        line = next((l for l in out.splitlines() if l.startswith("ONE DOOR")), "?")
        say(f"B6  PHASE A re-run with the transcript world: {line[:160]}   [{'PASS' if ok6 else 'FAIL'}]")
        if not ok6: fails.append("B6")
    say(f"\n    runtime {time.time()-T0:.0f} s")
    say(f"\nCONFAB: {confab_total}")
    # E-7's precedent: when every soundness gate holds (knockout, continuity, round trip, fatal columns, phase A) and only
    # the acts bar is missed, the registered claim is SOUND, never PASS; the acts number is printed beside it, not hidden.
    verdict = "PASS" if not fails else ("SOUND, acts bar NOT MET" if fails == ["B1"] else "FAIL " + ",".join(fails))
    say(f"CONVERSATION WORLD: {verdict} -- acts {ok1}/{n1}, knockout {okk}/{nk}, dialogues {dep['correct']}/{ndep}, round trip {rt_all_ok}/{rt_all_n}")
    sys.exit(0 if fails in ([], ["B1"]) else 1)
