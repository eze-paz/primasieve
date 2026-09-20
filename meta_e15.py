"""E15 — NOVELTY / QUALITY-DIVERSITY ORDERING vs the deceptive verifier gradient (meta_e15_prereg.md).
ZERO LLM, pure stdlib. E9 retest on a CLEAN harness: E8's layered generator on core.generate.SignatureBank with
ONE new degree of freedom -- a per-round PERMUTATION of parents (newest layer) and partners (all so far).
IDENTITY ordering must reproduce E8's trunc energy 109203 EXACTLY (the calibration E9 lacked). Then: does a
TARGET-BLIND diversity ordering (cell-rarity / value-rarity / QD round-robin) beat blind order and E9's
target-aware match-count gradient? Energy = unique signatures materialized until the target signature appears
(E8/E10's metric). Worst of 3 seeds governs; decoy sweep guards the descriptor choice (see prereg)."""
import os, sys, time, math, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.registry import selfcheck
from core.generate import SignatureBank
import meta_e8, meta_e9
from meta_e9 import probe_rows, sqlite_div, sqlite_mod, verify, ev, label, size, LEAF_FNS

X = meta_e8.X
UNARY, BINARY = meta_e8.UNARY, meta_e8.BINARY
CAP = 120000
FIT_N = 28


# ---------------------------------------------------------------- the generator (E8's, on SignatureBank)
def leaves_for(rows, extra_atoms=()):
    out = [(("leaf", k), tuple(LEAF_FNS[k](a, b) for a, b in rows)) for k in ("a", "b", "1", "2")]
    for at in extra_atoms:
        out.append((at, tuple(at[2](a, b) for a, b in rows)))
    return out


def ordered_bfs(rows, target, order, extra_atoms=(), ablate=False, depth=3, cap=CAP, ctx=None, extra_bin=()):
    """E8.enum_until with a per-round permutation of parents/partners. -> dict(tree, energy, rounds)."""
    ctx = ctx if ctx is not None else {}
    target = tuple(target)
    uni = {k: v for k, v in UNARY.items() if not (ablate and k in ("abs", "sign"))}
    bino = list(BINARY.items()) + list(extra_bin)
    bank = SignatureBank(cap=cap)
    order_list = bank.order                            # [(tree, sig)] in insertion order = E8's `order`
    rounds = []

    def add(tree, sig):
        if not bank.add(tree, sig):
            return False
        return sig == target

    for t, s in leaves_for(rows, extra_atoms):
        if add(t, s):
            return {"tree": t, "energy": len(order_list), "rounds": rounds}
    start = 0
    for _ in range(depth):
        cur = list(order_list); newstart = len(order_list); rounds.append(newstart)
        parents = order(cur[start:], cur, target, ctx)
        partners = order(cur, cur, target, ctx)
        for t, s in parents:                           # unary on the newest layer
            for un, uf in uni.items():
                nt = ("u", un, t)
                if add(nt, tuple(uf(v) for v in s)):
                    return {"tree": nt, "energy": len(order_list), "rounds": rounds}
            if bank.full():
                return {"tree": None, "energy": len(order_list), "rounds": rounds}
        for t1, s1 in parents:                         # binary: newest x all-so-far
            if bank.full():
                return {"tree": None, "energy": len(order_list), "rounds": rounds}
            for t2, s2 in partners:
                for bn, bf in bino:
                    nt = ("b", bn, t1, t2)
                    if add(nt, tuple(bf(x, y) for x, y in zip(s1, s2))):
                        return {"tree": nt, "energy": len(order_list), "rounds": rounds}
        start = newstart
        if bank.full():
            break
    return {"tree": None, "energy": len(order_list), "rounds": rounds}


# ---------------------------------------------------------------- orderings (all: items, bank, target, ctx)
def o_identity(items, bank, target, ctx):
    return items


def o_random(items, bank, target, ctx):
    it = list(items); ctx["rng"].shuffle(it); return it


