"""GENERAL RUN -- worlds as data, composition across worlds, the library in the loop, turns, research
(general_prereg.md, gates W1-W5 + G1-G3). Every gate carries the arm that reproduces TODAY'S MAIN (loaded from git
HEAD where the code changed) so that failure-on-main is shown by the same runner. Zero LLM. Offline: Wikidata from
the local cache, WordNet/KAIKKI from disk.

Usage:  python worlds_general.py"""
import os, sys, time, json, random, re, subprocess, types, collections
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason, symbols, READINGS, PARTIAL, WEAK, NOT_FOUND, Composite, _spans, _sym_pos
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

T0 = time.time()
BASELINE = "9ab9ed3"     # main BEFORE general_prereg.md (the commit this work started from): the arms below reproduce it


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


# ---------------------------------------------------------------------------------------------------------------
# the fourth domain: one JSON file. No module in core/ knows it exists.
def load_records(path):
    d = json.load(open(path, encoding="utf-8"))
    return Records([Table(c["headers"], c["rows"], name) for name, c in d["collections"].items()])


DOMAIN = os.path.join(HERE, "worlds", "orgchart.json")
RAW = json.load(open(DOMAIN, encoding="utf-8"))["collections"]
EMP = {r[0]: dict(zip(RAW["employees"]["headers"], r)) for r in RAW["employees"]["rows"]}
DEP = {r[0]: dict(zip(RAW["departments"]["headers"], r)) for r in RAW["departments"]["rows"]}
# an INDEPENDENT verifier for the gold: plain dictionary lookups over the file, not the engine
def emps(dep): return [e for e in EMP.values() if e["department"] == dep]
def F(x): return Fraction(x)


def same(a, b):
    try: return Fraction(str(a)) == Fraction(str(b))
    except Exception: return str(a).lower() == str(b).lower()


def score(fr, gold):
    """-> 'correct' | 'confab' | 'ask' | 'none' | 'partial'"""
    k = fr["kind"]
    if k in (ATTRIBUTED, COMMIT):
        vals = [a[1] for a in fr["answers"]]
        if len(vals) == 1 and same(vals[0], gold): return "correct"
        if any(same(v, gold) for v in vals) and len(vals) > 1: return "ask"      # a set: not a unique wrong answer
        return "confab"
    if k == READINGS: return "ask" if any(same(a[1], gold) for a in fr["answers"]) else "none"
    if k == PARTIAL: return "partial"
    return "none"


