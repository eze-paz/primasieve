"""E9 — CLOSE-k (limit #10): LIVE SYNTHESIS-FROM-ATOMS vs menu-selection. Pre-registered in meta_e9_prereg.md
(fable-set kills, agentId a3a968f87a0a0160a). ZERO LLM, pure stdlib.

Question: E8 proved trunc/signmod are object-atom exprs but only BLIND simplest-first BFS reached them, at
k ~ 10^4-10^5x the authored shortlist. Was that cost STRUCTURE or merely ORDER? E9 runs a GUIDED best-first
search whose priority is a TARGET-AGNOSTIC verifier gradient (# probed rows matched, Occam tie-break) over the
SAME atoms, from residuals of the REAL sqlite3 binary collected WITHOUT any target in the menu. If guided reaches
the same object-atom expression at k' <= 10x authored, the shortlist bought order and selection == synthesis.

Atoms (identical to meta_e8): leaves {a,b,1,2}; unary {abs,sign,neg}; binary {+,-,*,//}. Held byte-identical
across every target and decoy (generic-guidance proof). Energy = # unique exprs generated (deduped by fit-row
signature) until a full fit-row match = the SAME metric meta_e8.enum_until reports, so guided/blind is a fair
multiplier."""
import sqlite3, heapq, random, time, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import meta_e8  # BLIND baseline (enum_until) + shared object-grammar semantics

X = meta_e8.X
UNARY, BINARY = meta_e8.UNARY, meta_e8.BINARY          # exact same semantics as the blind baseline

# ---------------- SOUND ORACLE = the real SQLite C binary (independence guard) ----------------
_CON = sqlite3.connect(":memory:")
assert sqlite3.sqlite_version, "no sqlite3 C binary"    # divergence is a property of THIS binary, not authored here
def sqlite_div(a, b):
    if b == 0: return X
    return _CON.execute("select ?/?", (a, b)).fetchone()[0]
def sqlite_mod(a, b):
    if b == 0: return X
    return _CON.execute("select ?%?", (a, b)).fetchone()[0]

# ---------------- target-agnostic residual probes (UNCURATED, seeded, reported) ----------------
def probe_rows(n, seed, lo=-13, hi=13):
    """Systematic/pseudo-random integer (a,b), b!=0, signs varied but NOT hand-balanced. Fixed seeded order."""
    rng = random.Random(seed); rows = []
    while len(rows) < n:
        a = rng.randint(lo, hi); b = rng.randint(lo, hi)
        if b != 0: rows.append((a, b))
    return rows

# ---------------- expression trees over the atoms (tuples), size, eval, signature ----------------
LEAF_FNS = {"a": lambda a, b: a, "b": lambda a, b: b, "1": lambda a, b: 1, "2": lambda a, b: 2}
def ev(t, a, b):
    if t[0] == "leaf": return LEAF_FNS[t[1]](a, b)
    if t[0] == "u":    return UNARY[t[1]](ev(t[2], a, b))
    if t[0] == "b":    return BINARY[t[1]](ev(t[2], a, b), ev(t[3], a, b))
    if t[0] == "atom": return t[2](a, b)               # a reused, already-synthesized primitive (e.g. trunc)
    raise ValueError(t)
def size(t):
    if t[0] in ("leaf", "atom"): return 1
    if t[0] == "u": return 1 + size(t[2])
    return 1 + size(t[2]) + size(t[3])
def label(t):
    if t[0] == "leaf": return t[1]
    if t[0] == "atom": return t[1]
    if t[0] == "u": return f"{t[1]}({label(t[2])})"
    return f"({label(t[2])}{t[1]}{label(t[3])})"
def sig(t, rows): return tuple(ev(t, a, b) for a, b in rows)

# ---------------- GUIDED best-first synthesis (the treatment) ----------------
def guided_synth(rows, target_out, extra_atoms=(), extra_binops=(), priority="guided", cap=200000, seed=0):
    """Best-first over the atom expression space. priority='guided' -> (-#rows matched, size); 'random' -> random
    (the control, must sit at blind energy). Returns (energy, tree|None). Energy = # unique exprs generated."""
    rng = random.Random(1000 + seed)
    uni = list(UNARY); bino = list(BINARY) + list(extra_binops)
    leaves = [("leaf", k) for k in LEAF_FNS] + list(extra_atoms)
    tset = {tuple(target_out)}
    def matched(s): return sum(1 for u, v in zip(s, target_out) if u == v)
    def prio(t, s):
        if priority == "guided": return (-matched(s), size(t), rng.random())
        return (rng.random(),)                          # random-priority control
    seen = {}; energy = 0; frontier = []; counter = 0
    def push(t):
        nonlocal energy, counter
        s = sig(t, rows)
        if s in seen or energy >= cap: return s == tuple(target_out) and s not in seen
        seen[s] = t; energy += 1
        heapq.heappush(frontier, (prio(t, s), counter, t, s)); counter += 1
        return s == tuple(target_out)
    for lf in leaves:
        if push(lf): return energy, lf
    while frontier and energy < cap:
        _, _, t, _ = heapq.heappop(frontier)
        for uop in uni:                                 # unary(t)
            nt = ("u", uop, t)
            if push(nt): return energy, nt
        pool = list(seen.values())                      # binary(t, f) both orders, f over all seen
        for f in pool:
            for bop in bino:
                for nt in (("b", bop, t, f), ("b", bop, f, t)):
                    if push(nt): return energy, nt
            if energy >= cap: break
    return None, None

