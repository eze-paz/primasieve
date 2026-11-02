"""helper: compute one missing Vote of a program's components per call, in the given context (SZ_EXACT honoured)"""
import sys, json, os, time
sys_argv = sys.argv[:]; sys.argv = [sys.argv[0], "none"]
import sieve_prim4 as P4, sieve_prim as P
P4.install4(); st = json.load(open(sys_argv[1])); cx = sys_argv[2]; T0 = time.time()
for k in st["mem"] + st["lift"]:
    sp = json.loads(k); f = P.cname(cx, __import__("hashlib").md5(P.key(sp).encode()).hexdigest()[:16])
    if not os.path.exists(f): P.vote(cx, sp); print("cached", cx, P.describe(sp), f"{time.time() - T0:.0f}s", flush=True); break
else: print("all cached", cx)
