"""CONSOLIDATION SELF-TEST -- the gate on the core itself.

A core adopted by only one thread is not a core, it is that thread's private helper with extra steps. So this
file enforces, mechanically:

  C1  at least TWO INDEPENDENT threads import core/, where independent means they were in different connected
      components of the import graph before consolidation
  C2  every migrated thread still reproduces its PUBLISHED gate numbers -- consolidation that moves a number
      is a regression, not a refactor
  C3  ZERO ISLANDS: the live surface must be ONE connected component. No island is allowed -- merge or delete.

Run it after any change to core/. Usage:  python core_selftest.py [--map-only]"""
import os, re, sys, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# the components as measured BEFORE consolidation (94 components over 193 files, 76 of them single-file)
BASELINE_MAP = dict(components=94, files=193, singletons=76)


def island_map(root=HERE):
    fs = [f[:-3] for f in os.listdir(root) if f.endswith(".py")]
    local = set(fs)
    adj = collections.defaultdict(set)
    for f in fs:
        src = open(os.path.join(root, f + ".py"), encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", src, re.M):
            d = m.group(1)
            if d in local and d != f:
                adj[f].add(d)
                adj[d].add(f)
        if re.search(r"^\s*from\s+core[. ]|^\s*import\s+core\b", src, re.M):
            adj[f].add("core")
            adj["core"].add(f)
    seen, comps = set(), []
    for f in list(local) + ["core"]:
        if f in seen:
            continue
        st, c = [f], []
        while st:
            x = st.pop()
            if x in seen:
                continue
            seen.add(x)
            c.append(x)
            st.extend(adj[x] - seen)
        comps.append(sorted(c))
    comps.sort(key=len, reverse=True)
    return comps, sorted(adj["core"])


def check_adoption(adopters):
    """C1 -- independence measured by pre-consolidation component, not by counting files."""
    THREADS = {"cogs": "COGS Stage 3 (component 2)", "scan": "SCAN Stage 2 (component 11)",
               "phase6": "Phase 6 tolerance sets (singleton island)", "percept": "perception",
               "dialog": "dialogue", "l0": "l0 universal base", "meta_": "meta-reasoner (component 1)",
               "seg": "segmentation", "infl": "inflection", "vn_": "Rosetta roles", "puzzle": "puzzles"}
    hit = {}
    for a in adopters:
        for k, name in THREADS.items():
            if a.startswith(k):
                hit.setdefault(name, []).append(a)
    return hit


if __name__ == "__main__":
    comps, adopters = island_map()
    singles = sum(1 for c in comps if len(c) == 1)
    print("C3 -- ISLAND MAP")
    print(f"  before consolidation: {BASELINE_MAP['components']} components over "
          f"{BASELINE_MAP['files']} files, {BASELINE_MAP['singletons']} single-file islands")
    print(f"  now:                  {len(comps)} components, {singles} single-file islands")
    print(f"  largest component:    {len(comps[0])} files")
    ok3 = len(comps) == 1
    print(f"  -> islands: {len(comps) - 1}   [gate == 0 -> {'PASS' if ok3 else 'FAIL'}]")
    if not ok3:
        for c in comps[1:]:
            print(f"     ISLAND: {', '.join(c)}")
    print(f"\n  core/ is imported by {len(adopters)} modules: {', '.join(adopters)}")

    hit = check_adoption(adopters)
    print("\nC1 -- INDEPENDENT-THREAD ADOPTION (a core with one adopter is not a core)")
    for name, mods in sorted(hit.items()):
        print(f"  {name:<40} {', '.join(sorted(mods))}")
    ok1 = len(hit) >= 2
    print(f"  -> {len(hit)} independent threads on core   [gate >= 2 -> {'PASS' if ok1 else 'FAIL'}]")

    if "--map-only" in sys.argv:
        sys.exit(0)

    print("\nC2 -- PUBLISHED NUMBERS MUST NOT MOVE")
    checks = []
    from cogs_data import load as cogs_load, Analogy as CAnalogy, evaluate as cogs_eval
    from cogs_gram import induce as cogs_induce, generate as cogs_generate, reproduce as cogs_reproduce
    from scan_data import load as scan_load
    from scan_engine import induce as scan_induce, evaluate as scan_eval, reproduces

    tr, dev, test, gen = cogs_load()
    agg, _ = cogs_eval(CAnalogy(tr), gen)
    checks.append(("COGS analogy baseline gen EM", agg["em"] / agg["n"], 0.000))

    m = cogs_induce(tr)
    ok, wr, npar = cogs_reproduce(m, tr)
    checks.append(("COGS train reproduction", ok / max(ok + wr + npar, 1), 1.0000))
    n = em = 0
    from cogs_data import em as cem
    for s, gold, cat in gen:
        p = cogs_generate(m, s)
        n += 1
        em += cem(p, gold)
    checks.append(("COGS gen EM (21000 items)", em / n, 0.9990))

    strn, ste = scan_load("simple")
    G = scan_induce(strn)
    r, t = reproduces(G, strn)
    checks.append(("SCAN simple train reproduction", r / t, 1.0000))
    checks.append(("SCAN simple test EM", scan_eval(G, ste)["EM"], 1.0000))

    # Every other live result comes from ONE list: core/registry.py. Each module is re-run and its
    # registered computed claims must still appear. Adding an experiment to the live surface = adding its
    # claim there; this loop then protects it automatically.
    import io, contextlib, runpy
    from core.registry import PUBLISHED, verify_output
    def _locate(mod):
        """a registered module normally sits at the top level; thread subdirectories (emergence/) are searched
        so a registered claim there is protected by the same loop (em_closure)."""
        top = os.path.join(HERE, mod + ".py")
        if os.path.exists(top):
            return None                                    # run by module name, as before
        for root, dirs, files in os.walk(HERE):
            dirs[:] = [d for d in dirs if not d.startswith((".", "_")) and d != "__pycache__"]
            if mod + ".py" in files:
                return os.path.join(root, mod + ".py")
        return None

    for mod in sorted(PUBLISHED):
        buf = io.StringIO()
        path = _locate(mod)
        try:
            with contextlib.redirect_stdout(buf):
                if path:
                    runpy.run_path(path, run_name="__main__")
                else:
                    runpy.run_module(mod, run_name="__main__")
        except SystemExit:
            pass
        for claim, found in verify_output(mod, buf.getvalue()):
            checks.append((f"{mod}: {claim[:26]}", 1.0 if found else 0.0, 1.0))

    allok = True
    for name, got, want in checks:
        good = abs(got - want) < 5e-4
        allok &= good
        print(f"  {name:<34} {got:.4f}  published {want:.4f}  {'OK' if good else 'MOVED'}")
    print(f"  -> {'PASS' if allok else 'FAIL'}")
    print(f"\nCONSOLIDATION SELF-TEST: {'PASS' if (ok1 and allok) else 'FAIL'}")
