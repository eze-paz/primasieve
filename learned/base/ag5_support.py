"""AG5 (AG_prereg.md): accept the model's reply only when the text supports it; original sentences vs canonical clauses.
Run: py -3.12 ag5_support.py [--canon ag4_canon.json] [--all]"""
import os, sys, re, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
ARGV = list(sys.argv); sys.argv = [sys.argv[0]]
from b6_rwkv import hit
from ag3_canon import STOP, ent
import ag1_translator as A
CANON = ARGV[ARGV.index("--canon") + 1] if "--canon" in ARGV else "ag4_canon.json"
S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; C = json.load(open(CANON, encoding="utf-8"))
M = json.load(open("b2_conf_answers.json", encoding="utf-8")); P = json.load(open("r26_policy_answers.json", encoding="utf-8"))
AUXV = {"be", "do", "have", "did", "does", "was", "were", "is", "are", "had", "has"}
qidx = []; c = 0
for k, s in enumerate(S):
    for _ in s["qs"]: qidx.append(k)
PRq = set(range(0, 310)) | set(range(510, 910)); UNq = set(range(310, 510)) | set(range(910, 2510))
DEV = set(range(22, 102)) if "--all" not in ARGV else set(range(502))


def content(s): return [t.lower() for t in A.toks(s) if t[0].isalpha() and t.lower() not in STOP]


def qverb(q):
    ql = q.lower().rstrip("?")
    m = re.match(r"(?:who|what|where|when|why|how|whose|which \w+) (?:did|does|do|had|has|was|were|is|are)? ?(.+)$", ql)
    rest = m.group(1) if m else ql
    for w in rest.split():
        lem = A.lemma(w)
        if w not in STOP and lem not in AUXV and (lem != w or w.endswith("ed") or w.endswith("s")): return lem
    return None


def supported(reply, q, units):
    cw = content(reply)
    if not cw: return False
    text = " ".join(units).lower(); textw = set(content(text))
    if any(w not in textw and A.lemma(w) not in textw for w in cw): return False
    head = cw[-1]; v = qverb(q); qw = [w for w in content(q) if A.lemma(w) not in AUXV]
    for u in units:
        ul = content(u); ull = {A.lemma(w) for w in ul}
        if head in ul or A.lemma(head) in ull:
            if v and v in ull: return True
            if not v and any(w in ul for w in qw): return True
    return False


def run(label, f):
    r = collections.defaultdict(lambda: [0, 0])
    for i in range(len(M)):
        k = qidx[i]
        if k not in DEV: continue
        a = f(i)
        if a is None: continue
        r["practice" if i in PRq else "untouched"][0 if hit(a, M[i]["gold"]) else 1] += 1
    out = {}
    for set_ in ("practice", "untouched"):
        rr, ww = r[set_]; out[set_] = (rr - 3 * ww, rr, ww)
    print(f"AG5 {label:48s} practice {out['practice']}  untouched {out['untouched']}")
    return out


def reply(i, t=None):
    it = M[i]; x = it["reply"].strip()
    if x.lower() in ("unknown", "") or (t is not None and it["min_lp"] < t): return None
    return x


def units_of(i, sub):
    s = S[qidx[i]]
    if sub == "original": return [x.strip() for x in A.SENT.split(s["text"]) if x.strip()]
    return [x.strip() for x in A.SENT.split(C[s["id"]]["canon"]) if x.strip()] if s["id"] in C else None


def main():
    run("model unthresholded", lambda i: reply(i))
    run("model thresholded (B2b)", lambda i: reply(i, -0.11))
    for sub in ("original", "canonical"):
        run(f"unthresholded + support on {sub}", lambda i: reply(i) if units_of(i, sub) and supported(reply(i) or "", M[i]["q"], units_of(i, sub)) else None)
        run(f"thresholded + support on {sub}", lambda i: reply(i, -0.11) if units_of(i, sub) and supported(reply(i, -0.11) or "", M[i]["q"], units_of(i, sub)) else None)
    run("policy T22p alone", lambda i: P[i])
    run("policy, then thresholded model", lambda i: P[i] if P[i] is not None else reply(i, -0.11))
    for sub in ("original", "canonical"):
        run(f"policy, then thresholded + support on {sub}", lambda i: P[i] if P[i] is not None else (reply(i, -0.11) if units_of(i, sub) and supported(reply(i, -0.11) or "", M[i]["q"], units_of(i, sub)) else None))


if __name__ == "__main__":
    main()
