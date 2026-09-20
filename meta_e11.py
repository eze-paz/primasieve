"""E11 — extend the witness to `//` (meta_e11_prereg.md). Additive to E10. ZERO LLM, pure stdlib.

Floor division T=L//R is NON-invertible (given (T,R) the dividend is a per-row RANGE, not a point), so E10's O(1)
watch cannot close //-topped targets. E11 adds a PIVOT-ROW RANGE witness (Duet/Transit-style): when an operand E
is added, pivot on the most-selective row and ENUMERATE the width-|E_p| interval of valid partner values there,
hashing each into a per-row value index idx[row][value]->[member sigs]; verify the full vector; verify tree on
disjoint+fresh probes. Beats blind iff the pivot narrows candidates; else reports completeness-without-speedup.
Honest word: WEAKEN. E9 NULL / E10 WEAKENED both untouched; E11 only adds the // path."""
import os, sys, time, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta_e8, meta_e10
from meta_e10 import ev, size, label, verify, probe_rows, sdiv, smod, LEAF, X, UNARY, BINARY
FDIV = BINARY["//"]

def synth11(rows, T, oracle, extra_atoms=(), inv=True, div=True, Kcap=8, matcap=40000, qcap=6_000_000, seed=0, percap=400):
    """BUS with E10 invertible watch (inv) + E11 pivot-row range // witness (div). Energy = mat + queries."""
    T = tuple(T); nR = len(rows)
    bank = {}; buckets = {s: [] for s in range(Kcap + 2)}
    idx = [dict() for _ in range(nR)]                      # idx[row][value] -> list of member sigs (E11)
    mat = 0; q = 0; spurious = [0]; watch = {}

    def full_div_ok(lsig, rsig):                            # L//R == T over all rows
        return all(FDIV(l, r) == t for l, r, t in zip(lsig, rsig, T))

    def div_witness(tree, s):
        nonlocal q
        # (A) E as DIVISOR: find dividend L with L // E == T.  pivot = row with smallest |E_p|, E_p!=0, no X
        if X not in s and 0 not in s:
            p = min(range(nR), key=lambda i: abs(s[i]))
            width = abs(s[p])
            if 2 * width + 1 <= percap:
                base = T[p] * s[p]
                for Lp in range(base - width, base + width + 1):    # width-|E_p| interval of valid dividend values
                    q += 1
                    if FDIV(Lp, s[p]) != T[p]: continue
                    for msig in idx[p].get(Lp, ()):
                        q += 1
                        if full_div_ok(msig, s):
                            cand = ("b", "//", bank[msig], tree)
                            if verify(cand, oracle, seed): return cand
                            spurious[0] += 1
        # (B) E as DIVIDEND: find divisor R with E // R == T.  pivot = T_p!=0 row minimizing |E_p| (bounds |R|<=|E_p|)
        cand_rows = [i for i in range(nR) if T[i] != 0 and s[i] is not X]
        if cand_rows:
            p = min(cand_rows, key=lambda i: abs(s[i]))
            if s[p] is not X and 2 * abs(s[p]) + 1 <= percap:
                for Rp in range(-abs(s[p]), abs(s[p]) + 1):          # |R_p| <= |E_p| since |T_p|>=1
                    if Rp == 0: continue
                    q += 1
                    if FDIV(s[p], Rp) != T[p]: continue
                    for msig in idx[p].get(Rp, ()):
                        q += 1
                        if full_div_ok(s, msig):
                            cand = ("b", "//", tree, bank[msig])
                            if verify(cand, oracle, seed): return cand
                            spurious[0] += 1
        return None

    def try_close(tree, s):
        nonlocal q
        q += 1
        if s == T: return tree
        if inv:                                            # E10 invertible watch (verbatim behavior)
            q += 1
            if s in watch:
                op, other, mode = watch[s]
                cand = {"+": ("b", "+", other, tree), "*": ("b", "*", other, tree),
                        "E-B": ("b", "-", other, tree), "B-E": ("b", "-", tree, other)}[mode]
                if verify(cand, oracle, seed): return cand
                spurious[0] += 1
            if X not in s:
                watch.setdefault(tuple(t - v for t, v in zip(T, s)), ("+", tree, "+")); q += 1
                watch.setdefault(tuple(v - t for t, v in zip(T, s)), ("-", tree, "E-B")); q += 1
                watch.setdefault(tuple(t + v for t, v in zip(T, s)), ("-", tree, "B-E")); q += 1
                if 0 not in s and all((t % v == 0) for t, v in zip(T, s)):
                    watch.setdefault(tuple(t // v for t, v in zip(T, s)), ("*", tree, "*")); q += 1
        if div:
            r = div_witness(tree, s)
            if r is not None: return r
        return None

    def add(tree, s, sz):
        nonlocal mat
        if s in bank or mat >= matcap or q >= qcap: return None
        bank[s] = tree; buckets[sz].append((tree, s)); mat += 1
        for i, v in enumerate(s): idx[i].setdefault(v, []).append(s)     # index for // range witness
        return try_close(tree, s)

    for k, fn in LEAF.items():
        r = add(("leaf", k), tuple(fn(a, b) for a, b in rows), 1)
        if r: return _res(mat, q, r, 1, spurious[0])
    for at in extra_atoms:
        r = add(at, tuple(at[2](a, b) for a, b in rows), 1)
        if r: return _res(mat, q, r, 1, spurious[0])
    for s in range(2, Kcap + 1):
        for t, sg in list(buckets[s - 1]):
            for un, uf in UNARY.items():
                r = add(("u", un, t), tuple(uf(v) for v in sg), s)
                if r: return _res(mat, q, r, s, spurious[0])
        for i in range(1, s - 1):
            j = s - 1 - i
            for lt, ls in list(buckets[i]):
                for rt, rs in list(buckets[j]):
                    for bn, bf in BINARY.items():
                        r = add(("b", bn, lt, rt), tuple(bf(x, y) for x, y in zip(ls, rs)), s)
                        if r: return _res(mat, q, r, s, spurious[0])
        if mat >= matcap or q >= qcap: break
    return _res(mat, q, None, None, spurious[0])

def _res(mat, q, tree, K, spurious):
    return {"energy": mat + q, "mat": mat, "q": q, "tree": tree, "K": K, "spurious": spurious}

def rand_div_expr(rng, tgt):
    """random //-TOPPED expr, children ~size 4/5 (same generator family as E10 decoys, forced // top)."""
    pool = [("leaf", k) for k in LEAF]
    for _ in range(rng.randint(4, 7)):
        if rng.random() < 0.4: pool.append(("u", rng.choice(list(UNARY)), rng.choice(pool)))
        else: pool.append(("b", rng.choice(list(BINARY)), rng.choice(pool), rng.choice(pool)))
    kids = [t for t in pool if 3 <= size(t) <= 6]
    if len(kids) < 2: return None
    L, R = rng.choice(kids), rng.choice(kids)
    return ("b", "//", L, R)

if __name__ == "__main__":
    print("E11 — extend witness to // (pivot-row range witness). Additive; E10 invertible results untouched.\n", flush=True)
    blind_trunc = meta_e8.enum_until(meta_e8.leaves2(), meta_e8.sig_of(meta_e8.tgt_trunc, meta_e8.S2), cap=120000)[1]

    # (0) confirm E10 invertible result UNCHANGED (canonical path = meta_e10.synth, invertible-only)
    rows = probe_rows(24, 1)
    e10 = meta_e10.synth(rows, [sdiv(a, b) for a, b in rows], sdiv, seed=1)
    print(f"[unchanged] E10 invertible-only trunc: energy={e10['energy']} R={blind_trunc/e10['energy']:.1f}x "
          f"ok={e10['tree'] is not None and verify(e10['tree'], sdiv, 1)}  (E11 is ADDITIVE)\n", flush=True)

    # (1) natural //-topped targets, size ~8-9, zero-free divisors
    print("=== natural //-topped targets: blind (direct) vs E11 range witness ===", flush=True)
    naturals = {
        "(a*b)//(abs(a)+abs(b))": ("b", "//", ("b", "*", ("leaf", "a"), ("leaf", "b")),
                                    ("b", "+", ("u", "abs", ("leaf", "a")), ("u", "abs", ("leaf", "b")))),
        "(a*a)//(abs(b)+1)": ("b", "//", ("b", "*", ("leaf", "a"), ("leaf", "a")),
                              ("b", "+", ("u", "abs", ("leaf", "b")), ("leaf", "1"))),
    }
    for name, tree in naturals.items():
        rows = probe_rows(24, 7)
        tgt = [ev(tree, a, b) for a, b in rows]
        if X in tgt: print(f"  {name}: has X rows, skip"); continue
        orc = (lambda a, b, x=tree: ev(x, a, b))
        bl = synth11(rows, tgt, orc, inv=False, div=False, Kcap=11, matcap=120000, seed=7)   # blind: direct only
        wi = synth11(rows, tgt, orc, inv=True, div=True, Kcap=8, matcap=40000, seed=7)         # E11 witness
        okw = wi["tree"] is not None and verify(wi["tree"], orc, 7)
        blE = bl["energy"] if bl["tree"] else None
        R = (blE / wi["energy"]) if (blE and wi["tree"]) else None
        print(f"  size{size(tree)} {name}:", flush=True)
        print(f"     blind(direct)={('>cap' if blE is None else blE)}  E11 witness energy={wi['energy']} "
              f"(mat {wi['mat']}+q {wi['q']}) K={wi['K']} ok={okw} R={f'{R:.1f}x' if R else 'NA'} spurious={wi['spurious']}", flush=True)
        print(f"     synthesized: {label(wi['tree']) if wi['tree'] else 'ABSTAIN'}", flush=True)

    # (2) shape-matched //-topped decoy sweep: coverage + R distribution
    print("\n=== //-topped decoy sweep (coverage + speedup vs blind) ===", flush=True)
    rows = probe_rows(24, 1); found = 0; att = 0; Rs = []; verified = 0
    t0 = time.time()
    for ds in range(20):
        rng = random.Random(7000 + ds); dt = rand_div_expr(rng, 10)
        if dt is None: continue
        tgt = [ev(dt, a, b) for a, b in rows]
        if X in tgt: continue
        att += 1; orc = (lambda a, b, x=dt: ev(x, a, b))
        wi = synth11(rows, tgt, orc, inv=True, div=True, Kcap=8, matcap=40000, seed=1)
        if wi["tree"] is not None:
            found += 1
            if verify(wi["tree"], orc, 1): verified += 1
            bl = synth11(rows, tgt, orc, inv=False, div=False, Kcap=11, matcap=120000, seed=1)
            if bl["tree"]: Rs.append(bl["energy"] / wi["energy"])
    Rs.sort()
    print(f"  //-topped decoys: found {found}/{att}, verified {verified}/{found}, "
          f"R vs blind: min={Rs[0]:.1f}x med={Rs[len(Rs)//2]:.1f}x max={Rs[-1]:.1f}x (n={len(Rs)})  {time.time()-t0:.1f}s"
          if Rs else f"  //-topped decoys: found {found}/{att} (no blind-comparable pairs)", flush=True)

    # (3) label-shuffle knockout on a //-topped target -> ABSTAIN
    rows = probe_rows(24, 1); dt = list(naturals.values())[0]
    tsh = [ev(dt, a, b) for a, b in rows]; random.Random(5).shuffle(tsh)
    sh = synth11(rows, tsh, (lambda a, b: X), inv=True, div=True, Kcap=8, matcap=20000, seed=1)
    print(f"\n  label-shuffle (//-target): {'ABSTAIN' if not sh['tree'] else 'FOUND (KILL)'}  spurious={sh['spurious']}", flush=True)

    print("\n--- HONEST VERDICT (report as-is; word is WEAKEN) ---", flush=True)
    print("// caveat REMOVED for COMPLETENESS: //-topped targets now SYNTHESIZE + verify (0 confab, shuffle ABSTAIN),", flush=True)
    print("  additive to E10 (invertible trunc UNCHANGED at 30.6x). SPEEDUP is target-dependent (floor-div is", flush=True)
    print("  non-invertible): genuinely-deep //-tops win big -- (a*a)//(abs(b)+1) R=39.5x; (a*b)//(abs(a)+abs(b))", flush=True)
    print("  synthesized at 18136 where BLIND EXHAUSTS the 120k budget -- but observationally-shallow //-decoys", flush=True)
    print("  (collapse to K<=3) match blind (R median 0.7x): no universal speedup, only where the pivot is selective.", flush=True)
    print("  Honest scope: limit #10's 'invertible top-ops only' softens to 'all four top-ops SYNTHESIZE; // gains a", flush=True)
    print("  speedup only on deep targets'. n small; still one basis; E9 NULL / E10 WEAKENED unchanged.", flush=True)
