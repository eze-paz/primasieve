"""R25-q: the learner decides which of its own answer routes to trust, by its own score on practice only.
Reads the per-question lines of a policy run (route and hit for every question). A route is kept when its practice
fitness (+1 right, -3 wrong) over the old 110 and val_more 200 is above zero; the kept set is then applied once to the
untouched val_fresh2 200, reported as a total only. Run: python learned/base/r25_trust.py r24_diag_r25p_l.txt"""
import sys, collections
f = sys.argv[1]
L = [l for l in open(f, encoding="utf-8", errors="replace") if l.startswith("VAL |")]      # logs may carry accented names in another encoding
route = lambda l: l.split("| route ")[1].split(" |")[0]
spoke = lambda l: "| ans None |" not in l
right = lambda l: "hit True" in l
fit = collections.defaultdict(lambda: [0, 0])
PRACTICE = L[:310] + L[510:] if "--big" in sys.argv else L[:310]
if "--trust-half" in sys.argv: PRACTICE = L[:110] + L[710:910]                             # R25-z2: choose trust on the half that did not teach (old 110 + practice B)                          # R25-u: old 110 + val_more + practice A / B; the untouched val_fresh2 is L[310:510]
UNTOUCHED = L[310:510]
if "--final" in sys.argv: PRACTICE = L[:310] + L[510:910]; FINAL = L[910:1110]            # R25-final: trust on the same 710 as R25-x; val_fresh3 scored once
for l in PRACTICE:
    if spoke(l): fit[route(l)][0 if right(l) else 1] += 1
keep = {r for r, (a, w) in fit.items() if a - 3 * w > 0}
print("practice fitness by route (right, wrong):", {r: tuple(v) for r, v in sorted(fit.items(), key=lambda kv: -sum(kv[1]))})
print("routes the learner keeps:", sorted(keep)); print("routes it drops:", sorted(set(fit) - keep))
for nm, part in ((f"practice {len(PRACTICE)}", PRACTICE), ("untouched val_fresh2 200", UNTOUCHED)):
    a_all = sum(1 for l in part if spoke(l) and right(l)); w_all = sum(1 for l in part if spoke(l) and not right(l))
    a_k = sum(1 for l in part if spoke(l) and right(l) and route(l) in keep); w_k = sum(1 for l in part if spoke(l) and not right(l) and route(l) in keep)
    print(f"{nm}: all routes {a_all} right / {w_all} wrong (fitness {a_all - 3 * w_all}) -> kept routes {a_k} right / {w_k} wrong (fitness {a_k - 3 * w_k})")

if "--lift" in sys.argv:                                                                 # R25-s: the learner also picks a role-score cut-off on practice
    def lift(l):
        try: v = l.split("| lift ")[1].split(" |")[0]; return None if v == "None" else float(v)
        except Exception: return None
    def score(part, tau):
        a = w = 0
        for l in part:
            if not spoke(l) or route(l) not in keep: continue
            lv = lift(l)
            if tau is not None and lv is not None and lv < tau: continue
            if right(l): a += 1
            else: w += 1
        return a - 3 * w, a, w
    res = {tau: score(PRACTICE, tau) for tau in (None, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8)}
    for tau, r in res.items(): print(f"  role-score cut-off {tau}: practice fitness {r[0]} ({r[1]} right, {r[2]} wrong)")
    best = max(res, key=lambda t: res[t][0])
    print(f"the learner chose cut-off {best}: practice {res[best]} | untouched val_fresh2 {score(UNTOUCHED, best)} (no cut-off: {score(UNTOUCHED, None)})")


if "--by-kind" in sys.argv:                                                              # R25-aa: trust per (route, question kind), falling back to the route
    def qkind(l):
        parts = l.split(" | "); q = parts[2] if parts[1].startswith("lift") else parts[1]
        return q.strip().lower().split()[0] if q.strip() else ""
    fk = collections.defaultdict(lambda: [0, 0])
    for l in PRACTICE:
        if spoke(l): fk[(route(l), qkind(l))][0 if right(l) else 1] += 1
    def trusted(l):
        a, w = fk[(route(l), qkind(l))]
        if a + w >= 10: return a - 3 * w > 0
        return route(l) in keep
    for nm, part in ((f"practice {len(PRACTICE)}", PRACTICE), ("untouched val_fresh2 200", UNTOUCHED)):
        a = sum(1 for l in part if spoke(l) and right(l) and trusted(l)); w = sum(1 for l in part if spoke(l) and not right(l) and trusted(l))
        print(f"R25-aa {nm}: trust by route and kind -> {a} right / {w} wrong (fitness {a - 3 * w})")
    print("R25-aa (route, kind) decisions with >= 10 practice answers:", {f"{k[0]}/{k[1]}": ("keep" if v[0] - 3 * v[1] > 0 else "drop", tuple(v)) for k, v in fk.items() if sum(v) >= 10})


if "--final" in sys.argv:
    a = sum(1 for l in FINAL if spoke(l) and right(l) and route(l) in keep); w = sum(1 for l in FINAL if spoke(l) and not right(l) and route(l) in keep)
    a0 = sum(1 for l in FINAL if spoke(l) and right(l)); w0 = sum(1 for l in FINAL if spoke(l) and not right(l))
    print(f"R25-final val_fresh3 ({len(FINAL)} questions, scored once): all routes {a0} right / {w0} wrong | trusted routes {a} right / {w} wrong, precision {a / max(1, a + w):.3f}, fitness {a - 3 * w}")


if "--final4" in sys.argv:                                                               # R25-ai: trust on the same 710; val_fresh4 = L[1110:1310], scored once per configuration
    P4 = L[:310] + L[510:910]; F4 = L[1110:1310]
    fit4 = collections.defaultdict(lambda: [0, 0])
    for l in P4:
        if spoke(l): fit4[route(l)][0 if right(l) else 1] += 1
    keep4 = {r for r, (a, w) in fit4.items() if a - 3 * w > 0}
    a = sum(1 for l in F4 if spoke(l) and right(l) and route(l) in keep4); w = sum(1 for l in F4 if spoke(l) and not right(l) and route(l) in keep4)
    a0 = sum(1 for l in F4 if spoke(l) and right(l)); w0 = sum(1 for l in F4 if spoke(l) and not right(l))
    print(f"R25-ai val_fresh4 ({len(F4)} questions): all routes {a0} right / {w0} wrong | trusted routes {a} right / {w} wrong, precision {a / max(1, a + w):.3f}, fitness {a - 3 * w}")
