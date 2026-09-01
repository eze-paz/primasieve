"""Grammar-coverage census on SWE-bench Lite gold patches — NO Docker, NO model, static only.

Question: before spending compute, what FRACTION of the 300 real gold fixes even FIT the
zero-LLM stratified move grammar? This is an UPPER BOUND on the reasoner's possible score:
real coverage <= this, because we do NOT here verify (a) the edit site is localizable by our
trace/coverage method, nor (b) inserted material is actually in-scope. We only classify the
SHAPE of each gold diff against what the grammar can express.

Buckets (most-restrictive first; each patch counted once):
  out:multifile     - touches >1 non-test source file  (current pipeline = single-file)
  out:newdef        - adds a def/class/import           (beyond edit+insert grammar)
  s0/s1:line-mod    - one file, one hunk, k lines replaced by k lines, k<=2, all bodies
                      parse as expr/stmt edits          (single-token / depth-2 closure)
  s2:insert         - one file, pure addition of <=3 statements, no new def/class/import
  s2:delete         - one file, pure removal of <=3 statements
  s2:mixed-small    - one file, one hunk, added+removed <= 6, no new def/class/import
  out:large         - one file but bigger than the grammar can plausibly reach
Reads the dataset from the WSL swebench-env. Run: python swebench_census.py
"""
import re, ast, json, collections

def load():
    import datasets
    d=datasets.load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    return [(r["instance_id"], r["patch"]) for r in d]

HUNK=re.compile(r"^@@ .*@@")
def parse_patch(patch):
    """-> list of (filepath, [(added_lines, removed_lines)]) per hunk."""
    files=[]; cur=None; add=[]; rem=[]
    def flush_hunk():
        nonlocal add,rem
        if cur is not None and (add or rem): cur[1].append((add,rem))
        add=[]; rem=[]
    for line in patch.splitlines():
        if line.startswith("diff --git"):
            flush_hunk(); cur=None
        elif line.startswith("+++ b/"):
            flush_hunk(); cur=[line[6:],[]]; files.append(cur)
        elif line.startswith("--- ") or line.startswith("+++ "):
            continue
        elif HUNK.match(line):
            flush_hunk()
        elif cur is not None:
            if line.startswith("+"): add.append(line[1:])
            elif line.startswith("-"): rem.append(line[1:])
    flush_hunk()
    return files

def is_test(fp): return "/test" in fp or fp.startswith("test") or "tests/" in fp or fp.endswith("_test.py")
NEWDEF=re.compile(r"^\s*(def |class |import |from .+ import|@)")
def has_newdef(lines): return any(NEWDEF.match(l) for l in lines)

def parses_as_edit(added, removed):
    """Heuristic: a k-for-k line replacement whose lines each parse (as stmt) — proxy for
    the single-token / depth-2 expression grammar operating in place."""
    if len(added)!=len(removed) or len(added)>2: return False
    for l in added+removed:
        s=l.strip()
        if not s: return False
        try: ast.parse(s)
        except Exception:
            # allow expression fragments / clauses that aren't standalone statements
            try: ast.parse(s.rstrip(":")+": pass" if s.endswith(":") else s, mode="eval")
            except Exception: return False
    return True

def classify(files):
    src=[f for f in files if f[0].endswith(".py") and not is_test(f[0])]
    if len(src)==0: return "out:nonpy-or-testonly"
    if len(src)>1: return "out:multifile"
    fp,hunks=src[0]
    all_add=[l for h in hunks for l in h[0]]
    all_rem=[l for h in hunks for l in h[1]]
    if has_newdef(all_add): return "out:newdef"
    na,nr=len(all_add),len(all_rem)
    if len(hunks)==1:
        add,rem=hunks[0]
        if parses_as_edit(add,rem): return "s0/s1:line-mod"
    if nr==0 and 0<na<=3: return "s2:insert"
    if na==0 and 0<nr<=3: return "s2:delete"
    if len(hunks)==1 and (na+nr)<=6: return "s2:mixed-small"
    return "out:large"

if __name__=="__main__":
    data=load()
    counts=collections.Counter(); examples=collections.defaultdict(list)
    for iid,patch in data:
        b=classify(parse_patch(patch))
        counts[b]+=1
        if len(examples[b])<3: examples[b].append(iid)
    total=len(data)
    inscope=sum(v for k,v in counts.items() if not k.startswith("out"))
    print(f"=== SWE-bench Lite gold-patch grammar census (n={total}) ===\n")
    order=["s0/s1:line-mod","s2:insert","s2:delete","s2:mixed-small",
           "out:large","out:newdef","out:multifile","out:nonpy-or-testonly"]
    for k in order:
        if k in counts:
            print(f"{k:24s} {counts[k]:4d}  ({100*counts[k]/total:4.1f}%)   e.g. {', '.join(examples[k][:2])}")
    print(f"\nIN-GRAMMAR UPPER BOUND: {inscope}/{total} = {100*inscope/total:.1f}%")
    print("(upper bound: does NOT verify localizability or in-scope material)")
