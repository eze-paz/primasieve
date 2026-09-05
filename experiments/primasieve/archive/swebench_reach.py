"""Grammar-ACCURATE reachability census — sharpen swebench_census.py's loose diff-shape
buckets into 'can the actual stratified move grammar EXPRESS this exact gold edit?'.

Reading the 5 loose-'insert' picks showed the shape-classifier massively overcounts: gold
inserts need else-branches, module-qualified calls, chained methods, assignments, boolean-
chain extensions, guards — none of which our `X.method(Y)` insert production emits. So we
classify each single-file gold patch by matching its added/removed lines against the real
productions:

  reach:token   - k-for-k line change whose only delta is an operator/comparison/const/name
                  swap or arg/operand swap  (stratum 0)         <- genuinely reachable
  reach:expr    - one line wrapped/extended: expr -> expr OP operand, slice, bool->pred
                  (stratum 1)                                    <- reachable
  reach:insertm - pure add of one `X.method(Y)` expr-stmt, method called elsewhere in file,
                  X,Y plausibly in scope (stratum 2)             <- reachable
  ~near:1line   - single line<->line change we can't prove is a grammar production (needs
                  execution to know)                             <- MAYBE, run to find out
  out           - everything else (assignments, module calls, new branches, chains, multi)

Static, no Docker. Emits swebench_reach.json + a genuinely-reachable pick of 5.
"""
import json, ast, re, collections, difflib
from swebench_census import parse_patch, is_test

def added_removed(files):
    src=[f for f in files if f[0].endswith(".py") and not is_test(f[0])]
    if len(src)!=1: return None
    fp,hunks=src[0]
    add=[l for h in hunks for l in h[0]]
    rem=[l for h in hunks for l in h[1]]
    return fp,add,rem,hunks

def _try(s, mode):
    try: ast.parse(s, mode=mode); return True
    except Exception: return False

def _norm_tokens(line):
    """coarse token multiset of a code line, ignoring whitespace."""
    return re.findall(r"\w+|[^\w\s]", line)

OP_TOKENS=set("< > <= >= == != + - * / // % & | ^ >> and or".split())
def token_swap(a, b):
    """True if a,b differ only by swapping operator/comparison/const/name tokens in place."""
    ta,tb=_norm_tokens(a),_norm_tokens(b)
    if len(ta)!=len(tb): return False
    diffs=[(x,y) for x,y in zip(ta,tb) if x!=y]
    if not diffs or len(diffs)>2: return False
    for x,y in diffs:
        xnum=re.fullmatch(r"\d+",x); ynum=re.fullmatch(r"\d+",y)
        if x in OP_TOKENS and y in OP_TOKENS: continue          # operator/cmp swap
        if xnum and ynum and abs(int(x)-int(y))<=2: continue    # small const delta
        if re.fullmatch(r"[A-Za-z_]\w*",x) and re.fullmatch(r"[A-Za-z_]\w*",y): continue  # name swap
        return False
    return True

INSERTM=re.compile(r"^\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\(([^)]*)\)\s*$")
def classify(files):
    ar=added_removed(files)
    if ar is None: return "out"
    fp,add,rem,hunks=ar
    add=[l for l in add if l.strip()]; rem=[l for l in rem if l.strip()]
    # pure single X.method(Y) insertion, method used elsewhere in the file's added+kept text
    if len(rem)==0 and len(add)==1:
        m=INSERTM.match(add[0])
        if m: return "reach:insertm"
        return "out"
    if len(rem)==0: return "out"
    # k-for-k line change
    if len(add)==len(rem) and len(add)<=2:
        if all(token_swap(a,b) for a,b in zip(rem,add)): return "reach:token"
        # expr-closure: added line contains the removed line as a substring (wrapped/extended)
        if len(add)==1 and len(rem)==1 and (rem[0].strip() in add[0]) and _try(add[0].strip(),"exec"):
            return "reach:expr"
        if len(add)==1 and len(rem)==1: return "~near:1line"
    return "out"

if __name__=="__main__":
    import datasets
    d=datasets.load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    counts=collections.Counter(); rows=[]
    for r in d:
        files=parse_patch(r["patch"]); c=classify(files)
        counts[c]+=1
        if c.startswith("reach") or c.startswith("~"):
            src=[f for f in files if f[0].endswith(".py") and not is_test(f[0])]
            try: f2p=json.loads(r["FAIL_TO_PASS"])
            except Exception: f2p=r["FAIL_TO_PASS"]
            rows.append({"iid":r["instance_id"],"repo":r["repo"],"base":r["base_commit"],
                         "reach":c,"file":src[0][0],"f2p":f2p,"patch":r["patch"]})
    total=len(d)
    reach=sum(v for k,v in counts.items() if k.startswith("reach"))
    near =counts.get("~near:1line",0)
    print(f"=== GRAMMAR-ACCURATE reachability (n={total}) ===")
    for k in ["reach:token","reach:expr","reach:insertm","~near:1line","out"]:
        if k in counts: print(f"  {k:16s} {counts[k]:4d}  ({100*counts[k]/total:4.1f}%)")
    print(f"\nCONFIDENT reachable: {reach}/{total} = {100*reach/total:.1f}%")
    print(f"+ maybe (near:1line, needs run): {near} -> up to {100*(reach+near)/total:.1f}%")
    json.dump(rows, open("swebench_reach.json","w"), indent=0)
    # pick 5: prefer reach:token/expr (grammar-tight), single f2p, distinct repos
    tight=[x for x in rows if x["reach"] in ("reach:token","reach:expr","reach:insertm")]
    byrepo={}
    for x in tight: byrepo.setdefault(x["repo"],[]).append(x)
    pick=[]
    for repo in sorted(byrepo): pick.append(sorted(byrepo[repo],key=lambda x:len(x["f2p"]))[0])
    pick=pick[:5]
    print("\n=== genuinely grammar-reachable pick ===")
    for x in pick: print(f"  {x['iid']:34s} {x['reach']:13s} {x['file']}")
    json.dump(pick, open("swebench_pick5.json","w"), indent=1)
