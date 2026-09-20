"""EMERGENCE via library-learning (wake/sleep), ZERO LLM, domain-agnostic terms.

The claim under test: can new CAPABILITY appear that was never programmed — so the system reaches
a problem it provably could not before — purely from compressing its OWN solutions into reusable
operators? That is the only known LLM-free route toward broad coverage: not a bigger hand-written
grammar, but a grammar that GROWS itself.

  wake:  solve easy tasks by composing primitive operators (bottom-up, obs-equivalence pruned)
  sleep: find the recurring solution-fragment across solutions, abstract it into a NEW operator
  wake:  a HARD task, intractable in primitives within budget, is now solvable because the new
         operator collapses its depth.

Emergence = the hard task becomes solvable ONLY after learning from the easy ones. Agnostic =
everything is generic expression terms; the same loop works for any domain with an oracle.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.registry import selfcheck

import ast, itertools, time, collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Shared with l0.py, which invented the same signature-dedupe independently: core.generate.SignatureBank.
# The size-indexed traversal stays here -- it is load-bearing for the published expression counts
# (819 easy / 7019 primitives-only on the hard task / 3008 with the learned operator).
from core.generate import SignatureBank, compress_recurring

BIN = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b}

def synth(examples, var_names, consts=(1, 2), unary=None, max_size=9, budget=300000):
    """Bottom-up enumeration with binary + learned UNARY ops; obs-equivalence pruning.
    Returns (repr, ast_node, stats) or (None, None, stats)."""
    unary = unary or {}
    t0 = time.time(); target = tuple(e for _, e in examples)
    def vec(fn):
        out = []
        for env, _ in examples:
            try:
                v = fn(env); out.append(v if isinstance(v, int) else None)
            except Exception: out.append(None)
        return tuple(out)
    bank = SignatureBank(budget=budget); seen = bank.seen; banks = bank.by_size; tried = [0]
    def add(size, rep, fn):
        v = vec(fn)
        if not bank.add(rep, v, size=size, payload=fn): return None
        return rep if v == target else None
    for nm in var_names:
        r = add(1, nm, lambda env, nm=nm: env[nm])
        if r: return r, ast.parse(r, mode="eval").body, _st(t0, seen)
    for c in consts:
        add(1, str(c), lambda env, c=c: c)
    for size in range(2, max_size + 1):
        # unary ops (size = 1 + child)
        for uname, ufn in unary.items():
            for crep, cfn, _ in list(banks[size - 1]):
                tried[0] += 1
                if tried[0] > budget: return None, None, _st(t0, seen)
                r = add(size, f"{uname}({crep})", lambda env, ufn=ufn, cfn=cfn: ufn(cfn(env)))
                if r: return r, ast.parse(r, mode="eval").body, _st(t0, seen)
        # binary ops
        for ls in range(1, size):
            rs = size - 1 - ls
            if rs < 1: continue
            for (lr, lf, _), (rr, rf, _) in itertools.product(banks[ls], banks[rs]):
                for sym, op in BIN.items():
                    tried[0] += 1
                    if tried[0] > budget: return None, None, _st(t0, seen)
                    r = add(size, f"({lr} {sym} {rr})", lambda env, op=op, lf=lf, rf=rf: op(lf(env), rf(env)))
                    if r: return r, ast.parse(r, mode="eval").body, _st(t0, seen)
    return None, None, _st(t0, seen)

def _st(t0, seen): return {"secs": round(time.time() - t0, 2), "exprs": len(seen)}

# ---------------- sleep: learn an abstraction from solutions ----------------
def learn_unary(solution_asts):
    """Find the most common binary-op subtree with two STRUCTURALLY-EQUAL operands (e.g. x*x),
    across solutions -> abstract into a unary operator op(x)=x<sym>x. Fully generic over sym."""
    counter = collections.Counter()
    for a in solution_asts:
        for n in ast.walk(a):
            if isinstance(n, ast.BinOp) and ast.dump(n.left) == ast.dump(n.right):
                sym = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}.get(type(n.op))
                if sym: counter[sym] += 1
    if not counter: return None
    sym, cnt = compress_recurring([None], lambda _: counter.elements())   # core.vote.plurality, shared
    op = BIN[sym]
    name = {"*": "sq", "+": "dbl", "-": "zero"}.get(sym, "op")
    return name, (lambda x: op(x, x)), sym, cnt

if __name__ == "__main__":
    selfcheck(__file__)   # verifies this file\'s PUBLISHED claims (core/registry.py) at exit
    print("=== EMERGENCE via library-learning (zero-LLM, agnostic terms) ===\n")
    def ex(f, argn, pts): return [({argn[i]: p[i] for i in range(len(argn))}, f(*p)) for p in pts]
    PTS2 = [(3, 1), (5, 2), (7, 4), (2, 2), (6, 3), (4, 1)]

    # WAKE 1: solve easy tasks with PRIMITIVES only; collect solutions
    print("WAKE 1 — solve easy tasks with primitives (+,-,*):")
    easy = {"a*a": lambda a, b: a*a, "b*b": lambda a, b: b*b,
            "a*a - b*b": lambda a, b: a*a - b*b, "a*a + b*b": lambda a, b: a*a + b*b}
    sols = []
    for nm, f in easy.items():
        r, node, st = synth(ex(f, ["a", "b"], PTS2), ["a", "b"], max_size=7)
        print(f"   {nm:12s} -> {r}   [{st['exprs']} exprs, {st['secs']}s]")
        if node: sols.append(node)

    # SLEEP: compress recurring fragment into a NEW operator
    learned = learn_unary(sols)
    name, ufn, sym, cnt = learned
    print(f"\nSLEEP — recurring fragment across solutions: `x {sym} x` (seen {cnt}x) -> new operator '{name}(x) = x{sym}x'")

    # WAKE 2: a HARD task — a^4 - b^4 — before vs after learning
    hard = lambda a, b: a**4 - b**4
    HP = ex(hard, ["a", "b"], PTS2)
    print("\nWAKE 2 — HARD task a^4 - b^4:")
    r0, n0, s0 = synth(HP, ["a", "b"], max_size=9, budget=300000)
    print(f"   primitives only : {r0 or 'NOT FOUND (budget/size exceeded)'}   [{s0['exprs']} exprs, {s0['secs']}s]")
    r1, n1, s1 = synth(HP, ["a", "b"], unary={name: ufn}, max_size=9, budget=300000)
    print(f"   WITH learned '{name}': {r1}   [{s1['exprs']} exprs, {s1['secs']}s]")

    print(f"\n=== EMERGENCE: a^4-b^4 was {'UNREACHABLE' if not r0 else 'reachable'} with primitives, "
          f"{'REACHABLE' if r1 else 'still unreachable'} after the system learned '{name}' from its OWN solutions.")
    print("    Nothing about a^4-b^4 was programmed; the capability emerged from compression. Agnostic:")
    print("    the loop only touches generic terms + an oracle — swap the adapter, same emergence. ===")
