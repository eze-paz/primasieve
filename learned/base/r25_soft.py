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
ARGV = list(sys.argv); ARGV_SOFT = ARGV
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R
import r24_books as B, data as D0, r24_dict as D
import r24_qreader as QR
from b6_rwkv import hit

QW = {"who", "what", "where", "when", "why", "how", "which", "whose", "whom", "did", "does", "do", "was", "were", "is", "are", "had", "has"}
Z = np.load(os.path.join(HERE, os.environ.get("R25_VEC", "r25_vectors.npz"))); VEC = {w: v for w, v in zip(Z["vocab"].tolist(), Z["vecs"])}   # R25-ai: the vector file is chosen by the caller's environment


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


# ---------------- R25-j: informativeness and proximity, weights chosen by the learner ----------------
def candidates2(text, names):
    out = []
    for si, sent in enumerate(x for x in T.SENT.split(text) if x.strip()):
        cs, cf = R.construction(sent, names); raws = list(R.LAST_RAWS)
        words = [x for x in T.TOK.findall(sent) if x.isalpha()]; low = [w.lower() for w in words]
        for k, (sym, f) in enumerate(zip(cs, cf)):
            if sym in ("PERSON", "ENT") and f:
                span = raws[k] if k < len(raws) and raws[k] else f; sw = [x.lower() for x in span.split() if x.isalpha()]
                pos = next((i for i in range(len(low)) if sw and low[i:i + len(sw)] == sw), None)
                if pos is None: pos = next((i for i, w in enumerate(low) if sw and w == sw[-1]), 0)
                ctx = [(j, w) for j, w in enumerate(words) if not (pos <= j < pos + max(1, len(sw)))]
                out.append(dict(span=span, pos=pos, n=max(1, len(sw)), ctx=ctx))
    return out


def features2(text, q, names, protos, idf, use_idf, decay):
    qws = [w for w in T.TOK.findall(q) if w.isalpha() and w.lower() not in QW and w.lower() not in T.STOP]
    qv = [(vec(w), (idf.get(w.lower(), max(idf.values())) if use_idf else 1.0)) for w in qws]; qv = [(v, wt) for v, wt in qv if v is not None]
    kind = q.lower().split()[0]; proto = protos.get(kind); qslots = {w.lower() for w in qws}; rows = []
    for c in candidates2(text, names):
        if c["span"].split()[-1].lower() in qslots and len(c["span"].split()) <= 2: continue
        cv = [(j, vec(w)) for j, w in c["ctx"]]; cv = [(j, v) for j, v in cv if v is not None]
        if qv and cv:
            tot = sum(wt for _, wt in qv); m = 0.0
            for v, wt in qv:
                best = 0.0
                for j, u in cv:
                    d = j - (c["pos"] + c["n"] - 1) if j > c["pos"] else c["pos"] - j
                    best = max(best, float(np.dot(v, u)) * (1.0 if decay is None else decay ** max(0, d - 1)))
                m += wt * best
            match = m / tot
        else: match = 0.0
        h = head(c["span"]); hv = vec(h) if h else None
        typ = float(np.dot(hv, proto)) if (hv is not None and proto is not None) else (0.3 if (h and h[:1].isupper()) else 0.0)
        rows.append((c["span"], match, typ))
    return rows


