"""PERSIST -- the gate on core/store.py: evidence outlives the process (persist_prereg.md; EMERGENCE_PLAN.md S8).
Zero LLM. Offline: Wikidata from the cache, the dictionary from disk. A FRESH PROCESS (this file with --child) builds
untaught worlds, loads the store, and answers; the parent compares.

Usage:  python persist.py            # the gate
        python persist.py --child STORE QUESTIONS OUT   (internal)"""
import os, sys, time, json, subprocess, collections, tempfile, filecmp
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.exec import ExecWorld
from core.table import TableWorld
from core.kg import KGWorld
from core.gloss import GlossWorld
from core.session import Session
from core.ledger import Ledger
from core.store import save, load
from core.registry import selfcheck
from core.reason import READINGS, PARTIAL, NOT_FOUND

T0 = time.time()
OUT = os.path.join(HERE, "_nldata", "persist")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def fresh_worlds():
    """the general worlds, UNTAUGHT: nothing induced, nothing searched."""
    from kb_wikidata import Wikidata
    from kb_sources import Lexica
    import kg_multihop as KG
    import worlds_general as G
    src = Wikidata(offline=True); df = KG.make_df()
    return [KGWorld(src, df, name="Wikidata"), TableWorld(G.load_records(G.DOMAIN), name="records"), ExecWorld(name="exec"),
            GlossWorld(Lexica(online=False), name="dictionary")], df


def val(fr):
    if fr["kind"] in ("commit", "attributed") and len(fr["answers"]) == 1: return str(fr["answers"][0][1])
    return None


def answer_all(worlds, df, questions, dialogues):
    """-> {"single": [(kind, value)], "dialogues": [[(kind, value)]]}: single questions each in a fresh session; each
    dialogue in one session, turn by turn."""
    out = dict(single=[], dialogues=[])
    for q in questions:
        fr = Session(worlds, df).turn(q); out["single"].append([fr["kind"], val(fr)])
    for dlg in dialogues:
        s = Session(worlds, df); out["dialogues"].append([[s.turn(t)["kind"], val(s.turn(t)) if False else None] for t in []])
        row = []
        for t in dlg:
            fr = s.turn(t); row.append([fr["kind"], val(fr)])
        out["dialogues"][-1] = row
    return out


def child(store_path, q_path, out_path):
    worlds, df = fresh_worlds(); S = Session(worlds, df, ledger=Ledger())
    report = load(S, store_path) if store_path != "-" else {"loaded": False}
    qs = json.load(open(q_path, encoding="utf-8"))
    res = answer_all(worlds, df, qs["single"], qs["dialogues"])
    res["report"] = json.loads(json.dumps(report, default=str)); res["ledger"] = S.ledger.snapshot()
    res["exec_lexicon"] = sorted(worlds[2].lexicon); res["exec_library"] = sorted(worlds[2].lib.entries)
    json.dump(res, open(out_path, "w", encoding="utf-8"), default=str)


def run_child(store_path, qs, tag):
    q_path = os.path.join(OUT, f"questions.json"); out_path = os.path.join(OUT, f"child-{tag}.json")
    json.dump(qs, open(q_path, "w", encoding="utf-8"))
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", store_path, q_path, out_path], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace")
    if r.returncode != 0: say(r.stdout[-2000:]); say(r.stderr[-2000:]); raise SystemExit("child failed")
    return json.load(open(out_path, encoding="utf-8"))


