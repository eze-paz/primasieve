"""R26 T34: 'What did X do ...?' answered by X's predicate in the one matching sentence. Run: py -3.12 r26_do.py"""
import os, sys, re, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r26_stmatch as SM, r24_dict as Dct
def sents(text): return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
def do_op(text, q):
    m = re.match(r"what (?:did|does|do|will|would) (?:the |a |an )?([\w']+(?: [\w']+)?) do\b(.*)$", q.strip().rstrip("?"), re.I)
    if not m: return None
    x = m.group(1).split()[-1].lower(); rest = [w for w in SM.TOK.findall(m.group(2)) if w[0].isalnum() and w.lower() not in SM.STOP]
    S = sents(text); hits = []; last_named = None
    for s in S:
        toks = SM.TOK.findall(s); low = [t.lower() for t in toks]; nt = [SM.norm(t) for t in toks]
        for i in range(len(toks) - 1):
            subj = low[i] == x or (low[i] in ("he", "she", "they") and last_named == x)
            if subj and Dct.mainly_verb(low[i + 1]) and all(SM.norm(r) in nt for r in rest):
                pred = []
                for t in toks[i + 1:i + 9]:
                    if not t[0].isalnum() or (t.lower() in SM.CLAUSE_END and pred): break
                    pred.append(t)
                hits.append(" ".join(pred)); break
        for t in toks:
            if t[0].isupper() and t.lower() not in SM.STOP: last_named = t.lower()
    return hits[0] if len(hits) == 1 else None
if __name__ == "__main__":
    st = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    A = [do_op(s["text"], q) for s in st for q, g in s["qs"]]
    json.dump(A, open("r26_do_answers.json", "w", encoding="utf-8")); print("do answers:", sum(a is not None for a in A))