def main_j():
    t0 = time.time()
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
    train_b, _ = D0.books(); paras = B.paragraphs(train_b, 150000); E.induce_verbish([p["text"] for p in paras], k=200)
    D.ON = True; T.SPAN_STOP.update(D.verb_forms() - E.NOUNISH)
    dfc = collections.Counter()
    for p_ in paras: dfc.update({w.lower() for w in T.TOK.findall(p_["text"]) if w.isalpha()})
    idf = {w: float(np.log(len(paras) / (1 + c))) for w, c in dfc.items()}
    protos = protos_from(data[:7000])
    old = json.load(open("val_stories.json", encoding="utf-8"))["stories"] + json.load(open("val_fables.json", encoding="utf-8"))["stories"] + json.load(open("val_timespace.json", encoding="utf-8"))["stories"]
    more = json.load(open("val_more.json", encoding="utf-8"))["stories"]
    K = ("who", "what", "where", "when", "whom")
    practice = [(s["text"], q, g) for s in old + more[:20] for q, g in s["qs"] if q.lower().split()[0] in K]
    holdout = [(s["text"], q, g) for s in more[20:] for q, g in s["qs"] if q.lower().split()[0] in K]
    print(f"R25-j informativeness learned for {len(idf)} words ({time.time() - t0:.0f} s)", flush=True)
    def fit(F, items, lam, margin):
        r = w = 0
        for rows, (t, q, g) in zip(F, items):
            a = decide(rows, lam, margin)
            if a is None: continue
            r, w = (r + 1, w) if hit(a, g) else (r, w + 1)
        return r - 3 * w, r, w
    best = None
    for use_idf in (False, True):
        for decay in (None, 0.8, 0.6):
            fp = [features2(t, q, names, protos, idf, use_idf, decay) for t, q, g in practice]
            for lam in (0.0, 0.5, 1.0):
                top1 = fit(fp, practice, lam, 0.0)[1]
                for margin in (0.0, 0.1, 0.2, 0.3):
                    f_ = fit(fp, practice, lam, margin)
                    if best is None or f_[0] > best[0][0]: best = (f_, use_idf, decay, lam, margin)
                print(f"  idf {use_idf} decay {decay} LAM {lam}: practice top-1 right always answering {top1}/{len(practice)}", flush=True)
    f_, use_idf, decay, lam, margin = best
    fh = [features2(t, q, names, protos, idf, use_idf, decay) for t, q, g in holdout]
    print(f"R25-j the learner chose idf {use_idf} decay {decay} LAM {lam} MARGIN {margin}: practice fitness {f_} | holdout top-1 right always answering {fit(fh, holdout, lam, 0.0)[1]}/{len(holdout)} | holdout fitness at chosen margin {fit(fh, holdout, lam, margin)}", flush=True)
    fb = [features2(t, q, names, protos, idf, False, None) for t, q, g in holdout]
    print(f"R25-j reference (R25-h settings: no idf, no decay, LAM 0.5): holdout top-1 right always answering {fit(fb, holdout, 0.5, 0.0)[1]}/{len(holdout)}", flush=True)
    json.dump(dict(use_idf=use_idf, decay=decay, lam=lam, margin=margin), open("r25_soft_j.json", "w"))


# ---------------- R25-k: a role reader that matches loosely (structure from constructions, matching from vectors) ----------------
def qparse(q, names):
    """(asked role, question verb, question argument heads) or None"""
    qs, qf = QR.qshape(q, names); k = q.lower().split()[0]
    verbs = [x[2:] for x in qs if x.startswith("V:")]; v = verbs[0] if verbs else None
    if "--state" in ARGV_SOFT and k == "where" and verbs in ([], ["be"]) and len(qs) > 1 and qs[1] in ("was", "were", "w", "V:be"):   # R25-o2: the dictionary reads 'was' as the verb 'be'   # R25-o: 'where was X (at the end / at noon)' asks for a state
        a0 = [(f if isinstance(f, str) else " ".join(f)) for x, f in zip(qs, qf) if x in ("PERSON", "ENT") and f]
        tw = [w for w in T.TOK.findall(q) if w.isalpha() and w.lower() not in T.STOP and w.lower() not in ("where", "was", "were", "end")]
        if a0: return ("state", None, [a0[0].split()[-1]] + [w for w in tw if w.lower() != a0[0].split()[-1].lower()])
    if v is None: return None
    args = [(f if isinstance(f, str) else " ".join(f)) for x, f in zip(qs, qf) if x in ("PERSON", "ENT") and f]
    args = [a.split()[-1] for a in args if a.lower() not in ("it", "him", "her", "them", "he", "she", "they")]
    if k == "what" and verbs[-1] == "do" and "--do" in ARGV_SOFT:                         # R25-m: 'what did X do' asks for an action; 'what did X refuse to do' for a complement
        return ("comp", verbs[0], args) if len(verbs) >= 2 else ("do", None, args)
    if k == "who" and "did" not in qs: role = "subj"
    elif k in ("what", "who", "whom") and "did" in qs: role = "obj"
    elif k == "what": role = "subj"
    elif k == "where": role = "place"
    elif k == "when": role = "when"
    else: return None
    return role, v, args


