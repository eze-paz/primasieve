"""R26 T22i protocol: per-word rival-check margins chosen on the union of main-practice silent questions and all 600
extra practice questions; applied to silent questions of the main policy. Run: py -3.12 r26_t22i.py fix|fix2|fix3"""
import json, sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
from b6_rwkv import hit
V = sys.argv[1]
def nrm(x): return " ".join(x.lower().replace("'", " ").split())
def checked(a, c, t):
    if a is None: return None
    if t is None or not c: return a
    same = lambda x: hit(x, [nrm(a)]) or hit(a, [x])
    mine = max((s for x, s in c if same(x)), default=None); rival = max((s for x, s in c if not same(x)), default=None)
    if mine is None: return None
    return None if (rival is not None and rival - mine > t) else a
st = json.load(open('val_all13.json', encoding='utf-8'))['stories']; items = [(q, g) for s in st for q, g in s['qs']]
SC = json.load(open('r25_steelman2_scores.json', encoding='utf-8'))
L = [l for l in open('r24_diag_asA.txt', encoding='utf-8', errors='replace') if l.startswith('VAL |')]
route = [l.split('| route ')[1].split(' |')[0] for l in L]; ans = [l.split('| ans ')[1].split(' |')[0] for l in L]; ans = [None if a == 'None' else a for a in ans]
PR = list(range(310)) + list(range(510, 910)); fr = collections.defaultdict(lambda: [0, 0])
for i in PR:
    if ans[i]: fr[route[i]][0 if hit(ans[i], items[i][1]) else 1] += 1
trust = {r for r, (a, w) in fr.items() if a - 3 * w > 0}
silent = lambda i: not (ans[i] and route[i] in trust)
xs = json.load(open('r26_extra_practice.json', encoding='utf-8'))['stories']; xq = [(q, g) for s in xs for q, g in s['qs']]; XS = json.load(open('r26_xp_steelman2_scores.json', encoding='utf-8'))
A = json.load(open(f'r26_stmatch_{V}_answers.json', encoding='utf-8')); XA = json.load(open(f'r26_xp_{V}_answers.json', encoding='utf-8'))
T = {}
for k in ('who', 'what', 'where', 'when'):
    res = {}
    for t in (0, 1, 2, 4, 8, None):
        r = w = 0
        for i in PR:
            if silent(i) and items[i][0].split()[0].lower() == k:
                a = checked(A[i], SC[i]['c'], t)
                if a is not None: r += hit(a, items[i][1]); w += not hit(a, items[i][1])
        for i, (q, g) in enumerate(xq):
            if q.split()[0].lower() == k:
                a = checked(XA[i], XS[i]['c'], t)
                if a is not None: r += hit(a, g); w += not hit(a, g)
        res[t] = (r - 3 * w, r, w)
    t = max(res, key=lambda t: res[t][0])
    if res[t][0] > 0: T[k] = t
add = [(checked(A[i], SC[i]['c'], T[items[i][0].split()[0].lower()]) if (silent(i) and items[i][0].split()[0].lower() in T) else None) for i in range(len(items))]
json.dump(add, open(f'r26_t22i_{V}_policy.json', 'w', encoding='utf-8')); print(V, 'margins', T)
