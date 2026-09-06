"""SWE-MINE -- structural repair operators from a repository's own history (swe_mine_prereg.md). Static, no Docker.

    python swe_mine.py [--repo _nldata/repos/sympy] [--max-commits N] [--rebuild]

OBSERVE  commits touching >= 1 test file and exactly one non-test .py file (<= 80 changed lines): before/after text
DERIVE   the smallest differing statement span, classified with the census fix families (recovered verbatim), and
         canonicalised to a SKELETON (AST node types + arity, leaves -> numbered holes) and a SHAPE (top-level
         statement types removed -> added)
COVER    operators = skeletons by frequency, mined from commits before a date cutoff; coverage curve on the
         held-out year and (when the instance file is present) on SWE-bench Lite sympy gold patches, each judged
         against operators from BEFORE its base commit only
LENGTH   primitive-edit count of each operator (the path a token-level search would walk in the dark)"""
import os, sys, re, ast, json, time, subprocess, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_nldata", "swe_mine_edits.json")
INSTANCES = os.path.join(HERE, "_nldata", "swebench_lite_sympy.json")   # optional: [{instance_id, base_commit, patch, created_at}]

# ---------------------------------------------------------------- the census families, verbatim (swebench_families.py @ 8e7154b^)
NEWDEF = re.compile(r"^\s*(def |class |async def |@)")
IMPORT = re.compile(r"^\s*(import |from .+ import)")
GUARD = re.compile(r"^\s*if .+:\s*(return|continue|break|raise|pass)?\s*$")
GUARD2 = re.compile(r"^\s*(return|continue|break|raise)\b")
ASSIGN = re.compile(r"^\s*[\w\.\[\]]+\s*(=|\+=|-=|\*=|\|=|&=)\s*.+")
ELSEEL = re.compile(r"^\s*(else|elif .+):\s*$")
STRUCTURAL = {"small-mixed-rewrite", "large-rewrite", "add-def/class", "insert:large", "insert:else/elif-branch"}


def family(add, rem):
    add = [l for l in add if l.strip()]; rem = [l for l in rem if l.strip()]
    if len(add) == 1 and len(rem) == 1:
        a, r = add[0].strip(), rem[0].strip()
        if r and r in a and a != r:
            mid = a.replace(r, "").strip()
            if re.fullmatch(r"[-+*/%|&^]|and|or|\+ .+|.+ \+|[-+*/%].*|.*[-+*/%]", mid) or mid.startswith(("+", "-", "*", "/", "|", "&", "and", "or")):
                return "PROJECTION-frame (wrap/extend)"
        return "token/expr-rewrite (1-for-1)"
    if len(rem) == 0:
        if any(NEWDEF.match(l) for l in add): return "insert:new-def/decorator"
        if any(IMPORT.match(l) for l in add): return "insert:import"
        if any(ELSEEL.match(l) for l in add): return "insert:else/elif-branch"
        if all(GUARD.match(l) or GUARD2.match(l) for l in add[:1]) and len(add) <= 3: return "insert:guard (if/return/continue)"
        if any(ASSIGN.match(l) for l in add): return "insert:assignment"
        if len(add) <= 3: return "insert:small-other"
        return "insert:large"
    if len(add) == 0: return "delete-only"
    if any(NEWDEF.match(l) for l in add): return "add-def/class"
    if len(add) + len(rem) <= 6: return "small-mixed-rewrite"
    return "large-rewrite"


def is_test(path):
    p = path.lower()
    return "/tests/" in p or "/test_" in p or p.startswith("test") or os.path.basename(p).startswith("test_") or "/testing/" in p


# ---------------------------------------------------------------- git
def git(repo, *args, text=True):
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True, text=text, encoding="utf-8" if text else None,
                          errors="replace").stdout


def commits(repo, max_commits=None):
    """(sha, unix time, [paths]) for every non-merge commit, newest first."""
    args = ["log", "--no-merges", "--format=%H %ct", "--name-only", "--diff-filter=AM"] + ([f"-n{max_commits}"] if max_commits else [])
    out = git(repo, *args)                          # the limit goes to git: fetching all 62k commits' names took > 10 min
    res, cur = [], None
    for line in out.splitlines():
        if re.fullmatch(r"[0-9a-f]{40} \d+", line):
            if cur: res.append(cur)
            sha, ts = line.split(); cur = (sha, int(ts), [])
        elif line.strip() and cur:
            cur[2].append(line.strip())
    if cur: res.append(cur)
    return res[:max_commits] if max_commits else res


def candidates(cs):
    """commits touching >= 1 test file and exactly ONE non-test .py file."""
    out = []
    for sha, ts, paths in cs:
        py = [p for p in paths if p.endswith(".py")]
        src = [p for p in py if not is_test(p)]; tests = [p for p in py if is_test(p)]
        if len(src) == 1 and tests: out.append((sha, ts, src[0]))
    return out


