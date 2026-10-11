"""R25: the learner revises its own store from its own score (R25_prereg.md).
The learned readers are trained once; the persistent store (r25_store.json) is loaded, never rebuilt. The learner answers
its practice questions, collects its own failures, proposes revisions from them with general operators, tests each
revision on the practice questions it touches, and keeps it only if its own score rises. The store is saved for the
next run. The score is the learned readers alone: +1 right, -3 wrong, 0 silent (the model is the fallback, so a wrong
answer costs more than a silent one). Practice: the old 110 validation questions + fresh m1-m20. Holdout (aggregate
only, never used to choose): fresh m21-m40. B6 is not touched here.
Operators: SHAPE-ALIAS (a question shape with no template is read as a learned shape one edit away);
VERB-ALIAS (a question verb absent from the story is read as a verb the story has, kept across stories only if it pays).
Run: python learned/base/r25_self.py [--rounds N]"""
import os, sys, json, random, collections, time
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R
import r24_books as B, data as D0, r24_dict as D
import r24_qreader as QR
from b6_rwkv import hit

QR.ARGV = ["x", "--pron-ref", "--reinterp"]
STORE_F = os.path.join(HERE, "r25_store.json")
OK_LEVELS = ("exact", "noword", "exact-r", "noword-r", "alias")


