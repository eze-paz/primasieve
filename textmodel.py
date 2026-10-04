"""G4 -- A COUNTING MODEL OF TEXT (textmodel_prereg.md). Zero LLM. Offline: the Wiktionary store and WordNet.

Usage:  python textmodel.py [--quick] [--frac F]"""
import os, sys, time, json, random, hashlib, sqlite3, collections, subprocess, gc

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.textmodel import TextModel, RARE, EDGE
from core.reason import symbols
from core.registry import selfcheck

T0 = time.time()
KAIKKI = os.path.join(HERE, "_nldata", "kaikki_all.sqlite")
WN = os.path.join(HERE, "_nldata", "dict")
MODEL = os.path.join(HERE, "_nldata", "textmodel.json")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def held(w, seed=0): return int(hashlib.sha256(f"{seed}:{w}".encode()).hexdigest(), 16) % 10 == 0


def corpus(frac=1.0):
    train, test = [], []; db = sqlite3.connect(KAIKKI)
    for w, v in db.execute("select w, v from e"):
        e = json.loads(v); sents = [str(s) for s in e.get("defs", [])] + [str(s) for s in e.get("ex", [])]
        if held(w): test.extend(sents)
        elif frac >= 1.0 or int(hashlib.sha256(f"f:{w}".encode()).hexdigest(), 16) % 1000 < frac * 1000: train.extend(sents)
    return train, test


def wordnet():
    """-> {word: set(synset ids)} for single-word lemmas"""
    out = collections.defaultdict(set)
    for pos in ("noun", "verb", "adj", "adv"):
        for line in open(os.path.join(WN, f"data.{pos}"), encoding="utf-8", errors="replace"):
            if line.startswith(" "): continue
            f = line.split(); n = int(f[3], 16)
            for i in range(n):
                lem = f[4 + 2 * i].lower()
                if "_" in lem: continue
                lem = lem.split("(")[0]
                out[lem].add(pos + f[0])
    return out


def cloze_items(test, uni, n=5000, seed=5):
    """amended (prereg): the blank is a symbol outside the 100 commonest -- a content token, by count"""
    rng = random.Random(seed); items = []; top = {w for w, c in uni.most_common(100)}
    pool = list(test); rng.shuffle(pool)
    for s in pool:
        syms = symbols(s, "LN")
        cand = [i for i in range(1, len(syms) - 1) if syms[i] in uni and syms[i] not in top]
        if not cand: continue
        i = rng.choice(cand); items.append((syms[i - 1], syms[i], syms[i + 1]))
        if len(items) >= n: break
    return items


def cloze(m, items):
    top1 = top5 = left1 = common1 = 0; reasons = True; kinds = collections.Counter()
    top = {x for x, n in m.uni.most_common(100)}
    common = next(x for x, n in m.uni.most_common() if x not in top)
    for l, w, r in items:
        f = m.fill(l, r); reasons &= all(len(x[1]) == 3 and x[1][2] > 0 for x in f)
        kinds[f[0][1][0]] += 1
        top1 += f[0][0] == w; top5 += w in [x[0] for x in f]
        lo = m.left.get(m.norm(l)); left1 += bool(lo) and lo[0][0] == w
        common1 += w == common
    n = len(items)
    return dict(top1=top1 / n, top5=top5 / n, left1=left1 / n, common1=common1 / n, reasons=reasons, kinds=dict(kinds))


def similarity(m, wn, words):
    hit = base = tot = 0; reasons = True; ex = []
    common = [w for w, c in m.uni.most_common(12)]
    for w in words:
        nb = m.similar(w, 10); reasons &= all(isinstance(c, int) and c > 0 for _, c in nb)
        if not nb: tot += 10; continue
        good = [v for v, c in nb if wn.get(v, set()) & wn[w]]
        hit += len(good); tot += 10
        base += sum(1 for v in [x for x in common if x != w][:10] if wn.get(v, set()) & wn[w])
        if len(ex) < 8 and good: ex.append((w, nb[:6]))
    return hit / max(1, tot), base / max(1, tot), reasons, ex


