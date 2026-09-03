"""Did the projection engine improve SWE-bench? Static, no Docker. The projection frame family
is 'answer = existing_expr <binop> operand' (wrap/extend). Measure (a) how many gold fixes that
reaches (the new engine's ceiling contribution) and (b) break the rest into FIX-FAMILIES so we
know which frame family to build next and how much headroom each buys."""
import json, re, ast, collections
from swebench_census import parse_patch, is_test

def one_file(files):
    src = [f for f in files if f[0].endswith(".py") and not is_test(f[0])]
    return src[0] if len(src) == 1 else None

def added_removed(files):
    f = one_file(files)
    if not f: return None
    add = [l for h in f[1] for l in h[0] if l.strip()]
    rem = [l for h in f[1] for l in h[1] if l.strip()]
    return add, rem

NEWDEF = re.compile(r"^\s*(def |class |async def |@)")
IMPORT = re.compile(r"^\s*(import |from .+ import)")
GUARD  = re.compile(r"^\s*if .+:\s*(return|continue|break|raise|pass)?\s*$")
GUARD2 = re.compile(r"^\s*(return|continue|break|raise)\b")
ASSIGN = re.compile(r"^\s*[\w\.\[\]]+\s*(=|\+=|-=|\*=|\|=|&=)\s*.+")
ELSEEL = re.compile(r"^\s*(else|elif .+):\s*$")

def family(files):
    ar = added_removed(files)
    if ar is None:
        f2 = [x for x in files if x[0].endswith('.py') and not is_test(x[0])]
        return "multifile" if len(f2) > 1 else "nonpy-or-testonly"
    add, rem = ar
    # projection frame: one line replaced, new line = old line combined via a binary op
    if len(add) == 1 and len(rem) == 1:
        a, r = add[0].strip(), rem[0].strip()
        if r and r in a and a != r:
            mid = a.replace(r, "").strip()
            if re.fullmatch(r"[-+*/%|&^]|and|or|\+ .+|.+ \+|[-+*/%].*|.*[-+*/%]", mid) or mid.startswith(("+", "-", "*", "/", "|", "&", "and", "or")):
                return "PROJECTION-frame (wrap/extend)"
        return "token/expr-rewrite (1-for-1)"
    if len(rem) == 0:  # pure insertion
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

if __name__ == "__main__":
    import datasets
    d = datasets.load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    c = collections.Counter()
    for r in d: c[family(parse_patch(r["patch"]))] += 1
    n = len(d)
    order = ["PROJECTION-frame (wrap/extend)", "token/expr-rewrite (1-for-1)",
             "insert:guard (if/return/continue)", "insert:else/elif-branch", "insert:assignment",
             "insert:small-other", "insert:import", "insert:new-def/decorator", "delete-only",
             "small-mixed-rewrite", "add-def/class", "insert:large", "large-rewrite",
             "multifile", "nonpy-or-testonly"]
    print(f"=== SWE-bench Lite gold fixes by FIX-FAMILY (n={n}) ===\n")
    for k in order:
        if k in c: print(f"  {k:38s} {c[k]:4d}  ({100*c[k]/n:4.1f}%)")
    proj = c["PROJECTION-frame (wrap/extend)"]
    print(f"\nPROJECTION engine's frame family reaches: {proj}/{n} = {100*proj/n:.1f}% (the 'did we improve' number)")
    print("Biggest single-family headroom if we build that frame next:")
    for k in ["insert:guard (if/return/continue)", "insert:else/elif-branch", "insert:assignment"]:
        if k in c: print(f"    {k:38s} +{c[k]} ({100*c[k]/n:.1f}%)")
