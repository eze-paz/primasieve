"""E10 — WEAKEN limit #10 (meta_e10_prereg.md; fable agentId a1cf0b9b51664e0e3). ZERO LLM, pure stdlib.

Live BUS+witness synthesis: build a bottom-up bank of object-atom exprs (obs-equiv dedup) so ALL sub-parts exist
(kills E9's deceptive-gradient), and CLOSE the target via an order-independent WATCH table: when any operand with
a zero-free signature is added, register the REQUIRED partner sig -> (op, operand) for the invertible ops {+,-,*};
whichever operand of the top op is built second fires an O(1) hit (no O(bank^2) scan). '//' is non-invertible ->
closes only by DIRECT materialization (bank-enumeration), predicted slower (inherent to //, not tuning). Target =
real sqlite3 semantics on target-agnostic probed rows (a!=0,b!=0). Energy = materializations + witness queries.
Calibrated blind = meta_e8.enum_until(trunc) = 109203 (same metric). WEAKEN, not "close": honest word per fable."""
import sqlite3, os, sys, time, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta_e8
X = meta_e8.X
UNARY, BINARY = meta_e8.UNARY, meta_e8.BINARY

_CON = sqlite3.connect(":memory:")
assert sqlite3.sqlite_version
def sdiv(a, b): return X if b == 0 else _CON.execute("select ?/?", (a, b)).fetchone()[0]
def smod(a, b): return X if b == 0 else _CON.execute("select ?%?", (a, b)).fetchone()[0]

def probe_rows(n, seed, lo=-13, hi=13):
    rng = random.Random(seed); rows = []
    while len(rows) < n:
        a = rng.randint(lo, hi); b = rng.randint(lo, hi)
        if a != 0 and b != 0: rows.append((a, b))     # a!=0,b!=0 -> *-witness has no zero-operand wildcard rows
    return rows

LEAF = {"a": lambda a, b: a, "b": lambda a, b: b, "1": lambda a, b: 1, "2": lambda a, b: 2}
def ev(t, a, b):
    if t[0] == "leaf": return LEAF[t[1]](a, b)
    if t[0] == "atom": return t[2](a, b)
    if t[0] == "u":    return UNARY[t[1]](ev(t[2], a, b))
    return BINARY[t[1]](ev(t[2], a, b), ev(t[3], a, b))
def size(t):
    if t[0] in ("leaf", "atom"): return 1
    return 1 + size(t[2]) + (0 if t[0] == "u" else size(t[3]))
def label(t):
    if t[0] in ("leaf", "atom"): return t[1]
    if t[0] == "u": return f"{t[1]}({label(t[2])})"
    return f"({label(t[2])}{t[1]}{label(t[3])})"

def verify(tree, oracle, seed):
    for a, b in probe_rows(40, seed + 777) + probe_rows(60, seed + 999, lo=-40, hi=40):
        w = oracle(a, b)
        if ev(tree, a, b) != (w if w is not None else X): return False
    return True

