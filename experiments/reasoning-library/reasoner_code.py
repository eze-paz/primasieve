"""Code domain for the generic reasoner — ZERO LLM. QuixBugs repair by exact reasoning:

  expectation = the program's JSON testcases
  simulate    = really execute (step-capped tracer; the machine 'subs in values' 1e6x faster)
  diff        = failing tests + spectrum localization (Ochiai belief over buggy lines)
  moves       = enumerated single-site AST mutations on suspicious lines, smallest-first
                (the 'smallest necessary change' prior, formalized: the valid move set at
                 ONE expression site is tiny and enumerable — no proposer needed)

Solved = all testcases pass. Compare against the LLM arms in quixbugs_bench.py.
Usage:  python reasoner_code.py            # all JSON-testcase programs
        BUGFIX_SLICE=gcd,bitcount python reasoner_code.py
"""
import os, sys, json, copy, ast, math, time, types, itertools
from reasoner_core import reason

QB=os.path.expanduser("~/quixbugs")
SLICE=os.environ.get("BUGFIX_SLICE")
BUDGET=int(os.environ.get("BUGFIX_BUDGET","6000"))   # mutants per program
STEP_CAP=int(os.environ.get("BUGFIX_STEPCAP","5000"))
TIME_CAP=float(os.environ.get("BUGFIX_TIMECAP","120"))  # wall seconds per program

def load_tests(name):
    T=[]
    for line in open(f"{QB}/json_testcases/{name}.json"):
        line=line.strip()
        if not line: continue
        o=json.loads(line); inp,exp=o[0],o[1]
        if not isinstance(inp,list): inp=[inp]
        T.append((inp,exp))
    return T

def _norm(x):
    if isinstance(x,(list,tuple)): return [_norm(y) for y in x]
    return x

class StepLimit(Exception): pass

def run_one(src_code, name, inp, exp, cap=STEP_CAP, want_cov=False):
    """Execute compiled module code, call fn(name)(*inp). Returns (ok, covered_lines)."""
    ns={}
    try: exec(src_code, ns)
    except Exception: return False,set()
    fn=ns.get(name)
    if not callable(fn): return False,set()
    steps=[0]; cov=set()
    def tr(frame,event,arg):
        if event=="line":
            steps[0]+=1
            if steps[0]>cap: raise StepLimit()
            if frame.f_code.co_filename=="<cand>": cov.add(frame.f_lineno)
            # value-size guard: line caps bound STEPS, not time/memory — a mutant like
            # `n *= n-1` squares digit-count per iteration and dies inside single ops.
            for v in frame.f_locals.values():
                if (type(v) is int and v.bit_length()>100_000) or \
                   (type(v) in (list,str,tuple,set,dict) and len(v)>1_000_000): raise StepLimit()
        return tr
    old=sys.gettrace()
    try:
        sys.settrace(tr)
        r=fn(*copy.deepcopy(inp))
        if isinstance(r,types.GeneratorType): r=list(r)
        ok = abs(r-exp)<1e-4 if name=="sqrt" else (_norm(r)==_norm(exp))
    except Exception:
        ok=False
    finally:
        sys.settrace(old)
    return bool(ok),cov

# ---------- single-site AST mutation enumeration ----------
# NOTE: Pow/LShift are never mutation TARGETS: `n **= n-1` blows up in ONE bytecode op,
# which the line-event step cap cannot interrupt (found the hard way: hung the search).
BIN_OPS=[ast.Add,ast.Sub,ast.Mult,ast.Div,ast.FloorDiv,ast.Mod,ast.RShift,ast.BitOr,ast.BitAnd,ast.BitXor]
CMP_OPS=[ast.Lt,ast.LtE,ast.Gt,ast.GtE,ast.Eq,ast.NotEq]

BUILTIN_SWAPS={"all","any","min","max","sum","len","abs","sorted","reversed"}
def scope_names(tree):
    names=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Name): names.add(n.id)
        elif isinstance(n,ast.arg): names.add(n.arg)
    return sorted(names|BUILTIN_SWAPS)