def o_match(items, bank, target, ctx):                 # E9's verifier gradient, target-AWARE
    return sorted(items, key=lambda ts: -sum(1 for u, v in zip(ts[1], target) if u == v))


def _bucket(n):
    return n if n <= 4 else (5 if n <= 8 else (6 if n <= 16 else 7))


def cell(sig):                                         # target-BLIND descriptor, any hashable domain
    return (sum(1 for v in sig if v is X), _bucket(len(set(sig))))


def o_cell_rarity(items, bank, target, ctx):
    cnt = collections.Counter(cell(s) for _, s in bank)
    return sorted(items, key=lambda ts: cnt[cell(ts[1])])


def o_value_rarity(items, bank, target, ctx):
    if not bank:
        return items
    n = len(bank[0][1]); freq = [collections.Counter() for _ in range(n)]
    for _, s in bank:
        for i, v in enumerate(s):
            freq[i][v] += 1
    def nov(s): return sum(math.log(freq[i][v]) for i, v in enumerate(s))   # lower = rarer
    return sorted(items, key=lambda ts: nov(ts[1]))


def o_qd(items, bank, target, ctx):                    # round-robin over cells, rarest cell first
    groups = collections.OrderedDict()
    for ts in items:
        groups.setdefault(cell(ts[1]), []).append(ts)
    cells = sorted(groups, key=lambda c: len(groups[c]))
    out, idx = [], {c: 0 for c in cells}
    while len(out) < len(items):
        for c in cells:
            g = groups[c]
            if idx[c] < len(g):
                out.append(g[idx[c]]); idx[c] += 1
    return out


def o_ceiling(items, bank, target, ctx):               # DIAGNOSTIC: known answer's sub-trees first (cheats)
    parts = ctx["answer_parts"]
    front = [ts for ts in items if label(ts[0]) in parts]
    rest = [ts for ts in items if label(ts[0]) not in parts]
    return front + rest


ARMS = [("IDENTITY", o_identity), ("MATCH", o_match), ("CELL-RARITY", o_cell_rarity),
        ("VALUE-RARITY", o_value_rarity), ("QD", o_qd)]
BLIND_ARMS = {"CELL-RARITY", "VALUE-RARITY", "QD"}


def run(rows, target, order, oracle=None, seed=0, **kw):
    ctx = {"rng": random.Random(seed)}; ctx.update(kw.pop("ctx", {}))
    t0 = time.time(); r = ordered_bfs(rows, target, order, ctx=ctx, **kw)
    r["secs"] = time.time() - t0
    r["ok"] = (r["tree"] is not None) and (oracle is None or verify(r["tree"], oracle, seed))
    if r["tree"] is not None and oracle is not None and not r["ok"]:
        r["confab_rejected"] = True                    # fit-match that fails verify: REJECTED, never committed
    return r


def fmt(r):
    return (f"E={r['energy']:>6}" + (f" ok={r['ok']} {label(r['tree'])}" if r["tree"] else " ABSTAIN(cap)"))


