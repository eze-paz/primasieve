"""Code domain for the generic reasoner — ZERO LLM. QuixBugs repair by exact reasoning:

  expectation = the program's JSON testcases
  simulate    = really execute (step+value-size-capped tracer)
  diff        = failing tests + spectrum localization (Ochiai belief over buggy lines)
  moves       = STRATIFIED move grammar, iterative deepening over edit complexity:
      stratum 0: single-token edits (operator/comparison/const/name swaps, arg swaps, ...)
      stratum 1: depth-2 expression closure (expr -> expr OP operand for OP in {+,-,*,/,//,%},
                 slices expr[a:], bool-const -> predicate-over-scope)
      stratum 2: structural (wrap expr in an already-used call; insert/delete ONE statement
                 built only from the program's own methods/names — plastic-surgery rule)
    Escalation to a deeper stratum IS the epistemic move (acquire): search deeper only when
    the cheaper grammar is exhausted — 'smallest necessary change' formalized as strata.

  ANTI-CHEAT (principled, not benchmark-tuned):
    - builtins enter only as CONFUSION-PAIR swaps (all<->any, min<->max); never free injection
      (a free pool let mergesort 'solve' by swapping its recursive call to sorted()).
    - wrap/insert donors = functions/methods the program ALREADY calls (+ min/max), so a fix
      recombines the program's own material instead of importing an oracle.

Solved = all testcases pass. Compare against the LLM arms in quixbugs_bench.py.
Usage:  python reasoner_code.py            # all JSON-testcase programs
        BUGFIX_SLICE=gcd,bitcount python reasoner_code.py
"""
import os, sys, json, copy, ast, math, time, types
from reasoner_core import reason

QB=os.path.expanduser("~/quixbugs")
SLICE=os.environ.get("BUGFIX_SLICE")
BUDGET=int(os.environ.get("BUGFIX_BUDGET","40000"))  # mutants per program
STEP_CAP=int(os.environ.get("BUGFIX_STEPCAP","5000"))
TIME_CAP=float(os.environ.get("BUGFIX_TIMECAP","90"))  # wall seconds per program

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

def run_one(src_code, name, inp, exp, cap=STEP_CAP):
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

# ---------- stratified move grammar ----------
# NOTE: Pow/LShift are never mutation TARGETS: `n **= n-1` blows up in ONE bytecode op,
# which the line-event step cap cannot interrupt (found the hard way: hung the search).
BIN_OPS=[ast.Add,ast.Sub,ast.Mult,ast.Div,ast.FloorDiv,ast.Mod,ast.RShift,ast.BitOr,ast.BitAnd,ast.BitXor]
CMP_OPS=[ast.Lt,ast.LtE,ast.Gt,ast.GtE,ast.Eq,ast.NotEq]
EXPR_OPS=[(ast.Add,"+"),(ast.Sub,"-"),(ast.Mult,"*"),(ast.Div,"/"),(ast.FloorDiv,"//"),(ast.Mod,"%")]
CONFUSION_PAIRS={"all":"any","any":"all","min":"max","max":"min"}

def scope_names(tree):
    names=set()
    for n in ast.walk(tree):
        if isinstance(n,ast.Name): names.add(n.id)
        elif isinstance(n,ast.arg): names.add(n.arg)
    return sorted(names-set(CONFUSION_PAIRS))     # builtins never join the free swap pool

