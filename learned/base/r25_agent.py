"""R25-aq: an agent axis from the learner's own word vectors decides whether a 'who' answer is the right kind.
The axis is a principal direction of the 8,000 most frequent words' vectors, oriented so that people-words ('man',
'woman', 'doctor') sit at the high end and action-words ('took', 'threw') at the low end, and chosen as the direction
among the top 10 that separates those two seed sets best. On top of the routes the learner trusts (chosen on the 710
practice questions), a 'who' answer whose head word has a vector and falls below a cut-off is refused; the cut-off is
chosen on the same practice questions. A given block of untouched questions is scored once.
Run: python r25_agent.py DIAGFILE START END"""
import os, sys, re, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
f, a_, b_ = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
z = np.load(os.environ.get("R25_VEC", "r25_vectors_all.npz")); vocab = z["vocab"].tolist(); V = z["vecs"]; vi = {w: i for i, w in enumerate(vocab)}
top = V[:8000] - V[:8000].mean(0); _, _, Wt = np.linalg.svd(top, full_matrices=False)
people = [w for w in ("man", "woman", "boy", "girl", "doctor", "farmer", "king", "child", "mother", "father", "soldier", "servant") if w in vi]
acts = [w for w in ("took", "threw", "brought", "gave", "carried", "set", "put", "struck") if w in vi]
best = max(range(10), key=lambda k: abs(np.mean([V[vi[w]] @ Wt[k] for w in people]) - np.mean([V[vi[w]] @ Wt[k] for w in acts])))
ax = Wt[best] * (1 if np.mean([V[vi[w]] @ Wt[best] for w in people]) > np.mean([V[vi[w]] @ Wt[best] for w in acts]) else -1)
print(f"R25-aq agent axis = principal direction {best + 1}; people end: {[vocab[i] for i in np.argsort(top @ ax)[-8:]]}; other end: {[vocab[i] for i in np.argsort(top @ ax)[:8]]}")
L = [l for l in open(f, encoding="utf-8", errors="replace") if l.startswith("VAL |")]
route = lambda l: l.split("| route ")[1].split(" |")[0]
spoke = lambda l: "| ans None |" not in l
right = lambda l: "hit True" in l
q = lambda l: (l.split(" | ")[2] if l.split(" | ")[1].startswith("lift") else l.split(" | ")[1]).strip()
ans = lambda l: l.split("| ans ")[1].split(" |")[0]
def proj(l):
    if not q(l).lower().startswith("who"): return None
    ws = [w for w in re.findall(r"[A-Za-z]+", ans(l))]
    if not ws or ws[-1][:1].isupper() or ws[-1].lower() not in vi: return None          # names and unknown words pass
    return float(V[vi[ws[-1].lower()]] @ ax)
P = L[:310] + L[510:910]; F = L[a_:b_]
fr = collections.defaultdict(lambda: [0, 0])
for l in P:
    if spoke(l): fr[route(l)][0 if right(l) else 1] += 1
keep = {r for r, (x, y) in fr.items() if x - 3 * y > 0}
def score(part, tau):
    a = w = 0
    for l in part:
        if not spoke(l) or route(l) not in keep: continue
        p = proj(l)
        if tau is not None and p is not None and p < tau: continue
        a, w = (a + 1, w) if right(l) else (a, w + 1)
    return a - 3 * w, a, w
taus = [None] + sorted({round(x, 3) for x in np.quantile([proj(l) for l in P if spoke(l) and proj(l) is not None] or [0], [0.05, 0.1, 0.2, 0.3, 0.5])})
res = {t: score(P, t) for t in taus}
for t, r in res.items(): print(f"  cut-off {t}: practice {r}")
bt = max(res, key=lambda t: res[t][0])
print(f"R25-aq the learner chose cut-off {bt}; scored once, questions {a_}-{b_}: without the axis {score(F, None)} | with the axis {score(F, bt)}")
