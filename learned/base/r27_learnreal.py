"""R27 P4: learn inflection and answer order from practice question / story-sentence pairs. Run: py -3.12 r27_learnreal.py"""
import os, sys, re, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r24_dict as Dct
main = [(s["text"], q, g) for s in json.load(open("val_all13.json", encoding="utf-8"))["stories"] for q, g in s["qs"]]
PR = list(range(310)) + list(range(510, 910)); pairs = [main[i] for i in PR]
pairs += [(s["text"], q, g) for s in json.load(open("r26_extra_practice.json", encoding="utf-8"))["stories"] for q, g in s["qs"]]
TOK = re.compile(r"[A-Za-z']+")
past = collections.defaultdict(collections.Counter); order = collections.defaultdict(collections.Counter); used = 0
for text, q, g in pairs:
    qw = TOK.findall(q); 
    if len(qw) < 3 or qw[1].lower() not in ("did", "does", "do"): continue
    gold = g[0].lower(); sent = next((s for s in re.split(r"(?<=[.!?])\s+", text) if gold in s.lower()), None)
    if not sent: continue
    st = TOK.findall(sent); sl = [w.lower() for w in st]
    body = [w.lower() for w in qw[2:]]
    for i, w in enumerate(body):
        b = Dct.verb_base(w)
        if not b or i == 0: continue
        hit = next((k for k, x in enumerate(sl) if x != w and Dct.verb_base(x) == b), None)
        if hit is None: continue
        if qw[1].lower() == "did": past[b][sl[hit]] += 1
        after = [x for x in body[i + 1:] if len(x) > 2]
        pg = " ".join(sl).find(gold); pv = len(" ".join(sl[:hit + 1]))
        pa = min([len(" ".join(sl[:k])) for k, x in enumerate(sl) if x in after and k > hit] or [None]) if after else None
        PREPS = ("to","at","in","on","from","with","for","into","by","near","under","behind","after","before","over","onto","about")
        if pg >= pv and pa is not None: order[(qw[0].lower(), qw[1].lower(), "prep" if body[i + 1:] and body[i + 1] in PREPS else "noun")]["answer-first" if pg < pa else "rest-first"] += 1
        used += 1; break
P = {b: c.most_common(1)[0][0] for b, c in past.items()}
O = {" ".join(k): c.most_common(1)[0][0] for k, c in order.items() if sum(c.values()) >= 5}
json.dump(dict(past=P, order=O, order_counts={" ".join(k): dict(c) for k, c in order.items()}), open("r27_learned_real.json", "w", encoding="utf-8"), indent=1)
print(f"P4 learned from {used} pairs: {len(P)} past forms (e.g. {list(P.items())[:8]}); order by shape: {O}; counts {dict((' '.join(k), dict(c)) for k, c in order.items())}")
