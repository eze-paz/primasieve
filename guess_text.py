"""G2 -- GUESSING FROM TEXT (guess_text_prereg.md). Zero LLM. Offline: the crawl store and the Wiktionary store.

Usage:  python guess_text.py [--quick]"""
import os, sys, time, json, random, sqlite3, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.guesser import Guesser, text_cues, TEXT
from core.registry import selfcheck
from kb_guess import load_entities, labels, TARGETS, DB
from guess import held_out, say

T0 = time.time()
KAIKKI = os.path.join(HERE, "_nldata", "kaikki_all.sqlite")


def defs_of(db, w, k=3):
    r = db.execute("select v from e where w=?", (w.lower(),)).fetchone()
    return " ".join(json.loads(r[0]).get("defs", [])[:k]) if r else ""


def score(G, items, mode):
    """mode: 'text' (text cues only), 'facts' (claims + name, G1), 'both' -> {target: (asked, guessed, right)}, examples"""
    out = {}; ex = []
    for t in TARGETS:
        asked = guessed = right = 0
        for q, l, c, text in items:
            truth = {str(v).lower() for v in c.get(t, [])}
            if not truth: continue
            asked += 1
            if mode == "text": g = G.guess("", text_cues(text), t)
            elif mode == "facts": g = G.guess(l, c, t)
            else: g = G.guess(l, dict(c, **text_cues(text)), t)
            if not g: continue
            guessed += 1; ok = g[0][0] in truth; right += ok
            if mode == "text" and len(ex) < 400: ex.append((l, t, g[0][0], ok, g[0][1], text))
        out[t] = (asked, guessed, right)
    return out, ex


def pooled(rows):
    A = sum(a for a, g, r in rows.values()); Gs = sum(g for a, g, r in rows.values()); R = sum(r for a, g, r in rows.values())
    return R / max(1, Gs), Gs / max(1, A), R


def show(rows, tag):
    for t, (a, g, r) in rows.items():
        say(f"    {t:28s} n {a:5d}  coverage {g / max(1, a):5.2f}  precision {r / max(1, g):5.3f}")
    p, c, R = pooled(rows); say(f"    {tag}: pooled precision {p:.3f} at coverage {c:.3f} ({R} right)"); return p, c, R


