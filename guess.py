"""G1 -- THE GUESSER (guess_prereg.md). Zero LLM. Offline: the crawl store in label form.

Usage:  python guess.py [--quick]"""
import os, sys, time, json, random, hashlib, sqlite3, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.guesser import Guesser, name_cues
from core.registry import selfcheck
from kb_guess import load_entities, TARGETS, RULES

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def held_out(q, seed=0): return int(hashlib.sha256(f"{seed}:{q}".encode()).hexdigest(), 16) % 10 == 0


def evaluate(G, test, train, only_names=False):
    rows = {}; reasons_ok = True
    for t in TARGETS:
        base = collections.Counter(v.lower() for _, _, c in train for v in set(c.get(t, [])))
        bv = base.most_common(1)[0][0] if base else None
        total = right = guessed = multi = base_right = 0
        for q, l, c in test:
            truth = {str(v).lower() for v in c.get(t, [])}
            if not truth: continue
            total += 1; base_right += bv in truth
            cl = {} if only_names else c
            g = G.guess(l, cl, t)
            if not g: continue
            guessed += 1; multi += len(g) > 1
            reasons_ok &= all(len(r) == 3 and r[1] >= G.support and r[1] >= G.share * r[2] for v, r in g)
            right += g[0][0] in truth
        rows[t] = dict(total=total, guessed=guessed, right=right, multi=multi, base=base_right / max(1, total), base_value=bv)
    return rows, reasons_ok


def table(rows, tag):
    T = sum(r["total"] for r in rows.values()); Gs = sum(r["guessed"] for r in rows.values()); R = sum(r["right"] for r in rows.values())
    for t, r in rows.items():
        p = r["right"] / max(1, r["guessed"]); cov = r["guessed"] / max(1, r["total"])
        say(f"    {t:28s} n {r['total']:5d}  coverage {cov:5.2f}  precision {p:5.3f}  (baseline {r['base']:5.3f} '{r['base_value']}')  multi {r['multi']}")
    prec = R / max(1, Gs); cov = Gs / max(1, T)
    say(f"    {tag}: pooled precision {prec:.3f} at coverage {cov:.3f}  ({R} right of {Gs} guessed, {T} asked)")
    return prec, cov, R


def session_check(G, test, n_guess=40, n_known=10):
    """K6: planted graph worlds of held-out entities -- without their country (the guesser may speak) and with it (a known
    answer; the guess it would have made is checked)."""
    import research as Rg
    from chat import YES, NO
    from frames import parse, HUNCH
    from kb_guess import labels
    from core.kg import KGWorld
    from core.research import FetchedGraph
    from core.verdict import COMMIT, ATTRIBUTED, CONJECTURED
    G.labels = labels()
    pool = [e for e in test if e[2].get("country") and 1 <= len(e[1].split()) <= 3 and e[1].isascii()]
    hide, keep = pool[:n_guess], pool[n_guess:n_guess + n_known]
    data = {q: dict(label=l, aliases=[], desc="", claims={p: v[:8] for p, v in c.items() if p != "country"}) for q, l, c in hide}
    data.update({q: dict(label=l, aliases=[], desc="", claims={p: v[:8] for p, v in c.items()}) for q, l, c in keep})
    D, W, df = Rg.door(None); D.S.guesser = G
    pw = KGWorld(FetchedGraph(data, "planted"), df, name="planted"); D.S.worlds.append(pw)
    asked = guessed = right = other = fatal = parsed = 0; fed = 0; expect = [0, 0]; examples = []; kinds = collections.Counter()
    for q, l, c in hide:
        rec = D.turn(f"what is the country of {l.lower()}"); asked += 1
        fr = rec.get("_fr", {})
        if "guesser" in rec.get("sources", []) and rec["kind"] != CONJECTURED: fatal += 1
        if fr.get("guessed"):
            guessed += 1; ok = rec["values"][0].lower() in {v.lower() for v in c["country"]}; right += ok
            parsed += parse(rec["reply"]) is not None and parse(rec["reply"])["kind"] == HUNCH
            if len(examples) < 3: examples.append(rec["reply"])
            if fed < 10:
                D.turn(YES if ok else NO); fed += 1; expect[0 if ok else 1] += 1
        elif rec["kind"] in (COMMIT, ATTRIBUTED): other += 1
        if fr.get("prediction_checked"): expect[0 if fr["prediction_checked"][1] else 1] += 1      # a known source answered: the guess it would have made is checked
        kinds[rec["kind"]] += 1
    say(f"    kinds over the hidden: {dict(kinds)}")
    after_feedback = D.ledger.snapshot().get("guesser", (0, 0))
    checked = []
    for q, l, c in keep:
        rec = D.turn(f"what is the country of {l.lower()}"); fr = rec.get("_fr", {})
        if "guesser" in rec.get("sources", []) and rec["kind"] != CONJECTURED: fatal += 1
        if fr.get("prediction_checked"): checked.append(fr["prediction_checked"][1])
    final = D.ledger.snapshot().get("guesser", (0, 0))
    for r in examples: say(f"    e.g. {r}")
    say(f"    asked {asked}: guessed {guessed} ({right} right), answered by a known source {other}; replies parsed back as HUNCH {parsed}/{guessed}")
    say(f"    feedback on {fed} guesses (expected, with checked predictions, {expect[0]} confirmed, {expect[1]} contradicted) -> guesser record {after_feedback}")
    say(f"    known answers: {len(checked)} predictions checked ({sum(checked)} right) -> guesser record {final}")
    ok6 = guessed > 0 and fatal == 0 and parsed == guessed and tuple(after_feedback) == tuple(expect)         and len(checked) > 0 and tuple(final) == (expect[0] + sum(checked), expect[1] + len(checked) - sum(checked))
    say(f"K6  labelled guesses, record written by the user's word and by checked predictions, guesser never a fact (fatal {fatal})   [{'PASS' if ok6 else 'FAIL'}]")
    return ok6


