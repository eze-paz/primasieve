"""SWE-REACH -- is a plausible PREMISE for a structural fix already in the same file? Static, no Docker, minutes.

Owner's escalation idea: instead of deeper token search, restart from a plausible premise (a fragment of the
surrounding code) and explore a few edits around it. That is only worth building if the gold fix usually sits a
few structural edits from SOME same-file fragment. Measured here on a sample of mined structural fixes:

  for each fix: the gold ADDED block; every statement block in the BEFORE file (function bodies, branches, loop
  bodies) as a candidate premise; distance = Levenshtein over the sequence of AST node-type tokens (structure
  only, leaves as their kind); report the closest premise's distance, and the distance from the REMOVED block
  (where a token-level search starts). "Within reach" = <= 5 structural edits.

    python swe_reach.py [--sample 400] [--seed 1]"""
import os, sys, ast, json, random, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import swe_mine as M

STRUCTURAL = M.STRUCTURAL


def tokens(nodes):
    out = []
    for n in nodes:
        for x in ast.walk(n):
            if isinstance(x, ast.AST):
                out.append(type(x).__name__)
    return out


def lev(a, b, cap=60):
    if abs(len(a) - len(b)) > cap: return cap
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
        if min(prev) > cap: return cap
    return min(prev[-1], cap)


def blocks(tree):
    """every statement block in the file, and every contiguous sub-run of 1..3 statements inside it (a premise may
    be a slice of a sibling body, not the whole body)."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            if isinstance(body, list) and body and all(isinstance(x, ast.stmt) for x in body):
                for L in range(1, min(3, len(body)) + 1):
                    for i in range(len(body) - L + 1):
                        yield body[i:i + L]


if __name__ == "__main__":
    n_sample = int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else 400
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 1
    repo = os.path.join(HERE, "_nldata", "repos", "sympy")
    E = json.load(open(M.CACHE, encoding="utf-8"))
    st = [e for e in E if e["family"] in STRUCTURAL]
    random.Random(seed).shuffle(st); st = st[:n_sample]
    print(f"SWE-REACH -- same-file premise distance for {len(st)} sampled structural fixes (of {sum(1 for e in E if e['family'] in STRUCTURAL)})\n", flush=True)
    t0 = time.time(); rows = []
    for k, e in enumerate(st):
        before = M.file_at(repo, e["sha"] + "^", e["path"]); after = M.file_at(repo, e["sha"], e["path"])
        d = M.stmt_diff(before, after) if before and after else None
        if d is None: continue
        rem, add, _ = d
        if not add: continue
        gold = tokens(add)
        try: tb = ast.parse(before)
        except SyntaxError: continue
        gold_dump = {M.dump_stmt(s) for s in add}
        best = 60
        for blk in blocks(tb):
            if all(M.dump_stmt(s) in gold_dump for s in blk) and len(blk) == len(add): continue   # the gold itself already present: not a premise
            dist = lev(gold, tokens(blk), cap=best)
            if dist < best: best = dist
            if best == 0: break
        from_orig = lev(gold, tokens(rem)) if rem else len(gold)
        rows.append(dict(sha=e["sha"][:8], family=e["family"], gold_len=len(gold), premise=best, orig=from_orig))
        if k % 50 == 0: print(f"  ... {k}/{len(st)}  {time.time()-t0:.0f}s", flush=True)
    n = len(rows)
    print(f"\nmeasured {n} fixes in {time.time()-t0:.0f}s")
    for thr in (0, 2, 5, 10):
        p = sum(1 for r in rows if r["premise"] <= thr); o = sum(1 for r in rows if r["orig"] <= thr)
        print(f"  within {thr:2d} structural edits:  closest same-file premise {p:4d} ({100*p/n:4.1f}%)   from the original code {o:4d} ({100*o/n:4.1f}%)")
    med = sorted(r["premise"] for r in rows)[n // 2]; medo = sorted(r["orig"] for r in rows)[n // 2]
    print(f"  median distance: premise {med}   original {medo}   (gold block median size {sorted(r['gold_len'] for r in rows)[n//2]} tokens)")
    by = collections.defaultdict(list)
    for r in rows: by[r["family"]].append(r["premise"] <= 5)
    print("  within 5, by family: " + "  ".join(f"{f} {sum(v)}/{len(v)}" for f, v in by.items()))
    reach5 = sum(1 for r in rows if r["premise"] <= 5) / n
    print(f"\nSWE-REACH: same-file premise within 5 structural edits for {100*reach5:.1f}% of structural fixes "
          f"(the token search's own start point: {100*sum(1 for r in rows if r['orig'] <= 5)/n:.1f}%)")
