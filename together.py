"""TOGETHER -- everything on, one long conversation: do the new abilities compound? (together_prereg.md). Zero LLM.
Offline. Reuses the chat gate's 200 utterances, Door, score and round trip; adds a dependent batch, proposals, and a
second session in a fresh process. Arms: ALL, BASE (the chat gate's Door), ALL minus transfer, ALL minus proposals,
session 2 without the store.

Usage:  python together.py            # the gate
        python together.py --child STORE OUT   (internal: session 2)"""
import os, sys, time, json, random, subprocess, collections, shutil
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
import chat as C
from chat import Door, build_worlds, held_out, score, YES, NO
from frames import realize, parse, canonical
from core.verdict import COMMIT, CONJECTURED
from core.reason import READINGS, PARTIAL, NOT_FOUND
from core.registry import selfcheck

T0 = time.time()
OUT = os.path.join(HERE, "_nldata", "together")
BATCH = [("what is the difference between 9 and 4", F(5)), (YES, None), ("what is the difference between 20 and 8", F(12)),
         ("what is the total of 3 and 4", F(7)), (NO, None), ("what is the total of 3 and 4", "DENIED"),
         ("what is the salary of research minus support", F(495))]
PROBE = [q for q, g in BATCH if g is not None and g != "DENIED"]           # re-asked without feedback: the reference answers


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def same(a, b):
    try: return F(str(a)) == F(str(b))
    except Exception: return str(a).lower() == str(b).lower()


def worlds_on(df_on=True):
    worlds, df = build_worlds()
    if df_on:
        for w in worlds:
            if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    return worlds, df


def door(store=None, transfer=False, tag="x"):
    worlds, df = worlds_on(transfer or store is not None)
    path = os.path.join(OUT, f"{tag}.jsonl")
    if os.path.exists(path): os.remove(path)
    if store and os.path.exists(store): os.remove(store)
    return Door(worlds, df, transcript=path, seed=1, store=store, transfer=transfer), worlds, df


def value(rec):
    return rec["values"][0] if rec.get("values") and len(rec["values"]) == 1 and rec["kind"] in (COMMIT, "attributed", CONJECTURED) else None


def launder(rec):
    fr = rec.get("_fr")
    return 1 if fr and fr["kind"] == COMMIT and any(c[0] == "TRANSFER" for a in fr["answers"] for c in a[3]) else 0


def run_chat(D, items, kgw):
    res = collections.Counter(); confabs = []; la = 0; rt_ok = rt_n = 0; errors = 0; conj = conj_right = vals = 0
    for i, (text, typ, gold) in enumerate(items):
        rec = D.turn(text)
        if rec["error"]: errors += 1
        la += launder(rec)
        for k in range(3): rt_n += 1; rt_ok += parse(realize(rec["frame"], random.Random(1000 * i + k))) == canonical(rec["frame"])
        if value(rec) is not None:
            vals += 1
            if rec["kind"] == CONJECTURED: conj += 1
        if typ != "STRESS":
            s = score(rec, typ, gold, kgw.label); res[s] += 1
            if s == "confab": confabs.append((text, rec["values"], gold))
            if rec["kind"] == CONJECTURED and s == "correct": conj_right += 1
    return dict(res=res, confabs=confabs, laundering=la, rt=(rt_ok, rt_n), errors=errors, conj=conj, conj_right=conj_right, vals=vals, ms=[r["ms"] for r in D.records])


def run_batch(D):
    out = []
    for q, g in BATCH:
        rec = D.turn(q); out.append((q, rec["kind"], value(rec), g, launder(rec)))
    return out


def run_probe(D): return [(q, D.turn(q)["kind"], value(D.turn(q))) for q in PROBE]