_BATCH = {}


def file_at(repo, sha, path):
    """file contents via ONE persistent `git cat-file --batch` process (a subprocess per file was the bottleneck:
    ~0.3 s per spawn on Windows, thousands of files)."""
    proc = _BATCH.get(repo)
    if proc is None or proc.poll() is not None:
        proc = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        _BATCH[repo] = proc
    proc.stdin.write((sha + ":" + path + "\n").encode()); proc.stdin.flush()
    header = proc.stdout.readline().decode(errors="replace").strip()
    if header.endswith("missing") or len(header.split()) < 3: return ""
    size = int(header.split()[2])
    data = proc.stdout.read(size); proc.stdout.read(1)
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- statement-level diff and canonical skeletons
def _stmts(tree):
    """every statement list in the module with its owner, as (owner_key, [stmt...])."""
    out = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody", "handlers"):
            body = getattr(node, field, None)
            if isinstance(body, list) and body and all(isinstance(x, ast.AST) for x in body):
                out.append((node, field, body))
    return out


def dump_stmt(s):
    return ast.dump(s, annotate_fields=True, include_attributes=False)


def _owners(tree):
    """owner key -> statement list, computed once: (owner type, owner name, field, ordinal among same-key owners)."""
    out = {}; seen = collections.Counter()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): continue
        body = node.body
        if isinstance(body, list) and body:
            k0 = (type(node).__name__, getattr(node, "name", None))
            k = k0 + (seen[k0],); seen[k0] += 1
            out[k] = body
    return out


def stmt_diff(before_src, after_src):
    """the smallest statement-span edit: (removed stmts, added stmts, owner type) over owners present in both
    versions whose bodies differ; None when the files do not parse or nothing differs at statement level.
    Linear in the number of owners (the first version compared every owner with every owner and re-dumped whole
    class bodies each time -- it never finished on sympy's large modules)."""
    try:
        tb, ta = ast.parse(before_src), ast.parse(after_src)
    except SyntaxError:
        return None
    ob, oa = _owners(tb), _owners(ta)
    best = None
    for k, bodyb in ob.items():
        bodya = oa.get(k)
        if bodya is None: continue
        if len(bodyb) == len(bodya) and all(dump_stmt(x) == dump_stmt(y) for x, y in zip(bodyb, bodya)): continue
        db, da = [dump_stmt(x) for x in bodyb], [dump_stmt(x) for x in bodya]
        i = 0
        while i < min(len(db), len(da)) and db[i] == da[i]: i += 1
        j = 0
        while j < min(len(db), len(da)) - i and db[-1 - j] == da[-1 - j]: j += 1
        rem = bodyb[i:len(bodyb) - j]; add = bodya[i:len(bodya) - j]
        size = sum(len(d) for d in db[i:len(db) - j]) + sum(len(d) for d in da[i:len(da) - j])
        if best is None or size < best[0]: best = (size, rem, add, k[0])
    if best is None: return None
    _, rem, add, owner = best
    return rem, add, owner


LEAF_FIELDS = {"id", "attr", "arg", "name", "value", "asname", "module"}


def skeleton(nodes, depth=None):
    """canonical skeleton of a list of statements: node types and structure, leaves (names, attributes, constants)
    replaced by holes numbered by first occurrence -- the anti-unification of every edit that shares the shape.
    `depth`: subtrees below this depth are replaced by their node TYPE alone (depth-2 measurement, post hoc and
    labelled as such: the pre-registered level is the full skeleton)."""
    holes = {}
    def h(v):
        k = repr(v)
        if k not in holes: holes[k] = f"_{len(holes)}"
        return holes[k]
    def walk(n, d=0):
        if isinstance(n, ast.AST):
            if depth is not None and d >= depth: return f"<{type(n).__name__}>"
            parts = []
            for f, v in ast.iter_fields(n):
                if f in ("ctx", "type_comment", "kind"): continue
                if f in LEAF_FIELDS and not isinstance(v, (ast.AST, list)):
                    parts.append(f"{f}={h(v)}"); continue
                parts.append(f"{f}={walk(v, d + 1)}")
            return f"{type(n).__name__}({','.join(parts)})"
        if isinstance(n, list): return "[" + ",".join(walk(x, d) for x in n) + "]"
        if n is None: return "None"
        return h(n)
    return walk(nodes)


def shape(nodes):
    return "[" + ",".join(type(n).__name__ for n in nodes) + "]"


def prim_edits(rem, add):
    """primitive AST edits (insert/delete/replace of a node) between two statement lists: the path length."""
    def nodes(ns):
        return sum(1 for n in ns for _ in ast.walk(n))
    return max(nodes(rem), nodes(add))