def enumerate_edits(tree):
    """Yield (lineno, desc, apply_fn) where apply_fn mutates the node IN a fresh tree copy.
    Nodes are addressed by walk-order index so the edit replays on any deepcopy."""
    idx=-1; edits=[]
    names=scope_names(tree)
    for node in ast.walk(tree):
        idx+=1
        ln=getattr(node,"lineno",None)
        if isinstance(node,(ast.BinOp,ast.AugAssign)):
            for op in BIN_OPS:
                if not isinstance(node.op,op):
                    edits.append((ln,f"L{ln}: {type(node.op).__name__}->{op.__name__}",idx,("binop",op)))
        elif isinstance(node,ast.Compare) and len(node.ops)==1:
            for op in CMP_OPS:
                if not isinstance(node.ops[0],op):
                    edits.append((ln,f"L{ln}: {type(node.ops[0]).__name__}->{op.__name__}",idx,("cmp",op)))
        elif isinstance(node,ast.BoolOp):
            op=ast.Or if isinstance(node.op,ast.And) else ast.And
            edits.append((ln,f"L{ln}: {type(node.op).__name__}->{op.__name__}",idx,("bool",op)))
        elif isinstance(node,ast.Constant) and isinstance(node.value,int) and not isinstance(node.value,bool):
            for d in (1,-1):
                edits.append((ln,f"L{ln}: const {node.value}->{node.value+d}",idx,("const",node.value+d)))
        elif isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load):
            for nm in names:
                if nm!=node.id:
                    edits.append((ln,f"L{ln}: name {node.id}->{nm}",idx,("name",nm)))
            for d in (1,-1):   # off-by-one on a VARIABLE: mid -> mid+1
                edits.append((ln,f"L{ln}: {node.id}->{node.id}{'+' if d>0 else '-'}1",idx,("nameinc",d)))
            for nm in names:   # depth-2 synthesis: k -> k - num_lessoreq  (SyGuS-lite)
                if nm!=node.id and nm not in BUILTIN_SWAPS:
                    for op,sym in ((ast.Sub,"-"),(ast.Add,"+")):
                        edits.append((ln,f"L{ln}: {node.id}->{node.id}{sym}{nm}",idx,("namebin",(op,nm))))
        elif isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.Not):
            edits.append((ln,f"L{ln}: drop 'not'",idx,("dropnot",None)))
        elif isinstance(node,ast.Call) and len(node.args)>=2:
            edits.append((ln,f"L{ln}: swap args",idx,("swapargs",None)))
        elif isinstance(node,ast.Call) and len(node.args)==1 and isinstance(node.func,ast.Name):
            edits.append((ln,f"L{ln}: unwrap {node.func.id}(x)->x",idx,("unwrap",None)))
        if isinstance(node,ast.BinOp):
            edits.append((ln,f"L{ln}: swap operands",idx,("swapops",None)))
    return edits

def apply_edit(tree, idx, kind_arg):
    t=copy.deepcopy(tree); kind,arg=kind_arg
    for i,node in enumerate(ast.walk(t)):
        if i!=idx: continue
        if   kind=="binop": node.op=arg()
        elif kind=="cmp":   node.ops=[arg()]
        elif kind=="bool":  node.op=arg()
        elif kind=="const": node.value=arg
        elif kind=="name":  node.id=arg
        elif kind=="dropnot": return None if not hasattr(node,'operand') else _replace_node(t,node,node.operand)
        elif kind=="swapargs": node.args[0],node.args[1]=node.args[1],node.args[0]
        elif kind=="nameinc":
            rep=ast.BinOp(left=ast.Name(id=node.id,ctx=ast.Load()),
                          op=ast.Add() if arg>0 else ast.Sub(),right=ast.Constant(value=1))
            return _replace_node(t,node,ast.copy_location(rep,node))
        elif kind=="namebin":
            op,nm=arg
            rep=ast.BinOp(left=ast.Name(id=node.id,ctx=ast.Load()),op=op(),
                          right=ast.Name(id=nm,ctx=ast.Load()))
            return _replace_node(t,node,ast.copy_location(rep,node))
        elif kind=="unwrap": return _replace_node(t,node,node.args[0])
        elif kind=="swapops": node.left,node.right=node.right,node.left
        return t
    return None

