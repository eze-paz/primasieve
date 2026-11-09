"""Local bench launcher: runs each arm of a generation round as its own process (in parallel), sharing the disk caches
(Brown classes, fitted harmonic phases), then merges the arms into one generation file (same format as
g1b_jx_gen.json, so sieve_armjudge.py works unchanged).
Usage: py -3.12 sieve_bench.py OUT_DIR POFF NG 'ARMS_JSON' [PARALLEL] [TRACE]
Example: py -3.12 sieve_bench.py mtest/bench/x 197 20 '{"A": {...}, "B": {...}}' 3"""
import os, sys, json, time, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); M = os.path.join(HERE, "mtest")
out, poff, ng, arms = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4]); par = int(sys.argv[5]) if len(sys.argv) > 5 else 3; trace = sys.argv[6] if len(sys.argv) > 6 else "0"
out = os.path.abspath(out); os.makedirs(out, exist_ok=True); T0 = time.time()
src = open(os.path.join(HERE, "sieve_brown.py"), encoding="utf-8").read().split("\n")[:35]
open(os.path.join(out, "g.py"), "w", encoding="utf-8").write("\n".join(src) + "\n" + open(os.path.join(HERE, "sieve_g1b_kernel.py"), encoding="utf-8").read())
ENV = dict(os.environ, G1_LOCAL="1", G1_JX="1", G1_MODE="jx", G1_DATA=M, G1_CLS=os.path.join(M, "kaggle_ms", "data"), G1_BCACHE=os.path.join(M, "bench", "brown_mt27.npz"),
           G1_UD=os.path.join(M, "ud"), G1_PARSEPY=os.path.join(HERE, "sieve_parse.py"), G1_SVDCACHE=os.path.join(M, "bench", "svdcache"), G1_POFF=poff, G1_NG=ng, G1_TRACE=trace)
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
need_svd = [k for k, c in arms.items() if c.get("svd")]
if need_svd:                                                                                               # warm (or just load) the phase cache once before running in parallel
    d = os.path.join(out, "_warm"); os.makedirs(d, exist_ok=True); log("warming the harmonic phase cache")
    subprocess.run(["py", "-3.12", os.path.join(out, "g.py")], cwd=d, env=dict(ENV, G1_OUT=d, G1_NG="1", G1_ARMS=json.dumps({"W": arms[need_svd[0]]})), stdout=open(os.path.join(d, "log.txt"), "w"), stderr=subprocess.STDOUT)
procs, todo = {}, list(arms.items())
while todo or procs:
    while todo and len(procs) < par:
        k, c = todo.pop(0); d = os.path.join(out, k); os.makedirs(d, exist_ok=True)
        procs[k] = subprocess.Popen(["py", "-3.12", os.path.join(out, "g.py")], cwd=d, env=dict(ENV, G1_OUT=d, G1_ARMS=json.dumps({k: c})), stdout=open(os.path.join(d, "log.txt"), "w"), stderr=subprocess.STDOUT); log(f"started {k}")
    for k in list(procs):
        if procs[k].poll() is not None: log(f"finished {k} (exit {procs[k].returncode})"); procs.pop(k)
    time.sleep(5)
G = {}
for k in arms:
    f = os.path.join(out, k, "g1b_jx_gen.json")
    if not os.path.exists(f): log(f"MISSING {k}"); continue
    g = json.load(open(f, encoding="utf-8")); G[k] = g[k]; G.setdefault("truth", g["truth"])
    for line in open(os.path.join(out, k, "log.txt"), encoding="utf-8", errors="replace"):
        if line.startswith(("PLAG", "COMB")): print("  " + line.strip()[:160])
json.dump(G, open(os.path.join(out, "g1b_jx_gen.json"), "w", encoding="utf-8"), indent=0); log(f"merged {len(G) - 1} arms -> {out}/g1b_jx_gen.json")
