"""AG3 stage 3b: a symbolic question answerer over the AG1 translator's events (who / what / where / whom), run on the
original and on the canonical text of the same stories, so the only difference is the text. A question is read by a
few shapes into (verb lemma, known role filler, asked role); the answer is the asked role of the first event with the
same verb lemma whose known role matches (name match on first token, any content word for things). Silent otherwise.
Run: py -3.12 ag3_qa.py"""
import os, sys, re, json, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
import torch
ARGV = list(sys.argv); sys.argv = [sys.argv[0]]
import ag1_translator as A
from ag3_canon import STORIES, PRACTICE, UNTOUCHED, ent, STOP
from b6_rwkv import hit
AUX = r"(?:did|does|do|had|has|was|were|is|are)"
CANON = ARGV[ARGV.index("--canon") + 1] if "--canon" in ARGV else "ag3_canon.json"     # AG4: --canon ag4_canon.json --all --copular
COPULAR = "--copular" in ARGV
if "--all" in ARGV:                                                                     # question index ranges of R25: practice 0-309, 510-909
    _S = json.load(open(os.path.join(HERE, "val_all13.json"), encoding="utf-8"))["stories"]; _c = 0; PRACTICE = set(); UNTOUCHED = set()
    for _k, _s in enumerate(_S):
        (PRACTICE if (_c < 310 or 510 <= _c < 910) else UNTOUCHED).add(_k); _c += len(_s["qs"])
    STORIES = list(range(len(_S)))


V2 = "--v2" in ARGV
import r24_dict as D
def is_verb(w):
    return w not in STOP and (A.lemma(w) != w or (D.mainly_verb(w) if D.verb_base(w) else False))


def parse_q2(q):
    """AG8: the question verb is the first verb-like word after the wh-word and auxiliary; the subject is what precedes it"""
    ql = q.strip().rstrip("?").lower(); w = ql.split()
    if not w or w[0] not in ("who", "what", "where"): return None
    aux = len(w) > 1 and re.fullmatch(AUX, w[1]) is not None
    start = 2 if aux else 1; vi = next((i for i in range(start, len(w)) if is_verb(w[i])), None)
    if vi is None: return None
    subj = " ".join(w[start:vi]); rest = " ".join(w[vi + 1:]); verb = w[vi]
    if w[0] == "where": return (verb, "agent", subj, "place") if subj else None
    if subj: return verb, "agent", subj, "patient"                                      # who / what did X V?  -> patient
    return verb, "patient", rest, "agent"                                               # who / what V Y?  -> agent


def parse_q(q):
    """-> (verb word, known role, known filler, asked role) or None"""
    if V2:
        p = parse_q2(q)
        if p: return p
    ql = q.strip().rstrip("?").lower()
    m = re.match(rf"who {AUX} (.+?) (\w+)(?: (.*))?$", ql)                       # who did X V (Y)?  -> patient
    if m and m.group(2) not in STOP: return m.group(2), "agent", m.group(1), "patient"
    m = re.match(r"who (\w+)(?: (.*))?$", ql)                                      # who V (Y)?  -> agent
    if m and m.group(1) not in STOP: return m.group(1), "patient", m.group(2) or "", "agent"
    m = re.match(rf"what {AUX} (.+?) (\w+)(?: (.*))?$", ql)                      # what did X V?  -> patient
    if m and m.group(2) not in STOP: return m.group(2), "agent", m.group(1), "patient"
    m = re.match(r"what (\w+)(?: (.*))?$", ql)                                     # what V Y?  -> agent
    if m and m.group(1) not in STOP: return m.group(1), "patient", m.group(2) or "", "agent"
    m = re.match(rf"where {AUX} (.+?) (\w+)(?: (.*))?$", ql)                     # where did X V (Y)?  -> place
    if m and m.group(2) not in STOP: return m.group(2), "agent", m.group(1), "place"
    if COPULAR:
        m = re.match(r"(?:what|where|who) (?:was|were|is|are) (.+)$", ql)         # what / where was X?  -> copular patient
        if m: return "be", "agent", m.group(1), "patient"
    return None


def match(filler, span):
    if not filler: return True
    f = ent(filler).split(); s = ent(span).split()
    if not f or not s: return False
    return bool(set(f) & set(s) - STOP) or f[-1] == s[-1]