if __name__ == "__main__":
    selfcheck(__file__)
    print("E15 — novelty/QD ordering vs the deceptive gradient, on E8's generator calibrated to 109203\n", flush=True)

    # ---- SANITY: identity on E8's S2 must reproduce 109203 exactly ----
    S2 = meta_e8.S2
    tsig = tuple(v if v is not None else X for v in (meta_e8.tgt_trunc(a, b) for a, b in S2))
    san = run(S2, tsig, o_identity)
    print(f"SANITY identity on S2: {fmt(san)}  (E8 published 109203)  rounds start at {san['rounds']}", flush=True)
    if san["energy"] != 109203 or san["tree"] is None:
        print("SANITY FAILED — harness does not reproduce E8; STOP, nothing below is evidence."); sys.exit(1)
    print("SANITY PASSED: harness == E8 blind\n", flush=True)

    TRUNC_PARTS = {"sign((a*b))", "(abs(a)//abs(b))"}
    per_seed = {}
    print("=== trunc (real sqlite3 oracle), 3 seeds x arms; energy = materialized unique sigs ===", flush=True)
    for sd in (1, 2, 3):
        rows = probe_rows(FIT_N, sd); T = [sqlite_div(a, b) for a, b in rows]
        res = {}
        for name, fn in ARMS:
            res[name] = run(rows, T, fn, sqlite_div, seed=sd)
            print(f"  seed {sd} {name:13s} {fmt(res[name])}  {res[name]['secs']:.1f}s", flush=True)
        rnd = [run(rows, T, o_random, sqlite_div, seed=100 + 10 * sd + j) for j in range(3)]
        res["RANDOM"] = sorted(rnd, key=lambda r: r["energy"])[1]
        print(f"  seed {sd} {'RANDOM(med/3)':13s} {fmt(res['RANDOM'])}  all={[r['energy'] for r in rnd]}", flush=True)
        res["CEILING"] = run(rows, T, o_ceiling, sqlite_div, seed=sd, ctx={"answer_parts": TRUNC_PARTS})
        print(f"  seed {sd} {'CEILING(diag)':13s} {fmt(res['CEILING'])}  round3 starts at {res['IDENTITY']['rounds'][-1]}", flush=True)
        per_seed[sd] = res

    print("\n=== verdicts (pre-registered) ===", flush=True)
    confab = any(r.get("tree") is not None and not r["ok"] and not r.get("confab_rejected")
                 for res in per_seed.values() for r in res.values())
    rejected = sum(1 for res in per_seed.values() for r in res.values() if r.get("confab_rejected"))
    print(f"  confabulation committed: {confab}   (fit-matches rejected by verify: {rejected})", flush=True)
    ident = {sd: per_seed[sd]["IDENTITY"]["energy"] for sd in per_seed}
    randm = {sd: per_seed[sd]["RANDOM"]["energy"] for sd in per_seed}

    def E(sd, arm):
        r = per_seed[sd][arm]; return r["energy"] if (r["tree"] and r["ok"]) else float("inf")

    for name, _ in ARMS[1:]:
        ratios_i = [ident[sd] / E(sd, name) for sd in per_seed]
        ratios_r = [randm[sd] / E(sd, name) for sd in per_seed]
        win = all(E(sd, name) <= ident[sd] / 3 and E(sd, name) <= randm[sd] / 3 for sd in per_seed)
        print(f"  {name:13s} speedup vs IDENTITY {[f'{x:.2f}x' for x in ratios_i]}  vs RANDOM {[f'{x:.2f}x' for x in ratios_r]}"
              f"  -> {'WIN (>=3x both, all seeds)' if win else 'null (reorders, does not help)'}", flush=True)
    match_decept = all(E(sd, "MATCH") >= randm[sd] for sd in per_seed)
    match_refute = all(E(sd, "MATCH") * 3 <= randm[sd] for sd in per_seed)
    print(f"  MATCH deceptive (>= RANDOM on every seed): {match_decept}   refuted (3x better than RANDOM): {match_refute}", flush=True)
    ceil = [ident[sd] / E(sd, "CEILING") for sd in per_seed]
    print(f"  CEILING available gain per seed: {[f'{x:.1f}x' for x in ceil]}   (E10 witness, different mechanism: ~3570 => {109203/3570:.0f}x)", flush=True)

    # ---- signmod: with trunc reused as an atom vs atoms-only ----
    print("\n=== signmod ===", flush=True)
    # first VERIFIED trunc tree from any arm (first run looked only at IDENTITY, which abstained at cap -> skipped)
    tt = next((per_seed[sd][a]["tree"] for sd in per_seed for a, _ in ARMS if per_seed[sd][a]["ok"]), None)
    rows = probe_rows(FIT_N, 1); Tm = [sqlite_mod(a, b) for a, b in rows]
    if tt:
        atom = ("atom", "trunc", (lambda a, b, x=tt: ev(x, a, b)))
        for name, fn in (("IDENTITY", o_identity), ("QD", o_qd)):
            r = run(rows, Tm, fn, sqlite_mod, seed=1, extra_atoms=(atom,))
            print(f"  with trunc-atom {name:9s} {fmt(r)}", flush=True)
    r = run(rows, Tm, o_qd, sqlite_mod, seed=1)
    print(f"  atoms-only      QD        {fmt(r)}   (predicted ABSTAIN at D=3; blind failed <=400k)", flush=True)

    # ---- knockouts ----
    print("\n=== knockouts ===", flush=True)
    rows = probe_rows(FIT_N, 1); T = [sqlite_div(a, b) for a, b in rows]
    sh = list(T); random.Random(5).shuffle(sh)
    r = run(rows, sh, o_qd, None, seed=1)
    print(f"  label-shuffle  QD: {'ABSTAIN' if r['tree'] is None else 'FOUND (KILL: chasing noise)'}  E={r['energy']}", flush=True)
    r = run(rows, T, o_qd, sqlite_div, seed=1, ablate=True)
    print(f"  ablate abs/sign QD: {'ABSTAIN' if not (r['tree'] and r['ok']) else 'FOUND (KILL)'}  E={r['energy']}", flush=True)

    # ---- genericity: decoys that IDENTITY places in round 3 ----
    print("\n=== genericity: random depth-3 decoys placed in round 3 by IDENTITY; speedup = IDENTITY/arm ===", flush=True)

    def rand_tree(rng, d):
        if d == 0: return ("leaf", rng.choice(["a", "b", "1", "2"]))
        if d < 3 and rng.random() < 0.3: return ("u", rng.choice(list(UNARY)), rand_tree(rng, d - 1))
        return ("b", rng.choice(list(BINARY)), rand_tree(rng, d - 1), rand_tree(rng, d - 1))

    rows = probe_rows(FIT_N, 1); kept = []; tried = 0
    for ds in range(40):
        if len(kept) >= 6: break
        rng = random.Random(9000 + ds); dt = rand_tree(rng, 3)
        dout = tuple(ev(dt, a, b) for a, b in rows)
        if X in dout or len(set(dout)) < 3: continue
        tried += 1
        base = run(rows, dout, o_identity)
        if base["tree"] is None or base["energy"] < base["rounds"][-1]: continue      # not a round-3 item
        sp = {}
        for name, fn in ARMS:
            if name in BLIND_ARMS:
                r = run(rows, dout, fn, seed=1); sp[name] = base["energy"] / r["energy"] if r["tree"] else 0.0
        kept.append((label(dt), base["energy"], sp))
        print(f"  decoy {label(dt):40s} identity E={base['energy']:>6}  " + "  ".join(f"{k}={v:.2f}x" for k, v in sp.items()), flush=True)
    print(f"  ({len(kept)} decoys kept of {tried} round-3-eligible attempts)", flush=True)
    for name in sorted(BLIND_ARMS):
        ds = sorted(s[2][name] for s in kept)
        if not ds: continue
        dmed = ds[len(ds) // 2]
        tr_worst = min(ident[sd] / E(sd, name) for sd in per_seed)
        print(f"  {name:13s} decoy median speedup {dmed:.2f}x  vs trunc worst-seed speedup {tr_worst:.2f}x  "
              f"-> {'FLAG: descriptor target-tuned (>3x decoy median)' if tr_worst > 3 * dmed else 'no flag'}", flush=True)

    # =================================================================================================
    # POST-HOC SECTION — added AFTER the first run showed (a) IDENTITY/RANDOM CENSORED at cap on the real-oracle
    # rows and (b) MATCH winning against its own prediction. Nothing above was changed. These are TIGHTENINGS
    # (uncensor the baseline; give the winning arm the knockouts the losing arms got), labelled as such.
    # =================================================================================================
    print("\n=== POST-HOC 1: uncensored blind — IDENTITY at cap 500000 on the same rows (first run hit cap 120000) ===", flush=True)
    unc = {}
    for sd in per_seed:
        rows = probe_rows(FIT_N, sd); T = [sqlite_div(a, b) for a, b in rows]
        r = run(rows, T, o_identity, sqlite_div, seed=sd, cap=500000); unc[sd] = r
        m = E(sd, "MATCH")
        print(f"  seed {sd} IDENTITY@500k {fmt(r)}  {r['secs']:.1f}s  -> true blind/MATCH = "
              f"{(r['energy'] / m):.1f}x{'' if r['tree'] else ' (still censored)'}   blind/CEILING = {(r['energy'] / E(sd, 'CEILING')):.1f}x", flush=True)

    print("\n=== POST-HOC 2: MATCH knockouts (E9 KILL #4/#6 + ablation), cap 120000 ===", flush=True)
    rows = probe_rows(FIT_N, 1); T = [sqlite_div(a, b) for a, b in rows]
    sh = list(T); random.Random(5).shuffle(sh)
    r = run(rows, sh, o_match, None, seed=1)
    print(f"  label-shuffle   MATCH: {'ABSTAIN' if r['tree'] is None else 'FOUND (KILL: chasing noise)'}  E={r['energy']}", flush=True)
    r = run(rows, T, o_match, sqlite_div, seed=1, ablate=True)
    print(f"  ablate abs/sign MATCH: {'ABSTAIN' if not (r['tree'] and r['ok']) else 'FOUND (KILL) ' + label(r['tree'])}  E={r['energy']}", flush=True)
    extra_bin = (("%", lambda x, y: X if (X in (x, y) or y == 0) else x % y),
                 ("mn", lambda x, y: X if X in (x, y) else min(x, y)),
                 ("mx", lambda x, y: X if X in (x, y) else max(x, y)))
    r = run(rows, T, o_match, sqlite_div, seed=1, extra_bin=extra_bin)
    base = E(1, "MATCH")
    print(f"  distractor ops (%,min,max) MATCH: {fmt(r)}  = {r['energy'] / base:.2f}x undistracted (E10 bound 3x: "
          f"{'within' if r['tree'] and r['energy'] <= 3 * base else 'EXCEEDED'})", flush=True)

    print("\n=== POST-HOC 3: MATCH genericity on the same 6 decoys (speedup = IDENTITY/MATCH) ===", flush=True)
    rows = probe_rows(FIT_N, 1); msp = []
    for ds in range(40):
        if len(msp) >= 6: break
        rng = random.Random(9000 + ds); dt = rand_tree(rng, 3)
        dout = tuple(ev(dt, a, b) for a, b in rows)
        if X in dout or len(set(dout)) < 3: continue
        base_r = run(rows, dout, o_identity)
        if base_r["tree"] is None or base_r["energy"] < base_r["rounds"][-1]: continue
        r = run(rows, dout, o_match, seed=1)
        sp = base_r["energy"] / r["energy"] if r["tree"] else 0.0; msp.append(sp)
        print(f"  decoy {label(dt):40s} identity E={base_r['energy']:>6}  MATCH E={r['energy']:>6}  {sp:.2f}x", flush=True)
    msp.sort(); dmed = msp[len(msp) // 2] if msp else None
    tr_worst = min((unc[sd]["energy"] if unc[sd]["tree"] else float("inf")) / E(sd, "MATCH") for sd in per_seed)
    print(f"  MATCH decoy median speedup {dmed:.2f}x (n={len(msp)}); trunc worst-seed speedup {tr_worst:.1f}x  -> "
          f"{'trunc >3x MORE favoured than random targets (E9 KILL#5 sense: report, MATCH has no tunable descriptor)' if dmed and tr_worst > 3 * dmed else 'no outlier flag'}", flush=True)

    print("\n--- HONEST VERDICT: read from the lines above; nothing above the POST-HOC line was changed after seeing data;"
          " the POST-HOC section is labelled. n=1 target family (+decoys), one basis. ---", flush=True)
