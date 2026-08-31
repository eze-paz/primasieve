"""v4: needle-in-haystack bug in a LARGE codebase. The new hard part is LOCALIZATION:
you cannot propose a fix until you find WHERE the bug is, and the repo doesn't fit in an
LLM context. Localization is a search by TRACING execution/call-graph from the failing test
— mostly MODEL-FREE, which is why it scales.

Localization stack (strong -> weak):
  1. COVERAGE trace of failing test  -> collapses N functions to the execution PATH (needle inside)
  2. EXCEPTION traceback (crash bugs) -> innermost in-repo frame = culprit (rank 1)
  3. OCHIAI spectrum (silent bugs)    -> rank path funcs by executed-by-fail / also-by-pass
  4. LLM (only now)                   -> read top-k suspects + failing error, fix (v3 compose)
The LLM never sees the haystack; the trace hands it a ~3-function needle.

Repo = ~100 functions across labelled modules; ONE bug on a deep call chain
(process_order -> subtotal -> line_total -> to_cents[BUG]). Report haystack reduction,
rank of the true bug under each signal, then localize+fix with a LOCAL model.
"""
import sys, math, random, re, subprocess, tempfile, json, os, time, traceback as tbmod
random.seed(0)

# ---------------- build a large multi-"module" repo (dict name -> source) --------------------
REPO={}; MODULE_OF={}
# the real subsystem with a deep call chain; BUG lives in to_cents (comma not stripped)
REPO["to_cents"]      ="def to_cents(s):\n    return int(round(float(s[1:]) * 100))"          # BUG: no comma strip
REPO["line_total"]    ="def line_total(item):\n    return to_cents(item['price']) * item['qty']"
REPO["subtotal"]      ="def subtotal(items):\n    return sum(line_total(it) for it in items)"
REPO["apply_tax"]     ="def apply_tax(cents, rate):\n    return int(round(cents * (1 + rate)))"
REPO["normalize_cents"]="def normalize_cents(c):\n    return c if c > 0 else 0"
REPO["process_order"] =("def process_order(order):\n    st = subtotal(order['items'])\n"
                        "    taxed = apply_tax(st, order['tax'])\n    return normalize_cents(taxed)")
for n in REPO: MODULE_OF[n]="billing"
# ~100 filler functions across modules (the haystack) — pure, all correct
FILL=100
for i in range(FILL):
    m=f"util{i%8}"; name=f"{m}_h{i}"
    a,b,c=random.randint(2,9),random.randint(1,50),random.randint(51,97)
    REPO[name]=f"def {name}(x):\n    return (x*{a}+{b}) % {c}"
    MODULE_OF[name]=m
FUNCS=list(REPO)

# ---------------- test suite (assertions). Determine pass/fail by running on the repo ---------
TESTS=[
 "assert process_order({'items':[{'price':'$1,000.00','qty':1}],'tax':0.0})==100000",   # FAILS (comma bug)
 "assert process_order({'items':[{'price':'$5.00','qty':2}],'tax':0.1})==1100",          # pass: full chain, no comma
 "assert line_total({'price':'$3.00','qty':3})==900",                                    # pass: to_cents+line_total
 "assert apply_tax(1000,0.0)==1000",                                                     # pass: apply_tax only
 "assert normalize_cents(-5)==0",                                                        # pass: normalize only
 "assert normalize_cents(1000)==1000",                                                   # pass: normalize only
]
# add filler passing tests (compute expected from the correct filler impls)
_ns={}; exec("\n\n".join(REPO[n] for n in REPO), _ns)
for i in range(0,FILL,3):
    name=f"{ [k for k in FUNCS if k.endswith(f'_h{i}')][0] }"
    TESTS.append(f"assert {name}(7)=={_ns[name](7)}")

def build_ns(repo):
    ns={}; exec("\n\n".join(repo[n] for n in repo), ns); return ns

def run_one(assertion, ns):
    """run one assertion; return (passed, executed_funcs:set, crash_frames:list)."""
    executed=set()
    def tr(frame,event,arg):
        if event=='call':
            n=frame.f_code.co_name
            if n in repo_names: executed.add(n)
        return None
    repo_names=set(REPO)
    passed=True; crash=[]
    sys.settrace(tr)
    try:
        exec(assertion, ns)
    except Exception:
        passed=False
        for fr,_ in tbmod.walk_tb(sys.exc_info()[2]):
            n=fr.f_code.co_name
            if n in repo_names: crash.append(n)
    finally:
        sys.settrace(None)
    return passed, executed, crash

def localize(repo, tests):
    ns=build_ns(repo)
    results=[run_one(t, build_ns(repo)) for t in tests]     # fresh ns each (settrace + state safety)
    fails=[i for i,(p,_,_) in enumerate(results) if not p]
    passes=[i for i,(p,_,_) in enumerate(results) if p]
    # 1. coverage path of failing tests
    path=set()
    for i in fails: path|=results[i][1]
    # 2. crash traceback (deepest in-repo frame of first failing test)
    crash=results[fails[0]][2] if fails else []
    crash_site=crash[-1] if crash else None
    # 3. ochiai
    totalfail=len(fails)
    susp={}
    for f in repo:
        ef=sum(1 for i in fails if f in results[i][1])
        ep=sum(1 for i in passes if f in results[i][1])
        susp[f]= ef/math.sqrt(totalfail*(ef+ep)) if ef>0 and totalfail>0 else 0.0
    ranked=sorted(repo, key=lambda f:-susp[f])
    return dict(nfuncs=len(repo), nfail=len(fails), npass=len(passes),
               path=sorted(path), crash=crash, crash_site=crash_site, susp=susp, ranked=ranked)

