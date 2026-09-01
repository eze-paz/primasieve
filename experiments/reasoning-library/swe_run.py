"""Run our stratified engine against a REAL SWE-bench instance, verified by the REAL F2P test
inside a persistent container (fast oracle). Generic over instance via env vars."""
import os, sys, ast, time, subprocess, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import reasoner_code as rc

CONT = os.environ["SWE_CONT"]; FILEPATH = os.environ["SWE_FILE"]; F2P = os.environ["SWE_F2P"]
P2P = os.environ.get("SWE_P2P", "").split()      # previously-passing tests; a real fix keeps them GREEN
TIMECAP = float(os.environ.get("SWE_TIMECAP", "240")); STRATA = int(os.environ.get("SWE_STRATA", "1"))
ALLTESTS = " ".join([F2P] + P2P)                 # SWE-bench 'resolved' = F2P passes AND all P2P pass

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

def verify(src):
    put(src)
    # run F2P AND all P2P together; a real fix makes F2P pass WITHOUT breaking any P2P (anti-cheat)
    r = subprocess.run(["wsl.exe","-e","bash","-lc",
        f"docker exec {CONT} bash -lc 'cd /testbed && python -m pytest -q {ALLTESTS} >/dev/null 2>&1; echo $?'"],
        capture_output=True, text=True, timeout=180)
    return r.stdout.strip().endswith("0")

# sanity: gold-less baseline must FAIL, and capture the traceback for localization
put(orig)
base = subprocess.run(["wsl.exe","-e","bash","-lc",
    f"docker exec {CONT} bash -lc 'cd /testbed && python -m pytest -x {F2P} 2>&1'"],
    capture_output=True, text=True, timeout=180)
assert not verify(orig), "baseline unexpectedly passes"
print("baseline FAILS (as expected)", flush=True)

# ---- model-free localization: suspect lines named in the traceback for THIS file ----
import re
base_short = os.path.basename(FILEPATH)
suspects = set(int(m) for m in re.findall(rf"{re.escape(base_short)}:(\d+)", base.stdout)) \
         | set(int(m) for m in re.findall(rf'{re.escape(FILEPATH)}\D+?(\d+)', base.stdout))
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

t0 = time.time(); tried = 0; solved = None
edits = rc.enumerate_edits(tree, STRATA)
if allowed:
    edits = [e for e in edits if e[1] in allowed]
# order: cheapest stratum, name-swaps and simple edits first
edits.sort(key=lambda e: (e[0], {"cmp":0,"bool":1,"binop":2,"name":3}.get(e[4][0], 5)))
print(f"{len(edits)} candidate edits at strata<= {STRATA}", flush=True)
for s, ln, desc, idx, ka in edits:
    if time.time() - t0 > TIMECAP: print("TIME CAP", flush=True); break
    t2 = rc.apply_edit(tree, idx, ka)
    if t2 is None: continue
    try: src = ast.unparse(ast.fix_missing_locations(t2))
    except Exception: continue
    tried += 1
    if verify(src):
        solved = desc; print(f"  SOLVED [{tried}] {desc}  [{time.time()-t0:.0f}s]", flush=True); break
    if tried % 25 == 0: print(f"  ...{tried} tried, {time.time()-t0:.0f}s", flush=True)

put(orig)  # restore
print(f"\n=== {'SOLVED: '+solved if solved else 'UNSOLVED'} — {tried} candidates, {time.time()-t0:.0f}s ===")