def run_proposals(D, gold_of, rounds=5):
    log = []; seen = set(); keys = set()
    for _ in range(rounds):
        before = len(D.S.goals()); g, q = D.propose(exclude=keys)
        if q is None or q in seen: log.append(("none" if q is None else "repeat", q, None, None, before, before)); break
        seen.add(q); keys.add(g.key); rec = D.turn(q); v = value(rec); fb = None
        gold = gold_of.get(q)
        if v is not None and gold is not None:
            fb = YES if same(v, gold) else NO; D.turn(fb)
        elif rec["kind"] == READINGS and gold is not None and any(same(x, gold) for x in rec.get("values", [])):
            fb = "choice"; D.turn(next(x for x in rec["values"] if same(x, gold)))           # the chat's own CHOICE channel
        after = len(D.S.goals()); gone = fb is not None and g.key not in {x.key for x in D.S.goals()}
        log.append((g.kind, q, rec["kind"], fb, before, after, gone))
    return log


def child(store, out):
    worlds, df = worlds_on(True)
    D = Door(worlds, df, seed=2, store=(store if store != "-" else None), transfer=True)
    searched = [w for w in worlds if w.name == "exec"][0]
    res = dict(batch=[(q, k, v) for q, k, v in run_probe(D)], chat=[], report=json.loads(json.dumps(getattr(D, "store_report", {}), default=str)))
    for text, typ, gold in held_out()[:10]:
        rec = D.turn(text); res["chat"].append((text, rec["kind"], value(rec), score(rec, typ, gold, worlds[0].label) if typ != "STRESS" else "stress"))
    json.dump(res, open(out, "w", encoding="utf-8"), default=str)


def run_child(store, tag):
    out = os.path.join(OUT, f"child-{tag}.json")
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", store, out], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace")
    if r.returncode != 0: say(r.stdout[-1500:]); say(r.stderr[-1500:]); raise SystemExit("child failed")
    return json.load(open(out, encoding="utf-8"))


