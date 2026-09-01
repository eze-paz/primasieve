"""How much of SWE-bench can SYNTHESIS even target? Static, no Docker. A fix is 'synthesis-shaped'
if it replaces/adds a pure EXPRESSION (a return/assignment RHS with no new control flow). Then
split by grammar need: numeric (current synth.py) vs needs list/str/call/attr/comprehension."""
import re, ast, collections
from swebench_census import parse_patch, is_test

def one_file(files):
    s = [f for f in files if f[0].endswith(".py") and not is_test(f[0])]
    return s[0] if len(s) == 1 else None

def added_removed(files):
    f = one_file(files)
    if not f: return None
    add = [l for h in f[1] for l in h[0] if l.strip()]
    rem = [l for h in f[1] for l in h[1] if l.strip()]
    return add, rem

def target_expr(add, rem):
    """Extract the expression the fix introduces, if the change is a single expression/RHS."""
    # 1-for-1 line change, or single assignment/return insertion
    lines = add if (len(rem) == 0 and len(add) == 1) else (add if len(add) == 1 and len(rem) == 1 else None)
    if not lines: return None
    s = lines[0].strip()
    for pat in (r"^return\s+(.+)$", r"^[\w\.\[\]]+\s*=\s*(.+)$", r"^[\w\.\[\]]+\s*[-+*/|&]=\s*(.+)$"):
        m = re.match(pat, s)
        if m: s = m.group(1); break
    else:
        # bare expression line (e.g. inside a call-arg / boolean chain) — accept if it parses as expr
        pass
    try:
        node = ast.parse(s, mode="eval").body
        return node
    except Exception:
        return None

NUM_OK = (ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.Name, ast.Constant,
          ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
          ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq, ast.And, ast.Or, ast.Not,
          ast.USub, ast.UAdd, ast.BitOr, ast.BitAnd, ast.BitXor, ast.Load, ast.IfExp)
def classify_expr(node):
    kinds = {type(n) for n in ast.walk(node)}
    if kinds <= set(NUM_OK): return "synth:numeric (current grammar)"
    # richer but still pure-expression synthesis territory
    rich = (ast.Call, ast.Attribute, ast.Subscript, ast.Slice, ast.List, ast.Tuple, ast.Dict,
            ast.Set, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Str, ast.JoinedStr)
    if any(k in rich or issubclass(k, rich) for k in kinds):
        return "synth:rich-grammar (list/str/call/comp)"
    return "synth:other-expr"

if __name__ == "__main__":
    import datasets
    d = datasets.load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    c = collections.Counter(); ex = collections.defaultdict(list)
    for r in d:
        files = parse_patch(r["patch"]); ar = added_removed(files)
        if ar is None: c["not-single-file-expr"] += 1; continue
        node = target_expr(*ar)
        if node is None: c["not-a-pure-expression fix"] += 1; continue
        k = classify_expr(node); c[k] += 1
        if len(ex[k]) < 3: ex[k].append(r["instance_id"])
    n = len(d)
    print(f"=== SWE-bench Lite: what SYNTHESIS can target (n={n}) ===\n")
    for k in ["synth:numeric (current grammar)", "synth:rich-grammar (list/str/call/comp)",
              "synth:other-expr", "not-a-pure-expression fix", "not-single-file-expr"]:
        if k in c: print(f"  {k:40s} {c[k]:4d}  ({100*c[k]/n:4.1f}%)   {ex[k][:2]}")
    num = c["synth:numeric (current grammar)"]; rich = c["synth:rich-grammar (list/str/call/comp)"]
    print(f"\nCURRENT numeric synth can target: {num}/{n} = {100*num/n:.1f}%")
    print(f"+ rich-grammar extension would target: {rich}/{n} = {100*rich/n:.1f}%  (total pure-expr {100*(num+rich)/n:.1f}%)")
    print("(target = synthesis could produce the RHS; still needs point-spec extraction on the real repo + verify)")
