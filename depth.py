"""DEPTH -- the gate on composition depth and order across worlds (depth_prereg.md; EMERGENCE_PLAN.md S3). Zero LLM.
Offline: Wikidata from the cache, the dictionary from disk. The main arm is HEAD's core/ loaded from git (turns.py's
loader), so failure-on-main is shown by the same runner.

Usage:  python depth.py [--quick]"""
import os, sys, time, json, subprocess, collections, io, tarfile, tempfile, importlib
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.kg import KGWorld
from core.table import TableWorld, induce_lexicon
from core.exec import ExecWorld
from core.gloss import GlossWorld
from core.session import Session
from core.reason import READINGS, PARTIAL, NOT_FOUND
from core.registry import selfcheck

T0 = time.time()
MAIN = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def main_core():
    """HEAD's core/ as a separate set of modules (turns.py's loader)."""
    tar = subprocess.run(["git", "archive", MAIN, "core"], capture_output=True, cwd=HERE).stdout
    d = tempfile.mkdtemp(prefix="primasieve_main_"); tarfile.open(fileobj=io.BytesIO(tar)).extractall(d)
    saved = {k: v for k, v in sys.modules.items() if k == "core" or k.startswith("core.")}
    for k in saved: del sys.modules[k]
    sys.path.insert(0, d)
    try: mods = {name: importlib.import_module(f"core.{name}") for name in ("table", "kg", "exec", "gloss", "session", "reason")}
    finally:
        sys.path.remove(d)
        for k in [k for k in sys.modules if k == "core" or k.startswith("core.")]: del sys.modules[k]
        sys.modules.update(saved)
    return mods


EXEC_TEACH = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
              ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
              ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]
tw = lambda x: 2 * x + 1; bl = lambda x: 2 * x - 1
EXEC_TEACH += [(f"what is the twiddle of {x}", tw(x)) for x in (3, 5, 7, 10)] + [(f"what is the blorp of {x}", bl(x)) for x in (2, 4, 6, 9)]
KG_TEACH = [("what is the capital of the country of the brandenburg gate", "berlin"), ("what is the continent of the country of the taj mahal", "asia")]
QS = [("what is the salary of alice plus the salary of bob", F(270)), ("what is the salary of alice plus the floor of engineering", F(123)),
      ("what is the total salary of engineering plus the total salary of sales", F(600)), ("what is the salary of the manager of alice minus the salary of alice", F(30)),
      ("what is the double of the salary of the manager of alice", F(300)), ("what is the capital of the country of the city of research", "berlin"),
      ("what is the double of the floor of the department of alice", F(6)), ("what is the twiddle of the salary of alice plus 1", F(242))]
CONTROLS = [("what is the salary of alice plus the salary of nobody", None)]


def build(mods, G, KG, Wikidata, Lexica):
    src = Wikidata(offline=True); df = KG.make_df()
    d = json.load(open(G.DOMAIN, encoding="utf-8"))["collections"]                 # each arm's OWN Table/Records classes
    recs = mods["table"].Records([mods["table"].Table(c["headers"], c["rows"], name) for name, c in d.items()])
    lex, con, order = mods["table"].induce_lexicon(G.records_teaching(), recs)
    ex = mods["exec"].ExecWorld(name="exec"); ex.induce_lexicon(EXEC_TEACH)
    worlds = [mods["kg"].KGWorld(src, df, name="Wikidata"), mods["table"].TableWorld(recs, lex, order, name="records"), ex,
              mods["gloss"].GlossWorld(Lexica(online=False), name="dictionary")]
    return worlds, df


def score(fr, gold, G):
    if gold is None: return "none" if not fr["answers"] or fr["kind"] in (PARTIAL, READINGS, NOT_FOUND) else "confab"
    return G.score(fr, gold)


