"""R24 probe: why the learned readers are silent on plain 'What did X V?' validation questions (development on validation only)."""
import os, sys, json, random
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R, r24_qreader as QR
QR.ARGV = ARGV
data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
import r24_books as B, data as D
train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
train, QRD = R.closed_loop_train(data, names)
seqs = [list(R.construction(x, names)[0]) for s in data[:7000] for x in T.SENT.split(s["text"]) if x.strip()]
CH = R.Chunks(seqs); n6 = int(len(train) * 6 / 7); rd = R.Reader(CH); rd.learn(train[:n6], names, weigh=False); rd.learn(train[n6:], names, weigh=True)
tabs = (rd.w, rd.wn, rd.eqw, rd.eqn); rd = R.Reader(CH); rd.w, rd.wn, rd.eqw, rd.eqn = tabs; rd.learn(train, names, weigh=False)
stories = json.load(open("val_stories.json", encoding="utf-8"))["stories"] + json.load(open("val_fables.json", encoding="utf-8"))["stories"] + json.load(open("val_timespace.json", encoding="utf-8"))["stories"]
PICK = tuple(x.strip() for x in open(ARGV[1], encoding="utf-8")) if len(ARGV) > 1 else ("What did Ilse grow?", "What did Greta grow?", "What did Sven use?", "What did she teach?", "What did the ferryman charge?", "What did Pavel sew it with?", "What did the mayor have marked?", "What did the mouse gnaw through?", "Who sewed the sail?", "Where did the lamb stand?", "What was the bridge made of?", "Whose ring was it?")
for s in stories:
    for q, g in s["qs"]:
        if q not in PICK: continue
        print("=" * 100); print("Q:", q, "| gold", g); print("qshape:", QR.qshape(q, names)); print("keys:", [k for k in QR.keys_of(QR.qshape(q, names)[0]) if k in QRD.map])
        got = QRD.render(q, names); print("render:", got, "| level", QR.LASTQ.get("level"))
        if got: print("template:", QRD.map[next(k for k in QR.keys_of(QR.qshape(q, names)[0]) if k in QRD.map)].most_common(3))
        for x in T.SENT.split(s["text"]):
            if x.strip(): print("  sent:", x.strip()[:120]); print("    cons:", R.construction(x, names))
        print("learned answer:", QR.ask_learned(QRD, rd, s["text"], names, q), "| LAST", dict(R.LAST))
        print("cue answer:", E.ask_conf(E.Log(names).read(s["text"]), q))
