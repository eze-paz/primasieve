"""R25-dt: per trusted route, right / wrong on val_fresh10 (r24_diag_asA, 2310-2510) and val_fresh12 (r24_diag_dr, 2510-2710)."""
import collections
def load(f): return [l for l in open(f, encoding="utf-8", errors="replace") if l.startswith("VAL")]
route = lambda l: l.split("| route ")[1].split(" |")[0]; spoke = lambda l: "| ans None |" not in l
A = load("r24_diag_asA.txt"); D = load("r24_diag_dr.txt")
fit = collections.defaultdict(lambda: [0, 0])
for l in D[:310] + D[510:910]:
    if spoke(l): fit[route(l)][0 if "hit True" in l else 1] += 1
keep = {r for r, (a, w) in fit.items() if a - 3 * w > 0}
for nm, part in (("val_fresh10", A[2310:2510]), ("val_fresh12", D[2510:2710])):
    c = collections.defaultdict(lambda: [0, 0])
    for l in part:
        if spoke(l) and route(l) in keep: c[route(l)][0 if "hit True" in l else 1] += 1
    print(f"R25-dt {nm} trusted routes (right, wrong):", {r: tuple(v) for r, v in sorted(c.items(), key=lambda kv: -sum(kv[1]))})
