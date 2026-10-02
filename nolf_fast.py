"""FAST PROBE HARNESS for nolf hypotheses. Not an experiment: no gates, no claim. A speed tool.

WHY: every question so far cost a 240-900 s fit, of which ~70 s was rebuilding the same enumeration table and
most of the rest was re-solving skeletons already known to solve. The questions that actually matter are of the
form "is there a term for THIS skeleton at THIS depth / with THIS library?", which needs one skeleton and a
cached table.

The table is pickled per (world, max_ops, cap, library fingerprint) and reloaded in ~1 s, so a hypothesis costs
seconds instead of minutes. Solving is the UNCHANGED nolf_learn._solve -- verification, the evidence gate and the
denotation solve are the real ones, so a hit here is a real hit.

    python nolf_fast.py --world strings --list
    python nolf_fast.py --world strings --skel "['gloop', 6, 5, 6]"
    python nolf_fast.py --world strings --skel all-unsolved --max-ops 5
    python nolf_fast.py --world strings --skel all-unsolved --lib-from learned   # adopted fragments as leaves
"""
import os, sys, time, pickle, hashlib, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_learn as NL
import nolf_worlds as NW

CACHE = os.path.join(HERE, "_nolf_fast_cache")


def _setup(world):
    W = NW.Records() if world == "records" else NW.Strings()
    train = NW.splits(W, 1)["train"]
    L = NL.Learner(time_budget=10 ** 9)
    L._classes(train); L.demoted = set()
    L.log = []; L.t0 = time.time()      # fit() normally sets these; _adopt() writes to both
    elems = set(); ints = set(range(0, 10))
    for sit, _, _ in train:
        for x in sit:
            if NL.P.CHECK[NL.ELEM](x): elems.add(x)
            elif NL.P.CHECK[NL.SEQ](x):
                for y in x:
                    if NL.P.CHECK[NL.ELEM](y): elems.add(y)
    rels = [p for p in NL.P.pids() if NL.P.signature(p) == ((NL.INT, NL.INT), NL.BOOL)]
    sels = [("all",), ("any",)] + [("idx", k) for k in range(-1, 4)]
    L.universe = {NL.HI: sorted(ints), NL.HE: sorted(elems, key=repr), NL.HR: rels, NL.HS: sels}
    by_size = {}
    for sit, _, _ in train: by_size.setdefault(len(sit), []).append(sit)
    probes = [x for k in sorted(by_size) for x in by_size[k][:3]][:8]
    if len(probes) < 8: probes += [sit for sit, _, _ in train[:8 - len(probes)]]
    return W, train, L, probes, elems, rels, sels


def _plain(T):
    return {k: {ty: list(v) for ty, v in d.items()} for k, d in T.items()}


def _restore(d):
    T = collections.defaultdict(lambda: collections.defaultdict(list))
    for k, dd in d.items():
        for ty, v in dd.items(): T[k][ty] = list(v)
    return T


def table(world, probes, elems, rels, sels, max_ops, cap, library):
    """build once, reuse forever. The cache key covers everything that changes the table."""
    os.makedirs(CACHE, exist_ok=True)
    fp = hashlib.sha1(repr(sorted(map(repr, library or {}))).encode()).hexdigest()[:10]
    path = os.path.join(CACHE, f"{world}_ops{max_ops}_cap{cap}_lib{len(library or {})}_{fp}.pkl")
    NL.BANK_CAP = cap
    E = NL.Enumerator(probes, elems, rels, sels, library=library, max_ops=max_ops)
    if os.path.exists(path):
        t = time.time()
        with open(path, "rb") as f: raw = pickle.load(f)
        E.tables = {lam: _restore(d) for lam, d in raw.items()}
        print(f"  [table CACHED: loaded in {time.time()-t:.1f}s from {os.path.basename(path)}]", flush=True)
        return E
    t = time.time()
    E.table(False)
    secs = time.time() - t
    with open(path, "wb") as f:
        pickle.dump({lam: _plain(T) for lam, T in E.tables.items()}, f, protocol=4)
    tot = sum(len(E.tables[False][k].get(NL.BOOL, [])) for k in E.tables[False])
    print(f"  [table BUILT in {secs:.0f}s, {tot} BOOL terms, cached]", flush=True)
    return E