def main():
    selfcheck(__file__)
    if not (os.path.exists(DB) and os.path.exists(KAIKKI)): say("G2: NOT RUN (the crawl and Wiktionary stores are needed)"); return
    db = sqlite3.connect(KAIKKI)
    ents = load_entities(); items = []
    for q, l, c in ents:
        text = defs_of(db, l)
        if text: items.append((q, l, c, text))
    train = [x for x in items if not held_out(x[0])]; test = [x for x in items if held_out(x[0])]
    say(f"G2  GUESSING FROM TEXT (guess_text_prereg.md) -- {len(items)} crawl entities with a definition; train {len(train)}, test {len(test)}; {time.time() - T0:.0f} s\n")
    G = Guesser(TARGETS); n = G.learn([(l, dict(c, **text_cues(text))) for q, l, c, text in train])
    text_rules = sum(1 for t in TARGETS for cue in G.rules[t] if cue[0].startswith(TEXT))
    say(f"    admitted rules {sum(n.values())}, of them on text cues {text_rules}")
    fails = []
    rt, ex = score(G, test, "text"); p1, c1, R1 = show(rt, "TEXT ONLY")
    t1 = p1 >= 0.85 and c1 >= 0.25
    say(f"T1  text only: precision {p1:.3f} at coverage {c1:.3f}   [>= 0.85 at >= 0.25 -> {'PASS' if t1 else 'FAIL'}]\n")
    if not t1: fails.append("T1")
    G1 = Guesser(TARGETS); G1.learn([(l, c) for q, l, c, text in train])
    rf, _ = score(G1, test, "facts"); pf, cf, _ = show(rf, "FACTS + NAME (G1)")
    rb, _ = score(G, test, "both"); pb, cb, _ = show(rb, "FACTS + NAME + TEXT")
    t2 = cb > cf and pb >= 0.85
    say(f"T2  coverage {cf:.3f} -> {cb:.3f}, precision {pf:.3f} -> {pb:.3f}   [{'PASS' if t2 else 'FAIL'}]\n")
    if not t2: fails.append("T2")
    rng = random.Random(11); texts = [x[3] for x in train]; rng.shuffle(texts)
    GK = Guesser(TARGETS); GK.learn([(l, dict(c, **text_cues(tx))) for (q, l, c, _), tx in zip(train, texts)])
    rk, _ = score(GK, test, "text"); pk, ck, RK = show(rk, "KNOCKOUT (texts shuffled)")
    t3 = RK < 0.25 * R1
    say(f"T3  knockout right text-only guesses {RK} = {RK / max(1, R1):.1%} of T1's   [< 25 % -> {'PASS' if t3 else 'FAIL'}]\n")
    if not t3: fails.append("T3")
    rights = [e for e in ex if e[3]]; written = sum(1 for l, t, v, ok, why, text in rights if v in text.lower())
    say(f"T4  of {len(rights)} right text guesses (sampled), value written in the text: {written} ({written / max(1, len(rights)):.0%}); inferred: {len(rights) - written}")
    for l, t, v, ok, why, text in [e for e in rights if e[2] not in e[5].lower()][:5]:
        say(f"    inferred: {l!r} {t} -> {G.spell(v)} because {why}  | text: {text[:90]!r}")
    for l, t, v, ok, why, text in [e for e in ex if not e[3]][:4]:
        say(f"    wrong:    {l!r} {t} -> {G.spell(v)} because {why}  | text: {text[:90]!r}")
    # ---- T5 beyond the store
    known = {l.lower() for q, l, c in ents}; beyond = guessed5 = 0; show5 = []
    for w, v in db.execute("select w, v from e"):
        if w in known: continue
        e = json.loads(v)
        if "name" not in (e.get("pos") or []): continue
        beyond += 1
        g = G.guess("", text_cues(" ".join(e.get("defs", [])[:3])), "instance of")
        if g:
            guessed5 += 1
            if len(show5) < 30 and guessed5 % 97 == 1: show5.append((w, G.spell(g[0][0]), g[0][1], " ".join(e.get("defs", [])[:1])[:80]))
    say(f"\nT5  dictionary names outside the store: {beyond}; given an 'instance of' guess from their definition: {guessed5}")
    for w, v, why, d in show5: say(f"    {w!r:24s} -> {v:22s} because {why[0][1]!r} {why[1]}/{why[2]}  | {d!r}")
    # ---- T6 in a session
    t6 = session_check(G)
    if not t6: fails.append("T6")
    # ---- T8 hygiene
    core_src = open(os.path.join(HERE, "core", "guesser.py"), encoding="utf-8").read()
    t8 = not any(t in core_src.lower() for t in ("country", "instance of", "occupation", "wikidata", "town", "wiktionary"))
    say(f"T8  core/guesser.py holds no property, source or content word: {t8}   [{'PASS' if t8 else 'FAIL'}]")
    if not t8: fails.append("T8")
    say("\nT7  G1 AND REGISTERED NUMBERS")
    if "--quick" in sys.argv: say("    (skipped: --quick)")
    else:
        for f, args, needle in (("guess.py", ["--quick"], "G1: PASS"), ("chat.py", [], "ONE DOOR: PASS")):
            tt = time.time(); out = subprocess.run([sys.executable, f] + args, capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
            hit = needle in out; say(f"    {f:14s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
            if not hit: fails.append("T7")
    say(f"\nG2: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


def session_check(G):
    """T6: words only the dictionary knows, asked about; the guess must come from the definition, labelled."""
    import research as Rg
    from frames import parse, HUNCH
    from core.verdict import COMMIT, ATTRIBUTED
    G.labels = labels()
    D, W, df = Rg.door(None); D.S.guesser = G
    asked = guessed = fatal = 0; shown = []
    for w, t in [("gabrovo", "country"), ("nagqu", "country"), ("uluru", "country"), ("kleinmachnow", "country"),
                 ("dombes", "country"), ("cacheu", "country"), ("pielach", "country"), ("gabrovo", "continent")]:
        rec = D.turn(f"what is the {t} of {w}"); asked += 1; fr = rec.get("_fr", {})
        if "guesser" in rec.get("sources", []) and rec["kind"] in (COMMIT, ATTRIBUTED): fatal += 1
        if fr.get("guessed"):
            guessed += 1
            p = parse(rec["reply"]); fatal += not (p and p["kind"] == HUNCH)
        shown.append(f"    {w} / {t}: {rec['kind']}: {rec['reply'][:170]}")
    for s in shown: say(s)
    ok = guessed >= 3 and fatal == 0
    say(f"T6  {guessed}/{asked} turns answered with a labelled guess from the definition; fatal {fatal}   [>= 3, 0 -> {'PASS' if ok else 'FAIL'}]")
    return ok


if __name__ == "__main__":
    main()
