"""TURNS BIND OVER LONGER DIALOGUES -- the gate (turns_prereg.md). Zero LLM. Offline: Wikidata from the local cache,
WordNet/KAIKKI from disk. The worlds are exactly worlds_general.py's; the main arm (T-a) runs main's core/ loaded from
git so failure-on-main is shown by the same runner.

Usage:  python turns.py [--no-main]"""
import os, sys, time, json, random, re, subprocess, tarfile, io, tempfile, importlib, collections
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason, symbols, READINGS, PARTIAL, WEAK, NOT_FOUND
from core.verdict import ATTRIBUTED, COMMIT
from core.table import Table, Records, TableWorld, induce_lexicon
from core.kg import KGWorld
from core.exec import ExecWorld
from core.gloss import GlossWorld
from core.session import Session
from core.registry import selfcheck
from frames import realize, parse, canonical, to_frame, ANSWER, READ, PART, FOUND, PROPOSE
from kb_wikidata import Wikidata
from kb_sources import Lexica
import kg_multihop as KG
import worlds_general as G

MAIN = "fe0f26f2"        # main BEFORE turns_prereg.md: the T-a arm reproduces it
F = Fraction


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


# ---------------------------------------------------------------------------------------------------------------
DIALOGUES = [                                                   # (text, gold, dependent)
    ("D1 recency", [("what is the capital of france", "paris", False), ("what is the capital of japan", "tokyo", False),
                    ("what is its country", "japan", True), ("and its currency", "yen", True), ("and its continent", "asia", True)]),
    ("D2 ellipsis", [("what is the capital of italy", "rome", False), ("and the official language", "italian", True),
                     ("and the continent", "europe", True), ("and of spain", "europe", True), ("and the capital", "madrid", True)]),
    ("D3 cross-world", [("what is the city of sales", "rome", False), ("what is its country", "italy", True),
                        ("what is its official language", "italian", True), ("how many employees are in sales", F(2), False), ("double it", F(4), True)]),
    ("D5 arithmetic", [("what is 3 times 4", F(12), False), ("plus 5", F(17), True), ("times 2", F(34), True), ("minus 4", F(30), True),
                       ("what is the double of it", F(60), True), ("5 minus it", F(-55), True)]),
    ("D7 depth", [("what is the capital of france", "paris", False), ("what is 2 plus 2", F(4), False), ("times 3", F(12), True),
                  ("what is its country", "france", True)]),
    ("D11 difference", [("what is the salary of alice", F(120), False), ("and of bob", F(150), True), ("what is the difference", F(30), True)]),
    ("D12 person", [("who is the manager of alice", "bob", False), ("what is his salary", F(150), True), ("and his manager", "carol", True),
                    ("what is her department", "research", True)]),
]
CONTROLS = [
    ("C1 no antecedent", [("what is its currency", None), ("and its capital", None)]),
    ("C2 wrong kind (number)", [("what is 3 times 4", F(12)), ("what is its capital", None)]),
    ("C2 wrong kind (salary)", [("what is the salary of alice", F(120)), ("what is its continent", None)]),
]


def build_worlds(core_mod=None):
    """the four worlds of worlds_general.py. With `core_mod` (a dict of main's core modules) the main arm's classes."""
    C = core_mod or dict(table=sys.modules["core.table"], kg=sys.modules["core.kg"], exec=sys.modules["core.exec"],
                         gloss=sys.modules["core.gloss"], session=sys.modules["core.session"])
    recs = C["table"].Records([C["table"].Table(c["headers"], c["rows"], name) for name, c in G.RAW.items()])
    lexicon, contested, order = C["table"].induce_lexicon(G.records_teaching(), recs)
    recw = C["table"].TableWorld(recs, lexicon, order, name="records")
    src = Wikidata(offline=True); df = KG.make_df()
    kgw = C["kg"].KGWorld(src, df, name="Wikidata")
    execw = C["exec"].ExecWorld(name="exec")
    exec_teach = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
                  ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
                  ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]
    tw = lambda x: 2 * x + 1; bl = lambda x: 2 * x - 1
    exec_teach += [(f"what is the twiddle of {x}", tw(x)) for x in (3, 5, 7, 10)] + [(f"what is the blorp of {x}", bl(x)) for x in (2, 4, 6, 9)]
    execw.induce_lexicon(exec_teach)
    glossw = C["gloss"].GlossWorld(Lexica(online=False), name="dictionary")
    return [kgw, recw, execw, glossw], df, C["session"].Session


def main_core():
    """main's core/ package (git MAIN) as a separate set of modules, so both arms run in one process."""
    tar = subprocess.run(["git", "archive", MAIN, "core"], capture_output=True, cwd=HERE).stdout
    d = tempfile.mkdtemp(prefix="primasieve_main_"); tarfile.open(fileobj=io.BytesIO(tar)).extractall(d)
    saved = {k: v for k, v in sys.modules.items() if k == "core" or k.startswith("core.")}
    for k in saved: del sys.modules[k]
    sys.path.insert(0, d)
    try:
        mods = {name: importlib.import_module(f"core.{name}") for name in ("table", "kg", "exec", "gloss", "session", "reason")}
    finally:
        sys.path.remove(d)
        for k in [k for k in sys.modules if k == "core" or k.startswith("core.")]: del sys.modules[k]
        sys.modules.update(saved)
    return mods