def roles_of(sents):
    """for every verb occurrence in the story: (sentence index, verb, subject, object, place, when, clause heads)"""
    out = []
    for si, (cs, cf, raws) in enumerate(sents):
        when = next((cf[i] for i, x in enumerate(cs) if x == "WHEN" and cf[i]), None)
        for i, x in enumerate(cs):
            if not x.startswith("V:"): continue
            lo, hi = R.clause_of(cs, i)
            filled = lambda k_: (raws[k_] if k_ < len(raws) and raws[k_] else cf[k_])
            subj = next((filled(k_) for k_ in range(i - 1, lo - 1, -1) if cs[k_] in ("PERSON", "ENT", "PRON") and cf[k_]), None)
            if subj is None and lo > 0: subj = next((filled(k_) for k_ in range(lo - 1, -1, -1) if cs[k_] in ("PERSON", "ENT") and cf[k_]), None)
            obj = next((filled(k_) for k_ in range(i + 1, hi) if cs[k_] in ("PERSON", "ENT") and cf[k_] and not (k_ >= 1 and cs[k_ - 1] in R.PLACE_WORDS)), None)
            place = next((f"{cs[k_ - 1]} {filled(k_)}" for k_ in range(i + 1, hi) if cs[k_] == "ENT" and cf[k_] and k_ >= 1 and cs[k_ - 1] in (R.PLACE_WORDS - {"from", "with", "by", "through", "to"})), None)                     or next((filled(k_) for k_ in range(i + 1, hi) if cs[k_] == "ENT" and cf[k_] and k_ >= 1 and cs[k_ - 1] == "to"), None)
            heads = [str(cf[k_]).split()[-1] for k_ in range(lo, hi) if cs[k_] in ("PERSON", "ENT") and cf[k_]]
            if "--time-args" in ARGV_SOFT and when: heads += [w for w in T.TOK.findall(when) if w.isalpha() and w.lower() not in T.STOP]   # R25-n: a clause's time phrase is one of its arguments
            pred = " ".join(str(raws[k_]) for k_ in range(i, min(hi, len(raws))) if raws[k_] and cs[k_] not in (".", ",", "and", "but", "WHEN", "WHY", "COMP")).strip() or None     # R25-m: the action, verb to clause end
            comp = next((cf[k_] for k_, y in enumerate(cs) if y == "COMP" and cf[k_]), None)
            out.append(dict(si=si, verb=x[2:], subj=subj, obj=obj, place=place, when=when, heads=heads, do=pred, comp=comp))
    return out


