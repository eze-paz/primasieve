"""GRADED -- the gate on core/guide.py: a graded signal inside search, the verdict still binary (graded_prereg.md;
EMERGENCE_PLAN.md S1). Zero LLM. Stdlib only. Random targets over the exec term language, three arms on identical
targets and examples: BLIND (the shipped core.exec.synth), GUIDED (core.guide.best_first under lookahead-match),
SHUFFLED (the same queue under a random score -- the knockout of the signal).

Usage:  python graded.py [--targets N] [--cap APPS]"""
import os, sys, time, random, statistics, collections
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import primitives as P
from core.exec import synth, ev, Library, apply_op, X, CONSTS
from core.generate import SignatureBank
from core.guide import best_first
from core.registry import selfcheck

T0 = time.time()
XS = (Fraction(1), Fraction(2), Fraction(3), Fraction(5))
FRESH = tuple(Fraction(v) for v in range(4, 30) if Fraction(v) not in XS)[:20]
UNARY = [p for p in P.pids() if P.signature(p) == ((P.RAT,), P.RAT)]
BINARY = [p for p in P.pids() if P.signature(p) == ((P.RAT, P.RAT), P.RAT)]
LIB = Library()
N = len(XS)


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def size(t): return 1 if not isinstance(t, tuple) else 1 + sum(size(c) for c in t[1:])


def has_x(t): return t == X or (isinstance(t, tuple) and any(has_x(c) for c in t[1:]))


def vals_of(t): return tuple(ev(t, x, LIB) for x in XS)


def random_tree(rng, s):
    """a random tree of exactly s nodes over the language (leaves x, 1, 2)."""
    if s == 1: return rng.choice((X, X, 1, 2))
    if s == 2 or rng.random() < 0.3: return (rng.choice(UNARY), random_tree(rng, s - 1))
    ls = rng.randint(1, s - 2); return (rng.choice(BINARY), random_tree(rng, ls), random_tree(rng, s - 1 - ls))


def blind_table(max_size=9):
    """the shipped enumerator's order, recorded once: signature -> (tree, evaluation index, size). Verified below
    against core.exec.synth on sampled targets (same evaluation count), so the table IS the blind arm."""
    bank = SignatureBank(); by = bank.by_size; n = [0]; table = {}
    def add(sz, tree):
        n[0] += 1; vals = tuple(ev(tree, x, LIB) for x in XS)
        if any(v is None for v in vals): return
        if bank.add(tree, vals, size=sz, payload=None): table[vals] = (tree, n[0], sz)
    for leaf in (X,) + CONSTS: add(1, leaf)
    for sz in range(2, max_size + 1):
        for u in UNARY:
            for ctree, _, _ in list(by[sz - 1]): add(sz, (u, ctree))
        for ls in range(1, sz - 1):
            rs = sz - 1 - ls
            for ltree, _, _ in list(by[ls]):
                for rtree, _, _ in list(by[rs]):
                    for b in BINARY: add(sz, (b, ltree, rtree))
    return table, n[0]


