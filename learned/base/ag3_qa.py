"""AG3 stage 3b: a symbolic question answerer over the AG1 translator's events (who / what / where / whom), run on the
original and on the canonical text of the same stories, so the only difference is the text. A question is read by a
few shapes into (verb lemma, known role filler, asked role); the answer is the asked role of the first event with the
same verb lemma whose known role matches (name match on first token, any content word for things). Silent otherwise.
Run: py -3.12 ag3_qa.py"""
import os, sys, re, json, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
import torch
sys.argv = [sys.argv[0]]
import ag1_translator as A
from ag3_canon import STORIES, PRACTICE, UNTOUCHED, ent, STOP
from b6_rwkv import hit
AUX = r"(?:did|does|do|had|has|was|were|is|are)"


def parse_q(q):
    """-> (verb word, known role, known filler, asked role) or None"""
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
    return None


def match(filler, span):
    if not filler: return True
    f = ent(filler).split(); s = ent(span).split()
    if not f or not s: return False
    return bool(set(f) & set(s) - STOP) or f[-1] == s[-1]


def answer(events, q):
    p = parse_q(q)
    if not p: return None
    verb, krole, kfill, arole = p; lem = A.lemma(verb)
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
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; C = json.load(open("ag3_canon.json", encoding="utf-8"))
    res = collections.defaultdict(lambda: [0, 0, 0]); rows = []
    for k in STORIES:
        s = S[k]
        if s["id"] not in C: continue
        evs = {}
        for tname, text in (("original", s["text"]), ("canonical", C[s["id"]]["canon"])):
            evs[tname] = [e for sent in [x.strip() for x in A.SENT.split(text) if x.strip()] for e in T.read(sent)]
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