def _replace_node(tree, old, new):
    class R(ast.NodeTransformer):
        def visit(self,n):
            if n is old: return new
            return self.generic_visit(n)
    return R().visit(tree)

# ---------- Domain ----------
class CodeDomain:
    def __init__(self,name,src,tests):
        self.name=name; self.tests=tests
        self.tree0=ast.parse(src)
        self.best=len(tests)+1        # early-abandon threshold (updated in diff)
        self.deadline=time.time()+TIME_CAP
    def initial(self): return self.tree0
    def _code(self,tree):
        try: return compile(ast.fix_missing_locations(tree),"<cand>","exec")
        except Exception: return None
    def simulate(self,tree):
        code=self._code(tree)
        if code is None: return None
        res=[]; covs=[]; fails=0
        for inp,exp in self.tests:
            ok,cov=run_one(code,self.name,inp,exp)
            res.append(ok); covs.append(cov)
            if not ok:
                fails+=1
                if fails>=self.best: return None   # cannot strictly improve: abandon
        return (res,covs)
    def diff(self,obs):
        if obs is None: return (len(self.tests)+1, None)   # doesn't compile: worst
        res,covs=obs
        nfail=sum(1 for x in res if not x)
        self.best=min(self.best,nfail)
        if nfail==0: return (0,None)
        # Ochiai belief over lines: covered-in-fail / sqrt(totfail * covered-anywhere)
        totfail=nfail; susp={}
        allln=set().union(*covs) if covs else set()
        for ln in allln:
            ef=sum(1 for ok,c in zip(res,covs) if not ok and ln in c)
            ep=sum(1 for ok,c in zip(res,covs) if ok and ln in c)
            susp[ln]= ef/math.sqrt(totfail*(ef+ep)) if ef else 0.0
        return (nfail,susp)
    def moves(self,tree,susp):
        edits=enumerate_edits(tree)
        # order: suspicious lines first (belief), then smallest edit kinds
        rank={"cmp":0,"bool":1,"binop":2,"swapops":3,"dropnot":4,"const":5,"swapargs":6,
              "name":7,"nameinc":8,"unwrap":9,"namebin":10}
        def key(e):
            ln,desc,idx,(kind,arg)=e
            s=susp.get(ln,0.0) if susp else 0.0
            return (-s, rank.get(kind,9), idx)
        for ln,desc,idx,ka in sorted(edits,key=key):
            if time.time()>self.deadline: return          # per-program wall-clock cap
            if susp and susp.get(ln,0.0)==0.0: continue   # prune: never-in-failing-run lines
            t2=apply_edit(tree,idx,ka)
            if t2 is None: continue
            yield desc,t2
    def acquire(self,state,div): return None   # code domain: no external experience (honest)

def repair(name):
    tests=load_tests(name)
    src=open(f"{QB}/python_programs/{name}.py").read()
    dom=CodeDomain(name,src,tests)
    state,score,meta=reason(dom,budget=BUDGET)
    return score==0,meta,state

if __name__=="__main__":
    names=sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))
    if SLICE: names=[n for n in names if n in SLICE.split(",")]
    t0=time.time(); solved=[]; failed=[]; skipped=[]
    for name in names:
        tests=load_tests(name)
        # fair-scoring guard: reference must pass our runner
        csrc=open(f"{QB}/correct_python_programs/{name}.py").read()
        try: ccode=compile(csrc,"<cand>","exec")
        except Exception: skipped.append(name); continue
        if not all(run_one(ccode,name,i,e)[0] for i,e in tests):
            skipped.append(name); continue
        ok,meta,state=repair(name)
        (solved if ok else failed).append(name)
        fix=next((d for d,a,b in meta["trace"] if b==0),"")
        print(f"{name:26s} {'SOLVED' if ok else 'no    '} mutants={meta['tried']:5d} {meta['secs']:6.1f}s  {fix}",flush=True)
    S=len(solved)+len(failed)
    print(f"\n=== ZERO-LLM reasoner on QuixBugs: {len(solved)}/{S} solved ({len(skipped)} excluded) in {time.time()-t0:.0f}s ===")
    print(f"solved: {solved}")
    print(f"unsolved: {failed}")
