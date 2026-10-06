"""LOOP ITERATION 4 -- CONSTRUCTIONS LEARNED FROM NOVELS (novelgrammar_prereg.md). Zero LLM. Offline.

Usage:  python novelgrammar.py"""
import os, sys, re, json, time, random, hashlib, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.textmodel import TextModel
from core.constructions import FORWARD
from core.registry import selfcheck
from textmodel import MODEL, KAIKKI, held
import kb_constructions as KC
import kb_events as KE

T0 = time.time()
OUT = os.path.join(HERE, "_nldata", "constructions_books.json")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def b4_sentences():
    """the battery's B4 set: the first 10 held-out books, sentences of 4-60 words, at most 500 each"""
    out = []
    for b in KE.books(True)[:10]:
        text = open(os.path.join(KE.GUT, b + ".txt"), encoding="utf-8", errors="replace").read()
        out += [s for s in re.split(r"(?<=[.!?])\s+", text) if 4 <= len(s.split()) <= 60][:500]
    return out


def read_rate(R, sents):
    n = read = sup = con = 0; ex = []
    for s in sents:
        v, res = R.check(s); n += 1
        if res:
            read += 1; sup += sum(1 for _, x in res if x == "SUPPORTED"); con += sum(1 for _, x in res if x == "CONTRADICTED")
            if len(ex) < 6: ex.append((s, res))
    return n, read, sup, con, ex


def statements(R, store, common):
    """statements_prereg.md's F1 / F2 on the held-out dictionary sentences, with reader R"""
    by_type = collections.defaultdict(list)
    for q, cl in store.claims.items():
        for t in sorted(cl.get("P31", ()))[:1]:
            if q in store.lab: by_type[t].append(q)
    db = sqlite3.connect(KAIKKI); true = []
    for w, v in db.execute("select w, v from e"):
        if not held(w): continue
        e = json.loads(v); head = store.index.get(" ".join(symbols(w, "LN"))); defs = [str(x) for x in e.get("defs", [])]
        for s in defs + [str(x) for x in e.get("ex", [])]:
            h = head if s in defs else None; verdict, res = R.check(s, h)
            sup = [pr for pr, vv in res if vv == "SUPPORTED"]
            if sup: true.append((s, h, sup[0], verdict))
        if len(true) >= 2000: break
    f1 = sum(1 for s, h, pr, v in true if v == "SUPPORTED") / max(1, len(true)); cv = collections.Counter(); n = 0
    for s, h, pr, v in true:
        p, d = store.canon(*pr["lab"]); qa, qb = pr["pairs"][0]
        obj_m = pr["b"] if d == FORWARD else pr["a"]; subj = qa if d == FORWARD else qb; obj = qb if d == FORWARD else qa
        if obj_m[0] == obj_m[1]: continue
        ts = sorted(store.claims.get(obj, {}).get("P31", ()))[:1]
        if not ts: continue
        cands = [x for x in by_type[ts[0]] if x != obj and not store.holds({subj}, {x}, p, FORWARD)]
        if not cands: continue
        new = cands[int(hashlib.sha256(s.encode()).hexdigest(), 16) % len(cands)]
        syms, ms, (full, pos) = KC.tokens(s, store, common)
        lo, hi = pos[obj_m[0]], pos[obj_m[1] - 1] + 1
        verdict, _ = R.check(" ".join(full[:lo] + symbols(store.lab[new], "LN") + full[hi:]), h); cv[verdict] += 1; n += 1
    return f1, cv["SUPPORTED"] / max(1, n), len(true), n


def main():
    selfcheck(__file__)
    say("LOOP ITERATION 4 -- CONSTRUCTIONS LEARNED FROM NOVELS (novelgrammar_prereg.md)\n")
    store = KC.Store(); tm = TextModel.load(MODEL); common = {w for w, c in tm.uni.most_common(1000)}
    train_books = [os.path.join(KE.GUT, b + ".txt") for b in KE.books(False)]
    sents = b4_sentences(); say(f"    training books {len(train_books)}; B4 held-out sentences {len(sents)}")
    C0 = KC.learn(store, common, held=held)
    C1 = KC.learn(store, common, held=held, books=train_books)
    CK = KC.learn(store, common, held=held, books=train_books, shuffle_books=random.Random(5))
    say(f"    constructions: dictionary {len(C0.admitted)}, + books {len(C1.admitted)}, + shuffled books {len(CK.admitted)}  ({time.time() - T0:.0f} s)")
    r0 = read_rate(KC.Reader(store, C0, common), sents); r1 = read_rate(KC.Reader(store, C1, common), sents); rk = read_rate(KC.Reader(store, CK, common), sents)
    lab = lambda q: store.lab.get(q, q)
    for s, res in r1[4]:
        say(f"      {s[:80]!r}: " + "; ".join(f"{lab(pr['pairs'][0][0])} -{lab(pr['lab'][0])}- {lab(pr['pairs'][0][1])} [{v}]" for pr, v in res[:3]))
    fails = []
    n1 = r1[1] >= 0.05 * r1[0]
    say(f"N1  B4 read: dictionary-only {r0[1]}/{r0[0]}, with books {r1[1]}/{r1[0]} ({r1[1] / max(1, r1[0]):.2%})   [>= 5 % -> {'PASS' if n1 else 'FAIL'}]")
    prec = r1[2] / max(1, r1[2] + r1[3]); n2 = prec >= 0.85
    say(f"N2  precision on checkable propositions: {r1[2]}/{r1[2] + r1[3]} = {prec:.3f}   [>= 0.85 -> {'PASS' if n2 else 'FAIL'}]")
    f1, f2, nt, nc = statements(KC.Reader(store, C1, common), store, common)
    n3 = f1 >= 0.8 and f2 <= 0.01
    say(f"N3  statements with the books' constructions: true supported {f1:.1%} of {nt}, corrupted supported {f2:.2%} of {nc}   [>= 80 %, <= 1 % -> {'PASS' if n3 else 'FAIL'}]")
    gain = r1[1] - r0[1]; gk = rk[1] - r0[1]; n4 = gk < 0.25 * max(1, gain)
    say(f"N4  knockout gain {gk} vs main gain {gain}   [< 25 % -> {'PASS' if n4 else 'FAIL'}]")
    for ok, g in ((n1, "N1"), (n2, "N2"), (n3, "N3"), (n4, "N4")):
        if not ok: fails.append(g)
    KC.save(C1, OUT)
    say(f"\nITERATION 4: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; saved {OUT}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