def run_dialogue(SessionCls, worlds, df, turns, depth=3, score=True):
    """-> [(text, frame, seconds, verdict)] with verdict from worlds_general.score ('correct'|'confab'|'ask'|'none'|'partial'|'crash')"""
    S = SessionCls(worlds, df, depth=depth) if depth != 3 else SessionCls(worlds, df)
    out = []
    for text, gold, *_ in turns:
        t = time.time()
        try:
            fr = S.turn(text); v = G.score(fr, gold) if gold is not None else None
        except Exception as e:
            fr = dict(kind="CRASH", answers=[], error=repr(e)); v = "crash"
        out.append((text, fr, time.time() - t, v))
        if v == "crash": break
    return out


def vals(fr): return [a[1] for a in fr.get("answers", [])]


if __name__ == "__main__":
    selfcheck(__file__)
    say("TURNS -- longer dialogues: competing antecedents, ellipsis of either argument, cross-world chains, controls, knockout.\n")
    worlds, df, SessionCls = build_worlds()
    fails = []; confab_total = 0

    # ========================================================================= T-b / T-c / T-f / T-g: the session arm
    say("T-b  SESSION ARM (-> marks a turn that depends on a previous one)")
    dep = collections.Counter(); alone_frames = collections.Counter(); all_confab = 0; rt_ok = rt_n = 0; bare = 0; alone = collections.Counter(); slowest = (0.0, ""); t_sess = 0.0
    ndep = sum(1 for _, d in DIALOGUES for _, _, x in d if x)
    for name, d in DIALOGUES:
        say(f"  {name}")
        res = run_dialogue(SessionCls, worlds, df, d)
        for (text, gold, is_dep), (_, fr, secs, v) in zip(d, res):
            t_sess += secs; slowest = max(slowest, (secs, text))
            if v == "confab" or v == "crash": all_confab += 1
            if is_dep:
                dep[v] += 1
                fa = reason(text, worlds, df, cats="LN"); alone[G.score(fa, gold)] += 1          # T-c: the same turn alone
                alone_frames[to_frame(fa)["kind"]] += 1
            if fr.get("kind") != "CRASH":
                frame = to_frame(fr); rt_n += 1; ok = 0
                for s in range(3):
                    t = realize(frame, random.Random(rt_n * 10 + s)); ok += parse(t) == canonical(frame)
                rt_ok += (ok == 3)
                if frame["kind"] == PROPOSE and (not frame["consulted"] or not frame["action"]): bare += 1
            say(f"    {'->' if is_dep else '  '} {text:36s} {str(fr.get('kind')):10s} {str(vals(fr))[:34]:34s} gold {str(gold):9s} {v:8s} {secs:5.1f}s")
    ok_b = dep["correct"] >= 20 and all_confab == 0
    say(f"T-b  dependent turns: correct {dep['correct']}/{ndep} confab {dep['confab']} ask {dep['ask']} none {dep['none']} partial {dep['partial']} crash {dep['crash']}; "
        f"CONFAB over all 29 turns: {all_confab}   [>= 20/22, confab 0 -> {'PASS' if ok_b else 'FAIL'}]")
    ok_c = alone["correct"] == 0
    say(f"T-c  STAND-ALONE ARM (each dependent turn reasoned alone): {dict(alone)}; reply frames {dict(alone_frames)} "
        f"(a 'confab' here is the dictionary quoting the property word, a FOUND frame, never a value)   [correct 0 -> {'PASS' if ok_c else 'FAIL'}]")
    confab_total += all_confab
    if not ok_b: fails.append("T-b")
    if not ok_c: fails.append("T-c")

    # ========================================================================= T-d: controls
    say("\nT-d  CONTROLS (no antecedent; an antecedent of the wrong kind): no ANSWER frame may appear")
    ctrl_answers = 0; ctrl_kinds = collections.Counter()
    for name, d in CONTROLS:
        res = run_dialogue(SessionCls, worlds, df, d)
        for (text, gold), (_, fr, secs, v) in zip(d, res):
            t_sess += secs
            frame = to_frame(fr) if fr.get("kind") != "CRASH" else dict(kind="CRASH")
            if gold is None:
                ctrl_kinds[frame["kind"]] += 1
                if frame["kind"] == ANSWER or v == "crash": ctrl_answers += 1
            say(f"    {name:26s} {text:28s} {str(fr.get('kind')):10s} frame {frame['kind']:8s} {str(vals(fr))[:40]:40s} {'(control)' if gold is None else ''}")
    ok_d = ctrl_answers == 0
    say(f"T-d  control turns answered with a value: {ctrl_answers}; reply frames {dict(ctrl_kinds)}   [0 -> {'PASS' if ok_d else 'FAIL'}]")
    if not ok_d: fails.append("T-d")

    # ========================================================================= T-e: depth knockout
    say("\nT-e  DEPTH KNOCKOUT (D7: the antecedent is three turns back)")
    d7 = dict(DIALOGUES)["D7 depth"]
    r1 = run_dialogue(SessionCls, worlds, df, d7, depth=1); r3 = run_dialogue(SessionCls, worlds, df, d7, depth=3)
    v1, v3 = r1[-1][3], r3[-1][3]
    say(f"    depth 1: {d7[-1][0]!r} -> {r1[-1][1].get('kind')} {vals(r1[-1][1])} ({v1});   depth 3: {r3[-1][1].get('kind')} {vals(r3[-1][1])} ({v3})")
    ok_e = v1 != "correct" and v1 != "confab" and v3 == "correct"
    say(f"T-e  memory load-bearing: depth 1 loses it without confabulating, depth 3 answers   [{'PASS' if ok_e else 'FAIL'}]")
    if not ok_e: fails.append("T-e")

    # ========================================================================= T-f / T-g
    ok_f = rt_ok == rt_n and bare == 0
    say(f"\nT-f  ROUND TRIP on every session reply (3 realizations each): {rt_ok}/{rt_n}; bare abstain {bare}   [{'PASS' if ok_f else 'FAIL'}]")
    ok_g = t_sess < 120
    say(f"T-g  RUNTIME session arm + controls: {t_sess:.1f} s; slowest turn {slowest[0]:.1f} s ({slowest[1]!r})   [< 120 s -> {'PASS' if ok_g else 'FAIL'}]")
    if not ok_f: fails.append("T-f")
    if not ok_g: fails.append("T-g")

    # ========================================================================= T-a: fails on main
    if "--no-main" not in sys.argv:
        say(f"\nT-a  MAIN ARM (core/ of {MAIN}, loaded from git) on D1, D11 and D5 up to 'times 2'")
        try:
            mc = main_core(); mworlds, mdf, MSession = build_worlds(mc)
            m_confab = m_crash = 0; m_times2 = None
            subset = [("D1 recency", dict(DIALOGUES)["D1 recency"]), ("D11 difference", dict(DIALOGUES)["D11 difference"]),
                      ("D5 arithmetic", dict(DIALOGUES)["D5 arithmetic"][:3])]
            for name, d in subset:
                res = run_dialogue(MSession, mworlds, mdf, d)
                for (text, gold, is_dep), (_, fr, secs, v) in zip(d, res):
                    m_confab += (v == "confab"); m_crash += (v == "crash")
                    if text == "times 2": m_times2 = secs
                    say(f"    {name:16s} {text:34s} {str(fr.get('kind')):10s} {str(vals(fr))[:30]:30s} gold {str(gold):8s} {v:8s} {secs:6.1f}s{'  ' + fr.get('error', '') if v == 'crash' else ''}")
            s_times2 = next(secs for name, d in DIALOGUES if name == "D5 arithmetic" for (text, *_), secs in
                            zip(d, [x[2] for x in run_dialogue(SessionCls, worlds, df, d[:3])]) if text == "times 2")
            ratio = (m_times2 / s_times2) if (m_times2 and s_times2 > 0) else float("inf")
            ok_a = m_confab >= 1 and m_crash >= 1 and ratio >= 5
            say(f"T-a  main: confab {m_confab}, crash {m_crash}, 'times 2' {m_times2:.1f} s vs session arm {s_times2:.1f} s ({ratio:.1f}x)   [>= 1, >= 1, >= 5x -> {'FAILS ON MAIN' if ok_a else 'does not discriminate'}]")
        except Exception as e:
            ok_a = False; say(f"T-a  main arm could not run: {e!r}")
        if not ok_a: fails.append("T-a")

    # ========================================================================= T-h: hygiene
    say("\nT-h  HYGIENE")
    st = subprocess.run([sys.executable, "core_selftest.py", "--map-only"], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
    islands = re.search(r"-> islands: (\d+)", st); worldgate = re.search(r"world imports in core/ or kb_\*/wn_\*: (\d+)", st)
    ok_h = islands and islands.group(1) == "0" and worldgate and worldgate.group(1) == "0"
    say(f"    core_selftest --map-only: islands {islands.group(1) if islands else '?'}, world imports in mechanisms {worldgate.group(1) if worldgate else '?'}   [{'PASS' if ok_h else 'FAIL'}]")
    if not ok_h: fails.append("T-h")

    say(f"\nTURNS BIND: {'PASS' if not fails and confab_total == 0 else 'FAIL ' + ','.join(fails)} -- dependent {dep['correct']}/{ndep}, controls answered {ctrl_answers}, round trip {rt_ok}/{rt_n}, {t_sess:.0f} s")
    say(f"CONFAB: {confab_total}")
