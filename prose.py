"""C2 + C5 -- READING PROSE WITH A RESIDUE; TWO PROPOSITIONS IN ONE SENTENCE (prose_prereg.md). Zero LLM. Offline.

Usage:  python prose.py"""
import os, sys, re, json, time, random, sqlite3, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.textmodel import TextModel
from core.constructions import Constructions
from core.registry import selfcheck
from textmodel import MODEL, KAIKKI, held
import kb_constructions as KC

T0 = time.time()
ALICE = os.path.join(HERE, "_nldata", "alice.txt")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def measure(R, sents, closed):
    """-> dict of counts over (source, sentence, head) items"""
    st = collections.defaultdict(collections.Counter); residues = collections.defaultdict(list); multi = []; ex = collections.defaultdict(list)
    for src, s, h in sents:
        st[src]["sentences"] += 1
        verdict, res = R.check(s, h)
        if not res: continue
        st[src]["read"] += 1
        for pr, v in res: st[src][v] += 1
        syms = res[0][0]["syms"]
        acc = set()
        for pr, v in res:
            for m in (pr["a"], pr["b"]): acc.update(range(m[0], m[1]))
            acc.update(range(pr["a"][1], pr["b"][0]))
        opn = [p for p, x in enumerate(syms) if x not in closed and x[:1].isalpha()]
        if opn: residues[src].append(sum(1 for p in opn if p not in acc) / len(opn))
        if len(res) >= 2: multi.append((src, s, res))
        if len(ex[src]) < 4: ex[src].append((s, res))
    return st, residues, multi, ex


def main():
    selfcheck(__file__)
    say("C2 + C5  READING PROSE WITH A RESIDUE; TWO PROPOSITIONS IN ONE SENTENCE (prose_prereg.md)\n")
    store = KC.Store(); tm = TextModel.load(MODEL)
    common = {w for w, c in tm.uni.most_common(1000)}; closed = {w for w, c in tm.uni.most_common(100)}
    if not os.path.exists(KC.SAVED): say("C2: NOT RUN (run statements.py first; it saves the training-split constructions)"); return
    C = KC.load(); R = KC.Reader(store, C, common)
    sents = []; db = sqlite3.connect(KAIKKI)
    for w, v in db.execute("select w, v from e"):
        if not held(w): continue
        e = json.loads(v); head = store.index.get(" ".join(symbols(w, "LN")))
        for s in e.get("defs", []): sents.append(("definitions", str(s), head))
        for s in e.get("ex", []): sents.append(("examples", str(s), None))
    text = open(ALICE, encoding="utf-8", errors="replace").read()
    sents += [("alice", s.strip(), None) for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 3]
    say(f"    held-out sentences: {collections.Counter(x[0] for x in sents)}  ({time.time() - T0:.0f} s)")
    st, residues, multi, ex = measure(R, sents, closed)
    lab = lambda q: store.lab.get(q, q)
    for src in ("definitions", "examples", "alice"):
        c = st[src]; say(f"    {src:12s} read {c['read']}/{c['sentences']} ({c['read'] / max(1, c['sentences']):.1%}); supported {c['SUPPORTED']}, contradicted {c['CONTRADICTED']}, unknown {c['UNKNOWN']}; residue {sum(residues[src]) / max(1, len(residues[src])):.2f}")
        for s, res in ex[src][:3]:
            props = "; ".join(f"{lab(pr['pairs'][0][0])} -{lab(pr['lab'][0])} {pr['lab'][1]}- {lab(pr['pairs'][0][1])} [{v}]" for pr, v in res[:3])
            say(f"      {s[:80]!r}: {props}")
    fails = []
    cov = {src: st[src]["read"] / max(1, st[src]["sentences"]) for src in st}
    p1 = cov.get("definitions", 0) >= 0.15 and cov.get("examples", 0) >= 0.03
    say(f"P1  coverage: definitions {cov.get('definitions', 0):.1%}, examples {cov.get('examples', 0):.1%}, Alice {cov.get('alice', 0):.2%}   [>= 15 %, >= 3 % -> {'PASS' if p1 else 'FAIL'}]")
    S = sum(st[x]["SUPPORTED"] for x in st); X = sum(st[x]["CONTRADICTED"] for x in st)
    prec = S / max(1, S + X); p2 = prec >= 0.85
    say(f"P2  precision on checkable propositions: {S}/{S + X} = {prec:.3f}   [>= 0.85 -> {'PASS' if p2 else 'FAIL'}]")
    allres = [r for x in residues.values() for r in x]
    say(f"P3  mean residue (open-class symbols unaccounted for) in read sentences: {sum(allres) / max(1, len(allres)):.2f}   [printed]")
    keys = sorted(C.admitted); vals = [C.admitted[k] for k in keys]; random.Random(9).shuffle(vals)
    K = Constructions(max_len=7); K.admitted = dict(zip(keys, vals))
    stk, _, _, _ = measure(KC.Reader(store, K, common), [x for x in sents if x[0] != "alice"][:60000], closed)
    Sk = sum(stk[x]["SUPPORTED"] for x in stk); Xk = sum(stk[x]["CONTRADICTED"] for x in stk)
    pk = Sk / max(1, Sk + Xk); p4 = pk < 0.6
    say(f"P4  knockout (readings shuffled): precision {Sk}/{Sk + Xk} = {pk:.3f}   [< 0.6 -> {'PASS' if p4 else 'FAIL'}]")
    for ok, g in ((p1, "P1"), (p2, "P2"), (p4, "P4")):
        if not ok: fails.append(g)
    say(f"\nC2: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}")
    ms = sum(1 for src, s, res in multi for pr, v in res if v == "SUPPORTED"); mx = sum(1 for src, s, res in multi for pr, v in res if v == "CONTRADICTED")
    mprec = ms / max(1, ms + mx)
    for src, s, res in multi[:4]:
        say(f"      {s[:70]!r}: " + "; ".join(f"{lab(pr['pairs'][0][0])} -{lab(pr['lab'][0])}- {lab(pr['pairs'][0][1])} [{v}]" for pr, v in res[:4]))
    c5a = len(multi) >= 200; c5b = mprec >= 0.85
    say(f"C5a sentences with two or more propositions read: {len(multi)}   [>= 200 -> {'PASS' if c5a else 'FAIL'}]")
    say(f"C5b precision on them: {ms}/{ms + mx} = {mprec:.3f}   [>= 0.85 -> {'PASS' if c5b else 'FAIL'}]")
    say(f"\nC5: {'PASS' if c5a and c5b else 'FAIL ' + ','.join(g for ok, g in ((c5a, 'C5a'), (c5b, 'C5b')) if not ok)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
