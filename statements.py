"""C4 -- FACT-CHECKING STATEMENTS BY READING THEM (statements_prereg.md). Zero LLM. Offline.

Usage:  python statements.py [--quick]"""
import os, sys, json, time, hashlib, sqlite3, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.textmodel import TextModel
from core.constructions import FORWARD
from core.registry import selfcheck
from textmodel import MODEL, KAIKKI, held
import kb_constructions as KC

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def main():
    selfcheck(__file__)
    say("C4  FACT-CHECKING STATEMENTS BY READING THEM (statements_prereg.md)\n")
    store = KC.Store(); tm = TextModel.load(MODEL); common = {w for w, c in tm.uni.most_common(1000)}
    C = KC.learn(store, common, held=held)
    say(f"    constructions learned on the training headwords: {len(C.admitted)}  ({time.time() - T0:.0f} s)")
    R = KC.Reader(store, C, common)
    by_type = collections.defaultdict(list)
    for q, cl in store.claims.items():
        for t in sorted(cl.get("P31", ()))[:1]:
            if q in store.lab: by_type[t].append(q)
    db = sqlite3.connect(KAIKKI); true = []
    for w, v in db.execute("select w, v from e"):
        if not held(w): continue
        e = json.loads(v); head = store.index.get(" ".join(symbols(w, "LN"))); defs = [str(x) for x in e.get("defs", [])]
        for s in defs + [str(x) for x in e.get("ex", [])]:
            h = head if s in defs else None
            verdict, res = R.check(s, h)
            sup = [pr for pr, vv in res if vv == "SUPPORTED"]
            if sup: true.append((s, h, sup[0], verdict))
        if len(true) >= 2000: break
    say(f"    TRUE statements (held-out sentences with a supported proposition): {len(true)}  ({time.time() - T0:.0f} s)")
    f1n = sum(1 for s, h, pr, v in true if v == "SUPPORTED")
    # ---- corrupted: the object mention replaced by a same-type entity the store does not relate to the subject that way
    corrupted = []
    for s, h, pr, v in true:
        p, d = store.canon(*pr["lab"]); qa, qb = pr["pairs"][0]
        obj_m = pr["b"] if d == FORWARD else pr["a"]; subj = qa if d == FORWARD else qb; obj = qb if d == FORWARD else qa
        if obj_m[0] == obj_m[1]: continue                                   # the object is the headword: no text to replace
        ts = sorted(store.claims.get(obj, {}).get("P31", ()))[:1]
        if not ts: continue
        cands = [x for x in by_type[ts[0]] if x != obj and not store.holds({subj}, {x}, p, FORWARD) and " " not in store.lab[x][:0]]
        if not cands: continue
        k = int(hashlib.sha256(s.encode()).hexdigest(), 16) % len(cands); new = cands[k]
        syms, ms, (full, pos) = KC.tokens(s, store, common)
        lo, hi = pos[obj_m[0]], pos[obj_m[1] - 1] + 1
        text = " ".join(full[:lo] + symbols(store.lab[new], "LN") + full[hi:])
        corrupted.append((text, h, s))
    cv = collections.Counter(); ex = []
    for text, h, orig in corrupted:
        verdict, res = R.check(text, h); cv[verdict] += 1
        if len(ex) < 6: ex.append(f"      {orig[:60]!r} -> {text[:60]!r}: {verdict}")
    for x in ex: say(x)
    n = max(1, len(corrupted))
    fails = []
    f1 = f1n >= 0.8 * max(1, len(true))
    say(f"F1  true statements SUPPORTED: {f1n}/{len(true)}   [>= 80 % -> {'PASS' if f1 else 'FAIL'}]")
    f2 = cv["SUPPORTED"] <= 0.01 * n
    say(f"F2  corrupted statements SUPPORTED: {cv['SUPPORTED']}/{len(corrupted)}   [<= 1 % -> {'PASS' if f2 else 'FAIL'}]")
    f3 = cv["CONTRADICTED"] >= 0.3 * n
    say(f"F3  corrupted statements CONTRADICTED: {cv['CONTRADICTED']}/{len(corrupted)} (verdicts {dict(cv)})   [>= 30 % -> {'PASS' if f3 else 'FAIL'}]")
    for ok, g in ((f1, "F1"), (f2, "F2"), (f3, "F3")):
        if not ok: fails.append(g)
    # ---- F4 the chat
    import chat as CH
    KC.save(C)
    worlds, df = CH.build_worlds()
    D = CH.Door(worlds, df, seed=3, reader=R); falseyes = 0
    for t, truth in [("tokyo is the capital of japan", True), ("paris is the capital of germany", False), ("a commune in pas de calais, france", True),
                     ("hainaut, belgium", True), ("hainaut, france", False), ("the city of lyon, france", True), ("lyon, spain", False),
                     ("ohio, united states", True), ("ohio, canada", False), ("berlin, germany", True)]:
        r = D.turn(t); fk = r["frame"]["kind"]
        yes = fk == CH.CHECK_K and r["frame"].get("stated") is None
        falseyes += yes and not truth
        say(f"    {t!r:40s} -> {fk}: {r['reply'][:110]}")
    f4 = falseyes == 0
    say(f"F4  the chat: false 'Yes' {falseyes}   [0 -> {'PASS' if f4 else 'FAIL'}]")
    if not f4: fails.append("F4")
    say("\nF5  REGISTERED NUMBERS")
    if "--quick" in sys.argv: say("    (skipped: --quick)")
    else:
        out = subprocess.run([sys.executable, "chat.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = "ONE DOOR: PASS" in out; say(f"    chat.py        {'unchanged' if hit else 'MOVED'}")
        if not hit: fails.append("F5")
    say(f"\nC4: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