def apply_patch(before, patch, path):
    """apply the hunks of `patch` that touch `path` to `before` (single-file unified diff). -> text or None."""
    lines = before.splitlines(keepends=True)
    m = re.search(r"^--- a/" + re.escape(path) + r"\n\+\+\+ b/" + re.escape(path) + r"\n(.*?)(?=^--- a/|\Z)", patch, re.M | re.S)
    if not m: return None
    out, pos = [], 0
    for h in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n((?:[ +\-\\].*\n?)*)", m.group(1), re.M):
        start = int(h.group(1)) - 1
        if start < pos: return None
        out += lines[pos:start]; pos = start
        for l in h.group(5).splitlines(keepends=True):
            if l.startswith("-"):
                if pos >= len(lines) or lines[pos].rstrip("\n") != l[1:].rstrip("\n"): return None
                pos += 1
            elif l.startswith("+"): out.append(l[1:] if l.endswith("\n") else l[1:] + "\n")
            elif l.startswith(" "):
                if pos >= len(lines): return None
                out.append(lines[pos]); pos += 1
    out += lines[pos:]
    return "".join(out)


# ---------------------------------------------------------------- mining
def mine(repo, max_commits=None, rebuild=False, verbose=True):
    if os.path.exists(CACHE) and not rebuild:
        return json.load(open(CACHE, encoding="utf-8"))
    t0 = time.time()
    cs = commits(repo, max_commits); cand = candidates(cs)
    if verbose: print(f"  {len(cs)} commits, {len(cand)} candidates (>=1 test file + exactly one source .py)", flush=True)
    edits = []
    for n, (sha, ts, path) in enumerate(cand):
        after = file_at(repo, sha, path); before = file_at(repo, sha + "^", path)
        if not before or not after: continue
        bl, al = before.splitlines(), after.splitlines()
        if abs(len(al) - len(bl)) > 80: continue
        import difflib
        addl = [l[1:] for l in difflib.unified_diff(bl, al, n=0, lineterm="") if l.startswith("+") and not l.startswith("+++")]
        reml = [l[1:] for l in difflib.unified_diff(bl, al, n=0, lineterm="") if l.startswith("-") and not l.startswith("---")]
        if len(addl) + len(reml) > 80 or not (addl or reml): continue
        fam = family(addl, reml)
        d = stmt_diff(before, after)
        if d is None: continue
        rem, add, owner = d
        if len(rem) + len(add) == 0 or len(rem) + len(add) > 12: continue
        sb, sa = skeleton(rem), skeleton(add)
        if sb == sa: fam = "relabel (skeleton unchanged)"          # a docstring or constant change dressed as a rewrite
        edits.append(dict(sha=sha, ts=ts, path=path, family=fam, owner=owner,
                          skel=sb + " -> " + sa, shape=shape(rem) + " -> " + shape(add),
                          d1=skeleton(rem, 1) + " -> " + skeleton(add, 1), d2=skeleton(rem, 2) + " -> " + skeleton(add, 2),
                          d3=skeleton(rem, 3) + " -> " + skeleton(add, 3),
                          dump_rem=[dump_stmt(x) for x in rem], dump_add=[dump_stmt(x) for x in add],
                          path_len=prim_edits(rem, add), n_rem=len(rem), n_add=len(add)))
        if verbose and n % 500 == 0: print(f"  ... {n}/{len(cand)} candidates, {len(edits)} statement-level edits, {time.time()-t0:.0f}s", flush=True)
    json.dump(edits, open(CACHE, "w", encoding="utf-8"))
    if verbose: print(f"  mined {len(edits)} edits in {time.time()-t0:.0f}s -> {os.path.basename(CACHE)}", flush=True)
    return edits


def coverage_curve(train, held, key="skel", kmax=200, degenerate_frac=0.30):
    """operators = `key` values by frequency in train (degenerate ones excluded, K5); -> [(k, covered fraction)]."""
    freq = collections.Counter(e[key] for e in train)
    n_all = max(len(train), 1)
    degenerate = {op for op, c in freq.items() if c / n_all > degenerate_frac or (key == "skel" and op.count("_") <= 1)}
    ops = [op for op, _ in freq.most_common() if op not in degenerate][:kmax]
    curve = []
    covered_at = {}
    for k in (1, 2, 5, 10, 20, 50, 100, 200):
        top = set(ops[:k])
        cov = sum(1 for e in held if e[key] in top)
        curve.append((k, cov / max(len(held), 1)))
    return curve, ops, len(degenerate)


