"""THE FLUENCY BATTERY (FLUENCY_LOOP_PLAN.md, Section 1). Measures B1-B10 with the live chat's door built OFFLINE (every
ability on, no network), on the frozen test sets in tests/battery/. Writes BATTERY.json and prints the table.

    python battery.py [--fast]     (--fast skips the sub-gates that rerun whole experiments: B3, B7)"""
import os, sys, re, json, time, random, hashlib, subprocess, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.verdict import COMMIT, ATTRIBUTED, CONJECTURED
import chat as CH

T0 = time.time()
TB = os.path.join(HERE, "tests", "battery")
GUT = os.path.join(HERE, "_nldata", "gutenberg")
OUT = os.path.join(HERE, "BATTERY.json")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def norm(s): return " ".join(symbols(str(s), "LN"))


def hit(reply, gold): r = norm(reply); return any(norm(g) and norm(g) in r for g in gold)


def door(guesser=None):
    store = os.path.join(HERE, "_nldata", "battery_store.json")
    if os.path.exists(store): os.remove(store)
    D = CH.live_door(False, False, store, None, 3)
    if guesser is not None: D.S.guesser = guesser
    return D


def held_book(bid): return int(hashlib.sha256(f"book:{bid}".encode()).hexdigest(), 16) % 10 == 0


