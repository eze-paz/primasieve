"""DIAGNOSTIC: can nolf's term language express a construction that mentions the SAME slot word twice?

The sealed strings describer's hardest predicate is

    idx = [i for i,a in enumerate(s) if a == x]
    tv  = bool(idx) and all(i+1 < len(s) and s[i+1] == y for i in idx)

so its truth condition is AND( member(S,x), ALL(positions(S,x), i. eq(at(S,succ(i)), y)) ) -- and x occurs
TWICE. The non-emptiness conjunct is not decoration: ALL over an empty sequence is vacuously true while the
target is false, and x is absent from a 4-8 symbol string over 4 letters in roughly 10-32% of rows, so dropping
it fails verification on a large minority.

nolf requires `len(holes(term)) == nslots` and passes a PERMUTATION of the slot indices, so a term that binds one
slot twice is not merely unreachable -- it is unrepresentable, and every candidate of that shape is discarded
before the solver sees it (`if len(hs) != nslots: continue`).

That is a DEGREE-4 limit in core/grow.py's sense: the representation cannot STATE the distinction. Today's
collision probe returned 0 collisions and did not detect it, because collisions test whether
(situation, fill) -> truth is a consistent function, which it is. The representation just cannot write it.

This probe tests the claim directly: build the term by hand, hand it a NON-INJECTIVE slot mapping (0,0,1), and
ask the real `_fit_candidate` whether it fits. `_env_pool` indexes `fill[perm[j]]`, so a mapping works
mechanically -- injectivity is a convention in the candidate loop, not a requirement of the machinery.

    python nolf_reuse_probe.py --world strings
"""
import os, sys, time, itertools, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_learn as NL
import nolf_fast as F
from nolf_handterm_probe import ident

SIT = ("SIT",); VAR = ("VAR",)


def and_or(A):
    """separate AND from OR: both are (bool,bool)->bool and agree on (True,True)."""
    out = {}
    for p in NL.P.pids():
        if NL.P.signature(p) != ((NL.BOOL, NL.BOOL), NL.BOOL): continue
        out["and" if NL.P._FN[p](True, False) is False else "or"] = p
    return out


def main(world):
    W, train, L, probes, elems, rels, sels = F._setup(world)
    E = F.table(world, probes, elems, rels, sels, 4, 60000, None)
    g = F.groups_of(L, train)
    F.warmup(world, L, g, E)
    A = ident(); A.update(and_or(A))
    need = ["and", "member", "positions", "at_elem", "succ", "eq_elem"]
    missing = [n for n in need if n not in A]
    if missing:
        print("missing atoms, cannot build the term:", missing); return
    print("atoms:", {n: A[n][:6] for n in need}, flush=True)

    key = next((k for k in g if F.show_key(k) == "['gloop', 6, 5, 6]"), None)
    if key is None: print("target skeleton absent"); return
    rows = list(g[key])

    # DEMOTE the middle slot the way _learn_key would: the class-5 word becomes part of the construction, so the
    # remaining slots are (x, y) -- exactly two.
    mids = collections.Counter(r[1][1] for r in rows)
    print(f"target {F.show_key(key)}: {len(rows)} rows; middle-slot words {dict(mids)}", flush=True)
    dem = [(sit, (fill[0], fill[2]), tv) for sit, fill, tv in rows]
    nslots = 2

    he = ("H", NL.HE)
    pos = ("A", A["positions"], SIT, he)
    body = ("A", A["eq_elem"], ("A", A["at_elem"], SIT, ("A", A["succ"], VAR)), he)
    full = ("A", A["and"], ("A", A["member"], SIT, he), ("SK", "all", pos, body))
    novac = ("SK", "all", pos, body)                      # the same thing WITHOUT the non-emptiness conjunct

    for name, term, perm in [
        ("with non-emptiness (x twice)", full, (0, 0, 1)),
        ("without non-emptiness (x once)", novac, (0, 1)),
    ]:
        hs = NL.holes(term)
        print(f"\n--- {name}: ops={NL.ops(term)} holes={hs} slots={nslots} perm={perm}")
        print(f"    {NL.show(term)}")
        if len(hs) != nslots:
            print(f"    >>> the real candidate loop DISCARDS this shape: len(holes)={len(hs)} != nslots={nslots}")
        try:
            f = NL.compile_term(term)
        except Exception as e:
            print("    compile failed:", e); continue
        doms = L._initial_domains(dem, hs, perm)
        if doms is None:
            print("    no initial domains"); continue
        L.deadline = time.time() + 120
        d = L._fit_candidate(f, dem, hs, perm, doms)
        if d is not None:
            print("    *** FITS *** (real denotation solve + verification + evidence gate)")
            for k2, v in sorted(d.items(), key=lambda kv: repr(kv[0])):
                print(f"        {k2} = {next(iter(v))!r}" if len(v) == 1 else f"        {k2} = {sorted(v)[:5]}")
        else:
            print("    no fit")


if __name__ == "__main__":
    a = sys.argv
    main(a[a.index("--world") + 1] if "--world" in a else "strings")
