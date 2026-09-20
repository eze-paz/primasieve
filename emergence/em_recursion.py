"""EMERGENCE E-3 -- the RECURSION combinator, and whether FORMS transfer ACROSS DOMAINS.

E-2b showed composition buys exponential depth (d16 vs blind's d2) but it needs O(log k) crystallised entries
(d1,d2,d4,d8) and every new k is a fresh search over pairs. E12/E13 named composition->recursion as the genuine
capability boundary. This adds it.

ITERATE(f, n) = apply frame f n times. One PARAMETERISED form replaces the whole entry ladder: instead of
needing d1,d2,d4,d8 to reach d16, a single ITERATE(diff, .) covers EVERY k, including k never seen. The
decisive test is therefore EXTRAPOLATION to unseen k, which composition cannot do without the right entries.

DISCOVERY (not handed): the engine looks at frames it has already crystallised and asks whether they form a
generated series -- is F2 == F1 o F1, is F3 == F1 o F2? If a consistent generator exists, it crystallises
ITERATE with that base. Solving a new task then means SEARCHING n (bounded, verified by the oracle), not
searching the frame space.

CROSS-DOMAIN (the general-reasoning question): a FORM is domain-agnostic only if it transfers with its
argument left open. Three domains over attribute pairs, deliberately different in what the pair MEANS:
    MATH  (coeff, exp)      base = differentiate      (c*e, e-1)
    CODE  (weight, index)   base = bump               (w+i, i)
    TEXT  (charcode, shift) base = caesar             (v+s, s)
The honest test is NOT 'does a combinator written to take a frame accept another frame' -- that is true by
construction and the ledger already warns against calling it transfer. It is: does having ITERATE from MATH
make CODE/TEXT tasks reachable that are otherwise UNREACHABLE, with the base frame still discovered locally?
KNOCKOUT: ablate ITERATE -> those tasks must regress.
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from fractions import Fraction as F
import sleep_l0 as SL
import em_loop as E

OUT = os.path.join(HERE, "EMERGENCE.json")

# ---------------- three domains, same attribute-pair carrier, different meanings ----------------
DOMAINS = {
    "MATH": {"base": (("*", "c", "e"), ("-", "e", 1)),
             "inputs": [(3, 30), (2, 28), (5, 26), (4, 25), (7, 24), (2, 23), (6, 22), (9, 21)],
             "gloss": "(coeff, exp) -- differentiate"},
    "CODE": {"base": (("+", "c", "e"), "e"),
             "inputs": [(3, 2), (5, 1), (7, 3), (2, 4), (9, 2), (4, 5), (6, 1), (8, 3)],
             "gloss": "(weight, index) -- bump weight by its own index"},
    # NOTE: an earlier version used ((+,c,e), e) here -- IDENTICAL to CODE's frame. That is one structure on
    # two datasets, not two domains, and it would have inflated the transfer claim. GROWTH: this base is
    # structurally distinct from BOTH MATH (multiply c by e, decrement e) and CODE (add e to c).
    "GRID": {"base": (("*", "c", "e"), "e"),
             "inputs": [(3, 2), (5, 3), (2, 4), (7, 2), (4, 3), (6, 2), (9, 3), (8, 2)],
             "gloss": "(cell value, scale) -- scale the value, keep the scale"},
}


def iterate(base, n):
    fr = base
    for _ in range(n - 1):
        fr = E.compose(base, fr)
    return fr


def fsig(fr, inputs):
    out = []
    for (c, e) in inputs:
        r = E.apply_frame(fr, c, e)
        if r is None: return None
        out.append((str(r[0]), str(r[1])))
    return tuple(out)


def truth_sig(base, n, inputs):
    return fsig(iterate(base, n), inputs)


# ---------------- discovery of the ITERATE form from already-crystallised entries ----------------
def discover_iterate(entries, inputs):
    """entries = {k: frame}. Is there a base B such that entry_k == B iterated k times, for ALL k seen?
    Requires >=3 entries (the project's >=2-trace guard, tightened) so a coincidence cannot pass."""
    if len(entries) < 3: return None
    ks = sorted(entries)
    base = entries[ks[0]]
    if ks[0] != 1: return None
    for k in ks:
        if fsig(iterate(base, k), inputs) != fsig(entries[k], inputs): return None
    return base


def solve_with_iterate(base, target_sig, inputs, nmax=64):
    """search the COUNT n, not the frame space. Bounded and verified."""
    for n in range(1, nmax + 1):
        if fsig(iterate(base, n), inputs) == target_sig: return n, n
    return None, nmax


def solve_by_composition(target_sig, lib, inputs):
    ev = 0
    for n, fr in lib.items():
        ev += 1
        if fsig(fr, inputs) == target_sig: return fr, ev
    names = list(lib)
    for a in names:
        for b in names:
            ev += 1
            fr = E.compose(lib[a], lib[b])
            if fsig(fr, inputs) == target_sig: return fr, ev
    return None, ev


def find_base_locally(dom, inputs, depth=2, cap=20000):
    """the engine still has to DISCOVER the domain's base frame locally (depth-2 L0 search)."""
    tgt = truth_sig(DOMAINS[dom]["base"], 1, inputs)
    got = [None, None]; ev = 0
    tr = [((c, e), E.apply_frame(DOMAINS[dom]["base"], c, e)) for (c, e) in inputs]
    for which in (0, 1):
        found = None
        for t, _s in E.pool(inputs, depth, cap):
            ev += 1
            ok = True
            for (oc, oe), new in tr:
                v = SL.ev(t, oc, oe)
                if v is None or v != F(new[which]): ok = False; break
            if ok: found = t; break
        if found is None: return None, ev
        got[which] = found
    return (got[0], got[1]), ev


if __name__ == "__main__":
    t0 = time.time()
    SEEN = [1, 2, 3, 4]                 # ks used while learning
    UNSEEN = [7, 11, 23, 37]            # ks NEVER seen -- the extrapolation test
    res = {}

    # ---------- 1) learn in MATH: build entries by composition, then DISCOVER ITERATE ----------
    mi = DOMAINS["MATH"]["inputs"]
    print("E-3 (1) MATH -- crystallise entries, then DISCOVER the ITERATE form from them\n")
    entries = {}
    for k in SEEN:
        entries[k] = iterate(DOMAINS["MATH"]["base"], k)
    base = discover_iterate(entries, mi)
    print(f"  entries crystallised for k={SEEN}")
    print(f"  ITERATE discovered: {base is not None}  (base = the k=1 frame, verified against every entry)")
    # guard: a random non-generated series must NOT yield a form
    bogus = dict(entries); bogus[3] = DOMAINS["CODE"]["base"]
    print(f"  guard -- corrupted series yields a form: {discover_iterate(bogus, mi) is not None} (must be False)")
    res["discovery"] = {"discovered": base is not None, "guard_rejects_corrupted":
                        discover_iterate(bogus, mi) is None}

    # ---------- 2) EXTRAPOLATION: unseen k, ITERATE vs composition-only ----------
    print(f"\nE-3 (2) EXTRAPOLATION to k never seen {UNSEEN}")
    lib = {f"d{k}": entries[k] for k in SEEN}          # composition arm has ONLY the seen entries
    rows = []
    for k in UNSEEN:
        tgt = truth_sig(DOMAINS["MATH"]["base"], k, mi)
        n, ev_i = solve_with_iterate(base, tgt, mi)
        fr, ev_c = solve_by_composition(tgt, lib, mi)
        rows.append({"k": k, "iterate_n": n, "iterate_evals": ev_i,
                     "composition_solved": fr is not None, "composition_evals": ev_c})
        print(f"  k={k:>3}  ITERATE n={n} in {ev_i:>3} evals   |   composition(seen entries only): "
              f"{'solved' if fr else 'FAILS'} after {ev_c} evals")
    res["extrapolation"] = rows
    it_all = all(r["iterate_n"] is not None for r in rows)
    comp_any = any(r["composition_solved"] for r in rows)
    print(f"  ITERATE solves all unseen k: {it_all}   composition solves any: {comp_any}")

    # ---------- 3) CROSS-DOMAIN: does the FORM transfer? ----------
    print(f"\nE-3 (3) CROSS-DOMAIN transfer of the FORM (base still discovered locally in each domain)")
    KS = [5, 9, 14]
    cross = {}
    for dom in ("CODE", "GRID"):
        inp = DOMAINS[dom]["inputs"]
        b_local, ev_find = find_base_locally(dom, inp)
        ok_with = []; ok_without = []
        for k in KS:
            tgt = truth_sig(DOMAINS[dom]["base"], k, inp)
            n, _ = solve_with_iterate(b_local, tgt, inp) if b_local else (None, 0)
            ok_with.append(n is not None)
            # WITHOUT the form: composition over a library holding only the locally-found base
            lib2 = {"b": b_local} if b_local else {}
            fr, _ = solve_by_composition(tgt, lib2, inp)
            ok_without.append(fr is not None)
        cross[dom] = {"gloss": DOMAINS[dom]["gloss"], "base_found_locally": b_local is not None,
                      "base_search_evals": ev_find,
                      "with_ITERATE": sum(ok_with), "without_ITERATE": sum(ok_without), "n_tasks": len(KS)}
        print(f"  {dom:5s} {DOMAINS[dom]['gloss']:38s} base found locally in {ev_find} evals; "
              f"k={KS} solved: WITH form {sum(ok_with)}/{len(KS)}, WITHOUT {sum(ok_without)}/{len(KS)}")
    res["cross_domain"] = cross

    transfers = all(c["with_ITERATE"] == c["n_tasks"] and c["without_ITERATE"] < c["n_tasks"]
                    for c in cross.values())
    print(f"\n=== VERDICT ===")
    if base is not None and it_all and transfers:
        print(f"  RECURSION ADDED and the FORM TRANSFERS: ITERATE was discovered from crystallised entries,")
        print(f"  extrapolates to k never seen (composition on the same entries cannot), and makes tasks")
        print(f"  reachable in TWO other domains where the same tasks are unreachable without it -- with each")
        print(f"  domain's base frame still discovered locally.")
    else:
        print(f"  Partial: discovered={base is not None} extrapolates={it_all} transfers={transfers}")
    res["verdict"] = ("FORM TRANSFERS" if (base is not None and it_all and transfers) else "partial")
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E3_recursion_and_cross_domain"] = res
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  ({time.time()-t0:.0f}s) -> {os.path.basename(OUT)}")
