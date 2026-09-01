"""Measured zero-LLM score on the sympy reachable subset (4 instances). For each: build the
eval image (gold eval, also confirms gold resolves), stand up a container, run swe_run.py, and
OFFICIALLY verify any solve via run_evaluation. Prints a tally. Long-running (image builds)."""
import json, subprocess, os, re, time

BATCH = json.loads(subprocess.run(["wsl.exe","-e","bash","-lc","cat /tmp/sympy_batch.json"],
                                  capture_output=True, text=True).stdout)

def wsl(cmd, timeout=1800):
    return subprocess.run(["wsl.exe","-e","bash","-lc", cmd], capture_output=True, text=True, timeout=timeout)

def img_name(iid):  # swebench image naming: __ -> _1776_
    return "swebench/sweb.eval.x86_64." + iid.replace("__", "_1776_")

results = []
t0 = time.time()
for inst in BATCH:
    iid = inst["iid"]; src = inst["src"][0]; f2p = inst["f2p"][0]
    testfiles = " ".join(inst["testfile"])
    print(f"\n===== {iid} =====", flush=True)
    # 1) build image via gold eval (idempotent; cached if present)
    print("  building/eval gold ...", flush=True)
    wsl(f"source ~/swebench-env/bin/activate && cd ~ && python -m swebench.harness.run_evaluation "
        f"--dataset_name princeton-nlp/SWE-bench_Lite --predictions_path /tmp/{iid}.gold.jsonl "
        f"--instance_ids {iid} --run_id gold_{iid} --max_workers 1 --cache_level instance --clean False "
        f">/tmp/{iid}.goldlog 2>&1", timeout=3000)
    gold = wsl(f"cat ~/gold.gold_{iid}.json 2>/dev/null").stdout
    gold_ok = iid in gold
    print(f"  gold resolves: {gold_ok}", flush=True)
    # 2) container + test patch
    cont = "wk"
    wsl(f"docker rm -f {cont} >/dev/null 2>&1; docker run -d --name {cont} {img_name(iid)} tail -f /dev/null >/dev/null 2>&1")
    wsl(f"docker cp /tmp/{iid}.testpatch {cont}:/tmp/tp.patch && docker exec {cont} bash -lc 'cd /testbed && git apply /tmp/tp.patch'")
    # 3) run the search (MODE=sympy, bin/test over the instance's test files)
    env = dict(os.environ, SWE_CONT=cont, SWE_FILE=src, SWE_F2P=f2p, SWE_P2P="", SWE_MODE="sympy",
               SWE_TESTCMD=f"PYTHONWARNINGS=ignore::UserWarning bin/test -C {testfiles}",
               SWE_TIMECAP="360", SWE_STRATA="0")
    print("  searching ...", flush=True)
    r = subprocess.run(["python", "swe_run.py"], capture_output=True, text=True, env=env, timeout=1800)
    out = r.stdout
    solved_fast = "=== SOLVED" in out
    fix = re.search(r"SOLVED \[\d+\] (.+?)  \[", out)
    print(f"  fast-oracle: {'SOLVED '+fix.group(1) if solved_fast and fix else 'unsolved'}", flush=True)
    # 4) official verify if solved
    official = False
    if solved_fast:
        m = re.search(r"PATCH_START\n(.*?)PATCH_END", out, re.S)
        if m and m.group(1).strip():
            open(f"/tmp/{iid}.ours.patch", "w").write(m.group(1))
            wsl(f"docker cp /tmp/{iid}.ours.patch {cont}:/tmp/x 2>/dev/null; "
                f"python -c \"import json;p=open('/tmp/{iid}.ours.patch').read();"
                f"open('/tmp/{iid}.ourpred.jsonl','w').write(json.dumps({{'instance_id':'{iid}',"
                f"'model_name_or_path':'ours','model_patch':p}})+chr(10))\"")
            wsl(f"source ~/swebench-env/bin/activate && cd ~ && python -m swebench.harness.run_evaluation "
                f"--dataset_name princeton-nlp/SWE-bench_Lite --predictions_path /tmp/{iid}.ourpred.jsonl "
                f"--instance_ids {iid} --run_id chk_{iid} --max_workers 1 --cache_level instance --clean False "
                f">/tmp/{iid}.chklog 2>&1", timeout=900)
            official = iid in wsl(f"cat ~/ours.chk_{iid}.json 2>/dev/null").stdout
    print(f"  OFFICIAL resolved: {official}", flush=True)
    results.append({"iid": iid, "gold_ok": gold_ok, "fast": solved_fast, "official": official,
                    "fix": fix.group(1) if fix else None})
    wsl(f"docker rm -f {cont} >/dev/null 2>&1")

print("\n\n================ MEASURED ZERO-LLM SCORE (sympy reachable subset) ================")
solv = sum(1 for r in results if r["official"])
for r in results:
    print(f"  {r['iid']:26s} official={'YES' if r['official'] else 'no ':3s}  {r['fix'] or ''}")
print(f"\n  RESOLVED {solv}/{len(results)}  (zero LLM, official harness)  [{time.time()-t0:.0f}s total]")
json.dump(results, open("swe_sympy_results.json", "w"), indent=1)
