"""INCREMENTAL ENUMERATION TABLE -- the measurement (nolf_rebuild_prereg.md). Imports core/ only through nolf_learn;
the world module is touched only for the B5 fit.

B1/B2  extend(base -> L) and extend(L1 -> L2) are EQUIVALENT to full builds (signature sets per (lam, level, type))
B3     round-2 cost: time(extend L1 -> L2) vs time(full build L2)
B4     single-rebuild cost: time(base) + time(extend L) vs time(full build L)  -- the closure prereg's recommendation
B5     the learner through the new library path: records 1.000 / strings standing number, CONFAB 0  (--fit)

Fragments are the REAL ones harvested from one 240 s fit per world, in `nolf_fragments.json` (or --frags DIR with the
harvest pickles records_fit.pkl / strings_fit.pkl). Reports both max_ops=2 (the library pass's setting) and max_ops=4.

    python nolf_rebuild.py [--fit] [--cap 60000] [--ops 2,4] [--all] [--frags DIR]"""
import os, sys, time, pickle, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nolf_learn as NL


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def _dec(o):
    if isinstance(o, dict) and "__t" in o: return tuple(_dec(x) for x in o["__t"])
    if isinstance(o, list): return [_dec(x) for x in o]
    if isinstance(o, dict): return {k: _dec(v) for k, v in o.items()}
    return o


def load_fragments(world):
    """nolf_fragments.json: the fragments harvested from one 240 s fit per world (tuples encoded as {"__t": [...]})."""
    import json
    raw = _dec(json.load(open(os.path.join(HERE, "nolf_fragments.json"), encoding="utf-8")))[world]
    return dict(fragments={f: tuple(tv) for f, tv in raw["fragments"]}, probes=raw["probes"], elems=set(raw["elems"]), rels=raw["rels"], sels=raw["sels"])


def build(args, lib, max_ops):
    t = time.time(); E = NL.Enumerator(*args, library=dict(lib), max_ops=max_ops); E.table(False)
    return E, time.time() - t


def extend(E, lib):
    t = time.time(); rep = E.extend(dict(lib)); return rep, time.time() - t


def equivalent(Ea, Eb):
    sa, sb = Ea.signature_sets(), Eb.signature_sets()
    keys = sorted(set(sa) | set(sb), key=repr)
    diffs = [(k, len(sa.get(k, ())), len(sb.get(k, ())), len(sa.get(k, frozenset()) ^ sb.get(k, frozenset())))
             for k in keys if sa.get(k, frozenset()) != sb.get(k, frozenset())]            # (key, |full|, |extend|, |symmetric difference|)
    return diffs, sum(len(v) for v in sa.values())


