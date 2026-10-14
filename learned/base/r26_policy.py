"""R26: the comprehension policy assembled from the tested routes, with switches; choices on practice only.
Run: py -3.12 r26_policy.py [--fallback] [--why-because]"""
import json, sys, collections, re, os
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
from b6_rwkv import hit
st = json.load(open('val_all13.json', encoding='utf-8'))['stories']; items = [(s['text'], q, g) for s in st for q, g in s['qs']]; gold = [g for _, _, g in items]
SC = json.load(open('r25_steelman2_scores.json', encoding='utf-8')); W_ = 'w' if '--wilson' in sys.argv else ''
T22 = json.load(open(f'r26_t22f{W_}_policy.json' if '--fix2' in sys.argv else f'r26_t22e{W_}_policy.json' if '--fix' in sys.argv else 'r26_t22c_policy.json', encoding='utf-8')); O = json.load(open('r26_ops_answers.json', encoding='utf-8'))
L = [l for l in open('r24_diag_asA.txt', encoding='utf-8', errors='replace') if l.startswith('VAL |')]
route = [l.split('| route ')[1].split(' |')[0] for l in L]; ans = [l.split('| ans ')[1].split(' |')[0] for l in L]; ans = [None if a == 'None' else a for a in ans]
PR = list(range(310)) + list(range(510, 910)); UN = list(range(310, 510)) + list(range(910, 2510))
fr = collections.defaultdict(lambda: [0, 0])
for i in PR:
    if ans[i]: fr[route[i]][0 if hit(ans[i], gold[i]) else 1] += 1
trust = {r for r, (a, w) in fr.items() if a - 3 * w > 0}
def nrm(x): return " ".join(x.lower().replace("'", " ").split())
def veto(i, a, t):
    c = SC[i]['c']
    if t is None or not c: return False
    same = lambda x: hit(x, [nrm(a)]) or hit(a, [x])
    mine = max((s for x, s in c if same(x)), default=None); rival = max((s for x, s in c if not same(x)), default=None)
    return mine is not None and rival is not None and rival - mine > t
def fit(idx, f):
    r = w = 0
    for i in idx:
        x = f(i)
        if x is None: continue
        if hit(x, gold[i]): r += 1
        else: w += 1
    return r - 3 * w, r, w
TM = {}
for r in trust:
    idx = [i for i in PR if route[i] == r and ans[i]]
    if len(idx) < 5: TM[r] = None; continue
    res = {t: fit(idx, lambda i: None if veto(i, ans[i], t) else ans[i]) for t in (0, 1, 2, 4, 8, None)}
    TM[r] = max(res, key=lambda t: (res[t][0], t is None))
reader = lambda i: ans[i] if (ans[i] and route[i] in trust and not veto(i, ans[i], TM[route[i]])) else None
spoke = lambda i: bool(ans[i] and route[i] in trust)
def why_because(i):
    text, q, _ = items[i]
    if O[i][0] != "WHY" or O[i][1] is None: return None
    S = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    for k, s in enumerate(S):
        if O[i][1] in s:
            m = re.search(r"\bbecause\b\s+([^,.;]+)", s, re.I)
            if m: return m.group(1).strip()
            if k + 1 < len(S): m = re.match(r"\s*because\b\s+([^,.;]+)", S[k + 1], re.I)
            return m.group(1).strip() if m else None
    return None
extra = {}
if "--why-because" in sys.argv:
    f = fit([i for i in PR if not spoke(i)], why_because); print("WHY-because practice on silent:", f)
    if f[0] > 0: extra["why"] = why_because
ORD = json.load(open('r26_order_answers.json', encoding='utf-8')) if os.path.exists('r26_order_answers.json') else [None] * len(items)
if "--order" in sys.argv:
    f = fit([i for i in PR if not spoke(i) and not T22[i]], lambda i: ORD[i]); fu = fit([i for i in UN if not spoke(i) and not T22[i]], lambda i: ORD[i]); print("ORDER on silent practice:", f, "untouched:", fu)
    if f[0] > 0: extra["order"] = lambda i: ORD[i]
DOA = json.load(open('r26_do_answers.json', encoding='utf-8')) if os.path.exists('r26_do_answers.json') else [None] * len(items)
if "--do" in sys.argv:
    f = fit([i for i in PR if not spoke(i) and not T22[i]], lambda i: DOA[i]); fu = fit([i for i in UN if not spoke(i) and not T22[i]], lambda i: DOA[i]); print("DO on silent practice:", f, "untouched:", fu)
    if f[0] > 0: extra["do"] = lambda i: DOA[i]
T22D = json.load(open('r26_t22d_policy.json', encoding='utf-8')) if os.path.exists('r26_t22d_policy.json') else [None] * len(items)
def other(i):
    x = T22[i] or (T22D[i] if "--relax" in sys.argv else None) or (O[i][1] if O[i][0] in ("COUNT", "WHOSE") else None)
    if x is None and "order" in extra: x = extra["order"](i)
    if x is None and "do" in extra: x = extra["do"](i)
    if x is None and "why" in extra: x = extra["why"](i)
    return x
SMA = json.load(open('r26_stmatch_fix2_answers.json' if '--fix2' in sys.argv else 'r26_stmatch_fix_answers.json' if '--fix' in sys.argv else 'r26_stmatch_answers.json', encoding='utf-8')); TMW = {'who': 0, 'what': 1, 'where': 0, 'when': 8}
def sm_checked(i):
    a = SMA[i]; k = items[i][1].split()[0].lower()
    if a is None or k not in TMW: return None
    c = SC[i]['c']
    if not c: return a
    same = lambda x: hit(x, [nrm(a)]) or hit(a, [x])
    mine = max((s for x, s in c if same(x)), default=None); rival = max((s for x, s in c if not same(x)), default=None)
    if mine is None: return None
    return None if (rival is not None and rival - mine > TMW[k]) else a
def agree(i):
    a, b = ans[i], SMA[i]
    if not a or not b or spoke(i): return None
    return a if (hit(a, [nrm(b)]) or hit(b, [nrm(a)])) else None
if "--agree" in sys.argv:
    base_pol = lambda i: reader(i) or (None if spoke(i) else other(i))
    f = fit([i for i in PR if base_pol(i) is None], agree); fu = fit([i for i in UN if base_pol(i) is None], agree); print("AGREE on unanswered practice:", f, "untouched:", fu)
    if f[0] <= 0: sys.argv.remove("--agree")
def pol(i):
    r = reader(i)
    if r is not None: return r
    if spoke(i) and "--fallback2" in sys.argv: return sm_checked(i)
    if "--agree" in sys.argv and not spoke(i):
        o = other(i)
        return o if o is not None else agree(i)
    if spoke(i) and "--fallback" not in sys.argv: return None
    return other(i)
print(f"policy {[a for a in sys.argv[1:]]}: practice {fit(PR, pol)}, untouched {fit(UN, pol)}")
json.dump([pol(i) for i in range(len(items))], open('r26_policy_answers.json', 'w', encoding='utf-8'))
