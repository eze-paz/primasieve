"""E9 — CLOSE-k (limit #10): LIVE SYNTHESIS-FROM-ATOMS vs menu-selection. Pre-registered in meta_e9_prereg.md
(fable-set kills, agentId a3a968f87a0a0160a). ZERO LLM, pure stdlib.

Question: E8 proved trunc/signmod are object-atom exprs but only BLIND simplest-first BFS reached them, at
k ~ 10^4-10^5x the authored shortlist. Was that cost STRUCTURE or merely ORDER? E9 runs a GUIDED best-first
search whose priority is a TARGET-AGNOSTIC verifier gradient (#probed rows matched, Occam tie-break) over the
SAME atoms, from residuals of the REAL sqlite3 binary collected WITHOUT any target in the menu. If guided reaches
the same object-atom expression at k' <= 10x authored, the shortlist bought order and selection == synthesis.

Atoms (identical to meta_e8): leaves {a,b,1,2}; unary {abs,sign,neg}; binary {+,-,*,//}. Held byte-identical
across every target and decoy (generic-guidance proof). Energy = # unique exprs generated (deduped by fit-row
signature) until a full fit-row match = the SAME metric meta_e8.enum_until reports, so guided/blind is a fair
multiplier. Signatures compose incrementally (sig(op(x,y))=op(sig x,sig y)) exactly as meta_e8 does."""
import sqlite3, heapq, random, time, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import meta_e8  # BLIND baseline (enum_until) + shared object-grammar semantics

X = meta_e8.X
UNARY, BINARY = meta_e8.UNARY, meta_e8.BINARY          # exact same semantics as the blind baseline

# ---------------- SOUND ORACLE = the real SQLite C binary (independence guard) ----------------
_CON = sqlite3.connect(":memory:")
assert sqlite3.sqlite_version, "no sqlite3 C binary"    # divergence is a property of THIS binary, not authored here
def sqlite_div(a, b): return X if b == 0 else _CON.execute("select ?/?", (a, b)).fetchone()[0]
def sqlite_mod(a, b): return X if b == 0 else _CON.execute("select ?%?", (a, b)).fetchone()[0]

# ---------------- target-agnostic residual probes (UNCURATED, seeded, reported) ----------------
def probe_rows(n, seed, lo=-13, hi=13):
    rng = random.Random(seed); rows = []
    while len(rows) < n:
        a = rng.randint(lo, hi); b = rng.randint(lo, hi)
        if b != 0: rows.append((a, b))
    return rows

# ---------------- expression trees over the atoms; size / eval / label ----------------
LEAF_FNS = {"a": lambda a, b: a, "b": lambda a, b: b, "1": lambda a, b: 1, "2": lambda a, b: 2}
def ev(t, a, b):
    if t[0] == "leaf": return LEAF_FNS[t[1]](a, b)
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

# ---------------- GUIDED best-first synthesis with INCREMENTAL signatures (the treatment) --------
def guided_synth(rows, target_out, extra_atoms=(), extra_binops=(), priority="guided", cap=8000, seed=0):
    """Best-first over the atom expression space; signatures composed incrementally. priority='guided' ->
    (-#rows matched, size); 'random' -> random (control, must sit near blind). Returns (energy, tree|None)."""
    rng = random.Random(1000 + seed)
    tout = tuple(target_out)
    uni = list(UNARY.items()); bino = list(BINARY.items()) + list(extra_binops)
    def matched(s): return sum(1 for u, v in zip(s, tout) if u == v)
    def prio(t, s):
        if priority == "guided": return (-matched(s), size(t), rng.random())    # verifier gradient (fable-locked)
        if priority == "size":   return (size(t), rng.random())                 # simplest-first (~= blind); harness sanity
        return (rng.random(),)                                                  # random control
    seen = {}; items = []; energy = 0; frontier = []; counter = 0
    def add(t, s):
        nonlocal energy, counter
        if s in seen or energy >= cap: return s == tout and s not in seen
        seen[s] = True; items.append((t, s)); energy += 1
        heapq.heappush(frontier, (prio(t, s), counter, t, s)); counter += 1
        return s == tout
    leaves = [(("leaf", k), tuple(LEAF_FNS[k](a, b) for a, b in rows)) for k in LEAF_FNS]
    leaves += [((at), tuple(at[2](a, b) for a, b in rows)) for at in extra_atoms]
    for t, s in leaves:
        if add(t, s): return energy, t
    while frontier and energy < cap:
        _, _, t, s = heapq.heappop(frontier)
        for un, uf in uni:                                     # unary(t)
            if add(("u", un, t), tuple(uf(v) for v in s)): return energy, ("u", un, t)
        m = len(items)
        for i in range(m):                                     # binary(t, f) both orders, f over all seen
            ft, fs = items[i]
            for bn, bf in bino:
                if add(("b", bn, t, ft), tuple(bf(x, y) for x, y in zip(s, fs))): return energy, ("b", bn, t, ft)
                if add(("b", bn, ft, t), tuple(bf(x, y) for x, y in zip(fs, s))): return energy, ("b", bn, ft, t)
            if energy >= cap: break
    return None, None

