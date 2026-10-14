"""R26 T24: operators for how-many, whose, which, why and how questions (R26_prereg.md). Run: py -3.12 r26_ops.py"""
import os, sys, re, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r26_stmatch as SM
from b6_rwkv import hit
NUM = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty hundred dozen several".split()
def sents(text): return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
def sing(n): return n[:-3] + "y" if n.endswith("ies") else n[:-2] if n.endswith("ses") or n.endswith("xes") else n[:-1] if n.endswith("s") else n
def content_sentence(text, words):
    cw = [SM.norm(w) for w in words if w.lower() not in SM.STOP]
    if not cw: return None, None
    S = sents(text); hits = []
    for k, s in enumerate(S):
        nt = [SM.norm(t) for t in SM.TOK.findall(s)]
        if all(c in nt for c in cw): hits.append(k)
    return (S, hits[0]) if len(hits) == 1 else (S, None)
def op(text, q):
    ql = q.lower().rstrip("?"); qw = [w for w in SM.TOK.findall(q) if w[0].isalnum()]
    m = re.match(r"how many (\w+)", ql)
    if m:
        n = m.group(1); found = set()
        for mm in re.finditer(r"\b(" + "|".join(NUM) + r"|\d+)\s+(?:\w+\s+)?(\w+)", text.lower()):
            if mm.group(2) in (n, sing(n)) or sing(mm.group(2)) == sing(n): found.add(mm.group(1))
        return ("COUNT", found.pop()) if len(found) == 1 else ("COUNT", None)
    m = re.match(r"whose (\w+)", ql)
    if m:
        n = m.group(1); found = {mm.group(1) for mm in re.finditer(r"\b([A-Z][a-z]+)'s\s+(?:\w+\s+)?" + re.escape(n) + r"\b", text)}
        return ("WHOSE", found.pop()) if len(found) == 1 else ("WHOSE", None)
    m = re.match(r"which (\w+) (.*)", ql)
    if m:
        n = m.group(1); a = SM.answer(text, "who " + m.group(2) + "?") or SM.answer(text, "what " + m.group(2) + "?")
        if a and (a.lower().split()[-1] in (n, sing(n)) or a[0].isupper()): return ("WHICH", a)
        return ("WHICH", None)
    if ql.startswith("why"):
        rest = qw[1:]; rest = rest[1:] if rest and rest[0].lower() in SM.AUX else rest
        S, k = content_sentence(text, rest)
        if k is None: return ("WHY", None)
        for s in (S[k], S[k + 1] if k + 1 < len(S) else ""):
            mm = re.search(r"\b(because|so that|since|to)\b\s+([^,.;]+)", s if s is S[k] else (s if re.match(r"\s*(because|so)\b", s, re.I) else ""), re.I)
            if mm: return ("WHY", mm.group(2).strip())
        return ("WHY", None)
    if ql.startswith("how ") and not ql.startswith("how many") and not ql.startswith("how much"):
        rest = qw[1:]; rest = rest[1:] if rest and rest[0].lower() in SM.AUX else rest
        S, k = content_sentence(text, rest)
        if k is None: return ("HOW", None)
        mm = re.search(r"\b(by|with)\s+([^,.;]+)", S[k]) or re.search(r"\b(\w+ly)\b", S[k])
        return ("HOW", mm.group(0).strip() if mm else None)
    return (None, None)
def main():
    st = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; items = [(s["text"], q, g) for s in st for q, g in s["qs"]]; gold = [g for _, _, g in items]
    O = [op(t, q) for t, q, _ in items]; json.dump(O, open("r26_ops_answers.json", "w", encoding="utf-8"))
    L = [l for l in open("r24_diag_asA.txt", encoding="utf-8", errors="replace") if l.startswith("VAL |")]
    route = [l.split("| route ")[1].split(" |")[0] for l in L]; ans = [l.split("| ans ")[1].split(" |")[0] for l in L]; ans = [None if a == "None" else a for a in ans]
    PR = list(range(310)) + list(range(510, 910)); UN = list(range(310, 510)) + list(range(910, 2510))
    fr = collections.defaultdict(lambda: [0, 0])
    for i in PR:
        if ans[i]: fr[route[i]][0 if hit(ans[i], gold[i]) else 1] += 1
    trust = {r for r, (a, w) in fr.items() if a - 3 * w > 0}
    T22 = json.load(open("r26_t22c_policy.json", encoding="utf-8")) if os.path.exists("r26_t22c_policy.json") else [None] * len(items)
    base = lambda i: (ans[i] if (ans[i] and route[i] in trust) else None) or T22[i]
    def fit(idx, f):
        r = w = 0
        for i in idx:
            x = f(i)
            if x is None: continue
            if hit(x, gold[i]): r += 1
            else: w += 1
        return r - 3 * w, r, w
    keep = set()
    for k in ("COUNT", "WHOSE", "WHICH", "WHY", "HOW"):
        f = fit([i for i in PR if O[i][0] == k and base(i) is None], lambda i: O[i][1]); fu = fit([i for i in UN if O[i][0] == k and base(i) is None], lambda i: O[i][1])
        n = sum(1 for i in PR if O[i][0] == k)
        if f[0] > 0: keep.add(k)
        print(f"  {k}: {n} practice questions; on silent ones practice {f}, untouched {fu}")
    pol = lambda i: base(i) if base(i) is not None else (O[i][1] if O[i][0] in keep else None)
    print(f"T24 kept {sorted(keep)}; policy practice {fit(PR, pol)}, untouched {fit(UN, pol)} (T22c +309, base here {fit(UN, base)})")
if __name__ == "__main__":
    main()