def run(cmd, needle_re):
    out = subprocess.run([sys.executable] + cmd, capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
    return re.findall(needle_re, out)


def main():
    res = {}; false_facts = 0; samples = []
    # ---- B2 ordinary phrasing
    q = json.load(open(os.path.join(TB, "questions.json"), encoding="utf-8"))["items"]
    D = door(); right = abst = 0
    for it in q:
        r = D.turn(it["q"]); ok = hit(r["reply"], it["gold"]); right += ok
        if not ok and r["kind"] in (COMMIT, ATTRIBUTED) and r.get("values") and not r.get("statement"): false_facts += 1
        if r["kind"] not in (COMMIT, ATTRIBUTED, CONJECTURED): abst += 1
        if len(samples) < 15 and ok: samples.append((it["q"], r["reply"]))
    res["B2"] = dict(score=right / len(q), right=right, n=len(q), abstained=abst)
    say(f"B2  ordinary phrasing: {right}/{len(q)} = {right / len(q):.1%} (abstained {abst})  ({time.time() - T0:.0f} s)")
    # ---- B9 dialogues
    dl = json.load(open(os.path.join(TB, "dialogues.json"), encoding="utf-8"))["dialogues"]; full = turns_ok = turns = 0
    for d in dl:
        D = door(); ok_all = True
        for t, gold in d["turns"]:
            r = D.turn(t); ok = hit(r["reply"], gold); turns += 1; turns_ok += ok; ok_all &= ok
            if len(samples) < 30 and ok: samples.append((t, r["reply"]))
        full += ok_all
    res["B9"] = dict(score=full / len(dl), dialogues=full, n=len(dl), turns_ok=turns_ok, turns=turns)
    say(f"B9  dialogues fully right: {full}/{len(dl)}; turns {turns_ok}/{turns}  ({time.time() - T0:.0f} s)")
    # ---- B10 open domain (held-out entities; the guesser learned on the training split only)
    from core.guesser import Guesser
    from kb_guess import load_entities, TARGETS, labels
    from guess import held_out
    G = Guesser(TARGETS); G.learn([(l, c) for qq, l, c in load_entities() if not held_out(qq)]); G.labels = labels()
    od = json.load(open(os.path.join(TB, "open_domain.json"), encoding="utf-8"))["items"]
    D = door(G); fact = guessed = 0
    for it in od:
        r = D.turn(it["q"]); ok = hit(r["reply"], it["gold"])
        if ok and r["kind"] == CONJECTURED: guessed += 1
        elif ok: fact += 1
        elif r["kind"] in (COMMIT, ATTRIBUTED) and r.get("values") and not r.get("statement") and not all(r.get("quotes") or [False]): false_facts += 1
    res["B10"] = dict(score=(fact + guessed) / len(od), fact=fact, guessed=guessed, n=len(od))
    say(f"B10 open domain: {fact + guessed}/{len(od)} ({fact} as facts, {guessed} as labelled guesses)  ({time.time() - T0:.0f} s)")
    # ---- B6 stories
    st = json.load(open(os.path.join(TB, "stories.json"), encoding="utf-8"))["stories"]; sr = sn = 0
    for s in st:
        D = door()
        for sent in re.split(r"(?<=[.!?])\s+", s["text"]): D.turn(sent)
        for qq, gold in s["qs"]:
            r = D.turn(qq); sn += 1; sr += hit(r["reply"], gold)
    res["B6"] = dict(score=sr / sn, right=sr, n=sn)
    say(f"B6  story questions: {sr}/{sn}  ({time.time() - T0:.0f} s)")
    # ---- B5 + B4 on held-out novels (when the corpus is present)
    books = sorted(f[:-4] for f in os.listdir(GUT) if f.endswith(".txt")) if os.path.isdir(GUT) else []
    test_books = [b for b in books if held_book(b)][:10]
    if test_books:
        from core.textworld import SlotWorld, find_entities
        from core.textmodel import TextModel
        from textmodel import MODEL
        closed = {w for w, c in TextModel.load(MODEL).uni.most_common(100)}; gains = []
        for b in test_books:
            text = open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()
            raw = [t for t in (re.findall(r"[A-Za-z]+", s) for s in re.split(r"(?<=[.!?])\s+", text)) if len(t) >= 3]
            ents = find_entities(raw, closed=closed); S = SlotWorld(ents, closed); n = right = fr_ = 0
            for k, toks in enumerate(raw):
                syms = [t.lower() for t in toks]; m = [i for i, x in enumerate(syms) if x in ents]
                if k >= 100 and len({syms[i] for i in m}) == 1:
                    i = m[0]; cands = S.candidates()
                    if syms[i] in cands:
                        g, _ = S.guess_at(syms, i, cands); n += 1; right += g == syms[i]; fr_ += cands[0] == syms[i]
                S.read(syms)
            if n >= 50: gains.append((right - fr_) / n)
        res["B5"] = dict(score=sum(gains) / max(1, len(gains)), books=len(gains))
        say(f"B5  masked names in {len(gains)} held-out novels: {100 * res['B5']['score']:+.1f} points over frequency  ({time.time() - T0:.0f} s)")
        import kb_constructions as KC
        R = KC.Reader(KC.Store(), KC.load(), {w for w, c in TextModel.load(MODEL).uni.most_common(1000)})
        sents = []
        for b in test_books:
            text = open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()
            sents += [s for s in re.split(r"(?<=[.!?])\s+", text) if 4 <= len(s.split()) <= 60][:500]
        read = sum(1 for s in sents if R.check(s)[0] in ("SUPPORTED", "CONTRADICTED", "UNKNOWN"))
        res["B4_novels"] = dict(score=read / max(1, len(sents)), read=read, n=len(sents))
        say(f"B4  held-out novel sentences with a proposition read: {read}/{len(sents)}  ({time.time() - T0:.0f} s)")
    if "--fast" not in sys.argv:
        f = run(["statements.py", "--quick"], r"F[12] .*?: (\d+)/(\d+)"); b = run(["filled.py", "--quick"], r"B[12] .*?: (\d+)/(\d+)")
        if len(f) >= 2 and len(b) >= 2:
            res["B3"] = dict(dict_true=int(f[0][0]) / int(f[0][1]), dict_false_yes=int(f[1][0]) / int(f[1][1]),
                             conv_true=int(b[0][0]) / int(b[0][1]), conv_false_yes=int(b[1][0]) / int(b[1][1]))
            say(f"B3  statements: {res['B3']}")
        k = run(["chains.py"], r"K[12] +(?:reversed|coverage) (\d+)/(\d+)")
        if len(k) >= 2: res["B7"] = dict(reversed=int(k[0][0]) / max(1, int(k[0][1])), coverage=int(k[1][0]) / int(k[1][1])); say(f"B7  speak: {res['B7']}")
    res["B1"] = dict(false_facts=false_facts); say(f"B1  false facts stated as facts in B2/B10: {false_facts}")
    with open(os.path.join(TB, "b8_sample.md"), "w", encoding="utf-8") as fh:
        fh.write("# B8 blind rating sample\nRate each reply 1 (robotic) to 5 (natural).\n\n")
        for i, (qq, rr) in enumerate(random.Random(5).sample(samples, min(30, len(samples))), 1): fh.write(f"{i}. **{qq}** -> {rr}\n\n")
    res["time_s"] = round(time.time() - T0)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=1)
    say(f"\nBATTERY written: {OUT}; {res['time_s']} s")


if __name__ == "__main__":
    main()
