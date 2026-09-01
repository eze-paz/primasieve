"""Pin the real ceiling in the 3.3%..14.7% band by STATIC grammar-expressibility — for each
`near:1line` gold fix (single line -> single line), ask: does ANY single production of the
ACTUAL reasoner_code grammar, applied to the removed line, reproduce the added line exactly
(AST-equal)? This resolves all 34 maybes at once (no Docker); expressibility is the dominant
unknown. What it does NOT test: whether trace-localization lands on the site and whether the
search finds it under budget — that still needs execution, but only for the expressible ones.
"""
import json, ast
import reasoner_code as rc

def norm(tree):
    try: return ast.dump(ast.parse(tree.strip())) if isinstance(tree,str) else ast.dump(tree)
    except Exception: return None

def harvest_names(patch):
    ids=set()
    for l in patch.splitlines():
        if l[:1] in "+- " and not l.startswith(("+++","---")):
            try:
                for n in ast.walk(ast.parse(l[1:].strip())):
                    if isinstance(n,ast.Name): ids.add(n.id)
                    elif isinstance(n,ast.arg): ids.add(n.arg)
                    elif isinstance(n,ast.Attribute): ids.add(n.attr)
            except Exception: pass
    return sorted(ids)

def one_line_change(patch):
    """Return (removed, added) if the non-test hunk is exactly one line->one line, else None."""
    from swebench_census import parse_patch, is_test
    files=parse_patch(patch)
    src=[f for f in files if f[0].endswith(".py") and not is_test(f[0])]
    if len(src)!=1: return None
    add=[l for h in src[0][1] for l in h[0] if l.strip()]
    rem=[l for h in src[0][1] for l in h[1] if l.strip()]
    if len(add)==1 and len(rem)==1: return rem[0], add[0]
    return None

def expressible(removed, added, names):
    tgt=norm(added)
    if tgt is None: return False,"added-unparseable"
    try: tree=ast.parse(removed.strip())
    except Exception: return False,"removed-unparseable"
    # inject the hunk's identifiers into the grammar's scope so name/expr productions can reach
    rc.scope_names=lambda t, _n=names: sorted(set(_n)-set(rc.CONFUSION_PAIRS))
    for stratum in (0,1,2):
        for s,ln,desc,idx,ka in rc.enumerate_edits(tree,stratum):
            m=rc.apply_edit(tree,idx,ka)
            if m is None: continue
            if norm(m)==tgt: return True,desc
    return False,"not-in-grammar"

if __name__=="__main__":
    rows=json.load(open("swebench_reach.json"))
    near=[r for r in rows if r["reach"]=="~near:1line"]
    conf=[r for r in rows if r["reach"].startswith("reach")]
    yes=[]; no=[]; undec=[]
    for r in near:
        olc=one_line_change(r["patch"])
        if not olc: undec.append((r["iid"],"multi-hunk")); continue
        ok,why=expressible(olc[0],olc[1],harvest_names(r["patch"]))
        (yes if ok else (undec if "unparseable" in why else no)).append((r["iid"],why))
    total=len(rows)+ (300-len(rows))  # keep n=300 framing
    print(f"=== near:1line grammar-expressibility (of {len(near)} maybes) ===")
    print(f"  EXPRESSIBLE   : {len(yes):3d}   {[i for i,_ in yes][:6]}")
    print(f"  not-in-grammar: {len(no):3d}")
    print(f"  undecidable   : {len(undec):3d}  (fragments/multi-hunk)")
    for iid,why in yes: print(f"     + {iid}: {why}")
    confident=len(conf)                       # 10 from reach:token/expr/insertm
    lo=confident; hi=confident+len(yes)+len(undec)
    print(f"\nREFINED CEILING: confident {confident}/300 = {100*confident/300:.1f}%")
    print(f"  + expressible near-lines {len(yes)} -> {100*(confident+len(yes))/300:.1f}%")
    print(f"  + undecidable upper {len(undec)} -> {100*hi/300:.1f}% (was 14.7% loose)")
    json.dump([i for i,_ in yes], open("swebench_express_yes.json","w"))