def main():
    selfcheck(__file__)
    os.makedirs(OUT, exist_ok=True)
    import worlds_general as G
    import turns as T
    say("S8 PERSISTENCE AND CONSOLIDATION (persist_prereg.md)\n")
    worlds, df = fresh_worlds(); kgw, recw, execw, glossw = worlds
    S = Session(worlds, df, ledger=Ledger())
    # ---- session A: the exec teaching (W3 flow), the records teaching, one denial per world, the dialogues
    exec_teach = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
                  ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
                  ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]
    tw = lambda x: 2 * x + 1; bl = lambda x: 2 * x - 1; qu = lambda x: tw(tw(tw(x)))
    exec_teach += [(f"what is the twiddle of {x}", tw(x)) for x in (3, 5, 7, 10)] + [(f"what is the blorp of {x}", bl(x)) for x in (2, 4, 6, 9)]
    for q, g in exec_teach: S.teach(q, g, world=execw)
    execw.sleep()
    for x in (1, 2, 3, 4): S.teach(f"what is the quop of {x}", qu(x), world=execw)
    for q, g in [("what is the zorb of 0", 0), ("what is the zorb of 2", 6)]: S.teach(q, g, world=execw)
    fr = S.turn("what is the zorb of 3"); zorb_first = val(fr); S.deny("what is the zorb of 3"); zorb_after = val(S.turn("what is the zorb of 3"))
    for q, g in G.records_teaching(): S.teach(q, g, world=recw)
    S.teach("what is the peak salary of marketing", F(95), world=recw)
    recw.deny("what is the peak salary of engineering", F(380)); recw.induce_lexicon([(q, g) for q, g, w in S.teaching if w is recw])
    say(f"  session A: exec lexicon {sorted(execw.lexicon)}, library {len(execw.lib)}; zorb of 3 -> {zorb_first}, denied, then {zorb_after}; records lexicon {sorted(recw.lexicon)}; ledger {S.ledger.snapshot()}")
    heldx = [q for q, _ in [("what is 6 times 7", 42), ("what is 11 plus 12", 23), ("what is 20 minus 8", 12), ("what is the double of 9", 18),
             ("what is the twiddle of 8", 17), ("what is the blorp of 11", 21), ("what is the quop of 2", 23), ("what is the double of 3 times 4", 24),
             ("what is the twiddle of 2 plus 5", 15), ("what is 100 minus 1", 99), ("what is the blorp of the double of 3", 11), ("what is 4 times 25", 100),
             ("what is the quop of 5", 47), ("what is the zorb of 3", None)]]
    heldr = ["what is the total salary in research", "what is the average salary in sales", "what is the highest salary in engineering",
             "what is the lowest salary in support", "how many employees are in engineering", "which employee has the highest salary in research",
             "difference in salary between engineering and sales", "what is the salary of alice", "what is the city of sales", "what is the peak salary of research"]
    dialogues = [[t for t, g, d in turns] for name, turns in T.DIALOGUES]
    qs = dict(single=heldx + heldr, dialogues=dialogues)
    gold = answer_all(worlds, df, qs["single"], qs["dialogues"])          # session A's own post-teaching answers
    store1 = os.path.join(OUT, "store1.json"); rep = save(S, store1)
    say(f"  saved {store1} ({os.path.getsize(store1)} bytes); consolidation {rep}")

    # ---- P1 round trip in a fresh process
    say("\nP1  ROUND TRIP (fresh process loads the store)")
    c = run_child(store1, qs, "p1")
    same_single = sum(1 for a, b in zip(gold["single"], c["single"]) if a == b); n_single = len(qs["single"])
    same_dlg = sum(1 for a, b in zip(gold["dialogues"], c["dialogues"]) for x, y in zip(a, b) if x == y); n_dlg = sum(len(d) for d in dialogues)
    for (a, b, q) in zip(gold["single"], c["single"], qs["single"]):
        if a != b: say(f"    DIFF {q!r}: session A {a} vs loaded {b}")
    rpt = c["report"]["exec"]
    say(f"    load report exec: kept {rpt['kept']} dropped {rpt['dropped']} searched {rpt['searched']} pruned {rpt['pruned']} library {rpt['library']}; records bound {c['report']['records']['bound']}")
    confab = sum(1 for a, b in zip(gold["single"], c["single"]) if b[1] is not None and a[1] is not None and a != b)
    ok1 = same_single == n_single and same_dlg == n_dlg and not rpt["searched"] and confab == 0
    say(f"P1  identical answers: single {same_single}/{n_single}, dialogue turns {same_dlg}/{n_dlg}; re-searched words {len(rpt['searched'])}; CONFAB {confab}   [{'PASS' if ok1 else 'FAIL'}]")

    # ---- P2 verify, do not trust
    say("\nP2  VERIFY, DO NOT TRUST")
    data = json.load(open(store1, encoding="utf-8"))
    lib = data["worlds"]["exec"]["library"]
    tw_lid = execw.lexicon.get("twiddle"); idx = next(i for i, e in enumerate(lib) if e[0] == tw_lid)
    bad = json.loads(json.dumps(data)); bad["worlds"]["exec"]["library"][idx][1] = ["d99a935c64", "x", 2]       # x + 2: wrong for twiddle's examples
    store_bad = os.path.join(OUT, "store_bad.json"); json.dump(bad, open(store_bad, "w", encoding="utf-8"), sort_keys=True, indent=1)
    cb = run_child(store_bad, qs, "p2a"); rb = cb["report"]["exec"]
    same_b = sum(1 for a, b in zip(gold["single"], cb["single"]) if a == b)
    ok2a = tw_lid in rb["dropped"] and any(w == "twiddle" for w, n in rb["searched"]) and same_b == n_single
    say(f"    tampered tree: dropped {rb['dropped']}, re-searched {rb['searched']}, answers identical {same_b}/{n_single}   [{'PASS' if ok2a else 'FAIL'}]")
    cut = json.loads(json.dumps(data)); cut["worlds"]["exec"]["pairs"] = [p for p in cut["worlds"]["exec"]["pairs"] if "quop" not in p[0]]
    cut["session"]["teaching"] = [t for t in cut["session"]["teaching"] if "quop" not in t[0]]
    store_cut = os.path.join(OUT, "store_cut.json"); json.dump(cut, open(store_cut, "w", encoding="utf-8"), sort_keys=True, indent=1)
    cc = run_child(store_cut, qs, "p2b"); qi = qs["single"].index("what is the quop of 5")
    ok2b = "quop" not in cc["exec_lexicon"] and cc["single"][qi][0] != "commit"           # a dictionary gloss of the word may stand; no computed value may
    say(f"    teaching pair deleted: quop bound {'quop' in cc['exec_lexicon']}; 'what is the quop of 5' -> {cc['single'][qi]}   [{'PASS' if ok2b else 'FAIL'}]")
    ok2 = ok2a and ok2b
    say(f"P2  [{'PASS' if ok2 else 'FAIL'}]")

    # ---- P3 consolidation: idempotence and three sessions
    say("\nP3  CONSOLIDATION")
    w2, df2 = fresh_worlds(); S2 = Session(w2, df2, ledger=Ledger()); load(S2, store1)
    store2 = os.path.join(OUT, "store2.json"); save(S2, store2)
    ident = filecmp.cmp(store1, store2, shallow=False)
    say(f"    save -> load -> save: byte-identical {ident} ({os.path.getsize(store1)} vs {os.path.getsize(store2)} bytes)")
    # three sessions, each adding teaching
    chunks = [exec_teach[:10], exec_teach[10:], [(f"what is the quop of {x}", qu(x)) for x in (1, 2, 3, 4)]]
    path = None
    for k, chunk in enumerate(chunks):
        wk, dfk = fresh_worlds(); Sk = Session(wk, dfk, ledger=Ledger())
        if path: load(Sk, path)
        for q, g in chunk: Sk.teach(q, g, world=wk[2])
        path = os.path.join(OUT, f"multi{k}.json"); repk = save(Sk, path)
        say(f"    session {k + 1}: +{len(chunk)} pairs -> library {len(wk[2].lib)}, lexicon {sorted(wk[2].lexicon)}, consolidation {repk.get('exec')}")
    wu, dfu = fresh_worlds(); Su = Session(wu, dfu, ledger=Ledger())
    for q, g in exec_teach + chunks[2]: Su.teach(q, g, world=wu[2])
    union = os.path.join(OUT, "union.json"); save(Su, union)
    same_bytes = filecmp.cmp(path, union, shallow=False)
    wf, dff = fresh_worlds(); Sf = Session(wf, dff, ledger=Ledger()); rf = load(Sf, path)
    quop_ok = val(Session(wf, dff).turn("what is the quop of 5")) == "47"
    say(f"    three sessions vs one session taught the union: byte-identical {same_bytes} ({os.path.getsize(path)} vs {os.path.getsize(union)} bytes); loaded: pruned {rf['exec']['pruned']}, quop of 5 -> 47: {quop_ok}")
    ok3 = ident and same_bytes and rf["exec"]["pruned"] == 0 and quop_ok
    say(f"P3  [{'PASS' if ok3 else 'FAIL'}]")

    # ---- P4 the record persists
    say("\nP4  THE RECORD PERSISTS")
    led_same = c["ledger"] == {k: list(v) for k, v in S.ledger.snapshot().items()} or c["ledger"] == S.ledger.snapshot()
    zi = qs["single"].index("what is the zorb of 3")
    ok4 = led_same and c["single"][zi][1] != zorb_first and c["single"][zi] == gold["single"][zi]
    say(f"    ledger after load {c['ledger']} == session A {S.ledger.snapshot()}: {led_same}; zorb of 3 after load -> {c['single'][zi]} (denied value {zorb_first}, session A after denial {zorb_after})   [{'PASS' if ok4 else 'FAIL'}]")

    # ---- P5 knockout: no store
    say("\nP5  KNOCKOUT (fresh process, no store)")
    c0 = run_child("-", qs, "p5")
    taught = [i for i, q in enumerate(qs["single"]) if any(w in q for w in ("twiddle", "blorp", "quop", "total", "average", "highest", "lowest", "how many", "difference"))]
    forgotten = sum(1 for i in taught if c0["single"][i][0] != "commit")
    say(f"    taught words without the store: {forgotten}/{len(taught)} computed nothing (a dictionary gloss of the word is not a value)   [{'FAILS ON MAIN' if forgotten == len(taught) else 'does not discriminate'}]")
    ok5 = forgotten == len(taught)

    # ---- P6 registered numbers
    say("\nP6  REGISTERED NUMBERS")
    needles = {"tables_numbers.py": "TABLES AND NUMBERS: PASS -- correct 30/30, CONFAB 0", "worlds_general.py": "GENERAL WORLDS: PASS",
               "turns.py": "TURNS BIND: PASS", "chat.py": "ONE DOOR: PASS"}
    ok6 = True
    for f, needle in needles.items():
        t = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out and ("CONFAB: 0" in out or "CONFAB 0" in out or "TOTAL CONFAB: 0" in out)
        ok6 = ok6 and hit; say(f"    {f:20s} {'unchanged' if hit else 'MOVED'}  ({time.time() - t:.0f} s)")
    say(f"P6  [{'PASS' if ok6 else 'FAIL'}]")

    fails = [n for n, ok in (("P1", ok1), ("P2", ok2), ("P3", ok3), ("P4", ok4), ("P5", ok5), ("P6", ok6)) if not ok]
    say(f"\nCONFAB: {confab}")
    say(f"S8 PERSISTENCE: {'PASS' if not fails and confab == 0 else 'FAIL ' + ','.join(fails)} -- round trip {same_single}/{n_single} + {same_dlg}/{n_dlg}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    if "--child" in sys.argv:
        i = sys.argv.index("--child"); child(sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3])
    else:
        main()
