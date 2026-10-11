"""R25-h: a similarity-native reader built on the learner's own word vectors (R25_prereg.md).
For a question, every name / thing span in the story is a candidate. A candidate's score has two learned parts:
  match -- how well the words of its sentence cover the question's content words in the learner's vector space
           (for each question word, the best cosine to a sentence word), averaged over question words;
  type  -- how much the candidate's head word resembles the answers that kind of question gets, as a prototype
           vector averaged from the generator's gold answers for that question kind (who / what / where / when).
total = match + LAM * type. The reader answers only when the best candidate beats the second by at least MARGIN.
LAM and MARGIN are chosen by the learner itself on its practice questions (+1 right, -3 wrong, 0 silent);
the holdout (fresh m21-m40) is reported only. Run: python learned/base/r25_soft.py"""
import os, sys, json, random, collections, time
import numpy as np
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R
import r24_books as B, data as D0, r24_dict as D
import r24_qreader as QR
from b6_rwkv import hit

QW = {"who", "what", "where", "when", "why", "how", "which", "whose", "whom", "did", "does", "do", "was", "were", "is", "are", "had", "has"}
Z = np.load(os.path.join(HERE, "r25_vectors.npz")); VEC = {w: v for w, v in zip(Z["vocab"].tolist(), Z["vecs"])}


def vec(w):
    w = w.lower()
    return VEC.get(w) if w in VEC else VEC.get(E.lemma(w))


def head(span): ws = [x for x in T.TOK.findall(span) if x.isalpha()]; return ws[-1] if ws else None


def candidates(text, names):
    out = []
    for si, sent in enumerate(x for x in T.SENT.split(text) if x.strip()):
        cs, cf = R.construction(sent, names); raws = list(R.LAST_RAWS)
        words = [x for x in T.TOK.findall(sent) if x.isalpha()]
        for k, (sym, f) in enumerate(zip(cs, cf)):
            if sym in ("PERSON", "ENT") and f:
                span = raws[k] if k < len(raws) and raws[k] else f
                out.append(dict(span=span, sent=si, words=[w for w in words if w.lower() not in {x.lower() for x in span.split()}]))
    return out


def features(text, q, names, protos):
    qws = [w for w in T.TOK.findall(q) if w.isalpha() and w.lower() not in QW and w.lower() not in T.STOP]
    qv = [v for v in (vec(w) for w in qws) if v is not None]
    kind = q.lower().split()[0]; proto = protos.get(kind)
    qslots = {w.lower() for w in qws}
    rows = []
    for c in candidates(text, names):
        if {x.lower() for x in c["span"].split()} & qslots and len(c["span"].split()) <= 2 and c["span"].split()[-1].lower() in qslots: continue   # the question already names it
        sv = [v for v in (vec(w) for w in c["words"]) if v is not None]
        match = float(np.mean([max(0.0, max(float(np.dot(a, b)) for b in sv)) for a in qv])) if (qv and sv) else 0.0
        h = head(c["span"]); hv = vec(h) if h else None
        typ = float(np.dot(hv, proto)) if (hv is not None and proto is not None) else (0.3 if (h and h[:1].isupper()) else 0.0)
        rows.append((c["span"], match, typ))
    return rows


def protos_from(stories):
    """the type prototypes: mean vector of the head words of gold answers, per question kind"""
    acc = collections.defaultdict(list)
    for s in stories:
        for q, g in s["qs"]:
            h = head(g[0]); v = vec(h) if h else None
            if v is not None: acc[q.lower().split()[0]].append(v)
    return {k: (np.mean(v, 0) / (np.linalg.norm(np.mean(v, 0)) + 1e-9)) for k, v in acc.items() if len(v) >= 50}


def top(text, q, names, protos, lam=0.5):
    """the best candidate and its lead over the second, or (None, 0)"""
    rows = features(text, q, names, protos)
    if not rows: return None, 0.0
    sc = sorted(((m + lam * t, s) for s, m, t in rows), reverse=True)
    return sc[0][1], (sc[0][0] - sc[1][0]) if len(sc) > 1 else 1.0


def decide(rows, lam, margin):
    if not rows: return None
    sc = sorted(((m + lam * t, s) for s, m, t in rows), reverse=True)
    if len(sc) > 1 and sc[0][0] - sc[1][0] < margin: return None
    return sc[0][1]


def main():
    t0 = time.time()
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
    train_b, _ = D0.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    D.ON = True; T.SPAN_STOP.update(D.verb_forms() - E.NOUNISH)
    acc = collections.defaultdict(list)                                                    # the type prototypes: learned from the generator's gold answers
    for s in data[:7000]:
        for q, g in s["qs"]:
            h = head(g[0]); v = vec(h) if h else None
            if v is not None: acc[q.lower().split()[0]].append(v)
    protos = {k: (np.mean(v, 0) / (np.linalg.norm(np.mean(v, 0)) + 1e-9)) for k, v in acc.items() if len(v) >= 50}
    print(f"R25-h type prototypes learned for {sorted(protos)} ({time.time() - t0:.0f} s)", flush=True)
    old = json.load(open("val_stories.json", encoding="utf-8"))["stories"] + json.load(open("val_fables.json", encoding="utf-8"))["stories"] + json.load(open("val_timespace.json", encoding="utf-8"))["stories"]
    more = json.load(open("val_more.json", encoding="utf-8"))["stories"]
    practice = [(s["text"], q, g) for s in old + more[:20] for q, g in s["qs"] if q.lower().split()[0] in ("who", "what", "where", "when", "whom")]
    holdout = [(s["text"], q, g) for s in more[20:] for q, g in s["qs"] if q.lower().split()[0] in ("who", "what", "where", "when", "whom")]
    fp = [features(t, q, names, protos) for t, q, g in practice]; fh = [features(t, q, names, protos) for t, q, g in holdout]
    def fitness(F, items, lam, margin):
        r = w = 0
        for rows, (t, q, g) in zip(F, items):
            a = decide(rows, lam, margin)
            if a is None: continue
            if hit(a, g): r += 1
            else: w += 1
        return r - 3 * w, r, w
    grid = [(lam, m) for lam in (0.0, 0.5, 1.0, 2.0) for m in (0.0, 0.05, 0.1, 0.2, 0.3)]
    res = {k: fitness(fp, practice, *k) for k in grid}
    for k in grid: print(f"  LAM {k[0]} MARGIN {k[1]}: practice fitness {res[k][0]} (right {res[k][1]}, wrong {res[k][2]})", flush=True)
    best = max(grid, key=lambda k: res[k][0])
    hb = fitness(fh, holdout, *best)
    print(f"R25-h the learner chose LAM {best[0]} MARGIN {best[1]}: practice {res[best]} | holdout fitness {hb[0]} (right {hb[1]}, wrong {hb[2]}) over {len(holdout)} questions | practice questions {len(practice)}", flush=True)
    json.dump(dict(lam=best[0], margin=best[1], practice=res[best], holdout=hb), open("r25_soft_results.json", "w"))


if __name__ == "__main__":
    main()