def soft_role(text, q, names, story_cache=None):
    """(answer, verb similarity, argument match) for the best-matching clause, or (None, 0, 0)"""
    p = qparse(q, names)
    if p is None: return None, 0.0, 0.0
    role, v, args = p; vv = vec(v) if v else None
    if role == "state":                                                                   # R25-o: the place of the clauses about X; the time words choose among them, else the latest
        if story_cache is None:
            sents = []
            for x in T.SENT.split(text):
                if x.strip(): cs, cf = R.construction(x, names); sents.append((cs, cf, list(R.LAST_RAWS)))
            story_cache = roles_of(sents)
        x0 = args[0].lower(); rest = args[1:]
        about = [c for c in story_cache if c["place"] and any(r_ and r_.split()[-1].lower() == x0 for r_ in (c["subj"], c["obj"]))]
        if not about: return None, 0.0, 0.0
        if rest:
            def tm(c): ws = [w for w in T.TOK.findall(c["when"] or "") if w.isalpha()]; return max([1.0 if w.lower() == r.lower() else (max(0.0, float(np.dot(vec(w), vec(r)))) if vec(w) is not None and vec(r) is not None else 0.0) for w in ws for r in rest] or [0.0])
            best = max(about, key=lambda c: (tm(c), c["si"])); return best["place"], 1.0, tm(best)
        return about[-1]["place"], 1.0, 1.0
    if role != "do" and vv is None: return None, 0.0, 0.0
    if story_cache is None:
        sents = []
        for x in T.SENT.split(text):
            if x.strip(): cs, cf = R.construction(x, names); sents.append((cs, cf, list(R.LAST_RAWS)))
        story_cache = roles_of(sents)
    best = (None, -1.0, 0.0)
    for c in story_cache:
        cu = vec(c["verb"]); ans = c[role]
        if not ans or (role != "do" and cu is None): continue
        if role not in ("do", "comp") and any(ans.split()[-1].lower() == a.lower() for a in args): continue   # the question already names it
        if role == "do" and (not c["subj"] or not args or not any(c["subj"].split()[-1].lower() == a.lower() or (vec(a) is not None and vec(c["subj"].split()[-1]) is not None and float(np.dot(vec(a), vec(c["subj"].split()[-1]))) >= 0.8) for a in args[:1])): continue   # the action of the one the question names
        vs = 1.0 if (role == "do" or c["verb"] == v) else float(np.dot(vv, cu))
        am = float(np.mean([max([1.0 if h.lower() == a.lower() else max(0.0, float(np.dot(vec(a), vec(h)))) for h in c["heads"] if vec(h) is not None] or [0.0]) for a in args if vec(a) is not None])) if args else 0.5
        sc = vs + am
        if sc > best[1] + best[2]: best = (ans, vs, am)
    return best


def main_k():
    t0 = time.time()
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
    train_b, _ = D0.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    D.ON = True; T.SPAN_STOP.update(D.verb_forms() - E.NOUNISH); QR.ARGV = ["x", "--pron-ref"]
    old = json.load(open("val_stories.json", encoding="utf-8"))["stories"] + json.load(open("val_fables.json", encoding="utf-8"))["stories"] + json.load(open("val_timespace.json", encoding="utf-8"))["stories"]
    more = json.load(open("val_more.json", encoding="utf-8"))["stories"]
    practice = [(s["text"], q, g) for s in old + more[:20] for q, g in s["qs"]]
    holdout = [(s["text"], q, g) for s in more[20:] for q, g in s["qs"]]
    if "--big" in ARGV:                                                                   # R25-w: thresholds chosen on all 710 practice questions; the untouched val_fresh2 judges
        pa = json.load(open("val_practice_a.json", encoding="utf-8"))["stories"] + json.load(open("val_practice_b.json", encoding="utf-8"))["stories"]
        practice = [(s["text"], q, g) for s in old + more + pa for q, g in s["qs"]]
        holdout = [(s["text"], q, g) for s in json.load(open("val_fresh2.json", encoding="utf-8"))["stories"] for q, g in s["qs"]]
    fp = [(soft_role(t, q, names), g) for t, q, g in practice]; fh = [(soft_role(t, q, names), g) for t, q, g in holdout]
    def fit(F, tv, ta):
        r = w = 0
        for (a, vs, am), g in F:
            if a is None or vs < tv or am < ta: continue
            r, w = (r + 1, w) if hit(a, g) else (r, w + 1)
        return r - 3 * w, r, w
    grid = [(tv, ta) for tv in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5) for ta in (0.0, 0.3, 0.5, 0.65, 0.8, 1.0)]
    res = {k: fit(fp, *k) for k in grid}
    for k in grid: print(f"  verb similarity >= {k[0]}, argument match >= {k[1]}: practice {res[k]}", flush=True)
    best = max(grid, key=lambda k: res[k][0])
    print(f"R25-k the learner chose verb >= {best[0]}, args >= {best[1]}: practice {res[best]} | holdout {fit(fh, *best)} over {len(holdout)} | exact-verb-only reference (1.0, {best[1]}): holdout {fit(fh, 1.0, best[1])} ({time.time() - t0:.0f} s)", flush=True)
    json.dump(dict(tv=best[0], ta=best[1], practice=res[best], holdout=fit(fh, *best)), open("r25_soft_k.json", "w"))


if __name__ == "__main__":
    main_k() if "--k" in ARGV else (main_j() if "--j" in ARGV else main())
