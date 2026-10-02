"""DIAGNOSTIC (read-only): is the unsolved skeleton's truth condition EXPRESSIBLE with the atoms nolf already has?

Measured today: every ingredient the recorded blocker names already exists as a 1-atom primitive -- `_positions`
(seq,elem)->seq and a successor (int)->int. So "positions/successor fragments no adopted construction supplies"
is not a missing-atom problem. And the natural target shape

    ALL( positions(S, _e), x. REL_r(x, first_pos(S, _e)) )

counts as FOUR atom applications, not five -- inside MAX_OPS=4, therefore already IN the shipped table. The
search tried 127 of 20,159 candidates in 120 s and never reached it.

This builds such terms BY HAND and hands them to the real `_fit_candidate` -- the unchanged denotation solve,
verification and evidence gate. A hit proves the target is expressible and reachable, which would mean the
ceiling is ORDERING, not depth and not the atom basis. A miss on every hand-built shape says the shape is wrong
and depth is still open.

Nothing here is a gate: hand-building a candidate is cheating for the purposes of a claim. It is legitimate for
answering "does a solution exist in this space at all", which nothing else today could answer.

    python nolf_handterm_probe.py --world strings --skel "['gloop', 6, 5, 6]"
"""
import os, sys, time, itertools, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_learn as NL
import nolf_fast as F

SIT = ("SIT",); VAR = ("VAR",)


def ident():
    """name the atoms by behaviour on probes that actually separate them."""
    out = {}
    for p in NL.P.pids():
        a, r = NL.P.signature(p)
        if not all(t in (NL.INT, NL.BOOL, NL.SEQ, NL.ELEM) for t in a): continue
        fn = NL.P._FN[p]
        try:
            if a == (NL.SEQ, NL.ELEM) and r == NL.INT:
                v = fn((7, 8, 8, 9), 8)
                out[{1: "first_pos", 2: "last_pos_or_count"}.get(v, f"se_int_{v}")] = p
                if v == 2:                                    # separate last_pos from count
                    out["last_pos" if fn((8, 7, 7, 7), 8) == 0 else "count"] = p
            elif a == (NL.SEQ, NL.ELEM) and r == NL.SEQ: out["positions"] = p
            elif a == (NL.SEQ, NL.ELEM) and r == NL.BOOL: out["member"] = p
            elif a == (NL.INT,) and r == NL.INT and fn(3) == 4: out["succ"] = p
            elif a == (NL.SEQ,) and r == NL.INT:
                v = fn((7, 8, 9)); out({7: "min", 9: "max", 3: "len"}.get(v, f"s_int_{v}") if False else
                                       {7: "min", 9: "max", 3: "len"}.get(v, f"s_int_{v}")) if False else None
                out[{7: "min", 9: "max", 3: "len"}.get(v, f"s_int_{v}")] = p
            elif a == (NL.SEQ, NL.INT) and r == NL.ELEM: out["at_elem"] = p
            elif a == (NL.SEQ, NL.INT) and r == NL.INT: out["at_int"] = p
            elif a == (NL.SEQ, NL.INT) and r == NL.SEQ: out["at_seq"] = p
            elif a == (NL.ELEM, NL.ELEM) and r == NL.BOOL: out["eq_elem"] = p
            elif a == (NL.INT, NL.INT) and r == NL.INT and fn(3, 3) == 6: out["add"] = p
            elif a == (NL.BOOL,) and r == NL.BOOL: out["not"] = p
        except Exception:
            pass
    return out


def candidates(A):
    """hand-built shapes for 'every X <rel> Y' over a sequence world, with their atom counts."""
    he, hr, hi = ("H", NL.HE), ("H", NL.HR), ("H", NL.HI)
    pos = lambda e: ("A", A["positions"], SIT, e)
    fp = lambda e: ("A", A["first_pos"], SIT, e)
    succ = lambda t: ("A", A["succ"], t)
    ate = lambda i: ("A", A["at_elem"], SIT, i)
    C = []
    # universal over the positions of one element, relating each to something about the other
    C += [("SK", "all", pos(he), ("R", VAR, fp(he)))]                       # 4 atoms
    C += [("SK", "all", pos(he), ("R", fp(he), VAR))]                       # 4
    C += [("SK", "any", pos(he), ("R", VAR, fp(he)))]                       # 4
    # 'x followed by y': every position of x has y at its successor
    if "eq_elem" in A:
        C += [("SK", "all", pos(he), ("A", A["eq_elem"], ate(succ(VAR)), he))]   # 5
        C += [("SK", "any", pos(he), ("A", A["eq_elem"], ate(succ(VAR)), he))]   # 5
    # universal over the whole situation
    C += [("SK", "all", SIT, ("R", fp(he), fp(he)))]                        # 3
    C += [("S", pos(he), ("R", VAR, fp(he)))]                               # 4, selector is a WORD (hs hole)
    C += [("S", pos(he), ("R", fp(he), VAR))]                               # 4
    if "eq_elem" in A:
        C += [("S", pos(he), ("A", A["eq_elem"], ate(succ(VAR)), he))]      # 5, selector-as-word
        C += [("SK", "all", pos(he), ("A", A["eq_elem"], ate(("A", A["succ"], VAR)), he))]
    return C


def main(world, skel):
    W, train, L, probes, elems, rels, sels = F._setup(world)
    E = F.table(world, probes, elems, rels, sels, 4, 60000, None)
    g = F.groups_of(L, train)
    keys = {F.show_key(k): k for k in g}
    if skel not in keys:
        print("no such skeleton; run nolf_fast.py --list"); return
    A = ident()
    print("atoms identified:", {k: v[:6] for k, v in sorted(A.items())}, flush=True)

    F.warmup(world, L, g, E)

    key = keys[skel]; rows = list(g[key])
    nslots = sum(1 for x in key if x != "B" and x[0] == "C") + sum(1 for x in key if x == "B")
    print(f"target {skel}: {len(rows)} rows, {nslots} slots\n", flush=True)

    for term in candidates(A):
        hs = NL.holes(term)
        tag = f"ops={NL.ops(term)} holes={hs}"
        if len(hs) != nslots:
            print(f"  skip  {tag:34s} (needs {nslots} holes)  {NL.show(term)}"); continue
        hit = None
        L.deadline = time.time() + 45
        for perm in itertools.permutations(range(nslots)):
            try:
                f = NL.compile_term(term)
            except Exception:
                break
            doms = L._initial_domains(rows, hs, perm)
            if doms is None: continue
            d = L._fit_candidate(f, rows, hs, perm, doms)
            if d is not None: hit = (perm, d); break
        if hit:
            print(f"  *** FITS *** {tag}  perm={hit[0]}  {NL.show(term)}", flush=True)
            for k2, v in sorted(hit[1].items(), key=lambda kv: repr(kv[0]))[:6]:
                print(f"        {k2} = {sorted(v)[:4] if len(v)>1 else next(iter(v))!r}")
        else:
            print(f"  no fit {tag:34s}  {NL.show(term)}", flush=True)


if __name__ == "__main__":
    a = sys.argv
    main(a[a.index("--world") + 1] if "--world" in a else "strings",
         a[a.index("--skel") + 1] if "--skel" in a else "['gloop', 6, 5, 6]")