def main_table_module():
    """main BEFORE this work (git BASELINE) core/table.py, loaded as a standalone module: the single-table arm."""
    src = subprocess.run(["git", "show", f"{BASELINE}:experiments/primasieve/core/table.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8").stdout
    src = src.replace("from .reason import", "from core.reason import")
    m = types.ModuleType("table_main"); exec(compile(src, "table_main", "exec"), m.__dict__); return m


def main_to_frame():
    """to_frame of main BEFORE this work (git BASELINE f4_dialogue.py): the single-world PROPOSE of W5-a."""
    src = subprocess.run(["git", "show", f"{BASELINE}:experiments/primasieve/f4_dialogue.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8").stdout
    body = src[src.index("def to_frame(fr, world, kind_hint):"):src.index("class DictSources:")]
    ns = dict(ATTRIBUTED=ATTRIBUTED, COMMIT=COMMIT, READINGS=READINGS, PARTIAL=PARTIAL, WEAK=WEAK, NOT_FOUND=NOT_FOUND,
              ANSWER=ANSWER, READ=READ, PART=PART, FOUND=FOUND, PROPOSE=PROPOSE)
    exec(body, ns); return ns["to_frame"]


def records_teaching():
    return [
        ("what is the total salary", sum(F(e["salary"]) for e in EMP.values())),
        ("what is the total salary in sales", sum(F(e["salary"]) for e in emps("sales"))),
        ("what is the average salary in research", sum(F(e["salary"]) for e in emps("research")) / len(emps("research"))),
        ("what is the average start in engineering", sum(F(e["start"]) for e in emps("engineering")) / len(emps("engineering"))),
        ("what is the highest salary in support", max(F(e["salary"]) for e in emps("support"))),
        ("what is the highest floor", max(F(d["floor"]) for d in DEP.values())),
        ("what is the lowest start in sales", min(F(e["start"]) for e in emps("sales"))),
        ("what is the lowest salary in engineering", min(F(e["salary"]) for e in emps("engineering"))),
        ("how many employees are in research", F(len(emps("research")))),
        ("how many employees are in marketing", F(len(emps("marketing")))),
        ("which employee has the highest start in sales", max(emps("sales"), key=lambda e: e["start"])["employee"]),
        ("which department has the lowest floor in rome", "sales"),
        ("difference in salary between research and support", sum(F(e["salary"]) for e in emps("research")) - sum(F(e["salary"]) for e in emps("support"))),
        ("difference in start between engineering and sales", sum(F(e["start"]) for e in emps("engineering")) - sum(F(e["start"]) for e in emps("sales"))),
    ]


def coverage(fr, a, n):
    w = fr["answer_worlds"][fr["answers"].index(a)]
    return _sym_pos(_spans(w, a[4]), n)


if __name__ == "__main__":
    selfcheck(__file__)
    say("GENERAL -- a world is data; composition across worlds; the library in the loop; turns; research everywhere.\n")
    fails = []; confab_total = 0

    # =========================================================== W1: the fourth domain costs zero world code
    say("W1  A WORLD IS DATA -- worlds/orgchart.json (employees -> departments, employees -> employees)")
    recs = load_records(DOMAIN)
    say(f"    collections {list(recs.tables)}; references induced from the data: {dict(recs.refs)}")
    teach = records_teaching()
    lexicon, contested, order = induce_lexicon(teach, recs)
    say(f"    induced lexicon {lexicon} contested {contested} order {order}")
    held = [  # (question, gold, needs references?)
        ("what is the salary of alice", F(120), False),
        ("who is the manager of bob", "carol", False),
        ("what is the total salary in engineering", F(380), False),
        ("what is the average salary in sales", F(110), False),
        ("what is the highest salary in research", F(300), False),
        ("what is the lowest salary", F(70), False),
        ("how many employees are in support", F(2), False),
        ("which employee has the highest salary", "dave", False),
        ("which department has the lowest floor in lisbon", "support", False),
        ("difference in salary between engineering and sales", F(160), False),
        ("what is the start of judy", F(2012), False),
        ("what is the city of research", "berlin", False),
        ("who is the manager of the manager of alice", "carol", True),
        ("what is the city of the department of alice", "paris", True),
        ("what is the floor of the department of erin", F(1), True),
        ("what is the total salary of the department of ken", F(380), True),
        ("what is the salary of the manager of grace", F(130), True),
        ("what is the city of the department of the manager of heidi", "madrid", True),
        ("how many employees are in the department of alice", F(3), True),
        ("what is the average salary of the department of erin", F(110), True),
    ]
    # main arm: HEAD's TableWorld over the employees table alone, its own induced lexicon
    TM = main_table_module()
    emp_t = TM.Table(RAW["employees"]["headers"], RAW["employees"]["rows"])
    lex_m, _, ord_m = TM.induce_lexicon([(q, g) for q, g in teach], emp_t)
    main_world = TM.TableWorld(emp_t, lex_m, ord_m)
    recw = TableWorld(recs, lexicon, order, name="records")
    res_main = collections.Counter(); res_rec = collections.Counter(); ref_main = 0
    for q, g, ref in held:
        sm = score(reason(q, main_world, None, cats="LN"), g); res_main[sm] += 1; ref_main += (ref and sm == "correct")
        fr = reason(q, recw, None, cats="LN"); sr = score(fr, g); res_rec[sr] += 1
        v = fr["answers"][0][1] if fr["answers"] else "-"
        say(f"    {'[ref]' if ref else '     '} {q:62s} -> {fr['kind']:10s} {str(v):12s} gold {str(g):8s} {sr.upper() if sr != 'correct' else 'ok'}")
    n_ref = sum(1 for _, _, r in held if r)
    say(f"W1-a  MAIN ARM (HEAD core/table.py, employees alone): {dict(res_main)}; reference questions correct {ref_main}/{n_ref}   [0 -> {'FAILS ON MAIN' if ref_main == 0 else 'does not discriminate'}]")
    ok1 = res_rec["correct"] >= 18 and res_rec["confab"] == 0
    say(f"W1-b  RECORDS ARM: correct {res_rec['correct']}/{len(held)} confab {res_rec['confab']} ask {res_rec['ask']} partial {res_rec['partial']} none {res_rec['none']}   [>= 18, confab 0 -> {'PASS' if ok1 else 'FAIL'}]")
    core_mods = [f for f in os.listdir(os.path.join(HERE, "core")) if f.endswith(".py")]
    named = [f for f in core_mods if any(k in f for k in ("orgchart", "employee", "department"))]
    ok1c = isinstance(RAW, dict) and not named
    say(f"W1-c  ZERO WORLD CODE: domain = {os.path.relpath(DOMAIN, HERE)} (JSON) + {len(teach)} teaching pairs; core/ modules named after it: {named}   [none -> {'PASS' if ok1c else 'FAIL'}]")
    tn = subprocess.run([sys.executable, "tables_numbers.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
    ok1d = "TABLES AND NUMBERS: PASS -- correct 30/30, CONFAB 0" in tn
    say(f"W1-d  tables_numbers on the same module: {'30/30 CONFAB 0' if ok1d else 'MOVED'}   [{'PASS' if ok1d else 'FAIL'}]")
    confab_total += res_rec["confab"]
    if not (ref_main == 0 and ok1 and ok1c and ok1d): fails.append("W1")

    # =========================================================== the world list (the general engine)
    src = Wikidata(offline=True); df = KG.make_df()
    kgw = KGWorld(src, df, name="Wikidata")
    execw = ExecWorld(name="exec")
    exec_teach = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
                  ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
                  ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]
    tw = lambda x: 2 * x + 1; bl = lambda x: 2 * x - 1
    exec_teach += [(f"what is the twiddle of {x}", tw(x)) for x in (3, 5, 7, 10)] + [(f"what is the blorp of {x}", bl(x)) for x in (2, 4, 6, 9)]
    r = execw.induce_lexicon(exec_teach)
    say(f"\n    exec lexicon {execw.lexicon}; searched {[(w, n) for w, t, n in r['searched']]}; library {len(execw.lib)}")
    glossw = GlossWorld(Lexica(online=False), name="dictionary")
    worlds = [kgw, recw, execw, glossw]

    # =========================================================== W2: composition across worlds
    say("\nW2  COMPOSITION ACROSS WORLDS (records -> Wikidata, records -> exec)")
    cross = [
        ("what is the country of the city of engineering", "france"),
        ("what is the continent of the city of sales", "europe"),
        ("what is the official language of the city of research", "german"),
        ("what is the continent of the country of the city of support", "europe"),
        ("what is the official language of the country of the city of marketing", "spanish"),
        ("what is the total salary of engineering times 2", F(760)),
        ("what is the double of the salary of alice", F(240)),
        ("what is the salary of alice plus 30", F(150)),
        ("what is the country of the city of the department of alice", "france"),
        ("what is the continent of the city of the department of the manager of heidi", "europe"),
    ]
    single = {w.name: 0 for w in worlds}; comp = collections.Counter(); cov_ok = cov_n = 0; both = 0
    for q, g in cross:
        n = len(symbols(q, "LN")); best_single = 0
        for w in worlds:
            fr1 = reason(q, [w], df, cats="LN"); s1 = score(fr1, g); single[w.name] += (s1 == "correct")
            if s1 == "correct": say(f"      (single world {w.name} answers {q!r} alone)")
            for a in fr1["answers"]: best_single = max(best_single, coverage(fr1, a, n))
        fr = reason(q, worlds, df, cats="LN"); s = score(fr, g); comp[s] += 1
        v = fr["answers"][0][1] if fr["answers"] else "-"
        if s == "correct":
            a = fr["answers"][0]; cov_n += 1; cov_ok += (coverage(fr, a, n) > best_single)
            both += isinstance(a[4], Composite) and len({nm for nm in fr["sources"]}) >= 2 and len(a[3]) > 0
        say(f"    {q:78s} -> {fr['kind']:10s} {str(v):10s} gold {str(g):7s} {'ok' if s == 'correct' else s.upper()}  via {'+'.join(fr['sources'])}" + (f"  options {[a[1] for a in fr['answers']]}" if s == 'ask' else ""))
    say(f"W2-a  SINGLE-WORLD ARMS correct: {single}   [all 0 -> {'FAILS ON MAIN' if not any(single.values()) else 'does not discriminate'}]")
    ok2 = comp["correct"] >= 7 and comp["confab"] == 0 and both == comp["correct"]
    say(f"W2-b  COMPOSED: correct {comp['correct']}/{len(cross)} confab {comp['confab']} ask {comp['ask']} partial {comp['partial']} none {comp['none']}; certificates from both worlds {both}/{comp['correct']}   [>= 7, confab 0 -> {'PASS' if ok2 else 'FAIL'}]")
    say(f"W2-c  composite coverage > best single survivor: {cov_ok}/{cov_n}   [{'PASS' if cov_ok == cov_n and cov_n else 'FAIL'}]")
    confab_total += comp["confab"]
    if not (not any(single.values()) and ok2 and cov_ok == cov_n and cov_n): fails.append("W2")

    # =========================================================== W3: the library in the loop
    say("\nW3  THE LIBRARY IS WHAT THE LOOP SEARCHES OVER (twiddle 2x+1, blorp 2x-1, quop = twiddle^3 = 8x+7)")
    qu = lambda x: tw(tw(tw(x)))
    quop_teach = [(f"what is the quop of {x}", qu(x)) for x in (1, 2, 3, 4)]
    arms = {}
    for use_lib in (False, True):
        w = ExecWorld(name="exec"); w.induce_lexicon(exec_teach, use_library=use_lib)
        slept = w.sleep(); r = w.induce_lexicon(quop_teach, use_library=use_lib)
        fr = reason("what is the quop of 5", w, cats="LN")
        arms[use_lib] = (r, fr, slept, w)
        ev = [(wd, n, t is not None) for wd, t, n in r["searched"]]
        say(f"    {'LIBRARY' if use_lib else 'BLIND  '} arm: sleep {slept}; quop search {ev}; 'what is the quop of 5' -> {fr['kind']} {[a[1] for a in fr['answers']]}")
    rb, frb, _, _ = arms[False]; rl, frl, _, wl = arms[True]
    blind_bound = any(t is not None for _, t, _ in rb["searched"])
    say(f"W3-a  BLIND ARM: quop bound {blind_bound}; evaluations {[n for _, _, n in rb['searched']]}; reply {frb['kind']}   [not bound, no value -> {'FAILS ON MAIN' if not blind_bound and frb['kind'] == NOT_FOUND else 'does not discriminate'}]")
    lib_bound = any(t is not None for wd, t, _ in rl["searched"] if wd == "quop")
    ok3b = lib_bound and frl["kind"] == COMMIT and same(frl["answers"][0][1], 47) and any(c[0] == "TEACH" for c in frl["answers"][0][3])
    say(f"W3-b  LIBRARY ARM: quop bound {lib_bound} in {[n for wd, _, n in rl['searched'] if wd == 'quop']} evaluations; reply {frl['kind']} {[a[1] for a in frl['answers']]}; certificates cite teaching {any(c[0] == 'TEACH' for c in frl['answers'][0][3]) if frl['answers'] else False}   [COMMIT 47 -> {'PASS' if ok3b else 'FAIL'}]")
    heldx = [("what is 6 times 7", 42), ("what is 11 plus 12", 23), ("what is 20 minus 8", 12), ("what is the double of 9", 18),
             ("what is the twiddle of 8", 17), ("what is the blorp of 11", 21), ("what is the quop of 2", 23), ("what is the double of 3 times 4", 24),
             ("what is the twiddle of 2 plus 5", 15), ("what is 100 minus 1", 99), ("what is the blorp of the double of 3", 11), ("what is 4 times 25", 100)]
    hx = collections.Counter()
    for q, g in heldx:
        fr = reason(q, wl, cats="LN"); s = score(fr, g); hx[s] += 1
        if s != "correct": say(f"      held-out {q} -> {fr['kind']} {[a[1] for a in fr['answers']]} ({s})")
    # retraction: zap fits 2x+1 on two examples, then a third contradicts -> dropped and re-searched
    wz = ExecWorld(name="exec"); wz.induce_lexicon(exec_teach)          # a background: fillers are impure, zap is pure
    # two examples fit BOTH 2x+1 and x*x+1; the third contradicts whichever the search found first
    r1 = wz.induce_lexicon([("what is the zap of 2", 5), ("what is the zap of 0", 1)])
    t1 = wz.lib.entries.get(wz.lexicon.get("zap")); fr1 = reason("what is the zap of 5", wz, cats="LN")
    found_sq = bool(fr1["answers"]) and same(fr1["answers"][0][1], 26)
    third = ("what is the zap of 5", 11) if found_sq else ("what is the zap of 5", 26)
    r2 = wz.induce_lexicon([third])
    t2 = wz.lib.entries.get(wz.lexicon.get("zap")); frz = reason("what is the zap of 6", wz, cats="LN")
    retracted = t1 is not None and t2 is not None and t1 != t2 and bool(r2["dropped"]) and frz["kind"] == COMMIT and same(frz["answers"][0][1], 13 if found_sq else 37)
    say(f"      retraction: zap first {t1} -> after a contradicting example dropped {r2['dropped']} -> {t2}; zap of 6 -> {[a[1] for a in frz['answers']]}")
    ok3c = hx["confab"] == 0 and retracted
    say(f"W3-c  held-out arithmetic: correct {hx['correct']}/{len(heldx)} confab {hx['confab']} ask {hx['ask']}; retraction shown {retracted}   [confab 0 -> {'PASS' if ok3c else 'FAIL'}]")
    wx = ExecWorld(name="exec"); wx.induce_lexicon([("3x4", 12)]); frx = reason("60x39", wx, cats="LN")
    wn = ExecWorld(name="exec"); frn = reason("60x39", wn, cats="LN"); pn = to_frame(frn)
    ok3d = frx["kind"] == COMMIT and same(frx["answers"][0][1], 2340) and pn["kind"] == PROPOSE and bool(pn["consulted"])
    say(f"W3-d  60x39: with '3x4 -> 12' taught: {frx['kind']} {[a[1] for a in frx['answers']]}; untaught: {pn['kind']} consulted {pn['consulted'][:3]}   [{'PASS' if ok3d else 'FAIL'}]")
    confab_total += hx["confab"]
    if not (not blind_bound and frb["kind"] == NOT_FOUND and ok3b and ok3c and ok3d): fails.append("W3")

    # =========================================================== W4: turns bind
    say("\nW4  TURNS BIND (6 dialogues x 3 turns; turns 2-3 depend on the previous turn)")
    dialogues = [
        [("what is the capital of france", "paris", False), ("what is its country", "france", True), ("and its continent", "europe", True)],
        [("what is the salary of alice", F(120), False), ("and of bob", F(150), True), ("double it", F(300), True)],
        [("what is 3 times 4", F(12), False), ("plus 5", F(17), True), ("times 2", F(34), True)],
        [("what is the capital of japan", "tokyo", False), ("and its currency", "yen", True), ("and its continent", "asia", True)],
        [("what is the city of engineering", "paris", False), ("what is its country", "france", True), ("and its capital", "paris", True)],
        [("what is the twiddle of the blorp of 4", None, False), ("17", F(17), True), ("what is the twiddle of the blorp of 6", F(25), True)],   # 17 = blorp(twiddle(4)): the choice fixes the nesting
    ]
    alone = collections.Counter(); sess = collections.Counter(); rt_ok = rt_n = 0; bare = 0; pref_shown = False
    for d in dialogues:
        S = Session([kgw, recw, execw, glossw], df)
        for text, gold, dep in d:
            fr = S.turn(text); frame = to_frame(fr); rt_n += 1
            for _ in range(3):
                t = realize(frame, random.Random(rt_n)); rt_ok += parse(t) == canonical(frame)
            rt_ok -= 2      # count once per reply (3 samples must all round-trip)
            if frame["kind"] == PROPOSE and (not frame["consulted"] or not frame["action"]): bare += 1
            s = score(fr, gold) if gold is not None else ("ask" if fr["kind"] == READINGS else "none")
            if dep:
                sess[s] += 1
                fa = reason(text, worlds, df, cats="LN"); alone[score(fa, gold)] += 1
            if fr.get("preferred"): pref_shown = True
            v = [a[1] for a in fr["answers"]]
            say(f"    {'  ' if not dep else '->'} {text:44s} {fr['kind']:10s} {str(v)[:40]:40s} {'gold ' + str(gold) if gold is not None else ''} {s if dep else ''}{' (chosen)' if fr.get('chosen') else ''}{' (by preference, no ask)' if fr.get('preferred') else ''}")
    ndep = sum(1 for d in dialogues for _, _, dep in d if dep)
    say(f"W4-a  STAND-ALONE ARM (each dependent turn reasoned alone): {dict(alone)}   [correct 0 -> {'FAILS ON MAIN' if alone['correct'] == 0 else 'does not discriminate'}]")
    ok4b = sess["correct"] >= 10 and sess["confab"] == 0
    say(f"W4-b  SESSION ARM: correct {sess['correct']}/{ndep} confab {sess['confab']} ask {sess['ask']} none {sess['none']}   [>= 10, confab 0 -> {'PASS' if ok4b else 'FAIL'}]")
    say(f"W4-c  a READINGS choice binds the shape; the next same-shaped question is answered without asking: {pref_shown}   [{'PASS' if pref_shown else 'FAIL'}]")
    say(f"W4-d  ROUND TRIP on the session's replies: {rt_ok}/{rt_n}; bare abstain {bare}   [{'PASS' if rt_ok == rt_n and bare == 0 else 'FAIL'}]")
    confab_total += sess["confab"]
    if not (alone["correct"] == 0 and ok4b and pref_shown and rt_ok == rt_n and bare == 0): fails.append("W4")

    # =========================================================== W5: research is the default everywhere
    say("\nW5  RESEARCH IS THE DEFAULT (a miss in one world consults every other)")
    q = "what is the capital of xyzzyq"
    fr_kg = reason(q, kgw, df); old = main_to_frame()(fr_kg, kgw, "kg")
    names_old = [c for c in old["consulted"] if c.startswith("source ")]
    say(f"      main arm (HEAD to_frame, Wikidata alone): {old['kind']} consulted {old['consulted']}")
    fr = reason(q, worlds, df, cats="LN"); new = to_frame(fr)
    names_new = [c for c in new["consulted"] if c.startswith("source ")]
    say(f"      multi-world: {new['kind']} consulted {new['consulted']}; action: {new['action'] if new['kind'] == PROPOSE else '-'}")
    say(f"W5-a  MAIN ARM names {len(names_old)} sources   [0 -> {'FAILS ON MAIN' if not names_old else 'does not discriminate'}]")
    ok5b = new["kind"] == PROPOSE and len(names_new) >= 4
    say(f"W5-b  MULTI-WORLD PROPOSE names {len(names_new)} sources: {names_new}   [>= 4 -> {'PASS' if ok5b else 'FAIL'}]")
    frp = reason("what is a pomegranate", worlds, df, cats="LN"); fp = to_frame(frp)
    ok5c = fp["kind"] == FOUND and any("WORDNET" in s or "KAIKKI" in s for _, s in fp["quotes"])
    say(f"W5-c  'what is a pomegranate' through the same worlds: {fp['kind']} {fp.get('quotes', [])[:1]}   [FOUND with the gloss cited -> {'PASS' if ok5c else 'FAIL'}]")
    prompts = [q for q, _, _ in held] + [q for q, _ in cross] + [q for q, _ in heldx] + [t for d in dialogues for t, _, _ in d]
    bare5 = 0; dist = collections.Counter()
    for p in prompts:
        f5 = to_frame(reason(p, worlds, df, cats="LN")); dist[f5["kind"]] += 1
        if f5["kind"] == PROPOSE and (not f5["consulted"] or not f5["action"]): bare5 += 1
        if f5["kind"] == READ and not f5["split"]: bare5 += 1
    say(f"W5-d  BARE ABSTAIN over {len(prompts)} prompts through the multi-world loop: {bare5}; frames {dict(dist)}   [0 -> {'PASS' if bare5 == 0 else 'FAIL'}]")
    if not (not names_old and ok5b and ok5c and bare5 == 0): fails.append("W5")

    # =========================================================== G: global
    say("\nG   GLOBAL")
    lits = set()
    for m in ("reason.py", "exec.py", "session.py", "induce.py", "gloss.py", "table.py"):
        srcm = open(os.path.join(HERE, "core", m), encoding="utf-8").read()
        lits |= {(m, l) for l in re.findall(r'"([^"\n]*)"', srcm.split('"""', 2)[-1])}
    qwords = {w for p in prompts for w in p.lower().split()}
    leak = sorted((m, l) for m, l in lits if l.lower() in qwords)
    say(f"G2  authored English in core/: string literals sharing a token with any prompt: {leak}   [none -> {'PASS' if not leak else 'FAIL'}]")
    if leak: fails.append("G2")
    dt = time.time() - T0
    say(f"G3  runtime {dt:.0f}s   [< 300 -> {'PASS' if dt < 300 else 'FAIL'}]")
    if dt >= 300: fails.append("G3")
    say(f"\nTOTAL CONFAB: {confab_total}")
    say(f"GENERAL WORLDS: {'PASS' if not fails and confab_total == 0 else 'FAIL ' + ','.join(fails)} -- W1 {res_rec['correct']}/{len(held)}, W2 {comp['correct']}/{len(cross)}, W3 quop blind {'unbound' if not blind_bound else 'bound'} / library {'bound' if lib_bound else 'unbound'}, W4 {sess['correct']}/{ndep}, W5 sources {len(names_new)}")
