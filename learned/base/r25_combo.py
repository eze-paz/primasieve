"""R25-dp: the main system and the rare-word graph reader together, on val_fresh10 (untouched for the reader; scored
once for the main system in R25-as). Main system: its per-question answers and routes from the R25-as run
(r24_diag_asA.txt); its trusted routes chosen as always on the 710 practice questions (L[:310] + L[510:910]).
Reader: the R25-df configuration (its trust learned on practice A+B: who-questions only). Combination: the main
system's trusted answer when it has one; otherwise the reader's trusted answer; otherwise silent.
Run: py -3.12 r25_combo.py"""
import os, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
L = [l.rstrip("\n") for l in open(os.environ.get("R25_DIAG", "r24_diag_asA.txt"), encoding="utf-8", errors="replace") if l.startswith("VAL")]
route = lambda l: l.split("| route ")[1].split(" |")[0]
spoke = lambda l: "| ans None |" not in l and route(l) != "silent"
right = lambda l: "hit True" in l                                                       # as r25_trust.py
fit = collections.defaultdict(lambda: [0, 0])
for l in L[:310] + L[510:910]:
    if spoke(l): fit[route(l)][0 if right(l) else 1] += 1
keep = {r for r, (a, w) in fit.items() if a - 3 * w > 0}
src = open("r25_rwg.py", encoding="utf-8").read(); src = src[:src.index("tot = collections.Counter()")]
sys.argv = ["r25_rwg.py"]; R = {"__name__": "rwg", "__file__": os.path.join(HERE, "r25_rwg.py")}; exec(compile(src, "r25_rwg.py", "exec"), R)
pk = collections.defaultdict(collections.Counter)
for f in ("val_practice_a.json", "val_practice_b.json"):
    for st in json.load(open(f, encoding="utf-8"))["stories"]:
        for q, gold in st["qs"]:
            a = R["answer"](st["text"], q); key = (q.split()[0].lower(), R["FULL"][0], R["NEAR"][0])
            if a is not None: pk[key]["right" if R["norm"](a) in {R["norm"](x) for x in gold} else "wrong"] += 1
rkeep = {k for k, c in pk.items() if c["right"] - 3 * c["wrong"] > 0 and k[0] == "who"}
qs = [(st["text"], q, gold) for st in json.load(open(os.environ.get("R25_SET", "val_fresh10.json"), encoding="utf-8"))["stories"] for q, gold in st["qs"]]
OFF = int(os.environ.get("R25_OFF", "2310")); F = L[OFF:OFF + 200]; assert len(F) == len(qs) == 200
assert all(q in l for (t, q, g), l in zip(qs, F)), "main-system lines and val_fresh10 questions do not line up"
m = r = c = collections.Counter()
m, r, c = collections.Counter(), collections.Counter(), collections.Counter()
for (text, q, gold), l in zip(qs, F):
    main = (right(l) if spoke(l) and route(l) in keep else None)
    a = R["answer"](text, q); rd = None
    if a is not None and (q.split()[0].lower(), R["FULL"][0], R["NEAR"][0]) in rkeep: rd = R["norm"](a) in {R["norm"](x) for x in gold}
    for cnt, v in ((m, main), (r, rd), (c, main if main is not None else rd)):
        cnt["silent" if v is None else ("right" if v else "wrong")] += 1
for nm, cnt in (("main system, trusted", m), ("reader, trusted", r), ("together", c)):
    print(f"R25-dp {nm}: {cnt['right']} right / {cnt['wrong']} wrong / {cnt['silent']} silent (fitness {cnt['right'] - 3 * cnt['wrong']})", flush=True)