def main():
    selfcheck(__file__)
    os.makedirs(OUT, exist_ok=True)
    say("EVERYTHING ON, ONE LONG CONVERSATION (together_prereg.md)\n")
    items = held_out(); gold_of = {t: g for t, typ, g in items if typ != "STRESS"}; gold_of.update({q: g for q, g in BATCH if g not in (None, "DENIED")})
    fails = []
    # ---- ALL
    S1 = os.path.join(OUT, "store-all.json")
    D, W, df = door(store=S1, transfer=True, tag="all"); kgw = W[0]
    t = time.time(); all_chat = run_chat(D, items, kgw); say(f"ALL   200 utterances in {time.time() - t:.0f} s: {dict(all_chat['res'])}; probably {all_chat['conj']}/{all_chat['vals']} value answers (right {all_chat['conj_right']}); laundering {all_chat['laundering']}; round trip {all_chat['rt']}")
    all_batch = run_batch(D)
    for q, k, v, g, la in all_batch: say(f"      {q[:44]:46s} -> {k:11s} {v!s:8s} gold {g!s}{'  LAUNDERING' if la else ''}")
    # the verifier for a swapped question: the original pair's gold (same operator, one word changed), read off the worlds'
    # lexicons as data
    for w in W:
        for word, entry in getattr(w, "borrowed", {}).items():
            for q, g in getattr(w, "pairs", []):
                for x in q.split():
                    if getattr(w, "lexicon", {}).get(x) == entry[0] and x != word:
                        import re as _re; gold_of.setdefault(_re.sub(rf"\b{_re.escape(x)}\b", word, q, count=1), g)
    all_props = run_proposals(D, gold_of)
    for kind, q, k, fb, b, a, *gone in all_props: say(f"      proposal {kind:9s} {q!r:50s} -> {k} feedback {fb}; residue {b} -> {a}; goal settled {gone[0] if gone else None}")
    all_probe = run_probe(D)
    goals_left = len(D.S.goals())
    from core.store import save; save(D.S, S1)
    # ---- BASE
    Db, Wb, _ = door(tag="base")
    base_chat = run_chat(Db, items, Wb[0]); base_batch = run_batch(Db); base_probe = run_probe(Db)
    say(f"BASE  {dict(base_chat['res'])}; probably {base_chat['conj']}/{base_chat['vals']}; batch {[(k, v) for q, k, v, g, la in base_batch]}")
    # ---- ablations
    Dt, Wt, _ = door(store=os.path.join(OUT, "store-not.json"), transfer=False, tag="notransfer")
    run_chat(Dt, items, Wt[0]); not_batch = run_batch(Dt); run_proposals(Dt, gold_of); not_probe = run_probe(Dt)
    Dp, Wp, _ = door(store=os.path.join(OUT, "store-nop.json"), transfer=True, tag="noprop")
    run_chat(Dp, items, Wp[0]); run_batch(Dp); nop_probe = run_probe(Dp)
    # ---- session 2
    c2 = run_child(S1, "s2"); c0 = run_child("-", "nostore")

    # ---- E1
    p95 = sorted(all_chat["ms"][1:])[int(0.95 * (len(all_chat["ms"]) - 2))] / 1000
    e1 = (not all_chat["confabs"]) and all_chat["laundering"] == 0 and all_chat["rt"][0] == all_chat["rt"][1] and all_chat["errors"] == 0 and all_chat["res"]["correct"] >= base_chat["res"]["correct"] and p95 <= 2.0
    say(f"\nE1  NOTHING WORSE: ALL correct {all_chat['res']['correct']} vs BASE {base_chat['res']['correct']}; CONFAB {len(all_chat['confabs'])} {all_chat['confabs'][:3]}; LAUNDERING {all_chat['laundering']}; MISREPORT {all_chat['rt'][1] - all_chat['rt'][0]}; exceptions {all_chat['errors']}; p95 {p95:.2f} s   [{'PASS' if e1 else 'FAIL'}]")
    if not e1: fails.append("E1")
    # ---- E2
    bconj = sum(1 for q, k, v, g, la in all_batch if k == CONJECTURED)
    say(f"E2  THE PRICE: over the 200, {all_chat['conj']} of {all_chat['vals']} value answers are 'Probably' ({all_chat['conj_right']} right); over the dependent batch {bconj} of {sum(1 for q, k, v, g, la in all_batch if v is not None)}")
    # ---- E3
    b = {q: (k, v) for q, k, v, g, la in all_batch}
    t1 = b["what is the difference between 9 and 4"] == (CONJECTURED, "5"); t2 = b["what is the difference between 20 and 8"] == (COMMIT, "12")
    t3 = b["what is the total of 3 and 4"][0] in (NOT_FOUND, PARTIAL, READINGS, "PROPOSE") or b["what is the total of 3 and 4"][1] != "7"
    t4 = b["what is the salary of research minus support"][1] == "495"
    bb = {q: (k, v) for q, k, v, g, la in base_batch}
    base_none = all(bb[q][1] is None for q in ("what is the difference between 9 and 4", "what is the difference between 20 and 8", "what is the salary of research minus support"))
    e3 = t1 and t2 and t3 and t4 and not any(la for *_, la in all_batch)
    say(f"E3  DEPENDENT BATCH: transfer conjecture right {t1}; after 'correct' a COMMIT {t2}; after 'wrong' never again {t3}; records through an arithmetic word {t4}   [{'PASS' if e3 else 'FAIL'}]; BASE answers none: {base_none}   [{'FAILS ON MAIN' if base_none else 'does not discriminate'}]")
    if not (e3 and base_none): fails.append("E3")
    # ---- E4
    made = [p for p in all_props if p[0] not in ("none", "repeat")]
    seen_syms = {s for t, typ, g in items for s in t.lower().split()} | {s for q, g in BATCH for s in q.split()} | {s for w in W for q, g in getattr(w, "pairs", []) for s in q.split()}
    derivable = all(all(s in seen_syms or s.isdigit() for s in q.split()) for kind, q, k, fb, b_, a_, *_ in made)
    reduced = any(p[6] for p in made if len(p) > 6)                     # an answered proposal settled its goal
    e4 = bool(made) and derivable and reduced and not any(p[0] == "repeat" for p in all_props)
    say(f"E4  PROPOSALS: {len(made)} made, derivable from the session {derivable}, residue reduced by an answer {reduced}, repeats {sum(1 for p in all_props if p[0] == 'repeat')}; residue left {goals_left}   [{'PASS' if e4 else 'FAIL'}]")
    if not e4: fails.append("E4")
    # ---- E5
    ref = {q: (k, v) for q, k, v in all_probe}; s2 = {q: (k, v) for q, k, v in c2["batch"]}; s0 = {q: (k, v) for q, k, v in c0["batch"]}
    same2 = sum(1 for q in ref if s2.get(q) == ref[q]); commits2 = sum(1 for q, (k, v) in s2.items() if k == COMMIT)
    resea = c2["report"].get("exec", {}).get("searched", [])
    chat2_confab = sum(1 for t, k, v, s in c2["chat"] if s == "confab")
    for t, k, v, s in c2["chat"]:
        if s == "confab": say(f"      session 2 CONFAB: {t!r} -> {k} {v}")
    nostore_none = s0.get("what is the difference between 20 and 8", (None, None))[0] != COMMIT       # the CONFIRMED word needs the store; transfer alone still conjectures
    e5 = same2 == len(ref) and not resea and chat2_confab == 0 and s2["what is the difference between 20 and 8"][0] == COMMIT
    diffs = [(q, ref[q], s2.get(q)) for q in ref if s2.get(q) != ref[q]]
    say(f"E5  SESSION 2 from the store: batch identical {same2}/{len(ref)} (COMMITs {commits2}) {diffs}; re-searched {resea}; ten chat items confab {chat2_confab}   [{'PASS' if e5 else 'FAIL'}]; without the store the confirmed word is not a COMMIT: {nostore_none}   [{'FAILS ON MAIN' if nostore_none else 'does not discriminate'}]")
    if not (e5 and nostore_none): fails.append("E5")
    # ---- E6 compounding
    # "right" = a PLAIN answer (COMMIT/ATTRIBUTED) with the right value: a conjecture with the right value is not yet the
    # same thing, and that is exactly what the store and the confirmation add (declared with the first run's reading)
    def plain(k, v, q): return v is not None and k in (COMMIT, "attributed") and same(v, gold_of.get(q))
    right_all = {q for q, k, v in all_probe if plain(k, v, q)}
    lose = collections.defaultdict(list)
    for name, arm in (("no-transfer", {q: (k, v) for q, k, v in not_probe}), ("no-proposals", {q: (k, v) for q, k, v in nop_probe}), ("no-store (session 2)", {q: (k, v) for q, (k, v) in s0.items()}), ("base", {q: (k, v) for q, k, v in base_probe})):
        for q in right_all:
            k, v = arm.get(q, (None, None))
            if not plain(k, v, q): lose[q].append(name)
    joint = [q for q in right_all if len([a for a in lose[q] if a != "base"]) >= 2]
    say(f"E6  COMPOUNDING: right in ALL {len(right_all)}; lost by ablation: " + "; ".join(f"{q[:40]!r}: {lose[q]}" for q in sorted(right_all)))
    say(f"    JOINT (lost by two or more abilities switched off): {len(joint)} {joint}   [prediction >= 3]")
    # ---- E7
    say("\nE7  REGISTERED NUMBERS")
    ok7 = True
    if "--quick" in sys.argv:
        say("    (skipped: --quick)"); say(f"TOGETHER (quick): missed {fails or None}; joint {len(joint)}; {time.time() - T0:.0f} s"); return
    for f, needle in {"chat.py": "ONE DOOR: PASS", "chat_prose.py": "PROSE FRAMES: PASS", "transfer.py": "S4 TRANSFER: PASS", "goals.py": "S9 GOALS: SOUND"}.items():
        tt = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out; ok7 = ok7 and hit; say(f"    {f:16s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
    if not ok7: fails.append("E7")
    verdict = "PASS" if not fails else ("SOUND" if e1 and ok7 else "FAIL " + ",".join(fails))
    say(f"\nCONFAB: {len(all_chat['confabs'])}   LAUNDERING: {all_chat['laundering']}")
    say(f"TOGETHER: {verdict} -- joint {len(joint)}, probably {all_chat['conj']}/{all_chat['vals']}; {time.time() - T0:.0f} s" + (f" (missed: {fails})" if fails else ""))


if __name__ == "__main__":
    if "--child" in sys.argv:
        i = sys.argv.index("--child"); child(sys.argv[i + 1], sys.argv[i + 2])
    else: main()
