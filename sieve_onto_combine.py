"""SO final: every piece accepted in O1-O8 added to the base together, refitted on the fit positions"""
import os, sys, json
argv = sys.argv[:]
import sieve_onto as O, sieve_prim3 as P3, sieve_fs2 as F
base = json.load(open(O.BASE)); st = json.loads(json.dumps(base)); bm, bl = set(base["mem"]), set(base["lift"])
for idea in ("O1", "O2", "O3", "O4", "O5", "O6", "O7", "O8"):
    f = os.path.join(F.HERE, f"sieve_onto_{idea}.json")
    if not os.path.exists(f): continue
    s = json.load(open(f)); 
    for k, th in zip(s["mem"], s["th"][1:]):
        if k not in bm and k not in st["mem"]: st["mem"].append(k); st["th"].append(th); st["ga"].append(0.0); st["gact"].append(0)
    for k, be in zip(s["lift"], s["be"]):
        if k not in bl and k not in st["lift"]: st["lift"].append(k); st["be"].append(be)
M = P3.Model(O.CX, st); M.gact = st["gact"]; b0 = M.bits() / M.n; b1 = M.refit(40) / M.n; st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist())
json.dump(st, open(os.path.join(F.HERE, "sieve_onto_all.json"), "w")); F.log(f"SO all: {len(st['mem'])} Votes, {len(st['lift'])} lifts; fit {b0:.4f} -> {b1:.4f} (refit)")