SIM = float(ARGV[ARGV.index("--sim") + 1]) if "--sim" in ARGV else None
if SIM is not None:
    import numpy as np
    _z = np.load(os.path.join(HERE, "r25_vectors.npz"), allow_pickle=True); _V = _z["vecs"] / (np.linalg.norm(_z["vecs"], axis=1, keepdims=True) + 1e-9)
    _W = {w: i for i, w in enumerate(_z["vocab"].tolist())}
    def vsim(a, b):
        if a == b: return 1.0
        if a not in _W or b not in _W: return 0.0
        return float(_V[_W[a]] @ _V[_W[b]])
else:
    def vsim(a, b): return 1.0 if a == b else 0.0


def answer(events, q):
    p = parse_q(q)
    if not p: return None
    verb, krole, kfill, arole = p; lem = A.lemma(verb)
    if SIM is not None and not any(e["verb"] == lem for e in events):            # AG7: nearest event verb by learned vectors
        best = max(((vsim(lem, e["verb"]), e["verb"]) for e in events), default=(0, None))
        if best[0] >= SIM: lem = best[1]
    for e in events:
        if e["verb"] != lem: continue
        if krole == "patient" and kfill and not match(kfill, e.get("patient") or "") and not match(kfill, e.get("place") or ""): continue
        if krole == "agent" and not match(kfill, e.get("agent") or ""): continue
        a = e.get(arole)
        if a and ent(a) and ent(a) not in ("it", "them", "him", "her", "he", "she", "they"): return a
    return None


def main():
    data = [s for s in json.load(open("stories_train_v2.json", encoding="utf-8")) if s.get("events")]
    random.Random(0).shuffle(data); F = A.Feats([tk for st in data[:2240] for tk, _ in A.gold_examples(st)])
    vm = A.Tagger(F, 2, False); am = A.Tagger(F, len(A.ATAGS), True); sd = torch.load("ag1_translator.pt"); vm.load_state_dict(sd["vm"]); am.load_state_dict(sd["am"]); vm.eval(); am.eval()
    T = A.Translator(F, vm, am)
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; C = json.load(open(CANON, encoding="utf-8"))
    if COPULAR:
        from ag4_canon import events_of; reader = lambda sent: events_of(T, sent)
    else: reader = T.read
    res = collections.defaultdict(lambda: [0, 0, 0]); rows = []
    for k in STORIES:
        s = S[k]
        if s["id"] not in C: continue
        evs = {}
        for tname, text in (("original", s["text"]), ("canonical", C[s["id"]]["canon"])):
            evs[tname] = [e for sent in [x.strip() for x in A.SENT.split(text) if x.strip()] for e in reader(sent)]
            if V2:                                                                        # AG8: he / she / they -> the last named agent
                last = None
                for e in evs[tname]:
                    a = (e.get("agent") or "").strip()
                    if a.lower() in ("he", "she", "they"):
                        if last: e["agent"] = last
                    elif a and a[0].isupper(): last = a
        for q, g in s["qs"]:
            row = dict(id=s["id"], q=q, gold=g)
            for tname in ("original", "canonical"):
                a = answer(evs[tname], q); row[tname] = a
                cell = res[(tname, "practice" if k in PRACTICE else "untouched")]
                if a is None: cell[2] += 1
                elif hit(a, g): cell[0] += 1
                else: cell[1] += 1
            rows.append(row)
    json.dump(rows, open("ag3_qa_rows.json", "w", encoding="utf-8"), indent=1)
    for key in sorted(res):
        r, w, sil = res[key]; print(f"AG3-QA {key[0]:9s} text, {key[1]:9s}: {r} right / {w} wrong / {sil} silent / fitness {r - 3 * w} / precision {r / max(1, r + w):.2f}")
    ch = [x for x in rows if (x["original"] is None) != (x["canonical"] is None) or (x["original"] and x["canonical"] and hit(x["original"], x["gold"]) != hit(x["canonical"], x["gold"]))]
    print(f"AG3-QA questions whose outcome changed: {len(ch)}")
    for x in ch[:14]: print("  ", x["q"], "| gold", x["gold"][0], "| original", x["original"], "| canonical", x["canonical"])


if __name__ == "__main__":
    main()
