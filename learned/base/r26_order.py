"""R26 T25: ORDER operator -- an anchor sentence plus statement match restricted to one side of it. Run: py -3.12 r26_order.py"""
import os, sys, re, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r26_stmatch as SM, r26_ops as OPS
def sents(text): return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
def order(text, q):
    ql = q.strip().rstrip("?")
    S = sents(text)
    m = re.match(r"(.+?) (after|before) (.+)$", ql, re.I)
    if m:
        main, rel, anc = m.group(1), m.group(2).lower(), m.group(3)
        aw = [w for w in SM.TOK.findall(anc) if w[0].isalnum()]
        _, k = OPS.content_sentence(text, aw)
        if k is None: return None
        rng = range(k + 1, len(S)) if rel == "after" else range(k - 1, -1, -1)
    else:
        m = re.match(r"(.+?),? (first|at first|last|at the end|in the end|finally)$", ql, re.I)
        if not m: return None
        main, rel = m.group(1), m.group(2).lower()
        rng = range(len(S)) if "first" in rel else range(len(S) - 1, -1, -1)
    for j in rng:
        a = SM.answer(S[j], main + "?")
        if a: return a
    return None
if __name__ == "__main__":
    st = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    A = [order(s["text"], q) for s in st for q, g in s["qs"]]
    json.dump(A, open("r26_order_answers.json", "w", encoding="utf-8")); print("order answers:", sum(a is not None for a in A))