def edit1(a, b):
    """True when tuple b is one insertion, deletion or substitution away from tuple a"""
    if a == b or abs(len(a) - len(b)) > 1: return False
    if len(a) == len(b): return sum(x != y for x, y in zip(a, b)) == 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def main():
    t0 = time.time(); rounds = int(ARGV[ARGV.index("--rounds") + 1]) if "--rounds" in ARGV else 4
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
    train_b, _ = D0.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    E.HOLD_RULES.update(json.load(open("r24_hold_results.json"))["rules"])
    D.ON = True; T.SPAN_STOP.update(D.verb_forms() - E.NOUNISH)
    train, QRD = R.closed_loop_train(data, names)
    seqs = [list(R.construction(x, names)[0]) for s in data[:7000] for x in T.SENT.split(s["text"]) if x.strip()]
    CH = R.Chunks(seqs); n6 = int(len(train) * 6 / 7); rd = R.Reader(CH); rd.learn(train[:n6], names, weigh=False); rd.learn(train[n6:], names, weigh=True)
    tabs = (rd.w, rd.wn, rd.eqw, rd.eqn); rd = R.Reader(CH); rd.w, rd.wn, rd.eqw, rd.eqn = tabs; rd.learn(train, names, weigh=False)
    print(f"R25 readers trained ({time.time() - t0:.0f} s)", flush=True)

    store = json.load(open(STORE_F, encoding="utf-8")) if os.path.exists(STORE_F) else {"shape_alias": {}, "verb_alias": {}, "history": []}
    QR.STORE.clear(); QR.STORE.update(store)
    print("R25 store loaded:", {k: len(v) for k, v in store.items()}, flush=True)

    old = json.load(open("val_stories.json", encoding="utf-8"))["stories"] + json.load(open("val_fables.json", encoding="utf-8"))["stories"] + json.load(open("val_timespace.json", encoding="utf-8"))["stories"]
    more = json.load(open("val_more.json", encoding="utf-8"))["stories"]
    practice = [(s["text"], q, g) for s in old + more[:20] for q, g in s["qs"]]
    holdout = [(s["text"], q, g) for s in more[20:] for q, g in s["qs"]]

    def one(text, q, g):
        a = QR.ask_learned(QRD, rd, text, names, q)
        if a is None or QR.LASTQ.get("level") not in OK_LEVELS: return 0
        return 1 if hit(a, g) else -3
    def score(items): return [one(*x) for x in items]
    def summary(sc): return dict(right=sum(1 for x in sc if x == 1), wrong=sum(1 for x in sc if x == -3), fitness=sum(sc))

    QR.STORE.clear(); hold_empty = summary(score(holdout)); QR.STORE.update(store)        # the learner with no store at all: the reference for the gate
    base = score(practice)
    if "--prune" in ARGV:                                                                # R25-b: the learner re-judges its own earlier revisions by the transfer rule
        nw0 = lambda q: repr(tuple(x for x in QR.abstract_q(QR.qshape(q, names)[0]) if x != "w"))
        for key in ("shape_alias", "verb_alias"):
            for a in list(store[key]):
                b = store[key].pop(a); QR.STORE.clear(); QR.STORE.update(store)
                without = score(practice)
                better = {practice[i][0] for i in range(len(practice)) if base[i] > without[i]}; worse = [i for i in range(len(practice)) if base[i] < without[i]]
                if sum(base) - sum(without) > 0 and len(better) >= 2 and not worse: store[key][a] = b
                else: store["history"].append(dict(op="prune", kind=key, src=a, dst=b, gain=sum(base) - sum(without), stories=len(better))); print(f"  pruned {key}: {a} -> {b} (gain {sum(base) - sum(without)}, stories {len(better)})", flush=True); base = without
                QR.STORE.clear(); QR.STORE.update(store)
        json.dump(store, open(STORE_F, "w", encoding="utf-8"), indent=1)
        print(f"R25 after pruning: practice {summary(base)} | store {dict((k, len(v)) for k, v in store.items())}", flush=True)
    hold0 = summary(score(holdout))
    print(f"R25 start: practice {summary(base)} | holdout {hold0}", flush=True)
    nw = lambda q: tuple(x for x in QR.abstract_q(QR.qshape(q, names)[0]) if x != "w")
    targets = {k[1] for k in QRD.map if k[0] == "noword"}

    for rnd in range(rounds):
        accepted = 0
        # failures: questions the learned readers do not answer right
        fails = [i for i, sc in enumerate(base) if sc != 1]
        shapes = [repr(nw(q)) for _, q, _ in practice]; qverbs = []
        for _, q, _ in practice:
            got = QRD.render(q, names); qverbs.append({x[2:] for x in got[0] if x.startswith("V:")} if got else set())
        # SHAPE-ALIAS candidates from unrendered failures
        cand = collections.Counter()
        for i in fails:
            text, q, g = practice[i]
            if QR.QReader.render(QRD, q, names) is not None: continue
            src = nw(q)
            if repr(src) in store["shape_alias"]: continue
            for t in targets:
                if t and src and t[0] == src[0] and edit1(src, t): cand[("shape", repr(src), repr(t))] += 1
        # VERB-ALIAS candidates from rendered-but-silent failures
        for i in fails:
            text, q, g = practice[i]
            got = QR.QReader.render(QRD, q, names)
            if not got: continue
            qv = [x[2:] for x in got[0] if x.startswith("V:")]
            sv = {y[2:] for x in T.SENT.split(text) if x.strip() for y in R.construction(x, names)[0] if y.startswith("V:")}
            for v in qv:
                if v in sv or v in store["verb_alias"]: continue
                for u in sv: cand[("verb", v, u)] += 1
        print(f"R25 round {rnd + 1}: {len(fails)} failures, {len(cand)} candidate revisions", flush=True)
        for (kind, a, b), n in cand.most_common():
            key = "shape_alias" if kind == "shape" else "verb_alias"
            if a in store[key]: continue
            store[key][a] = b; QR.STORE.clear(); QR.STORE.update(store)
            touched = [i for i in range(len(practice)) if (shapes[i] == a if kind == "shape" else a in qverbs[i])]
            new = list(base)
            for i in touched: new[i] = one(*practice[i])
            delta = sum(new) - sum(base)
            better = {practice[i][0] for i in touched if new[i] > base[i]}; worse = [i for i in touched if new[i] < base[i]]
            if delta > 0 and len(better) >= 2 and not worse:                              # R25-b: it must transfer -- help questions in two or more stories, break none
                base = new; accepted += 1; store["history"].append(dict(round=len(store["history"]), op=kind, src=a, dst=b, delta=delta))
                print(f"  kept {kind}: {a} -> {b} (practice +{delta})", flush=True)
            else:
                del store[key][a]; QR.STORE.clear(); QR.STORE.update(store)
        print(f"R25 round {rnd + 1}: kept {accepted}; practice {summary(base)} ({time.time() - t0:.0f} s)", flush=True)
        json.dump(store, open(STORE_F, "w", encoding="utf-8"), indent=1)
        if not accepted: break
    hold1 = summary(score(holdout))
    print(f"R25 end: practice {summary(base)} | holdout empty store {hold_empty} | start of run {hold0} -> end {hold1} | store {dict((k, len(v)) for k, v in store.items())}", flush=True)
    json.dump(dict(practice=summary(base), holdout_empty=hold_empty, holdout_before=hold0, holdout_after=hold1), open("r25_results.json", "w"))


if __name__ == "__main__":
    main()