def warmup(world, L, g, E, skip=None, per=20, passes=1):
    """MEASURED THE HARD WAY: a skeleton solved in isolation mostly does not solve at all -- the denotation CSP is
    only tractable once earlier constructions have PINNED words (that is what the real loop's pinned_frac
    curriculum buys). Warm-up therefore has to run before any probe, and it costs minutes, so it is CACHED: the
    same waste the table had."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"warm_{world}_{'skip' + hashlib.sha1(repr(skip).encode()).hexdigest()[:6] if skip else 'all'}.pkl")
    if os.path.exists(path):
        t = time.time()
        with open(path, "rb") as f: dom, gram, rows_of = pickle.load(f)
        L.dom, L.grammar, L.rows_of = dom, gram, rows_of
        print(f"  [warm-up CACHED: {len(gram)} constructions, {len(dom)} pinned, loaded in {time.time()-t:.1f}s]", flush=True)
        return L
    L.grammar = {}; L.dom = {}; L.demoted = set()
    t0 = time.time()
    for _ in range(passes):
        for k in sorted(g, key=lambda k: -len(g[k])):
            if k in L.grammar or len(g[k]) < NL.MIN_ROWS or (skip and k in skip): continue
            L.deadline = time.time() + per
            f = L._solve(k, list(g[k]), E)
            if f:
                L._adopt(k, list(g[k]), f)
                print(f"  warm-up: {show_key(k)} -> {NL.show(f[0][0])}", flush=True)
    print(f"  [warm-up BUILT in {time.time()-t0:.0f}s: {len(L.grammar)} constructions, {len(L.dom)} pinned, cached]", flush=True)
    with open(path, "wb") as f: pickle.dump((L.dom, L.grammar, L.rows_of), f, protocol=4)
    return L


def groups_of(L, train):
    g = collections.defaultdict(list)
    for sit, toks, tv in train:
        key, fill = L._key([("c", L.cls[w], w) for w in toks])
        g[key].append((sit, fill, tv))
    return g


def show_key(key):
    return repr([x if x == "B" else x[1] for x in key])


def main(world, want, max_ops, cap, lib_from, per_skel):
    W, train, L, probes, elems, rels, sels = _setup(world)
    g = groups_of(L, train)
    library = None
    if lib_from == "learned":
        # the six terms the real run adopts, as leaves -- the library lever, without re-earning it
        seeds = [("S", ("SIT",), ("A", "b2c6", ("VAR",), ("H", NL.HE)))]
        library = {}
        print("  [--lib-from learned: seeding adopted-shape fragments is not reconstructible here; use --max-ops]")
    E = table(world, probes, elems, rels, sels, max_ops, cap, library)
    keys = sorted(g, key=lambda k: -len(g[k]))
    keys = [k for k in keys if len(g[k]) >= NL.MIN_ROWS]
    if want == "--list":
        print(f"{'rows':>6}  skeleton")
        for k in keys: print(f"{len(g[k]):6d}  {show_key(k)}")
        return
    targets = keys if want == "all" else [k for k in keys if show_key(k) == want]
    if not targets:
        print(f"no skeleton matches {want!r}; use --list"); return
    print(f"=== {W.name}  max_ops={max_ops} cap={cap}  solving {len(targets)} skeleton(s), {per_skel}s each")
    for k in targets:
        rows = g[k]
        L.grammar = {}; L.dom = {}; L.demoted = set()
        L.deadline = time.time() + per_skel
        t = time.time()
        found = L._solve(k, list(rows), E)
        dt = time.time() - t
        if found:
            print(f"  SOLVED   {len(rows):5d} rows  {dt:6.1f}s  {NL.show(found[0][0])}   <- {show_key(k)}", flush=True)
        else:
            print(f"  no term  {len(rows):5d} rows  {dt:6.1f}s  {'(deadline)' if dt >= per_skel - 1 else '(exhausted)'}"
                  f"   <- {show_key(k)}", flush=True)


if __name__ == "__main__":
    a = sys.argv
    world = a[a.index("--world") + 1] if "--world" in a else "strings"
    max_ops = int(a[a.index("--max-ops") + 1]) if "--max-ops" in a else 4
    cap = int(a[a.index("--cap") + 1]) if "--cap" in a else 60000
    per = int(a[a.index("--per") + 1]) if "--per" in a else 60
    lib = a[a.index("--lib-from") + 1] if "--lib-from" in a else None
    want = "--list" if "--list" in a else (a[a.index("--skel") + 1] if "--skel" in a else "all")
    main(world, want, max_ops, cap, lib, per)