if __name__ == "__main__":
    from core.registry import selfcheck
    selfcheck(__file__)
    repo = sys.argv[sys.argv.index("--repo") + 1] if "--repo" in sys.argv else os.path.join(HERE, "_nldata", "repos", "sympy")
    maxc = int(sys.argv[sys.argv.index("--max-commits") + 1]) if "--max-commits" in sys.argv else None
    t0 = time.time()
    print("SWE-MINE -- structural repair operators from the repository's own history (swe_mine_prereg.md)\n", flush=True)
    edits = mine(repo, maxc, rebuild="--rebuild" in sys.argv)
    fams = collections.Counter(e["family"] for e in edits)
    print("\nstatement-level edits by census family:")
    for f, c in fams.most_common(): print(f"  {f:38s} {c:5d}  ({100*c/len(edits):4.1f}%)")
    struct = [e for e in edits if e["family"] in STRUCTURAL]
    print(f"\nSTRUCTURAL edits: {len(struct)} of {len(edits)}")
    head_ts = max(e["ts"] for e in edits)
    cutoff = head_ts - 365 * 86400
    train = [e for e in struct if e["ts"] < cutoff]; held = [e for e in struct if e["ts"] >= cutoff]
    print(f"train (before {datetime.datetime.utcfromtimestamp(cutoff).date()}): {len(train)}   held-out year: {len(held)}")
    for key in ("skel", "d3", "d2", "d1", "shape"):
        if key not in train[0]: continue
        curve, ops, ndeg = coverage_curve(train, held, key)
        rep = sum(1 for op, c in collections.Counter(e[key] for e in train).items() if c >= 2)
        print(f"\n{key.upper()}-level operators: {len(set(e[key] for e in train))} distinct in train ({rep} recurring), {ndeg} degenerate excluded"
              + ("   [post hoc abstraction level, not the pre-registered one]" if key in ("d1", "d2", "d3") else ""))
        print("  k -> held-out structural coverage: " + "  ".join(f"{k}:{c:.3f}" for k, c in curve))
        if key in ("d2", "d1"):
            freq = collections.Counter(e[key] for e in train)
            for op in ops[:5]:
                ex = next(e for e in train if e[key] == op)
                print(f"    x{freq[op]:<4d} {ex['family']:24s} {op[:130]}")
        if key == "skel":
            skel_cov200 = curve[-1][1]
            print("  top operators (frequency, path length, example family):")
            freq = collections.Counter(e["skel"] for e in train)
            for op in ops[:8]:
                ex = next(e for e in train if e["skel"] == op)
                print(f"    x{freq[op]:<4d} len {ex['path_len']:<3d} {ex['family']:24s} {ex['shape']}   {op[:90]}")
    plen = collections.Counter(min(e["path_len"], 30) for e in struct)
    print("\npath length (primitive AST edits) of structural edits: " + "  ".join(f"{k}:{plen[k]}" for k in sorted(plen)))
    # SWE-bench Lite sympy instances, time-respecting
    if os.path.exists(INSTANCES):
        inst = json.load(open(INSTANCES, encoding="utf-8"))
        print(f"\nSWE-bench Lite sympy instances: {len(inst)} (operators from commits BEFORE each base commit only)")
        cov = tot = 0
        for it in inst:
            base_ts = int(git(repo, "show", "-s", "--format=%ct", it["base_commit"]).strip() or 0)
            # gold patch: apply to the base file and diff at statement level
            m = re.search(r"^--- a/(\S+)", it["patch"], re.M)
            if not m or not m.group(1).endswith(".py"): continue
            path = m.group(1)
            before = file_at(repo, it["base_commit"], path)
            after = apply_patch(before, it["patch"], path) if before else None
            if after is None: print(f"  {it['instance_id']}: gold patch did not apply cleanly (skipped)"); continue
            d = stmt_diff(before, after)
            if d is None or family([l[1:] for l in it["patch"].splitlines() if l.startswith("+") and not l.startswith("+++")],
                                   [l[1:] for l in it["patch"].splitlines() if l.startswith("-") and not l.startswith("---")]) not in STRUCTURAL:
                continue
            tot += 1
            ops_before = {e["skel"] for e in struct if e["ts"] < base_ts}
            hit = skeleton(d[0]) + " -> " + skeleton(d[1]) in ops_before
            cov += hit
            print(f"  {it['instance_id']:22s} {shape(d[0])} -> {shape(d[1]):28s} path {prim_edits(d[0], d[1]):3d}  covered: {hit}")
        print(f"  structural sympy instances {tot}, covered by earlier-history operators: {cov}  ({100*cov/max(tot,1):.1f}%)")
    verdict = "PASS" if skel_cov200 >= 0.30 else "FAIL"
    print(f"\nSWE-MINE K1 (skeleton coverage of held-out structural fixes at k<=200 >= 0.30): {skel_cov200:.3f} -> {verdict}")
    print(f"({time.time()-t0:.0f}s)")