def called_funcs(tree):
    """Donor functions for wraps: what the program itself calls, plus min/max (lattice ops)."""
    fs={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    return sorted((fs|{"min","max"})-{"print"})

def called_methods(tree):
    ms={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    return sorted(ms)

def enumerate_edits(tree, stratum):
    """List of (stratum, lineno, desc, node_idx, (kind,arg)) up to the given stratum.
    Nodes addressed by walk-order index so an edit replays on any deepcopy."""
    idx=-1; edits=[]
    names=scope_names(tree); donors=called_funcs(tree)
    def add(s,ln,desc,i,ka):
        if s<=stratum: edits.append((s,ln,desc,i,ka))
    for node in ast.walk(tree):
        idx+=1
        ln=getattr(node,"lineno",None)
        # ---- stratum 0: single-token ----
        if isinstance(node,(ast.BinOp,ast.AugAssign)):
            for op in BIN_OPS:
                if not isinstance(node.op,op):
                    add(0,ln,f"L{ln}: {type(node.op).__name__}->{op.__name__}",idx,("binop",op))
        if isinstance(node,ast.Compare) and len(node.ops)==1:
            for op in CMP_OPS:
                if not isinstance(node.ops[0],op):
                    add(0,ln,f"L{ln}: {type(node.ops[0]).__name__}->{op.__name__}",idx,("cmp",op))
        if isinstance(node,ast.BoolOp):
            op=ast.Or if isinstance(node.op,ast.And) else ast.And
            add(0,ln,f"L{ln}: {type(node.op).__name__}->{op.__name__}",idx,("bool",op))
        if isinstance(node,ast.Constant) and isinstance(node.value,int) and not isinstance(node.value,bool):
            for d in (1,-1):
                add(0,ln,f"L{ln}: const {node.value}->{node.value+d}",idx,("const",node.value+d))
        if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load):
            if node.id in CONFUSION_PAIRS:
                add(0,ln,f"L{ln}: {node.id}->{CONFUSION_PAIRS[node.id]}",idx,("name",CONFUSION_PAIRS[node.id]))
            for nm in names:
                if nm!=node.id:
                    add(0,ln,f"L{ln}: name {node.id}->{nm}",idx,("name",nm))
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.Not):
            add(0,ln,f"L{ln}: drop 'not'",idx,("dropnot",None))
        if isinstance(node,ast.Call) and len(node.args)>=2:
            add(0,ln,f"L{ln}: swap args",idx,("swapargs",None))
        if isinstance(node,ast.Call) and len(node.args)==1 and isinstance(node.func,ast.Name):
            add(0,ln,f"L{ln}: unwrap {node.func.id}(x)->x",idx,("unwrap",None))
        if isinstance(node,ast.BinOp):
            add(0,ln,f"L{ln}: swap operands",idx,("swapops",None))
        # ---- stratum 1: depth-2 expression closure ----
        if isinstance(node,(ast.Name,ast.Call,ast.Subscript)) and \
           (not isinstance(node,ast.Name) or isinstance(node.ctx,ast.Load)):
            operands=[("name",nm) for nm in names]+[("const",1)]
            for op,sym in EXPR_OPS:
                for okind,ov in operands:
                    if isinstance(node,ast.Name) and okind=="name" and ov==node.id: continue
                    add(1,ln,f"L{ln}: .{sym}{ov}",idx,("exprbin",(op,okind,ov,False)))
                    if op in (ast.Sub,ast.Div):     # non-commutative: also operand OP expr
                        add(1,ln,f"L{ln}: {ov}{sym}.",idx,("exprbin",(op,okind,ov,True)))
            for nm in names:
                add(1,ln,f"L{ln}: .[{nm}:]",idx,("slicefrom",nm))
                add(1,ln,f"L{ln}: .[:{nm}]",idx,("sliceto",nm))
        if isinstance(node,ast.Constant) and isinstance(node.value,bool):
            for nm in names:
                for cop,csym in ((ast.Eq,"=="),(ast.NotEq,"!="),(ast.Gt,">"),(ast.Lt,"<")):
                    add(1,ln,f"L{ln}: {node.value}->{nm}{csym}0",idx,("booltopred",(nm,cop)))
        # ---- stratum 2: structural wraps ----
        if isinstance(node,(ast.BinOp,ast.Call)):
            for f in donors:
                add(2,ln,f"L{ln}: wrap {f}(.)",idx,("wrap1",f))
                for okind,ov in [("const",0)]+[("name",nm) for nm in names]:
                    add(2,ln,f"L{ln}: wrap {f}({ov},.)",idx,("wrap2",(f,okind,ov)))
    return edits

def enumerate_stmt_moves(tree, susp):
    """Stratum 2: insert X.m(Y) (methods/names from the program only) or delete one statement,
    in blocks that lie on a failing path."""
    methods=called_methods(tree); names=scope_names(tree); out=[]; idx=-1
    for node in ast.walk(tree):
        idx+=1
        for field in ("body","orelse","finalbody"):
            body=getattr(node,field,None)
            if not isinstance(body,list) or not body or not all(isinstance(s,ast.stmt) for s in body): continue
            blines={getattr(s,"lineno",None) for s in body}
            if susp and not any(susp.get(l,0.0)>0 for l in blines): continue
            for i in range(len(body)+1):
                ln=body[min(i,len(body)-1)].lineno
                for m in methods:
                    for X in names:
                        for Y in names:
                            if Y!=X: out.append((2,ln,f"L{ln}: insert {X}.{m}({Y})",idx,("insert",(field,i,m,X,Y))))
            for i,s in enumerate(body):
                if len(body)>1:
                    out.append((2,getattr(s,"lineno",None),f"L{getattr(s,'lineno',None)}: delete stmt",idx,("delstmt",(field,i))))
    return out