def main():
    selfcheck(__file__)
    import worlds_general as G, kg_multihop as KG
    from kb_wikidata import Wikidata
    from kb_sources import Lexica
    say(f"S3 COMPOSITION DEPTH AND ORDER (depth_prereg.md); main arm = {MAIN[:8]}\n")
    fails = []; confab = 0
    import core.table, core.kg, core.exec, core.gloss, core.session, core.reason
    new = dict(table=core.table, kg=core.kg, exec=core.exec, gloss=core.gloss, session=core.session, reason=core.reason)
    arms = {"MAIN": main_core(), "NEW": new}
    results = {}
    for arm, mods in arms.items():
        worlds, df = build(mods, G, KG, Wikidata, Lexica)
        S = mods["session"].Session(worlds, df)
        if arm == "NEW":
            for q, g in KG_TEACH: S.teach(q, g, world=worlds[0])
        rows = []; times = []
        for q, g in QS + CONTROLS:
            t = time.time(); fr = mods["reason"].reason(q, worlds, df, cats="LN"); dt = time.time() - t; times.append(dt)     # no context: the loop itself
            rows.append((q, g, fr["kind"], [str(a[1]) for a in fr["answers"]][:4], score(fr, g, G), dt))
        results[arm] = (rows, times, getattr(worlds[0], "nesting", None))
        say(f"{arm}  (graph nesting {results[arm][2]})")
        for q, g, k, v, s, dt in rows: say(f"    {k:10s} {v!s:28s} gold {g!s:8s} {s:8s} {dt:4.1f}s  {q}")
    newrows, newtimes, nest = results["NEW"]; mainrows = results["MAIN"][0]
    c = collections.Counter(s for *_, s, _ in newrows[:len(QS)]); cm = collections.Counter(s for *_, s, _ in mainrows[:len(QS)])
    conf_new = c["confab"] + sum(1 for *_, s, _ in newrows[len(QS):] if s == "confab"); confab += conf_new
    # D1: the eight: 6 correct (the four two-argument, 300, 6), the capital question not a lone wrong COMMIT, twiddle READINGS
    want = {QS[i][0]: "correct" for i in (0, 1, 2, 3, 4, 6)}
    d1 = all(s == want[q] for q, g, k, v, s, dt in newrows if q in want) and newrows[5][4] in ("correct", "ask", "partial") and newrows[7][2] == READINGS and conf_new == 0
    say(f"\nD1  new arm: {dict(c)}; capital-of-the-country -> {newrows[5][2]} {newrows[5][3]}; CONFAB {conf_new}   [{'PASS' if d1 else 'FAIL'}]")
    d2 = cm["confab"] >= 2 and cm["partial"] >= 4
    say(f"D2  main arm: {dict(cm)}   [2 confabulations, 4 PARTIAL -> {'FAILS ON MAIN' if d2 else 'does not discriminate'}]")
    p95 = sorted(newtimes)[int(0.95 * (len(newtimes) - 1))]
    d3 = p95 < 2.0
    say(f"D3  p95 time per question {p95:.2f} s   [< 2 s -> {'PASS' if d3 else 'FAIL'}]")
    ctrl = newrows[len(QS):]
    # the contradicted-nesting control: one first-inner pair -> mixed -> the capital question is not a lone COMMIT
    worlds, df = build(new, G, KG, Wikidata, Lexica); S = core.session.Session(worlds, df)
    S.teach(KG_TEACH[0][0], KG_TEACH[0][1], world=worlds[0])
    S.teach("what is the country of the capital of germany", "berlin", world=worlds[0])          # FIRST-INNER (unnatural): capital(country(germany)) = berlin
    fr = core.session.Session(worlds, df).turn("what is the capital of the country of berlin")
    lone_wrong = fr["kind"] == "attributed" and len(fr["answers"]) == 1 and str(fr["answers"][0][1]).lower() != "berlin"
    d4 = all(s == "none" for *_, s, _ in ctrl) and worlds[0].nesting == "mixed" and fr["kind"] in (READINGS, PARTIAL, "attributed") and not lone_wrong
    say(f"D4  controls: no second argument -> {[k for q, g, k, v, s, dt in ctrl]}; contradicted nesting -> {worlds[0].nesting}, capital of the country of berlin -> {fr['kind']} {[str(a[1]) for a in fr['answers']]}   [{'PASS' if d4 else 'FAIL'}]")
    for n, ok in (("D1", d1), ("D2", d2), ("D3", d3), ("D4", d4)):
        if not ok: fails.append(n)
    say("\nD5  REGISTERED NUMBERS")
    if "--quick" in sys.argv:
        say("    (skipped: --quick)")
        say(f"\nCONFAB: {confab}\nS3 DEPTH (quick, D5 not run): {'ok so far' if not fails and confab == 0 else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s"); return
    needles = {"worlds_general.py": "GENERAL WORLDS: PASS", "turns.py": "TURNS BIND: PASS", "chat.py": "ONE DOOR: PASS", "chat_prose.py": "PROSE FRAMES: PASS",
               "kg_multihop.py": "KG MULTI-HOP: PASS", "critical.py": "W6 CRITICAL THINKING: PASS", "negative.py": "S6 NEGATIVE EVIDENCE: SOUND",
               "persist.py": "S8 PERSISTENCE: PASS", "order.py": "S5 WORD ORDER: PASS", "transfer.py": "S4 TRANSFER: PASS", "tables_numbers.py": "TABLES AND NUMBERS: PASS"}
    d5 = True
    for f, needle in needles.items():
        t = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out and any(x in out for x in ("CONFAB: 0", "CONFAB 0", "TOTAL CONFAB: 0", "MISREPORT 0", "REPEAT 0", "LAUNDERING: 0", "CONFAB (wrong value answered): 0"))
        d5 = d5 and hit; say(f"    {f:20s} {'unchanged' if hit else 'MOVED'}  ({time.time() - t:.0f} s)")
    say(f"D5  [{'PASS' if d5 else 'FAIL'}]")
    if not d5: fails.append("D5")
    say(f"\nCONFAB: {confab}")
    say(f"S3 DEPTH: {'PASS' if not fails and confab == 0 else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
