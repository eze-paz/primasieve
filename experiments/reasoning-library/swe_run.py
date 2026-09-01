"""Run our stratified engine against a REAL SWE-bench instance, verified by the REAL F2P test
inside a persistent container (fast oracle). Generic over instance via env vars."""
import os, sys, ast, time, subprocess, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import reasoner_code as rc

CONT = os.environ["SWE_CONT"]; FILEPATH = os.environ["SWE_FILE"]; F2P = os.environ["SWE_F2P"]
P2P = os.environ.get("SWE_P2P", "").split()      # previously-passing tests; a real fix keeps them GREEN
TIMECAP = float(os.environ.get("SWE_TIMECAP", "240")); STRATA = int(os.environ.get("SWE_STRATA", "2"))  # MAX stratum; search escalates 0->..->STRATA (P0.5)
MODE = os.environ.get("SWE_MODE", "pytest")      # 'pytest' | 'sympy' (bin/test, count-parsed)
ALLTESTS = " ".join([F2P] + P2P)
# full in-container test command (a real fix must pass F2P AND leave every co-located test green)
TESTCMD = os.environ.get("SWE_TESTCMD", f"python -m pytest -q {ALLTESTS}")

def dexec(cmd):
    return subprocess.run(["wsl.exe","-e","bash","-lc", f"docker exec {CONT} bash -lc {shq(cmd)}"],
                          capture_output=True, text=True, timeout=120)
def shq(s): return "'" + s.replace("'", "'\\''") + "'"

orig = dexec(f"cat /testbed/{FILEPATH}").stdout
print(f"file {FILEPATH}: {len(orig.splitlines())} lines", flush=True)

def put(src):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(src); tp = f.name
    wp = subprocess.run(["wslpath","-a",tp], capture_output=True, text=True).stdout.strip() if False else tp
    subprocess.run(["wsl.exe","-e","bash","-lc",
                    f"docker cp $(wslpath -a '{tp}') {CONT}:/testbed/{FILEPATH}"], capture_output=True, text=True)
    os.unlink(tp)

def runtests(src):
    put(src)
    r = subprocess.run(["wsl.exe","-e","bash","-lc",
        f"docker exec {CONT} bash -lc {shq('cd /testbed && ' + TESTCMD + ' 2>&1; echo EXIT=$?')}"],
        capture_output=True, text=True, timeout=int(os.environ.get("SWE_TESTTIMEOUT","900")))
    return r.stdout

def passed(out):
    # a real fix: F2P passes AND no co-located test regressed (anti-cheat)
    if MODE == "sympy":
        import re
        npass = sum(int(x) for x in re.findall(r"(\d+) passed", out))
        nbad = sum(int(x) for x in re.findall(r"(\d+) (?:exceptions|failed|fail)", out))
        return npass > 0 and nbad == 0
    return "EXIT=0" in out

FASTCMD = os.environ.get("SWE_FASTCMD")   # cheap F2P-only oracle for the search sweep

def runtests_fast(src):
    put(src)
    r = subprocess.run(["wsl.exe","-e","bash","-lc",
        f"docker exec {CONT} bash -lc {shq('cd /testbed && ' + FASTCMD + ' 2>&1; echo EXIT=0')}"],
        capture_output=True, text=True, timeout=int(os.environ.get("SWE_TESTTIMEOUT","900")))
    return r.stdout

def verify(src):
    if FASTCMD:
        if not passed(runtests_fast(src)): return False   # cheap reject
    return passed(runtests(src))                          # full-suite confirm

# sanity: gold-less baseline must FAIL, and capture the traceback for localization
base_out = runtests(orig)
assert not passed(base_out), "baseline unexpectedly passes"
print("baseline FAILS (as expected)", flush=True)

# ---- model-free localization: suspect lines named in the traceback for THIS file ----
import re
# match the FULL file path only (basename alone also matches e.g. test_<file> and mislocalizes)
suspects = set(int(m) for m in re.findall(rf'{re.escape(FILEPATH)}"?,?\s*line\s*(\d+)', base_out)) \
         | set(int(m) for m in re.findall(rf'{re.escape(FILEPATH)}:(\d+)', base_out))
culprit = None
mnc = re.search(r"NameError: name '(\w+)' is not defined", base_out)
if mnc: culprit = mnc.group(1); print(f"NameError culprit: '{culprit}'", flush=True)
tree = ast.parse(orig)
allowed = set()
if suspects:
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and getattr(n, "end_lineno", None):
            if any(n.lineno <= s <= n.end_lineno for s in suspects):
                allowed |= set(range(n.lineno, n.end_lineno + 1))
    print(f"traceback suspects {sorted(suspects)} -> localized to {len(allowed)} lines", flush=True)
else:
    print("no traceback localization (searching whole file)", flush=True)

def lev(a, b):
    if a == b: return 0
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j-1] + 1, prev + (ca != cb))
    return d[-1]
def cprior(e):
    if culprit and e[4][0] == "name" and f"name {culprit}->" in e[2]:
        return (0, lev(culprit, e[2].split("->")[-1].strip()))
    return (1, 0)
t0 = time.time(); tried = 0; solved = None
# pseudo-susp from traceback localization: gates stratum-2 insert/delete to suspect blocks
susp = {ln: 1.0 for ln in allowed} if allowed else {}
stratum = 0
while stratum <= STRATA and solved is None and time.time() - t0 <= TIMECAP:
    edits = rc.enumerate_edits(tree, stratum)
    if stratum >= 2:
        edits += rc.enumerate_stmt_moves(tree, susp)
    if allowed:
        edits = [e for e in edits if e[1] in allowed]
    edits.sort(key=lambda e: (cprior(e), e[0], {"cmp":0,"bool":1,"binop":2,"name":3}.get(e[4][0], 5)))
    if culprit and stratum == 0:
        print(f"prioritizing name-swaps of '{culprit}' by edit-distance ({sum(1 for e in edits if cprior(e)[0]==0)} candidates)", flush=True)
    print(f"{len(edits)} candidate edits at stratum {stratum}", flush=True)
    for s, ln, desc, idx, ka in edits:
        if time.time() - t0 > TIMECAP: print("TIME CAP", flush=True); break
        t2 = rc.apply_edit(tree, idx, ka)
        if t2 is None: continue
        try: cand_src = ast.unparse(ast.fix_missing_locations(t2))
        except Exception: continue
        tried += 1
        if verify(cand_src):
            solved = desc; solved_src = cand_src
            print(f"  SOLVED [{tried}] {desc}  [{time.time()-t0:.0f}s]", flush=True); break
        if tried % 25 == 0: print(f"  ...{tried} tried, {time.time()-t0:.0f}s", flush=True)
    if solved is None and stratum < STRATA:
        stratum += 1
        print(f"--- escalate -> stratum {stratum} (reset to pristine; tree never mutated)", flush=True)

if solved:
    put(solved_src)   # leave the fix in place and emit the patch for official verification
    diff = subprocess.run(["wsl.exe","-e","bash","-lc",
        f"docker exec {CONT} bash -lc 'cd /testbed && git diff'"], capture_output=True, text=True).stdout
    print("PATCH_START\n" + diff + "PATCH_END", flush=True)
else:
    put(orig)
print(f"\n=== {'SOLVED: '+solved if solved else 'UNSOLVED'} — {tried} candidates, {time.time()-t0:.0f}s ===")