def _replace_node(tree, old, new):
    class R(ast.NodeTransformer):
        def visit(self,n):
            if n is old: return new
            return self.generic_visit(n)
    return R().visit(tree)

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
        elif kind=="swapops": node.left,node.right=node.right,node.left
        elif kind=="unwrap": return _replace_node(t,node,node.args[0])
        elif kind=="exprbin":
            op,okind,ov,rev=arg
            operand=ast.Constant(value=ov) if okind=="const" else ast.Name(id=ov,ctx=ast.Load())
            l,r=(operand,copy.deepcopy(node)) if rev else (copy.deepcopy(node),operand)
            return _replace_node(t,node,ast.copy_location(ast.BinOp(left=l,op=op(),right=r),node))
        elif kind in ("slicefrom","sliceto"):
            lo=ast.Name(id=arg,ctx=ast.Load()) if kind=="slicefrom" else None
            hi=ast.Name(id=arg,ctx=ast.Load()) if kind=="sliceto" else None
            rep=ast.Subscript(value=copy.deepcopy(node),slice=ast.Slice(lower=lo,upper=hi,step=None),ctx=ast.Load())
            return _replace_node(t,node,ast.copy_location(rep,node))
        elif kind=="booltopred":
            nm,cop=arg
            rep=ast.Compare(left=ast.Name(id=nm,ctx=ast.Load()),ops=[cop()],comparators=[ast.Constant(value=0)])
            return _replace_node(t,node,ast.copy_location(rep,node))
        elif kind=="wrap1":
            rep=ast.Call(func=ast.Name(id=arg,ctx=ast.Load()),args=[copy.deepcopy(node)],keywords=[])
            return _replace_node(t,node,ast.copy_location(rep,node))
        elif kind=="wrap2":
            f,okind,ov=arg
            first=ast.Constant(value=ov) if okind=="const" else ast.Name(id=ov,ctx=ast.Load())
            rep=ast.Call(func=ast.Name(id=f,ctx=ast.Load()),args=[first,copy.deepcopy(node)],keywords=[])
            return _replace_node(t,node,ast.copy_location(rep,node))
        elif kind=="insert":
            field,pos,m,X,Y=arg
            stmt=ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id=X,ctx=ast.Load()),attr=m,ctx=ast.Load()),
                                         args=[ast.Name(id=Y,ctx=ast.Load())],keywords=[]))
            getattr(node,field).insert(pos, ast.fix_missing_locations(ast.copy_location(stmt,node)))
        elif kind=="delstmt":
            field,pos=arg
            del getattr(node,field)[pos]
        return t
    return None

# ---------- Domain ----------
class CodeDomain:
    def __init__(self,name,src,tests):
        self.name=name; self.tests=tests
        self.tree0=ast.parse(src)
        self.best=len(tests)+1        # early-abandon threshold (updated in diff)
        self.deadline=time.time()+TIME_CAP
        self.stratum=0                # iterative deepening over edit complexity
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
        if obs is None: return (len(self.tests)+1, None)   # doesn't compile / abandoned
        res,covs=obs
        nfail=sum(1 for x in res if not x)
        self.best=min(self.best,nfail)
        if nfail==0: return (0,None)
        totfail=nfail; susp={}
        allln=set().union(*covs) if covs else set()
        for ln in allln:
            ef=sum(1 for ok,c in zip(res,covs) if not ok and ln in c)
            ep=sum(1 for ok,c in zip(res,covs) if ok and ln in c)
            susp[ln]= ef/math.sqrt(totfail*(ef+ep)) if ef else 0.0
        return (nfail,susp)
    def moves(self,tree,susp):
        edits=enumerate_edits(tree,self.stratum)
        if self.stratum>=2: edits+=enumerate_stmt_moves(tree,susp)
        def key(e):
            s,ln,desc,idx,ka=e
            b=susp.get(ln,0.0) if susp else 0.0
            return (s,-b,idx)                 # cheapest stratum first, then belief
        for s,ln,desc,idx,ka in sorted(edits,key=key):
            if time.time()>self.deadline: return
            if susp and susp.get(ln,0.0)==0.0: continue
            t2=apply_edit(tree,idx,ka)
            if t2 is None: continue
            yield desc,t2
    def acquire(self,state,div):
        # epistemic move = deepen the grammar, only when the cheaper stratum is exhausted.
        # Also RESET to the pristine program: a partial improvement accepted at a cheap
        # stratum strands the true deeper single-edit fix (cross-stratum stranding).
        if self.stratum<2 and time.time()<self.deadline:
            self.stratum+=1
            self.best=len(self.tests)+1        # reset abandon threshold with the state
            return (f"deepen grammar -> stratum {self.stratum} + reset to pristine", self.tree0)
        return None

def repair(name):
    tests=load_tests(name)
    src=open(f"{QB}/python_programs/{name}.py").read()
    dom=CodeDomain(name,src,tests)
    state,score,meta=reason(dom,budget=BUDGET)
    return score==0,meta,state,dom

if __name__=="__main__":
    names=sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))
    if SLICE: names=[n for n in names if n in SLICE.split(",")]
    t0=time.time(); solved=[]; failed=[]; skipped=[]
    for name in names:
        tests=load_tests(name)
        csrc=open(f"{QB}/correct_python_programs/{name}.py").read()
        try: ccode=compile(csrc,"<cand>","exec")
        except Exception: skipped.append(name); continue
        if not all(run_one(ccode,name,i,e)[0] for i,e in tests):
            skipped.append(name); continue
        ok,meta,state,dom=repair(name)
        (solved if ok else failed).append(name)
        fix=next((d for d,a,b in meta["trace"] if b==0),"")
        print(f"{name:26s} {'SOLVED' if ok else 'no    '} stratum={dom.stratum} mutants={meta['tried']:6d} {meta['secs']:6.1f}s  {fix}",flush=True)
    S=len(solved)+len(failed)
    print(f"\n=== ZERO-LLM stratified reasoner on QuixBugs: {len(solved)}/{S} solved ({len(skipped)} excluded) in {time.time()-t0:.0f}s ===")
    print(f"solved: {solved}")
    print(f"unsolved: {failed}")
