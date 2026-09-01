"""Index the Python standard library as an analog corpus (readily accessible, high quality,
bounded ~167 modules). Extract every function definition + a structural signature, and rank
by similarity to a buggy function. No download, no LLM — the corpus is already on disk."""
import os, ast, sysconfig, math

def stdlib_dir(): return sysconfig.get_path("stdlib")

_INDEX = None
def _build_index(max_files=None):
    """Parse every stdlib module ONCE; slice function segments from a pre-split line list
    (avoids ast.get_source_segment's per-call re-split = quadratic on big modules)."""
    d = stdlib_dir(); out = []; n = 0
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".py") or fn.startswith("test"): continue
        try:
            src = open(os.path.join(d, fn), encoding="utf-8").read(); tree = ast.parse(src)
        except Exception: continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and getattr(node, "end_lineno", None):
                if node.end_lineno - node.lineno > 60: continue          # skip giant funcs
                seg = "\n".join(lines[node.lineno - 1:node.end_lineno])
                # dedent to column 0 so it parses standalone
                import textwrap; seg = textwrap.dedent(seg)
                if 0 < len(seg) < 4000: out.append((f"{fn}::{node.name}", seg))
        n += 1
        if max_files and n >= max_files: break
    return out

def iter_funcs(max_files=None):
    global _INDEX
    if _INDEX is None: _INDEX = _build_index(max_files=max_files)
    return iter(_INDEX)

import functools
@functools.lru_cache(maxsize=40000)
def struct_sig(src):
    """Structural signature: node-type bag + relational flags for retrieval."""
    try: t = ast.parse(src)
    except Exception: return None
    f = next((n for n in ast.walk(t) if isinstance(n, ast.FunctionDef)), None)
    if f is None: return None
    bag = {}
    for n in ast.walk(t): bag[type(n).__name__] = bag.get(type(n).__name__, 0) + 1
    fn = f.name
    recursive = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == fn
                    for n in ast.walk(t))
    ret_binop = any(isinstance(n, ast.Return) and isinstance(n.value, ast.BinOp) for n in ast.walk(t))
    has_comp = any(isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp)) for n in ast.walk(t))
    # union-comprehension relation: return BinOp with a comprehension on one side
    union_comp = any(isinstance(n, ast.Return) and isinstance(n.value, ast.BinOp)
                     and any(isinstance(s, (ast.ListComp,)) for s in (n.value.left, n.value.right))
                     for n in ast.walk(t))
    return {"bag": bag, "recursive": recursive, "ret_binop": ret_binop,
            "has_comp": has_comp, "union_comp": union_comp}

def _cos(a, b):
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values())); nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0

def similarity(bug_sig, cand_sig):
    if cand_sig is None: return 0.0
    s = _cos(bug_sig["bag"], cand_sig["bag"])                       # structural overlap
    for flag, w in (("recursive", 0.6), ("union_comp", 0.8), ("has_comp", 0.3), ("ret_binop", 0.2)):
        if bug_sig[flag] and cand_sig[flag]: s += w                 # shared relational structure
    return s

def retrieve(buggy_src, k=30, max_files=None):
    bsig = struct_sig(buggy_src); scored = []
    for name, src in iter_funcs(max_files=max_files):
        cs = struct_sig(src)
        scored.append((similarity(bsig, cs), name, src, cs))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]

if __name__ == "__main__":
    import os
    buggy = open(os.path.expanduser("~/quixbugs/python_programs/powerset.py")).read()
    top = retrieve(buggy, k=12)
    total = sum(1 for _ in iter_funcs())
    print(f"stdlib functions indexed: {total}")
    bsig = struct_sig(buggy)
    print(f"powerset (buggy) sig: recursive={bsig['recursive']} union_comp={bsig['union_comp']} has_comp={bsig['has_comp']}\n")
    print("top-12 stdlib analogs for powerset (by structural similarity):")
    for sc, name, src, cs in top:
        print(f"  {sc:5.2f}  {name:38s} rec={cs['recursive']} union_comp={cs['union_comp']} comp={cs['has_comp']}")
    # how many stdlib funcs carry the specific union-comprehension relation powerset needs?
    uc = sum(1 for _, src in iter_funcs() if (struct_sig(src) or {}).get("union_comp"))
    rec_uc = sum(1 for _, src in iter_funcs()
                 if (struct_sig(src) or {}).get("union_comp") and (struct_sig(src) or {}).get("recursive"))
    print(f"\nstdlib coverage of the needed pattern: union_comp={uc}, recursive+union_comp={rec_uc}")