def main():
    args = sys.argv[1:]
    want = int(args[args.index("--targets") + 1]) if "--targets" in args else 60
    CAP = int(args[args.index("--cap") + 1]) if "--cap" in args else 100000
    HYBRID = int(args[args.index("--hybrid") + 1]) if "--hybrid" in args else None     # S1b: blind through this size, guided beyond
    SEED = int(args[args.index("--seed") + 1]) if "--seed" in args else 2026
    GUIDED = HYBRID if HYBRID is not None else True
    SCORE = args[args.index("--score") + 1] if "--score" in args else "lookahead"      # "lookahead" (charged) | "match" (free)
    selfcheck(__file__)
    say(f"S1{'b HYBRID' if HYBRID else ''} GRADED SEARCH (graded_prereg.md): {want} targets (seed {SEED}), cap {CAP} applications per arm, n = {N} examples at x = {[int(x) for x in XS]}; score {SCORE}" + (f"; blind through size {HYBRID}, the bank seeding the queue, guided beyond" if HYBRID else ""))
    table, total = blind_table()
    say(f"  blind space to size 9: {total} evaluations, {len(table)} distinct signatures")

    # ---- the blind table is the shipped enumerator: identical evaluation counts on sampled targets
    rng = random.Random(11); checked = 0
    for vals, (tree, idx, sz) in rng.sample(sorted(table.items(), key=lambda kv: kv[1][1]), 6):
        t2, n2 = synth(list(zip(XS, vals)), LIB, max_size=9, cap=10 ** 6)
        assert n2 == idx and vals_of(t2) == vals, (idx, n2)
        checked += 1
    say(f"  table verified against core.exec.synth on {checked} targets: identical evaluation counts")

    # ---- targets: random trees whose blind MINIMAL size is 5..9 (reachable; the question is cost)
    DEEP = int(args[args.index("--deep") + 1]) if "--deep" in args else 0        # at least this many targets of minimal size >= 8
    rng = random.Random(SEED); targets = []; seen = set(); drawn = 0
    ndeep = lambda: sum(1 for _, _, _, s, _ in targets if s >= 8)
    while (len(targets) < want or ndeep() < DEEP) and drawn < 60000:
        drawn += 1; t = random_tree(rng, rng.randint(5, 9))
        if not has_x(t): continue
        vals = vals_of(t)
        if any(v is None for v in vals) or vals in seen or vals not in table: continue
        btree, bidx, bsz = table[vals]
        if not 5 <= bsz <= 9: continue
        if len(targets) >= want and bsz < 8: continue           # past the quota, only deep targets are still wanted
        seen.add(vals); targets.append((vals, btree, bidx, bsz, t))
    say(f"  targets: {len(targets)} from {drawn} draws; minimal sizes {dict(sorted(collections.Counter(s for _, _, _, s, _ in targets).items()))}")

    # ---- the three arms
    apply = lambda op, *a: apply_op(op, list(a), LIB)
    leaves = [(X, list(XS))] + [(c, [Fraction(c)] * N) for c in CONSTS]
    consts = list(CONSTS)                   # int leaves, as the tree grammar spells them (apply_op converts)
    res = {"BLIND": [], "GUIDED": [], "SHUFFLED": []}; confab = collections.Counter(); spurious = collections.Counter()
    for k, (vals, btree, bidx, bsz, t) in enumerate(targets):
        ex = list(zip(XS, vals))
        bapps = bidx * N
        res["BLIND"].append((bapps if bapps <= CAP else None, btree if bapps <= CAP else None))
        gt, gapps = synth(ex, LIB, max_size=9, cap=CAP, guided=GUIDED, score=SCORE)
        res["GUIDED"].append((gapps if gt is not None else None, gt))
        srng = random.Random(1000 + k)
        st, sapps = best_first(list(XS), vals, leaves, UNARY, BINARY, consts, apply, cap=CAP, max_size=9,
                               score=lambda v: (srng.random(), None, 0))
        if st is not None and vals_of(st) != vals: st = None            # the door (never fired: counted below)
        res["SHUFFLED"].append((sapps if st is not None else None, st))
        for arm, tree in (("BLIND", btree if bapps <= CAP else None), ("GUIDED", gt), ("SHUFFLED", st)):
            if tree is None: continue
            if vals_of(tree) != vals: confab[arm] += 1
            elif any(ev(tree, x, LIB) != ev(t, x, LIB) for x in FRESH): spurious[arm] += 1
        if k < 12 or k % 10 == 0:
            say(f"    t{k:02d} size {bsz}  blind {bapps:>7}  guided {gapps:>7}{'' if gt is not None else ' (none)'}  shuffled {sapps:>7}{'' if st is not None else ' (none)'}")

    def solved(arm): return sum(1 for a, _ in res[arm] if a is not None)
    both = [(b, g) for (b, _), (g, _) in zip(res["BLIND"], res["GUIDED"]) if b is not None and g is not None]
    both_s = [(b, s) for (b, _), (s, _) in zip(res["BLIND"], res["SHUFFLED"]) if b is not None and s is not None]
    ratio_g = statistics.median(b / g for b, g in both) if both else 0.0
    ratio_s = statistics.median(b / s for b, s in both_s) if both_s else 0.0
    worse = [(b, g) for b, g in both if g > b]
    worst = max((g / b for b, g in worse), default=0.0)
    by_size = collections.defaultdict(list); sh_size = collections.defaultdict(list)
    for (b, _), (g, _), (s, _), (_, _, _, sz, _) in zip(res["BLIND"], res["GUIDED"], res["SHUFFLED"], targets):
        if b is not None and g is not None: by_size[sz].append(b / g)
        if b is not None and s is not None: sh_size[sz].append(b / s)
    say("")
    g1 = solved("GUIDED") >= solved("BLIND")
    say(f"G1  REACH under cap {CAP}: BLIND {solved('BLIND')}/{len(targets)}  GUIDED {solved('GUIDED')}/{len(targets)}  SHUFFLED {solved('SHUFFLED')}/{len(targets)}   [guided >= blind -> {'PASS' if g1 else 'FAIL'}]")
    deep = [r for s, v in by_size.items() if s >= 8 for r in v]; shallow = [r for s, v in by_size.items() if s <= 7 for r in v]
    if HYBRID:
        g2 = bool(deep) and statistics.median(deep) >= 2.0 and all(abs(r - 1.0) < 1e-9 for r in shallow)
        say(f"G2b COST: median ratio on minimal size >= 8 ({len(deep)} targets) = {statistics.median(deep) if deep else 0:.2f}; sizes <= 7 identical to blind: {all(abs(r - 1.0) < 1e-9 for r in shallow)}; by size {{{', '.join(f'{s}: {statistics.median(v):.2f} (n={len(v)})' for s, v in sorted(by_size.items()))}}}   [deep >= 2.0, shallow == 1.0 -> {'PASS' if g2 else 'FAIL'}]")
    else:
        g2 = ratio_g >= 2.0
        say(f"G2  COST: median applications(BLIND)/applications(GUIDED) over {len(both)} both-solved = {ratio_g:.2f}; by minimal size {{{', '.join(f'{s}: {statistics.median(v):.2f} (n={len(v)})' for s, v in sorted(by_size.items()))}}}   [>= 2.0 -> {'PASS' if g2 else 'FAIL'}]")
    g3 = ratio_s < 2.0 and solved("SHUFFLED") <= solved("BLIND")
    say(f"G3  ATTRIBUTION: SHUFFLED median ratio {ratio_s:.2f}, solved {solved('SHUFFLED')} (blind {solved('BLIND')}); shuffled by size {{{', '.join(f'{s}: {statistics.median(v):.2f} (n={len(v)})' for s, v in sorted(sh_size.items()))}}}   [shuffled < 2.0 and no more solved -> {'PASS' if g3 else 'FAIL'}]")
    g4 = sum(confab.values()) == 0 and spurious["GUIDED"] <= spurious["BLIND"] + 2
    say(f"G4  SOUNDNESS: CONFAB {dict(confab) or 0}; spurious (reproduces the 4 examples, differs from the target on 20 fresh x) {dict(spurious)}   [confab 0, guided spurious <= blind + 2 -> {'PASS' if g4 else 'FAIL'}]")
    say(f"G5  DECEPTION (recorded): GUIDED costlier than BLIND on {len(worse)}/{len(both)} both-solved targets; worst ratio {worst:.2f}x")

    # ---- G6: the registered numbers do not move; W3 under guided=True still binds quop
    import subprocess
    from core.exec import ExecWorld
    from core.reason import reason
    tn = subprocess.run([sys.executable, "tables_numbers.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
    wg = subprocess.run([sys.executable, "worlds_general.py"], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
    ok_tn = "TABLES AND NUMBERS: PASS -- correct 30/30, CONFAB 0" in tn; ok_wg = "GENERAL WORLDS: PASS" in wg and "TOTAL CONFAB: 0" in wg
    exec_teach = [("what is 3 times 4", 12), ("what is 5 times 6", 30), ("what is 2 times 9", 18), ("what is 7 plus 1", 8),
                  ("what is 2 plus 5", 7), ("what is 9 minus 4", 5), ("what is 8 minus 3", 5),
                  ("what is the double of 4", 8), ("what is the double of 7", 14), ("what is the double of 10", 20)]
    tw = lambda x: 2 * x + 1; bl = lambda x: 2 * x - 1; qu = lambda x: tw(tw(tw(x)))
    exec_teach += [(f"what is the twiddle of {x}", tw(x)) for x in (3, 5, 7, 10)] + [(f"what is the blorp of {x}", bl(x)) for x in (2, 4, 6, 9)]
    w = ExecWorld(name="exec"); r0 = w.induce_lexicon(exec_teach, guided=GUIDED, score=SCORE); w.sleep()
    r = w.induce_lexicon([(f"what is the quop of {x}", qu(x)) for x in (1, 2, 3, 4)], guided=GUIDED, score=SCORE)
    fr = reason("what is the quop of 5", w, cats="LN")
    quop_ok = fr["kind"] == "commit" and fr["answers"] and Fraction(str(fr["answers"][0][1])) == 47
    heldx = [("what is 6 times 7", 42), ("what is 11 plus 12", 23), ("what is 20 minus 8", 12), ("what is the double of 9", 18),
             ("what is the twiddle of 8", 17), ("what is the blorp of 11", 21), ("what is the quop of 2", 23), ("what is the double of 3 times 4", 24),
             ("what is the twiddle of 2 plus 5", 15), ("what is 100 minus 1", 99), ("what is the blorp of the double of 3", 11), ("what is 4 times 25", 100)]
    hc = collections.Counter()
    for q, g in heldx:
        f = reason(q, w, cats="LN")
        if f["kind"] == "commit" and len(f["answers"]) == 1: hc["correct" if Fraction(str(f["answers"][0][1])) == g else "confab"] += 1
        else: hc["other"] += 1
    g6 = ok_tn and ok_wg and quop_ok and hc["confab"] == 0
    say(f"G6  REGISTERED NUMBERS: tables_numbers {'30/30' if ok_tn else 'MOVED'}; worlds_general {'PASS' if ok_wg else 'MOVED'}; W3 under guided=True: searched {[(wd, n) for wd, t, n in r0['searched'] + r['searched']]}, quop of 5 -> {fr['kind']} {[a[1] for a in fr['answers']]}, held-out {dict(hc)}   [{'PASS' if g6 else 'FAIL'}]")

    verdict = "PASS" if (g1 and g2 and g3 and g4 and g6) else ("SOUND" if (g4 and g6 and g3) else "NULL")
    say(f"\nCONFAB: {sum(confab.values())}")
    say(f"S1{'b HYBRID' if HYBRID else ''} GRADED SEARCH ({SCORE}): {verdict} -- reach blind {solved('BLIND')} guided {solved('GUIDED')} shuffled {solved('SHUFFLED')} of {len(targets)}; median cost ratio {ratio_g:.2f} (shuffled {ratio_s:.2f}); deception {len(worse)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
