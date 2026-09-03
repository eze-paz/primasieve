"""Angelic point-spec SYNTHESIS — construct a NOVEL expression to hit a target value, ZERO LLM.

Frames/edits can only reshape existing code; synthesis BUILDS new structure. The unlock is the
pinpoint spec: localize the wrong expression, read off the value it MUST produce per input
(angelic value), then bottom-up enumerate compositions of in-scope vars + operators until one
matches the spec on all inputs — with OBSERVATIONAL-EQUIVALENCE pruning (dedupe expressions by
their output vector) so the search stays tractable to depth. This is the FlashFill/SyGuS core.

Demonstrates: (1) synthesize multi-operator expressions from I/O that NO single frame reaches;
(2) repair a bug whose fix requires building such an expression.
"""
import ast, itertools, time

BIN = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
       "//": lambda a, b: a // b if b != 0 else _ERR, "%": lambda a, b: a % b if b != 0 else _ERR}
class _E:  # error sentinel (division by zero etc.) — makes the output vector distinct, never matches
    __slots__ = ()
_ERR = _E()

def synth(examples, var_names, consts=(0, 1, 2, -1), max_size=6, budget=400000, verbose=True):
    """examples: [(env_dict, expected_value)]. Returns (expr_str, stats) or (None, stats).
    Bottom-up enumeration by size; observational-equivalence dedup by output vector."""
    t0 = time.time()
    target = tuple(e for _, e in examples)
    def vec(fn):
        out = []
        for env, _ in examples:
            try:
                v = fn(env)
                out.append(v if isinstance(v, int) else _ERR)
            except Exception:
                out.append(_ERR)
        return tuple(out)
    seen = {}                          # output_vector -> expr_str (obs-equivalence)
    banks = {1: []}                    # size -> list of (expr_str, fn, vector)
    def add(size, rep, fn):
        v = vec(fn)
        if any(x is _ERR for x in v) and target not in ([v]): pass
        if v in seen: return False
        seen[v] = rep; banks.setdefault(size, []).append((rep, fn, v))
        return v == target
    # size 1: terminals
    for nm in var_names:
        if add(1, nm, lambda env, nm=nm: env[nm]): return nm, _stats(t0, seen)
    for c in consts:
        if add(1, str(c), lambda env, c=c: c): return str(c), _stats(t0, seen)
    tried = 0
    for size in range(2, max_size + 1):
        for ls in range(1, size):
            rs = size - 1 - ls
            if rs < 1 or rs not in banks or ls not in banks: continue
            for (lrep, lfn, _), (rrep, rfn, _) in itertools.product(banks[ls], banks[rs]):
                for sym, op in BIN.items():
                    tried += 1
                    if tried > budget:
                        if verbose: print(f"  budget hit ({budget})");
                        return None, _stats(t0, seen)
                    rep = f"({lrep} {sym} {rrep})"
                    fn = (lambda env, op=op, lfn=lfn, rfn=rfn: op(lfn(env), rfn(env)))
                    if add(size, rep, fn):
                        return rep, _stats(t0, seen)
    return None, _stats(t0, seen)

def _stats(t0, seen):
    return {"secs": round(time.time() - t0, 2), "distinct_exprs": len(seen)}

# ---------------- point-spec repair: fix a bug by synthesizing its return expression ----------------
def repair_return(buggy_src, fname, io_examples, arg_names, max_size=6):
    """io_examples: [(args_tuple, expected_output)]. Localize the return expr as wrong; its angelic
    value per input IS the expected output; synthesize a replacement; splice; return fixed src."""
    envs = [({arg_names[i]: args[i] for i in range(len(arg_names))}, exp) for args, exp in io_examples]
    expr, stats = synth(envs, arg_names, max_size=max_size)
    if expr is None: return None, stats
    tree = ast.parse(buggy_src)
    ret = next(n for n in ast.walk(tree) if isinstance(n, ast.Return))
    ret.value = ast.parse(expr, mode="eval").body
    return ast.unparse(ast.fix_missing_locations(tree)), (expr, stats)

def run_fn(src, fname, args):
    ns = {}; exec(src, ns); return ns[fname](*args)

if __name__ == "__main__":
    print("=== ANGELIC POINT-SPEC SYNTHESIS (zero-LLM): build NOVEL expressions from a value-spec ===\n")

    # (1) pure synthesis: targets that need multi-level composition (NO single frame reaches these)
    def demo(name, f, argn, pts):
        ex = [({argn[i]: p[i] for i in range(len(argn))}, f(*p)) for p in pts]
        expr, st = synth(ex, argn, max_size=7)
        print(f"  {name:22s} -> {expr}   [{st['distinct_exprs']} distinct exprs, {st['secs']}s]")
    demo("a*a - b*b", lambda a, b: a*a - b*b, ["a", "b"], [(3, 1), (5, 2), (7, 4), (2, 2), (9, 3)])
    demo("(a+b) * (a-b)", lambda a, b: (a+b)*(a-b), ["a", "b"], [(4, 1), (6, 2), (8, 3), (3, 1), (10, 5)])
    demo("a*b + c*d", lambda a, b, c, d: a*b + c*d, ["a", "b", "c", "d"],
         [(1, 2, 3, 4), (2, 2, 1, 1), (3, 1, 2, 2), (0, 5, 4, 1), (2, 3, 3, 2)])
    demo("a*b - a - b + 1", lambda a, b: a*b - a - b + 1, ["a", "b"], [(2, 3), (4, 5), (3, 3), (6, 2), (5, 4)])

    # (2) repair: a bug whose fix REQUIRES a synthesized multi-op expression (beyond any frame)
    print("\n  repair demo: buggy returns a*a (wrong); true = a*a - b*b. Localize+point-spec+synthesize:")
    buggy = "def sqdiff(a, b):\n    return a * a\n"
    io = [((3, 1), 8), ((5, 2), 21), ((7, 4), 33), ((2, 2), 0), ((6, 3), 27)]  # a*a - b*b
    fixed, meta = repair_return(buggy, "sqdiff", io, ["a", "b"], max_size=7)
    if fixed:
        ok = all(run_fn(fixed, "sqdiff", args) == exp for args, exp in io)
        print(f"    synthesized: {meta[0]}   verified={ok}")
        print("    fixed:", fixed.replace("\n", "  "))
    else:
        print("    no expression found in budget")
    print("\n=== synthesis BUILDS structure edits/frames cannot; pruned by observational equivalence ===")