def main():
    selfcheck(__file__)
    if not os.path.exists(KAIKKI): say("G4: NOT RUN (the Wiktionary store is absent)"); return
    frac = float(sys.argv[sys.argv.index("--frac") + 1]) if "--frac" in sys.argv else 1.0
    train, test = corpus(frac)
    say(f"G4  A COUNTING MODEL OF TEXT (textmodel_prereg.md) -- {len(train)} training sentences, {len(test)} held-out; {time.time() - T0:.0f} s")
    m = TextModel(); info = m.learn(train); say(f"    learned: {info}  ({time.time() - T0:.0f} s)")
    m.save(MODEL); m2 = TextModel.load(MODEL)
    fails = []
    items = cloze_items(test, m.uni)
    c = cloze(m, items)
    say(f"    cloze on {len(items)} held-out blanks: top-1 {c['top1']:.3f}, top-5 {c['top5']:.3f}; left-only {c['left1']:.3f}; commonest word {c['common1']:.3f}; contexts used {c['kinds']}")
    m1 = c["top1"] >= 2 * c["common1"] and c["top1"] > c["left1"]
    say(f"M1  top-1 {c['top1']:.3f} vs commonest {c['common1']:.3f} and left-only {c['left1']:.3f}   [>= 2x and > -> {'PASS' if m1 else 'FAIL'}]")
    say(f"M2  top-5 {c['top5']:.3f}   [printed]")
    if not m1: fails.append("M1")
    for l, w, r in items[:6]:
        f = m.fill(l, r, 3); say(f"    e.g. '{l} ___ {r}' (truth '{w}') -> {[(x[0], x[1][0], x[1][2]) for x in f]}")
    wn = wordnet()
    rng = random.Random(9)
    # a test word needs a WordNet synonym in the vocabulary: lemmas sharing a synset
    by_syn = collections.defaultdict(set)
    for w, ss in wn.items():
        if m.uni.get(w, 0) >= 50:
            for s in ss: by_syn[s].add(w)
    cands = sorted({w for s, ws in by_syn.items() if len(ws) >= 2 for w in ws})
    words = rng.sample(cands, min(1000, len(cands)))
    p4, b4, r4, ex = similarity(m, wn, words)
    say(f"\n    similarity on {len(words)} words with a WordNet synonym in vocabulary: top-10 neighbours sharing a synset {p4:.3f}; frequency baseline {b4:.3f}")
    for w, nb in ex: say(f"    e.g. {w}: {nb}")
    m4 = p4 >= 3 * b4 and p4 > 0
    say(f"M4  {p4:.3f} vs {b4:.3f}   [>= 3x -> {'PASS' if m4 else 'FAIL'}]")
    if not m4: fails.append("M4")
    m6 = c["reasons"] and r4
    say(f"M6  every fill and neighbour carries its count reason: {m6}   [{'PASS' if m6 else 'FAIL'}]")
    if not m6: fails.append("M6")
    same = all(m.fill(l, r) == m2.fill(l, r) for l, w, r in items[:300]) and all(m.similar(w) == m2.similar(w) for w in words[:100])
    src = open(os.path.join(HERE, "core", "textmodel.py"), encoding="utf-8").read()
    imports = [l for l in src.splitlines() if l.startswith(("import ", "from "))]
    m7 = same and all(l in ("import collections", "import json", "from .reason import symbols") for l in imports)
    say(f"M7  save/load identical {same}; imports {imports}   [{'PASS' if m7 else 'FAIL'}]")
    if not m7: fails.append("M7")
    # ---- knockouts: the same corpus with each training sentence's words shuffled
    del m, m2; gc.collect()
    rng = random.Random(13); shuf = []
    for s in train:
        t = symbols(s, "LN"); rng.shuffle(t); shuf.append(" ".join(t))
    del train; gc.collect()
    mk = TextModel(); mk.learn(shuf); del shuf; gc.collect()
    ck = cloze(mk, items); pk, bk, _, _ = similarity(mk, wn, words)
    m3 = ck["top1"] < 0.6 * c["top1"]; m5 = pk < 0.5 * p4
    say(f"\nM3  knockout cloze top-1 {ck['top1']:.3f} = {ck['top1'] / max(1e-9, c['top1']):.0%} of M1   [< 60 % -> {'PASS' if m3 else 'FAIL'}]")
    say(f"M5  knockout similarity {pk:.3f} = {pk / max(1e-9, p4):.0%} of M4   [< 50 % -> {'PASS' if m5 else 'FAIL'}]")
    if not m3: fails.append("M3")
    if not m5: fails.append("M5")
    say("\nM8  REGISTERED NUMBERS")
    if "--quick" in sys.argv: say("    (skipped: --quick)")
    else:
        for f, args, needle in (("guess.py", ["--quick"], "G1: PASS"), ("chat.py", [], "ONE DOOR: PASS")):
            tt = time.time(); out = subprocess.run([sys.executable, f] + args, capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
            hit = needle in out; say(f"    {f:14s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
            if not hit: fails.append("M8")
    say(f"\nG4: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
