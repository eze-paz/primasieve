"""helper: compute one missing scored-position Vote of a program per call (keeps each run under five minutes)"""
import sys, json, os, hashlib, time
import sieve_prim as P
st = json.load(open(sys.argv[1])); T0 = time.time()
for k in st["mem"] + st["lift"]:
    if not os.path.exists(os.path.join(P.PD, f"eval_{hashlib.md5(k.encode()).hexdigest()[:16]}.npz")):
        P.vote("eval", json.loads(k)); print("cached", P.describe(json.loads(k)), f"{time.time() - T0:.0f}s", flush=True); break
else: print("all cached")