# ---------------- verification: disjoint rows + FRESH active probes against sqlite ----------------
def verify(tree, oracle, seed):
    disj = probe_rows(40, seed + 777)
    for a, b in disj:
        if ev(tree, a, b) != (oracle(a, b) if oracle(a, b) is not None else X): return False
    fresh = probe_rows(60, seed + 999, lo=-40, hi=40)   # fresh, wider active probes
    for a, b in fresh:
        want = oracle(a, b); got = ev(tree, a, b)
        if got != (want if want is not None else X): return False
    return True

# ---------------- run one target across arms + report ----------------
def target_sig(oracle, rows): return tuple((oracle(a, b) if oracle(a, b) is not None else X) for a, b in rows)

def run_target(name, oracle, seed, extra_atoms=(), fit_n=24):
    fit = probe_rows(fit_n, seed)
    tout = target_sig(oracle, fit)
    t0 = time.time()
    gE, gt = guided_synth(fit, tout, extra_atoms=extra_atoms, priority="guided", seed=seed)
    rE, _ = guided_synth(fit, tout, extra_atoms=extra_atoms, priority="random", cap=60000, seed=seed)
    ok = gt is not None and verify(gt, oracle, seed)
    return {"name": name, "guided": gE, "guided_ok": ok, "expr": label(gt) if gt else None,
            "random": rE, "sz": size(gt) if gt else None, "secs": time.time() - t0, "fit": fit}

