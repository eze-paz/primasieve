"""R25-ds: secondary, lenient scoring of R25-dr (labelled as such; the registered strict numbers stand). An answer also
counts if it is one word equal to the last word of a gold form ('Okafor' for 'mrs. okafor'). Same trusted answers."""
import os, sys, re, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
norm = lambda s: " ".join(re.findall(r"[a-z0-9']+", s.lower()))
def ok(a, golds): a = norm(a); return a in {norm(g) for g in golds} or (len(a.split()) == 1 and a in {norm(g).split()[-1] for g in golds if norm(g)})
L = [l for l in open("r24_diag_dr.txt", encoding="utf-8", errors="replace") if l.startswith("VAL")]
route = lambda l: l.split("| route ")[1].split(" |")[0]; spoke = lambda l: "| ans None |" not in l
fit = collections.defaultdict(lambda: [0, 0])
for l in L[:310] + L[510:910]:
    if spoke(l): fit[route(l)][0 if "hit True" in l else 1] += 1
keep = {r for r, (a, w) in fit.items() if a - 3 * w > 0}
qs = [(q, g) for st in json.load(open("val_fresh12.json", encoding="utf-8"))["stories"] for q, g in st["qs"]]
c = collections.Counter()
for (q, g), l in zip(qs, L[2510:2710]):
    if spoke(l) and route(l) in keep:
        ans = l.split("| ans ")[1].split(" | hit")[0]; c["right" if ok(ans, g) else "wrong"] += 1
print(f"R25-ds main system trusted, lenient secondary scoring on val_fresh12: {c['right']} right / {c['wrong']} wrong (strict: 16 / 25)")