def main():
    selfcheck(__file__)
    from kb_guess import DB
    if not os.path.exists(DB): say("G1: NOT RUN (the crawl store is absent: python emergence/kb_crawl.py --crawl)"); return
    ents = load_entities(); say(f"G1  THE GUESSER (guess_prereg.md) -- {len(ents)} entities, {time.time() - T0:.0f} s\n")
    train = [e for e in ents if not held_out(e[0])]; test = [e for e in ents if held_out(e[0])]
    G = Guesser(TARGETS); n_rules = G.learn([(l, c) for _, l, c in train])
    say(f"    admitted rules: {n_rules}  ({time.time() - T0:.0f} s)")
    rows, reasons_ok = evaluate(G, test, train)
    prec, cov, right = table(rows, "MAIN")
    fails = []
    k1 = prec >= 0.85 and cov >= 0.35
    beat = sum(1 for r in rows.values() if r["guessed"] and r["right"] / r["guessed"] > r["base"])
    k2 = beat >= 7
    say(f"K1  pooled precision {prec:.3f} at coverage {cov:.3f}   [>= 0.85 at >= 0.35 -> {'PASS' if k1 else 'FAIL'}]")
    say(f"K2  above baseline on {beat}/8 targets   [>= 7 -> {'PASS' if k2 else 'FAIL'}]")
    if not k1: fails.append("K1")
    if not k2: fails.append("K2")
    # K3 knockout: each target's values shuffled across training entities
    rng = random.Random(7); shuf = [(l, dict(c)) for _, l, c in train]
    for t in TARGETS:
        idx = [i for i, (l, c) in enumerate(shuf) if t in c]; vals = [shuf[i][1][t] for i in idx]; rng.shuffle(vals)
        for i, v in zip(idx, vals): shuf[i][1][t] = v
    GK = Guesser(TARGETS); nk = GK.learn(shuf)
    rk, _ = evaluate(GK, test, train); say("\n    knockout:"); pk, ck, rightk = table(rk, "KNOCKOUT")
    share_rules = sum(nk.values()) / max(1, sum(n_rules.values())); share_right = rightk / max(1, right)
    k3 = share_rules < 0.20 and share_right < 0.25
    say(f"K3  knockout: admitted rules {share_rules:.1%} of main, right guesses {share_right:.1%} of main   [< 20 % and < 25 % -> {'PASS' if k3 else 'FAIL'}]")
    if not k3: fails.append("K3")
    say(f"K4  every guess carries (cue, hits, n) with the admission bar met: {reasons_ok}   [{'PASS' if reasons_ok else 'FAIL'}]")
    if not reasons_ok: fails.append("K4")
    rn, _ = evaluate(G, test, train, only_names=True); say("\n    names alone:"); table(rn, "NAMES")
    say("K5  printed")
    ex = [e for e in test if e[2].get("country")][:5]
    for q, l, c in ex:
        g = G.guess(l, c, "country")
        say(f"    e.g. {l!r}: truth {c['country'][:2]} -> {[(v, r) for v, r in g[:2]]}")
    # ---- K6 in a session
    k6 = session_check(G, test)
    if not k6: fails.append("K6")
    # ---- K7 the live chat
    src = open(os.path.join(HERE, "chat.py"), encoding="utf-8").read()
    live = src[src.index("def live_door"):src.index("def repl")]
    k7 = "build_guesser()" in live and "guesser=" in live
    say(f"K7  the live door builds the guesser: {k7}   [{'PASS' if k7 else 'FAIL'}]")
    if not k7: fails.append("K7")
    # ---- K9 hygiene
    core_src = open(os.path.join(HERE, "core", "guesser.py"), encoding="utf-8").read()
    imports = [l for l in core_src.splitlines() if l.startswith(("import ", "from "))]
    k9 = all(l in ("import collections", "import json", "from .reason import symbols") for l in imports) and not any(t in core_src.lower() for t in ("country", "instance of", "occupation", "wikidata"))
    say(f"K9  core/guesser.py: imports {imports}; no property or source word: {k9}   [{'PASS' if k9 else 'FAIL'}]")
    if not k9: fails.append("K9")
    if "--measure" in sys.argv:
        say(f"\nG1 (measure only): missed {fails or None}; {time.time() - T0:.0f} s"); return
    say("\nK8  REGISTERED NUMBERS")
    if "--quick" in sys.argv: say("    (skipped: --quick)")
    else:
        for f, args, needle in (("chat.py", [], "ONE DOOR: PASS"), ("research.py", [], "RESEARCH BY ITSELF: PASS"), ("crosscheck.py", ["--quick"], "CROSSCHECK (quick): missed None")):
            tt = time.time(); out = subprocess.run([sys.executable, f] + args, capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
            hit = needle in out; say(f"    {f:14s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
            if not hit: fails.append("K8")
    say(f"\nG1: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
