"""R26 T22c: statement match checked by the rival score, margins per question word chosen on practice; saves the
answers it adds for silent questions (r26_t22f_policy.json). Run: py -3.12 r26_t22c.py"""
import json, sys, collections, os
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
from b6_rwkv import hit
st = json.load(open('val_all13.json', encoding='utf-8'))['stories']; items = [(q, g) for s in st for q, g in s['qs']]; gold = [g for _, g in items]
A = json.load(open('r26_stmatch_fix2_answers.json', encoding='utf-8')); SC = json.load(open('r25_steelman2_scores.json', encoding='utf-8'))
L = [l for l in open('r24_diag_asA.txt', encoding='utf-8', errors='replace') if l.startswith('VAL |')]
route = [l.split('| route ')[1].split(' |')[0] for l in L]; ans = [l.split('| ans ')[1].split(' |')[0] for l in L]; ans = [None if a == 'None' else a for a in ans]
PR = list(range(310)) + list(range(510, 910)); UN = list(range(310, 510)) + list(range(910, 2510))
fr = collections.defaultdict(lambda: [0, 0])
for i in PR:
    if ans[i]: fr[route[i]][0 if hit(ans[i], gold[i]) else 1] += 1
trust = {r for r, (a, w) in fr.items() if a - 3 * w > 0}
base = lambda i: ans[i] if (ans[i] and route[i] in trust) else None
wh = lambda i: items[i][0].split()[0].lower()
def nrm(x): return " ".join(x.lower().replace("'", " ").split())
def checked(i, t):
    a = A[i]
    if a is None: return None
    c = SC[i]['c']
    if t is None or not c: return a
    same = lambda x: hit(x, [nrm(a)]) or hit(a, [x])
    mine = max((s for x, s in c if same(x)), default=None); rival = max((s for x, s in c if not same(x)), default=None)
    if mine is None: return None
    return None if (rival is not None and rival - mine > t) else a
def fit(idx, f):
    r = w = 0
    for i in idx:
        x = f(i)
        if x is None: continue
        if hit(x, gold[i]): r += 1
        else: w += 1
    return r - 3 * w, r, w
T = {}
for k in ("who", "what", "where", "when"):
    idx = [i for i in PR if wh(i) == k and base(i) is None]
    res = {t: fit(idx, lambda i: checked(i, t)) for t in (0, 1, 2, 4, 8, None)}
    if '--wilson' in sys.argv:
        import math
        def lb(r, w):
            n = r + w
            if n == 0: return 0.0
            p = r / n; z = 1.96; return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
        ok = [t for t in (None, 8, 4, 2, 1, 0) if lb(res[t][1], res[t][2]) >= 0.75]
        if ok: T[k] = ok[0]
    else:
        t = max(res, key=lambda t: res[t][0])
        if res[t][0] > 0: T[k] = t
add = [(checked(i, T[wh(i)]) if (base(i) is None and wh(i) in T) else None) for i in range(len(items))]
json.dump(add, open('r26_t22fw_policy.json' if '--wilson' in sys.argv else 'r26_t22f_policy.json', 'w', encoding='utf-8'))
pol = lambda i: base(i) or add[i]
print(f"T22f margins {T}; policy practice {fit(PR, pol)}, untouched {fit(UN, pol)}")
