import os, sys, json, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R, r24_qreader as QR
data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
import r24_books as B, data as D
train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
why = collections.Counter(); shown = 0
for s in data[:7000]:
    if not s.get("events"): continue
    stmts = [R.event_statement(e) for e in s["events"]]
    for q, g in s["qs"]:
        if not q.lower().startswith("what did"): continue
        qs, qf = QR.qshape(q, names); qslots = {f.lower() for x, f in zip(qs, qf) if x in ("PERSON", "ENT")}; qv = next((x for x in qs if x.startswith("V:")), None)
        ok = None
        for st in stmts:
            cs, cf = R.construction(st, names); fl = {f.lower() for f in cf if f}
            if qv is None: ok = ok or "no verb in question"; continue
            if qv not in cs: ok = ok or "verb not in statement"; continue
            gold = next((f for f in cf if f and (f.lower() == g[0].lower() or f.lower() == T.key_of("ENT", g[0].lower().split()) or g[0].lower() in f.lower())), None)
            if not gold: ok = "gold not a filler"; continue
            if not (qslots & fl or not qslots): ok = "slots disjoint"; continue
            ok = "PAIRED"; break
        why[ok] += 1
        if ok != "PAIRED" and shown < 12: shown += 1; print(ok, "|", q, g, "|", qs, qf, "|", [(R.construction(st, names)) for st in stmts][:2])
print(why)