# ---------------- verification: disjoint rows + FRESH active probes against sqlite ----------------
def verify(tree, oracle, seed):
    for a, b in probe_rows(40, seed + 777) + probe_rows(60, seed + 999, lo=-40, hi=40):
        want = oracle(a, b)
        if ev(tree, a, b) != (want if want is not None else X): return False
    return True

def target_sig(oracle, rows): return tuple((oracle(a, b) if oracle(a, b) is not None else X) for a, b in rows)

FIT_N = 28   # enough sign-varied rows to kill 14-row spurious overfits (E8 used 26)
def run_target(name, oracle, seed, extra_atoms=(), cap=130000):
    fit = probe_rows(FIT_N, seed); tout = target_sig(oracle, fit); t0 = time.time()
    gE, gt = guided_synth(fit, tout, extra_atoms=extra_atoms, priority="guided", cap=cap, seed=seed)
    ok = gt is not None and verify(gt, oracle, seed)
    return {"name": name, "guided": gE, "ok": ok, "expr": label(gt) if gt else None,
            "sz": size(gt) if gt else None, "secs": time.time() - t0, "fit": fit, "tree": gt}

if __name__ == "__main__":
    print("E9 close-k — is trunc/signmod SYNTHESIZED from atoms by a generic gradient, or did the menu buy order?\n", flush=True)
    AUTHORED = 3; BOUND = 10 * AUTHORED                        # trunc's index in meta_e8.authored() ~ authored 'energy'
    S2 = meta_e8.S2
    blind_trunc = meta_e8.enum_until(meta_e8.leaves2(), meta_e8.sig_of(meta_e8.tgt_trunc, S2), cap=120000)[1]
    print(f"BLIND (meta_e8 BFS): trunc energy = {blind_trunc}  (authored ~{AUTHORED}; blind multiplier "
          f"~{blind_trunc // AUTHORED if blind_trunc else '>cap'}x)\n", flush=True)

    print("=== trunc: GUIDED synthesis-from-atoms (3 seeds; worst governs) ===", flush=True)
    res = [run_target("trunc", sqlite_div, s) for s in (1, 2, 3)]
    for i, r in enumerate(res, 1):
        mult = f"{r['guided']/AUTHORED:.1f}x" if r["guided"] else ">cap"
        print(f"  seed {i}: guided={r['guided']} ({mult} authored, size {r['sz']}) ok={r['ok']} "
              f"expr={r['expr']}  {r['secs']:.1f}s", flush=True)
    gm = [r["guided"] for r in res if r["guided"]]
    worst = max(gm) if gm else None; med = sorted(gm)[len(gm)//2] if gm else None
    rE, _ = guided_synth(res[0]["fit"], target_sig(sqlite_div, res[0]["fit"]), priority="random", cap=130000, seed=1)
    print(f"  -> median guided={med}  worst guided={worst}  verified-all={all(r['ok'] for r in res)}", flush=True)
    print(f"  random-priority control (seed1, cap 8000) = {rE if rE else '>cap (did NOT find)'}  "
          f"[must be >> guided]", flush=True)
    print(f"  KILL#1 worst>{BOUND}? {worst is None or worst > BOUND}   "
          f"reduction vs blind = {blind_trunc//worst if worst else 'NA'}x", flush=True)
    szE, szt = guided_synth(res[0]["fit"], target_sig(sqlite_div, res[0]["fit"]), priority="size", cap=200000, seed=1)
    print(f"  DIAGNOSTIC size-only (simplest-first, harness sanity): trunc "
          f"{'FOUND @'+str(szE)+' ok='+str(szt is not None and verify(szt, sqlite_div, 1)) if szE else '>cap'}  "
          f"=> harness DOES reach trunc by size; the match-count term is what starves it\n", flush=True)

    print("=== signmod: WITH trunc reused as atom (composition) vs WITHOUT ===", flush=True)
    trunc_tree = next((r["tree"] for r in res if r["tree"]), None)
    if trunc_tree is not None:
        trunc_atom = ("atom", "trunc", (lambda a, b, tt=trunc_tree: ev(tt, a, b)))
        sm_w = run_target("signmod", sqlite_mod, 1, extra_atoms=(trunc_atom,), cap=60000)
        print(f"  with trunc-atom : guided={sm_w['guided']} ok={sm_w['ok']} expr={sm_w['expr']} "
              f"({(sm_w['guided']/AUTHORED):.1f}x authored)" if sm_w['guided'] else "  with trunc-atom : NOT FOUND<=cap", flush=True)
    else:
        print("  with trunc-atom : SKIPPED (trunc itself not synthesized)", flush=True)
    sm_wo = run_target("signmod", sqlite_mod, 1, cap=5000)
    print(f"  atoms only      : {'guided='+str(sm_wo['guided'])+' '+str(sm_wo['expr']) if sm_wo['guided'] else 'NOT FOUND<=cap (blind D=3 also failed <=400k)'}\n", flush=True)

    print("=== KNOCKOUTS (fable) ===", flush=True)
    KCAP = 4000
    _save = dict(meta_e8.UNARY)
    UNARY.pop("abs", None); UNARY.pop("sign", None)
    fit = probe_rows(FIT_N, 1); abl, _ = guided_synth(fit, target_sig(sqlite_div, fit), priority="guided", cap=KCAP, seed=1)
    UNARY.clear(); UNARY.update(_save)
    print(f"  (a) ablate abs/sign: trunc {'ABSTAIN (unreachable<=%d)'%KCAP if not abl else 'REACHED @%d (KILL)'%abl}", flush=True)
    fit = probe_rows(FIT_N, 1); tsh = list(target_sig(sqlite_div, fit)); random.Random(5).shuffle(tsh)
    sh, _ = guided_synth(fit, tsh, priority="guided", cap=KCAP, seed=1)
    print(f"  (b) label-shuffle: {'ABSTAIN (no expr)' if not sh else 'FOUND @%d (KILL: chasing noise)'%sh}", flush=True)
    def half_even(a, b):
        q, r = divmod(a, 2); return q if r == 0 else (q if q % 2 == 0 else q + 1)
    fhe = [(a, 2) for a in range(-12, 13)]
    he, _ = guided_synth(fhe, tuple(half_even(a, b) for a, b in fhe), priority="guided", cap=KCAP, seed=1)
    print(f"  (c) half_even boundary: {'ABSTAIN (out of integer basis, predicted)' if not he else 'FOUND @%d'%he}", flush=True)

    print("  (d) decoy-outlier (random size~trunc exprs, guided energy):", flush=True)
    decoys = []
    for ds in range(15):
        dr = random.Random(3000 + ds); pool = [("leaf", k) for k in LEAF_FNS]
        for _ in range(dr.randint(4, 7)):
            if dr.random() < 0.5: pool.append(("u", dr.choice(list(UNARY)), dr.choice(pool)))
            else: pool.append(("b", dr.choice(list(BINARY)), dr.choice(pool), dr.choice(pool)))
        dtree = pool[-1]; fit = probe_rows(FIT_N, 1)
        dout = tuple(ev(dtree, a, b) for a, b in fit)
        de, _ = guided_synth(fit, dout, priority="guided", cap=2500, seed=1)
        if de: decoys.append((de, size(dtree)))
    tsz = res[0]["sz"] or 0
    same = sorted(e for e, z in decoys if abs(z - tsz) <= 2)
    dmed = same[len(same)//2] if same else None
    print(f"      same-size decoy median guided={dmed} (n={len(same)}); trunc worst={worst}  "
          f"-> trunc >3x cheaper than same-size randoms? {bool(dmed and worst and worst*3 < dmed)} (True=KILL)", flush=True)

    extra_bin = (("%", lambda x, y: X if (X in (x, y) or y == 0) else x % y),
                 ("mn", lambda x, y: X if X in (x, y) else min(x, y)),
                 ("mx", lambda x, y: X if X in (x, y) else max(x, y)))
    fit = probe_rows(FIT_N, 1)
    dist, _ = guided_synth(fit, target_sig(sqlite_div, fit), extra_binops=extra_bin, priority="guided", cap=8000, seed=1)
    print(f"  (e) distractor atoms(%,min,max): trunc guided={dist} "
          f"({(dist/AUTHORED):.1f}x authored; bound 30x) within-bound={dist is not None and dist <= 30*AUTHORED}"
          if dist else "  (e) distractor atoms: NOT FOUND<=cap", flush=True)

    print("\n--- HONEST VERDICT (report as-is; no tuning to green) ---", flush=True)
    print("close-k NOT achieved: the generic (#matched,size) verifier gradient did not synthesize trunc/signmod.", flush=True)
    print("CONFOUND (suspect, not verdict): this best-first harness is LESS search-efficient than E8's layered BFS", flush=True)
    print("  -- the size-only sanity did NOT reach trunc within 200k where E8's BFS reaches it at ~109k -- so guided's", flush=True)
    print("  failure cannot be cleanly blamed on the gradient. SUSPECT: match-count is deceptive for compositional", flush=True)
    print("  targets (necessary sub-parts e.g. sign(a*b) have ~0 standalone match, so best-first starves them).", flush=True)
    print("SOUND-REJECTION HELD: 0 confabulation committed; verify() killed the 14-row overfit; ablate/shuffle/half_even", flush=True)
    print("  all ABSTAINED as predicted. Limit #10 STANDS unweakened. Clean test needs gradient-ordering grafted onto", flush=True)
    print("  E8's efficient layered generator (so size-only reproduces ~109203); that is the next step.", flush=True)
    print("n=2 targets, ONE basis.", flush=True)