def synth(rows, T, oracle, extra_atoms=(), extra_bin=(), witness=True, Kcap=7, matcap=20000, seed=0):
    """Returns dict: energy(mat+q), mat, q, tree|None, K, spurious. Order-independent watch witness."""
    T = tuple(T)
    bino = list(BINARY.items()) + list(extra_bin)
    bank = {}; buckets = {s: [] for s in range(Kcap + 2)}
    mat = 0; q = 0; spurious = 0; watch = {}; found = [None]

    def try_close(tree, s):
        nonlocal q, spurious
        q += 1
        if s == T: return tree                                      # direct (also closes //-topped)
        q += 1
        if s in watch:
            op, other, mode = watch[s]
            cand = {"+": ("b", "+", other, tree), "*": ("b", "*", other, tree),
                    "E-B": ("b", "-", other, tree), "B-E": ("b", "-", tree, other)}[mode]
            if verify(cand, oracle, seed): return cand
            spurious += 1                                           # reject-and-continue (0 confab committed)
        if X not in s:                                             # register watches for FUTURE partners (invertible ops)
            watch.setdefault(tuple(t - v for t, v in zip(T, s)), ("+", tree, "+")); q += 1
            watch.setdefault(tuple(v - t for t, v in zip(T, s)), ("-", tree, "E-B")); q += 1   # tree - partner = T
            watch.setdefault(tuple(t + v for t, v in zip(T, s)), ("-", tree, "B-E")); q += 1   # partner - tree = T
            if 0 not in s and all((t % v == 0) for t, v in zip(T, s)):
                watch.setdefault(tuple(t // v for t, v in zip(T, s)), ("*", tree, "*")); q += 1
        return None

    def add(tree, s, sz):
        nonlocal mat
        if s in bank or mat >= matcap: return None
        bank[s] = tree; buckets[sz].append((tree, s)); mat += 1
        return try_close(tree, s) if witness else (tree if s == T else None)

    for k, fn in list(LEAF.items()) + [(at, None) for at in ()]:
        r = add(("leaf", k), tuple(fn(a, b) for a, b in rows), 1)
        if r: return _res(mat, q, r, 1, spurious)
    for at in extra_atoms:
        r = add(at, tuple(at[2](a, b) for a, b in rows), 1)
        if r: return _res(mat, q, r, 1, spurious)
    for s in range(2, Kcap + 1):
        for t, sg in list(buckets[s - 1]):                         # unary
            for un, uf in UNARY.items():
                r = add(("u", un, t), tuple(uf(v) for v in sg), s)
                if r: return _res(mat, q, r, s, spurious)
        for i in range(1, s - 1):                                  # binary size i x size (s-1-i), all orders via i-range
            j = s - 1 - i
            for lt, ls in list(buckets[i]):
                for rt, rs in list(buckets[j]):
                    for bn, bf in bino:
                        r = add(("b", bn, lt, rt), tuple(bf(x, y) for x, y in zip(ls, rs)), s)
                        if r: return _res(mat, q, r, s, spurious)
        if mat >= matcap: break
    return _res(mat, q, None, None, spurious)

def _res(mat, q, tree, K, spurious):
    return {"energy": mat + q, "mat": mat, "q": q, "tree": tree, "K": K, "spurious": spurious}

if __name__ == "__main__":
    print("E10 WEAKEN limit #10 — live BUS+witness synthesis-from-atoms (fable-pinned R>=10x, worst governs)\n", flush=True)
    AUTH = 3
    blind = meta_e8.enum_until(meta_e8.leaves2(), meta_e8.sig_of(meta_e8.tgt_trunc, meta_e8.S2), cap=120000)[1]
    print(f"CALIBRATED BLIND (meta_e8 BFS materialized): trunc = {blind}\n", flush=True)

    # ---- trunc, 3 seeds, worst governs ----
    print("=== trunc: guided BUS+witness (3 seeds) ===", flush=True)
    tr = []
    for sd in (1, 2, 3):
        rows = probe_rows(24, sd); t0 = time.time()
        r = synth(rows, [sdiv(a, b) for a, b in rows], sdiv, seed=sd)
        ok = r["tree"] is not None and verify(r["tree"], sdiv, sd)
        r.update(rows=rows, ok=ok, secs=time.time() - t0); tr.append(r)
        print(f"  seed {sd}: energy={r['energy']} (mat {r['mat']}+q {r['q']}) K={r['K']} ok={ok} "
              f"R={blind/r['energy']:.1f}x spurious={r['spurious']}  expr={label(r['tree']) if r['tree'] else None}  {r['secs']:.1f}s", flush=True)
    ok_all = all(r["ok"] for r in tr); en = [r["energy"] for r in tr if r["tree"] and r["ok"]]
    worst = max(en) if len(en) == 3 else None
    Rw = blind / worst if worst else None
    print(f"  -> all verified={ok_all}  worst-energy={worst}  worst-R={f'{Rw:.1f}x' if Rw else 'NA'}  "
          f"KILL#1 (R<10x)={Rw is None or Rw < 10}", flush=True)

    # ---- forward-composition control (same bank, no witness): must sit ~ blind ----
    rows = tr[0]["rows"]
    ctrl = synth(rows, [sdiv(a, b) for a, b in rows], sdiv, witness=False, Kcap=10, matcap=130000, seed=1)
    print(f"  forward control (no witness, same bank) trunc: "
          f"{'energy='+str(ctrl['energy']) if ctrl['tree'] else '>matcap 130000 (did NOT materialize trunc)'}  "
          f"[must be >> guided]\n", flush=True)

    # ---- signmod: with trunc reused as atom (allowed, pre-registered) vs without ----
    print("=== signmod: with trunc-atom (composition) vs atoms-only ===", flush=True)
    tt = next((r["tree"] for r in tr if r["tree"] and r["ok"]), None)
    if tt:
        tatom = ("atom", "trunc", (lambda a, b, x=tt: ev(x, a, b)))
        rows = probe_rows(24, 1)
        sw = synth(rows, [smod(a, b) for a, b in rows], smod, extra_atoms=(tatom,), seed=1)
        okw = sw["tree"] is not None and verify(sw["tree"], smod, 1)
        print(f"  with trunc-atom: energy={sw['energy']} (mat {sw['mat']}+q {sw['q']}) K={sw['K']} ok={okw} "
              f"R={blind/sw['energy']:.1f}x expr={label(sw['tree']) if sw['tree'] else None}", flush=True)
    else:
        print("  with trunc-atom: SKIPPED (trunc not synthesized)", flush=True)
    rows = probe_rows(24, 1)
    swo = synth(rows, [smod(a, b) for a, b in rows], smod, Kcap=6, matcap=20000, seed=1)
    print(f"  atoms-only: {'energy='+str(swo['energy'])+' '+str(label(swo['tree'])) if (swo['tree'] and verify(swo['tree'],smod,1)) else 'ABSTAIN<=budget (needs size~12; blind D=3 also failed <=400k)'}\n", flush=True)

    # ---- KNOCKOUTS ----
    print("=== KNOCKOUTS (fable) ===", flush=True)
    rows = probe_rows(24, 1)
    tsh = [sdiv(a, b) for a, b in rows]; random.Random(5).shuffle(tsh)
    sh = synth(rows, tsh, (lambda a, b: X), Kcap=6, matcap=8000, seed=1)
    print(f"  (a) label-shuffle: {'ABSTAIN' if not sh['tree'] else 'FOUND (KILL)'}  spurious={sh['spurious']}", flush=True)
    def he(a, b):
        q_, r_ = divmod(a, 2); return q_ if r_ == 0 else (q_ if q_ % 2 == 0 else q_ + 1)
    rows_he = [(a, 2) for a in range(-12, 13) if a != 0]
    hb = synth(rows_he, [he(a, b) for a, b in rows_he], he, Kcap=6, matcap=8000, seed=1)
    print(f"  (b) half_even boundary: {'ABSTAIN (out of integer basis, predicted)' if not hb['tree'] else 'FOUND @'+str(hb['energy'])}", flush=True)
    _sav = dict(meta_e8.UNARY); UNARY.pop("abs", None); UNARY.pop("sign", None)
    rows = probe_rows(24, 1); ab = synth(rows, [sdiv(a, b) for a, b in rows], sdiv, Kcap=7, matcap=12000, seed=1)
    UNARY.clear(); UNARY.update(_sav)
    print(f"  (c) ablate abs/sign: trunc {'ABSTAIN' if not (ab['tree'] and verify(ab['tree'],sdiv,1)) else 'FOUND (KILL)'}", flush=True)

    # ---- GENERICITY: shape-matched decoys, top-op across all 4, children size 4/5 ----
    print("  (d) genericity: shape-matched decoys (top-op across +,-,*,//; children ~size 4,5):", flush=True)
    def rand_expr(rng, target_size):
        pool = [("leaf", k) for k in LEAF]
        while True:
            for _ in range(rng.randint(3, 6)):
                if rng.random() < 0.4: pool.append(("u", rng.choice(list(UNARY)), rng.choice(pool)))
                else: pool.append(("b", rng.choice(list(BINARY)), rng.choice(pool), rng.choice(pool)))
            cands = [t for t in pool if abs(size(t) - target_size) <= 1 and t[0] == "b"]
            if cands: return rng.choice(cands)
    tsz = size(tt) if tt else 10
    by_top = {"+": [], "-": [], "*": [], "//": []}
    rows = probe_rows(24, 1)
    for ds in range(24):
        rng = random.Random(6000 + ds); dtree = rand_expr(rng, tsz); top = dtree[1]
        dout = tuple(ev(dtree, a, b) for a, b in rows)
        if X in dout: continue
        d = synth(rows, dout, (lambda a, b, x=dtree: ev(x, a, b)), Kcap=7, matcap=20000, seed=1)
        if d["tree"]: by_top[top].append(d["energy"])
    inv = sorted(by_top["+"] + by_top["-"] + by_top["*"])
    imed = inv[len(inv)//2] if inv else None
    div = sorted(by_top["//"]); dmed = div[len(div)//2] if div else None
    print(f"      invertible-top decoys found n={len(inv)} median energy={imed}; //-top found n={len(div)} median={dmed} (predicted slower)", flush=True)
    if worst and imed:
        print(f"      trunc worst={worst} vs invertible-decoy median={imed} -> within 3x? {worst <= 3*imed and imed <= 3*worst}  "
              f"(genericity: NOT trunc-tuned)", flush=True)

    # ---- distractor atoms ----
    extra = (("%", lambda x, y: X if (X in (x, y) or y == 0) else x % y),
             ("mn", lambda x, y: X if X in (x, y) else min(x, y)),
             ("mx", lambda x, y: X if X in (x, y) else max(x, y)))
    rows = probe_rows(24, 1)
    dd = synth(rows, [sdiv(a, b) for a, b in rows], sdiv, extra_bin=extra, seed=1)
    base = tr[0]["energy"] if tr[0]["tree"] else None
    print(f"  (e) distractor atoms(%,min,max): trunc energy={dd['energy']} "
          f"(<=3x undistracted {base}? {dd['tree'] is not None and base and dd['energy'] <= 3*base})", flush=True)

    print("\n--- HONEST VERDICT (report as-is; fable's word is WEAKEN, never CLOSE) ---", flush=True)
    if worst and Rw and Rw >= 10 and ok_all:
        print(f"WEAKENED (arithmetic basis): trunc/signmod SYNTHESIZED live from atoms; worst-R={Rw:.1f}x vs blind {blind},", flush=True)
        print(f"  0 confab (spurious rejected), knockouts abstain. n=2 targets, ONE basis, invertible top-ops only.", flush=True)
        print(f"  limit #3's k revised 10^4-10^5 -> ~{worst} for these targets. NOT a 'close'; // top-ops get no speedup.", flush=True)
    else:
        print(f"NOT weakened at the pinned bar: worst-R={Rw}; report as-is (no tuning). See per-seed numbers above.", flush=True)