def measure(world, d, cap, max_ops):
    NL.BANK_CAP = cap
    args = (d["probes"], d["elems"], d["rels"], d["sels"]); L = d["fragments"]
    items = list(L.items()); L1 = dict(items[:len(items) // 2]); L2 = dict(items)
    say(f"\n  [{world}] max_ops={max_ops} cap={cap}: {len(L2)} fragments, round-1 library {len(L1)}")
    Ef, tf = build(args, L2, max_ops)                                     # the full build with everything
    E0, tb = build(args, {}, max_ops); rep, te = extend(E0, L2)           # base, then extend by everything
    d1, n = equivalent(Ef, E0)
    say(f"    full build L2            {tf:7.1f} s   ({n} signatures)")
    say(f"    base {tb:5.1f} s + extend L2 {te:5.1f} s = {tb + te:5.1f} s   delta terms {rep}   B1 {'EQUIVALENT' if not d1 else 'DIFFERS ' + str(d1[:4])}")
    E1, t1 = build(args, L1, max_ops); rep2, t12 = extend(E1, L2)       # round 1 full, round 2 incremental
    d2, _ = equivalent(Ef, E1)
    say(f"    full build L1 {t1:5.1f} s, then extend L1->L2 {t12:5.1f} s   delta terms {rep2}   B2 {'EQUIVALENT' if not d2 else 'DIFFERS ' + str(d2[:4])}")
    b3 = tf / t12 if t12 > 0 else float("inf"); b4 = 1 - (tb + te) / tf if tf > 0 else 0.0
    say(f"    B3 round-2 speedup  full(L2)/extend(L1->L2) = {b3:.2f}x     B4 single-rebuild saving = {100 * b4:.0f}%")
    return dict(world=world, max_ops=max_ops, cap=cap, full=tf, base=tb, ext=te, r1=t1, ext2=t12, b1=not d1, b2=not d2, b3=b3, b4=b4, nsig=n)


def fit(world, budget):
    import nolf_worlds as NW
    W = NW.Records() if world == "records" else NW.Strings()
    from core.verdict import score_two_mode
    sp = NW.splits(W, 1); t = time.time()
    L = NL.Learner(time_budget=budget).fit(sp["train"])
    r = {split: score_two_mode(L, [((sit, toks), tv) for sit, toks, tv in sp[split]]) for split in ("heldout_iid", "heldout_comp")}
    em, emi = r["heldout_comp"]["EM"], r["heldout_iid"]["EM"]
    confab = r["heldout_comp"]["confab"] + r["heldout_iid"]["confab"]
    say(f"  [{world}] fit {time.time() - t:.0f} s: {len(L.grammar)} constructions, library build {getattr(L, 'library_build_seconds', 0):.1f} s, "
        f"comp EM {em:.4f} iid EM {emi:.4f} CONFAB {confab:.4f}")
    return em, emi, confab, len(L.grammar)


if __name__ == "__main__":
    from core.registry import selfcheck
    selfcheck(__file__)
    a = sys.argv
    frags = a[a.index("--frags") + 1] if "--frags" in a else None
    cap = int(a[a.index("--cap") + 1]) if "--cap" in a else 60000
    ops = [int(x) for x in a[a.index("--ops") + 1].split(",")] if "--ops" in a else [2]      # the registered setting; --ops 2,4 for the full report (records at 4 is ~100 s per build)
    # strings at max_ops=4 with its 12 fragments: the three full builds did not finish in 50 minutes on the registration
    # day (the library pass's max_ops=2 is what keeps the lever affordable); reported as not run unless asked for
    skip = set() if "--all" in a else {("strings", 4)}
    say("INCREMENTAL TABLE -- extend() vs full rebuild (nolf_rebuild_prereg.md)")
    rows = []
    for world in (() if "--fit-only" in a else ("records", "strings")):
        if frags:
            path = os.path.join(frags, f"{world}_fit.pkl")
            if not os.path.exists(path): say(f"  [{world}] no fragments at {path}"); continue
            d = pickle.load(open(path, "rb"))
        else:
            d = load_fragments(world)
        say(f"\n[{world}] fragments ({len(d['fragments'])}):")
        for f, tv in d["fragments"].items(): say(f"    {NL.show(f)}  {tv}")
        for mo in ops:
            if (world, mo) in skip:
                say(""); say(f"  [{world}] max_ops={mo}: NOT RUN (full builds exceeded 50 min at registration; --all to run)"); continue
            rows.append(measure(world, d, cap, mo))
        if cap == 60000:
            rows.append(measure(world, d, 6000, 2))            # the shipped cap: reported, not gated (arrival order decides)
    say("\nGATES (cap 60000):")
    g = [r for r in rows if r["cap"] == 60000]
    by_ops = {mo: [r for r in g if r["max_ops"] == mo] for mo in sorted({r["max_ops"] for r in g})}
    for mo, rr in by_ops.items():
        say(f"  max_ops={mo}: B1 {'EQUIVALENT' if all(r['b1'] for r in rr) else 'DIFFERS'}, B2 {'EQUIVALENT' if all(r['b2'] for r in rr) else 'DIFFERS'} on {[r['world'] for r in rr]}")
    b1 = all(r["b1"] for r in g); b2 = all(r["b2"] for r in g)
    b3 = max([r["b3"] for r in g if r["max_ops"] == 2] or [0]); b4 = [round(100 * r["b4"]) for r in g if r["max_ops"] == 2]
    eq2 = bool(by_ops.get(2)) and all(r["b1"] and r["b2"] for r in by_ops[2])
    say(f"  B1 extend(base->L) equivalent to full build on every (world, max_ops) run: {'PASS' if b1 else 'FAIL'}")
    say(f"  B2 extend(L1->L2) equivalent to full build L2 on every (world, max_ops) run: {'PASS' if b2 else 'FAIL'}")
    say(f"  B3 best round-2 speedup at max_ops=2: {b3:.2f}x   [>= 3x -> {'PASS' if b3 >= 3 else 'FAIL'}]")
    say(f"  B4 single-rebuild saving at max_ops=2 (records, strings): {b4} %   [reported; predicted < 20%]")
    if "--fit" in a:
        say("\nB5 the learner through the new library path (240 s per world):")
        r_rec = fit("records", 240); r_str = fit("strings", 240)
        ok5 = r_rec[0] >= 0.95 and r_rec[2] == 0 and r_str[2] == 0
        say(f"  B5 records comp EM {r_rec[0]:.4f} (>= 0.95), CONFAB {r_rec[2] + r_str[2]}; strings comp EM {r_str[0]:.4f} (standing 0.7483)   [{'PASS' if ok5 else 'FAIL'}]")
    if rows:
        at4 = by_ops.get(4, [])
        say(f"\nINCREMENTAL TABLE at max_ops=2 (the library pass): {'EQUIVALENT' if eq2 else 'NOT EQUIVALENT'}; round-2 speedup {b3:.2f}x; "
            f"at max_ops=4: {'not run' if not at4 else ('equivalent' if all(r['b1'] and r['b2'] for r in at4) else 'differs by a few signatures (the signature is approximate and not compositional)')}")