# ---------------- verifier + local-model fix over the localized suspects ---------------------
PY=sys.executable
def run_suite(repo, tests, timeout=10):
    code="\n\n".join(repo[n] for n in repo)+"\nimport json\n_res=[]\n"
    for a in tests:
        code+=f"try:\n    {a}\n    _res.append(True)\nexcept Exception as _e:\n    _res.append(f'{{type(_e).__name__}}: {{_e}}')\n"
    code+="print('__R__'+json.dumps(_res))\n"
    with tempfile.NamedTemporaryFile('w',suffix='.py',delete=False,encoding='utf-8') as f:
        f.write(code); path=f.name
    try: p=subprocess.run([PY,path],capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired: os.unlink(path); return 0
    os.unlink(path)
    line=next((l for l in p.stdout.splitlines() if l.startswith('__R__')),None)
    return sum(1 for x in json.loads(line[5:]) if x is True) if line else 0

if __name__=="__main__":
    t0=time.time()
    L=localize(REPO, TESTS)
    N=L['nfuncs']
    print(f"REPO: {N} functions across modules; {L['nfail']} failing / {L['npass']} passing tests")
    print(f"1. COVERAGE  : failing test executes {len(L['path'])}/{N} funcs -> {100*(1-len(L['path'])/N):.0f}% of haystack pruned")
    print(f"   path = {L['path']}")
    print(f"2. TRACEBACK : crash frames {L['crash']}  -> culprit = {L['crash_site']} (rank 1 for crash bugs)")
    top=[(f, round(L['susp'][f],3)) for f in L['ranked'][:6]]
    print(f"3. OCHIAI    : top-6 by suspiciousness = {top}")
    bug_rank=L['ranked'].index('to_cents')+1
    print(f"   true bug 'to_cents' ochiai-rank = {bug_rank}/{N}")
    # combined suspects = union of crash_site + ochiai top-3, intersected with failing path
    suspects=[]
    for f in ([L['crash_site']] if L['crash_site'] else [])+L['ranked'][:3]:
        if f in L['path'] and f not in suspects: suspects.append(f)
    print(f"\nLOCALIZED SUSPECTS handed to LLM: {suspects}  (haystack {N} -> {len(suspects)})")
    print(f"localization time: {time.time()-t0:.1f}s (model-free)\n", flush=True)

    if os.environ.get("BUGFIX_FIX","1")=="1":
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        torch.set_num_threads(10)
        MODEL=os.environ.get("BUGFIX_MODEL","Qwen/Qwen2.5-1.5B-Instruct")
        print(f"loading {MODEL} for fix over {len(suspects)} suspects ...", flush=True)
        tok=AutoTokenizer.from_pretrained(MODEL)
        if tok.pad_token is None: tok.pad_token=tok.eos_token
        model=AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, low_cpu_mem_usage=True).eval()
        import torch as T
        @T.no_grad()
        def gen(msgs,n=200,temp=0.0):
            txt=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
            ids=tok(txt,return_tensors="pt")
            o=model.generate(**ids,max_new_tokens=n,do_sample=temp>0,temperature=max(temp,1e-5),pad_token_id=tok.eos_token_id)
            return tok.decode(o[0][ids.input_ids.shape[1]:],skip_special_tokens=True)
        def block(t):
            b=re.findall(r"```(?:python)?\s*(.*?)```",t,re.S); return (b[0] if b else t).strip()
        base=run_suite(REPO,TESTS); tot=len(TESTS); cur=dict(REPO)
        # failing error for context
        _,_,crash=run_one(TESTS[0], build_ns(REPO))
        errctx=next((f"in {c}" for c in reversed(crash)), "")
        print(f"start {base}/{tot}. fixing suspects (budget 1 call each)...", flush=True)
        for s in suspects:
            usr=(f"This function is the suspected bug (failing test crashes {errctx}):\n```python\n{cur[s]}\n```\n"
                 f"Failing assertion: {TESTS[0]}\nOutput only the corrected function.")
            cand=block(gen([{"role":"system","content":"You are a precise Python bug-fixer. Output only the corrected function in a ```python block."},
                            {"role":"user","content":usr}]))
            if re.search(rf"def\s+{s}\b",cand):
                trial=dict(cur); trial[s]=cand; np_=run_suite(trial,TESTS)
                ok = np_>run_suite(cur,TESTS)
                print(f"  edit {s}: {run_suite(cur,TESTS)}->{np_}/{tot} {'APPLY' if ok else 'reject'}", flush=True)
                if ok: cur=trial
                if run_suite(cur,TESTS)==tot: break
        print(f"\nFINAL: {run_suite(cur,TESTS)}/{tot}  ({'SOLVED' if run_suite(cur,TESTS)==tot else 'partial'})")
        if run_suite(cur,TESTS)==tot: print("fixed to_cents:\n"+cur['to_cents'])