if __name__ == "__main__":
    print("E9 close-k — is trunc/signmod SYNTHESIZED from atoms by a generic gradient, or did the menu buy order?\n")
    AUTHORED = 3    # trunc's index in meta_e8.authored() shortlist ~ the authored 'energy'
    BOUND = 10 * AUTHORED

    # BLIND baselines from meta_e8 (same metric, same atoms) --------------------------------------
    S2 = meta_e8.S2
    blind_trunc = meta_e8.enum_until(meta_e8.leaves2(), meta_e8.sig_of(meta_e8.tgt_trunc, S2), cap=120000)[1]
    print(f"BLIND (meta_e8 BFS): trunc energy = {blind_trunc}  (authored ~ {AUTHORED}; blind multiplier "
          f"~ {blind_trunc // AUTHORED}x)\n")

    # ---- MAIN: trunc, multi-seed (>=3), worst governs ----
    print("=== trunc: GUIDED synthesis-from-atoms (3 seeds; worst governs) ===")
    res = [run_target("trunc", sqlite_div, s) for s in (1, 2, 3)]
    for r in res:
        mult = f"{r['guided']/AUTHORED:.1f}x" if r["guided"] else ">cap"
        print(f"  seed {res.index(r)+1}: guided={r['guided']} ({mult} authored, size {r['sz']}) ok={r['guided_ok']} "
              f"expr={r['expr']}  | random-prio={r['random']}  {r['secs']:.1f}s")
    gm = [r["guided"] for r in res if r["guided"]]
    worst = max(gm) if gm else None
    med = sorted(gm)[len(gm)//2] if gm else None
    allok = all(r["guided_ok"] for r in res)
    print(f"  -> median guided={med}  worst guided={worst}  verified-all={allok}  "
          f"random-prio~blind={all((r['random'] is None or r['random']>2000) for r in res)}")
    print(f"  KILL#1 (worst>{BOUND})={worst is None or worst>BOUND}   "
          f"reduction vs blind = {blind_trunc//worst if worst else 'NA'}x\n")

    # ---- signmod: with trunc reused as an atom (composition, pre-registered) ----
    print("=== signmod: WITH trunc reused as atom (composition) vs WITHOUT ===")
    trunc_expr = res[0]["expr"]; trunc_tree = None
    # rebuild trunc tree from the successful search for reuse:
    _, trunc_tree = guided_synth(res[0]["fit"], target_sig(sqlite_div, res[0]["fit"]), priority="guided", seed=1)
    trunc_atom = ("atom", "trunc", lambda a, b: (ev(trunc_tree, a, b) if trunc_tree else X))
    sm_with = run_target("signmod", sqlite_mod, 1, extra_atoms=(trunc_atom,))
    sm_without = run_target("signmod", sqlite_mod, 1)
    print(f"  with trunc-atom : guided={sm_with['guided']} ok={sm_with['guided_ok']} expr={sm_with['expr']} "
          f"({sm_with['guided']/AUTHORED:.1f}x authored)" if sm_with['guided'] else
          f"  with trunc-atom : NOT FOUND <= cap")
    print(f"  without (atoms only): guided={sm_without['guided']} "
          f"{'(FOUND '+str(sm_without['expr'])+')' if sm_without['guided'] else '= NOT FOUND <= cap (blind D=3 also failed <=400k)'}\n")

    # ---- KNOCKOUTS ----
    print("=== KNOCKOUTS (fable) ===")
    # (a) ablate abs/sign -> must ABSTAIN (cap). Temporarily remove them from UNARY.
    _save = dict(meta_e8.UNARY)
    UNARY.pop("abs", None); UNARY.pop("sign", None)
    fit = probe_rows(24, 1); abl, _ = guided_synth(fit, target_sig(sqlite_div, fit), priority="guided", cap=60000, seed=1)
    UNARY.clear(); UNARY.update(_save)
    print(f"  (a) ablate abs/sign: trunc {'ABSTAIN (unreachable)' if not abl else f'REACHED @ {abl} (KILL)'}")
    # (b) label-shuffle -> must ABSTAIN
    fit = probe_rows(24, 1); tout = list(target_sig(sqlite_div, fit)); random.Random(5).shuffle(tout)
    sh, _ = guided_synth(fit, tout, priority="guided", cap=60000, seed=1)
    print(f"  (b) label-shuffle: {'ABSTAIN (no expr)' if not sh else f'FOUND @ {sh} (KILL: chasing noise)'}")
    # (c) half_even boundary probe -> predicted ABSTAIN (needs %2+branch, not in integer atom basis)
    def half_even(a, b):  # round(a/2) half-to-even as an integer-domain probe: a even->a//2 exact; test on a only
        q, r = divmod(a, 2); return q if r == 0 else (q if q % 2 == 0 else q + 1)
    fit_he = [(a, 2) for a in range(-12, 13)]
    he, _ = guided_synth(fit_he, tuple(half_even(a, b) for a, b in fit_he), priority="guided", cap=60000, seed=1)
    print(f"  (c) half_even boundary: {'ABSTAIN (out of integer basis, as predicted)' if not he else f'FOUND @ {he}'}")
    # (d) decoy-outlier: 20 random same-size exprs; trunc must NOT be >3x cheaper than same-size randoms
    print("  (d) decoy-outlier (20 random size~trunc exprs, guided energy):")
    decoys = []
    for ds in range(20):
        dr = random.Random(3000 + ds)
        # build a random expr of ~ trunc size by random assembly
        pool = [("leaf", k) for k in LEAF_FNS]
        for _ in range(dr.randint(4, 7)):
            if pool and dr.random() < 0.5:
                t = dr.choice(pool); pool.append(("u", dr.choice(list(UNARY)), t))
            else:
                t1, t2 = dr.choice(pool), dr.choice(pool); pool.append(("b", dr.choice(list(BINARY)), t1, t2))
        dtree = pool[-1]
        fit = probe_rows(24, 1); dout = sig(dtree, fit)
        de, _ = guided_synth(fit, dout, priority="guided", cap=40000, seed=1)
        if de: decoys.append((de, size(dtree)))
    same_sz = [e for e, z in decoys if worst and abs(z - (res[0]["sz"] or 0)) <= 2]
    dmed = sorted(same_sz)[len(same_sz)//2] if same_sz else None
    print(f"      same-size decoy median guided={dmed} (n={len(same_sz)});  trunc worst={worst}  "
          f"-> trunc >3x cheaper than same-size randoms? "
          f"{bool(dmed and worst and worst*3 < dmed)}  (True=KILL: guidance tuned to target)")
    # (e) distractor atoms %,min,max added -> k' must stay <= 30x authored
    extra_bin = (("%", lambda x, y: X if (X in (x, y) or y == 0) else x % y),
                 ("mn", lambda x, y: X if X in (x, y) else min(x, y)),
                 ("mx", lambda x, y: X if X in (x, y) else max(x, y)))
    fit = probe_rows(24, 1)
    dist, dtree2 = guided_synth(fit, target_sig(sqlite_div, fit), extra_binops=extra_bin, priority="guided", seed=1)
    print(f"  (e) distractor atoms(%,min,max): trunc guided={dist} "
          f"({dist/AUTHORED:.1f}x authored, bound 30x) ok={dist is not None and dist <= 30*AUTHORED}")

    print("\nVERDICT INPUTS: guided reaches trunc from atoms via a target-agnostic (#matched,size) gradient;")
    print("compare worst-guided vs 10x-authored bound (KILL#1) and vs blind reduction; random-prio control must")
    print("sit near blind; knockouts (a)-(e) must behave as predicted. n=2 targets, ONE basis. Report as-is.")
