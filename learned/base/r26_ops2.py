"""R26 T24c: WHY and HOW operators, version 2. Run: py -3.12 r26_ops2.py"""
import os, sys, re, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = [sys.argv[0], "--fix4"]
import r26_stmatch as SM
from b6_rwkv import hit
PRON = ("he", "she", "him", "her", "his", "they", "them", "their")
def matched(text, q):
    qw = [w for w in SM.TOK.findall(q) if w[0].isalnum()]; rest = qw[1:]
    if rest and rest[0].lower() in SM.AUX: rest = rest[1:]
    content = [SM.norm(w) for w in rest if w.lower() not in SM.STOP and w.lower() not in ("late", "long")]
    content = [c[:-2] if c.endswith("'s") else c for c in content]
    if not content: return None
    S = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]; hits = []; last = None
    for k, s in enumerate(S):
        toks = SM.TOK.findall(s); nt = [SM.norm(t) for t in toks]; nt = [x[:-2] if x.endswith("'s") else x for x in nt]
        if last: nt = [last if (x in PRON and last not in nt) else x for x in nt]
        if all(c in nt for c in content):
            vi = max(nt.index(c) for c in content); hits.append((k, toks, vi))
        for i, t in enumerate(toks):
            if t[0].isupper() and t.lower() not in SM.STOP and i > 0: last = SM.norm(t)
    if len(hits) != 1: return None
    k, toks, vi = hits[0]; return S, k, toks, vi
def clause(toks, i, n=10):
    out = []
    for t in toks[i:i + n]:
        if not t[0].isalnum() or (t.lower() in ("and", "but", "because", "when", "while") and out): break
        out.append(t)
    return " ".join(out) if out else None
def why(text, q):
    m = matched(text, q)
    if not m: return None
    S, k, toks, vi = m; low = [t.lower() for t in toks]
    if "because" in low: return clause(toks, low.index("because") + 1, 14)
    if k + 1 < len(S) and re.match(r"\s*because\b", S[k + 1], re.I): return clause(SM.TOK.findall(S[k + 1]), 1, 14)
    for i in range(len(low) - 1):
        if low[i] == "so" and low[i + 1] == "that": return clause(toks, i + 2, 12)
    if "so" in low and low.index("so") < vi:                                                    # 'X, so <event>' -> X
        j = low.index("so"); start = max([i + 1 for i in range(j) if not toks[i][0].isalnum() and i < j - 1] + [0])
        return clause(toks, start, j - start) if j > start else None
    for i in range(vi + 1, len(low)):
        if low[i] == "to" and i + 1 < len(low) and SM.Dct.mainly_verb(low[i + 1]): return clause(toks, i, 10)
        if low[i] == "for": return clause(toks, i, 6)
    return None
def how(text, q):
    ql = q.lower(); m = matched(text, q)
    if not m: return None
    S, k, toks, vi = m; low = [t.lower() for t in toks]
    if re.match(r"how (late|long|far|early)", ql):
        for i in range(len(low)):
            if (low[i] in SM.NUMW or low[i].isdigit()) and i + 1 < len(low) and low[i + 1] in ("minutes", "minute", "hours", "hour", "days", "day", "weeks", "years", "miles", "kilometres"):
                return " ".join(toks[max(0, i - 1):i + 3])
        return None
    for i in range(max(0, vi - 1), len(low)):
        if low[i] in ("by", "on", "through", "with") and i + 1 < len(low) and low[i + 1] not in SM.TIMEW: return clause(toks, i, 6)
        if low[i] in ("took", "take", "takes") and i + 1 < len(low) and low[i + 1] in ("a", "the", "an"): return clause(toks, i, 5)
    return None
def run(path):
    st = json.load(open(path, encoding="utf-8"))["stories"]; out = []
    for s in st:
        for q, g in s["qs"]:
            ql = q.lower()
            out.append(("WHY", why(s["text"], q)) if ql.startswith("why") else ("HOW", how(s["text"], q)) if ql.startswith("how") and not ql.startswith(("how many", "how much")) else (None, None))
    return out
if __name__ == "__main__":
    json.dump(run("val_all13.json"), open("r26_ops2_answers.json", "w", encoding="utf-8")); json.dump(run("r26_extra_practice.json"), open("r26_xp_ops2_answers.json", "w", encoding="utf-8"))
    xs = json.load(open("r26_extra_practice.json", encoding="utf-8"))["stories"]; xg = [g for s in xs for _, g in s["qs"]]; XO = json.load(open("r26_xp_ops2_answers.json", encoding="utf-8"))
    for kind in ("WHY", "HOW"):
        r = sum(1 for (k, a), g in zip(XO, xg) if k == kind and a and hit(a, g)); w = sum(1 for (k, a), g in zip(XO, xg) if k == kind and a and not hit(a, g))
        print(f"{kind} on extra practice: {r} right / {w} wrong")
