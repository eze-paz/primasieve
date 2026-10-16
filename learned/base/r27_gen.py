"""R27 G1: plan-constrained generation -- the plan gives the content words, the system's own count model writes the
sentence (R27_prereg.md). Run: py -3.12 r27_gen.py [--n N] [--score]"""
import os, sys, re, json, math, time, statistics as st
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ARGV0 = list(sys.argv); sys.argv = [sys.argv[0], "--p2e"]
import r27_retell as RT
from r27_answer import past
os.chdir(HERE)
X = np.load("r25_kn2_o5mxa_index.npz"); top = X["words"].tolist(); wid = {w: i + 1 for i, w in enumerate(top)}; RARE = 65535
NMAX = int(X["nmax"]); TOT1 = float(X["TOT1"]); C1disc = float(X["C1disc"]); MUL = np.uint64(0x9E3779B97F4A7C15); np.seterr(over="ignore")
Dn = {n: X[f"D{n}"] for n in range(1, NMAX + 1)}
c1 = X["cnt1"]; p1 = np.full(65536, C1disc / TOT1 / 65536); np.add.at(p1, X["wd1"].astype(np.int64), np.maximum(c1 - Dn[1][np.minimum(c1, 3) - 1], 0) / TOT1)
IX = {n: (X[f"ctx{n}"], X[f"wd{n}"].astype(np.int64), X[f"cnt{n}"], X[f"hu{n}"], X[f"tot{n}"], X[f"dm{n}"]) for n in range(2, NMAX + 1)}
def hl(ids):
    h = np.uint64(0)
    for j, x in enumerate(ids): h = (h ^ np.uint64(x)) * MUL + np.uint64(j + 1)
    return h
_cache = {}
def kn_full(prev):
    key = tuple(prev[-(NMAX - 1):])
    if key in _cache: return _cache[key]
    p = p1.copy()
    for n in range(2, NMAX + 1):
        if len(prev) < n - 1: break
        hc = hl(prev[-(n - 1):]); ctx, wd, cnt, hu, tot, dm = IX[n]; i = np.searchsorted(hu, hc)
        if i >= len(hu) or hu[i] != hc: break
        lo, hi = np.searchsorted(ctx, hc, "left"), np.searchsorted(ctx, hc, "right"); c = cnt[lo:hi]
        p *= dm[i] / tot[i]; p[wd[lo:hi]] += np.maximum(c - Dn[n][np.minimum(c, 3) - 1], 0) / tot[i]
    if len(_cache) > 200000: _cache.clear()
    _cache[key] = p; return p
FUNC = np.array([wid[w] for w in top[:300] if w.isalpha()])                                       # the 300 commonest words: the model may add these freely
FUNCSET = set(top[:300])
SLOT = [np.array([wid[w] for w in ("the", "a", "an") if w in wid]),                       # before the subject
        np.array([wid[w] for w in ("had", "would", "could", "was", "were", "then", "also", "soon", "just", "finally") if w in wid]),   # subject -> verb (no negation or frequency: they change the meaning)
        np.array([wid[w] for w in ("the", "a", "an", "his", "her", "their", "its", "to", "at", "in", "on", "into", "for", "with", "from", "up", "down", "out", "over", "back", "of", "some", "all", "by", "near", "under", "behind", "across") if w in wid]),   # after the verb
        np.array([wid[w] for w in ("the", "a", "an", "his", "her", "their", "its", "some") if w in wid])]   # before a direct object: no preposition
def forms(v):
    b = RT.D.verb_base(v) or v; out = {b, past(b), b + "s", b + "ed", (b[:-1] if b.endswith("e") else b) + "ing", v.lower()}
    return [f for f in out if f in wid]
def generate(req, width=8, vi=1, gaps=None):
    """req: list of lists of acceptable word forms, in order. Total log-probability; at most 1 free word before the
    first required token and 3 between required tokens."""
    beams = [(0.0, [0], [], 0, 0)]; done = []
    for step in range(5 * len(req) + 2):
        nb = []
        for lp, prev, words, r, free in beams:
            p = kn_full(prev)
            fl = req[r]
            if r == vi and len(fl) > 1 and words:                                                  # verb agreement with a chosen auxiliary
                aux = next((x for x in reversed(words[-2:]) if x in ("had", "was", "were", "would", "could", "did")), None)
                b = fl[0]
                if aux == "had": fl = [f for f in fl if f == past(b)] or fl
                elif aux in ("was", "were"): fl = [f for f in fl if f.endswith("ing")] or fl
                elif aux in ("would", "could", "did"): fl = [b] if b in wid else fl
                else: fl = [f for f in fl if f == past(b)] or fl
            cand = [(wid[f], f, r + 1, 0) for f in fl]
            gcls, gmax = gaps[r] if gaps else ((0, 1) if r == 0 else ((1, 3) if r <= vi else (2, 3)))
            if gcls is not None and free < gmax:
                allow = SLOT[gcls]                                                       # the gap's word class
                fids = allow[np.argsort(-p[allow])[:12]]
                cand += [(int(i), top[int(i) - 1], r, free + 1) for i in fids]
            for i, w, r2, f2 in cand:
                if words and w == words[-1]: continue
                if w in ("was", "were") and words:                                                # be agrees with the subject
                    plural = words[-1].endswith("s") and words[-1] not in ("his", "was") or words[-1] in ("they", "we")
                    if (w == "were") != plural: continue
                stt = (lp + math.log(max(p[i], 1e-12)), prev + [i], words + [w], r2, f2)
                (done if r2 == len(req) else nb).append(stt)
        nb.sort(key=lambda s: -s[0]); beams = nb[:width]
        if not beams: break
    if not done: return None
    return max(done, key=lambda s: s[0])[2]
DETS = {"the", "a", "an", "his", "her", "their", "its", "my", "our"}
PREPS = {"to", "at", "in", "on", "into", "for", "with", "from", "by", "near", "under", "behind", "across", "over", "through", "onto", "towards"}
def requirements(r):
    """the plan: subject (its determiner and head), the verb (all forms; base first), the object and the place with the
    story's own determiner / possessive and preposition. gaps[j]: which words the model may add before token j."""
    req = []; gaps = []
    subj = [w.lower() for w in re.findall(r"[A-Za-z']+", str(r["subj"]))]
    if not subj or subj[-1] not in wid: return None
    if len(subj) > 1 and subj[0] in DETS: req.append([subj[0]]); gaps.append((None, 0)); req.append([subj[-1]]); gaps.append((None, 0))
    else: req.append([subj[-1]]); gaps.append((0, 1) if subj[-1] not in ("he", "she", "they", "it") and not str(r["subj"])[0].isupper() else (None, 0))
    b = RT.D.verb_base(r["verb"]) or r["verb"]; vf = [x for x in [b] + forms(r["verb"]) if x in wid]
    if not vf: return None
    vi = len(req); req.append(list(dict.fromkeys(vf))); gaps.append((1, 2))
    for slot in ("obj", "place"):
        if r.get(slot):
            ws = [w.lower() for w in re.findall(r"[A-Za-z']+", str(r[slot]))]
            if not ws or ws[-1] not in wid: continue
            first = True
            if ws[0] in PREPS and slot == "place": req.append([ws[0]]); gaps.append((None, 0)); ws = ws[1:]; first = False
            g0 = (3, 1) if slot == "obj" else (2, 2)
            if ws and ws[0] in DETS and len(ws) > 1: req.append([ws[0]]); gaps.append((None, 0) if slot == "obj" else (g0 if first else (None, 0))); first = False
            req.append([ws[-1]]); gaps.append(g0 if first else (None, 0))
    return req, vi, gaps
G2B = "--g2b" in ARGV0; G2 = "--g2" in ARGV0 or G2B
def plan_ok(text, r):
    """G2: the subject's head stands before the verb within 6 words, no other verb form between them"""
    sw = re.findall(r"[A-Za-z']+", str(r["subj"]))
    if not sw: return False
    head = sw[-1].lower(); vb = RT.D.verb_base(r["verb"]) or r["verb"]
    if G2B and RT.D.verb_base(head) and head not in ("he", "she", "they", "it"): return False        # G2b: a verb form is not a subject
    for sent in RT.T.SENT.split(text):
        w = [x.lower() for x in re.findall(r"[A-Za-z']+", sent)]
        for i, x in enumerate(w):
            if x != head: continue
            for j in range(i + 1, min(len(w), i + 7)):
                bj = RT.D.verb_base(w[j])
                if G2B and w[j] in ("and", "but", "or", "so"): break                                  # G2b
                if bj == vb: return True
                if bj and RT.D.mainly_verb(w[j]) and w[j] not in ("had", "was", "were", "would", "could", "did", "has", "is"): break
    return False
def realise_words(words, text):
    names = {w.lower(): w for w in re.findall(r"(?<=[a-z,;] )[A-Z][a-z]+", text)}
    out = [names.get(w, w) if not (i == 0) else w for i, w in enumerate(words)]
    ws = [names.get(w, w) for w in words]
    ws = ["an" if (w == "a" and i + 1 < len(ws) and ws[i + 1][0].lower() in "aeiou") else w for i, w in enumerate(ws)]
    if len(ws) < 3: return None
    s = " ".join(ws); return s[0].upper() + s[1:] + "."
if __name__ == "__main__":
    st_ = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; qn = 0; un = []
    for k, s in enumerate(st_):
        if 310 <= qn < 510 or qn >= 910: un.append(k)
        qn += len(s["qs"])
    N = int(ARGV0[ARGV0.index("--n") + 1]) if "--n" in ARGV0 else 20
    rows = []; t0 = time.time()
    for k in un[:N]:
        text = st_[k]["text"]
        for r in [x for x in RT.plan(text) if (not G2) or plan_ok(text, x)][:3]:
            rq = requirements(r)
            if not rq: continue
            req, vi, gaps = rq; w = generate(req, vi=vi, gaps=gaps)
            if not w: continue
            src = next((s for s in RT.T.SENT.split(text) if str(r["subj"]).split()[-1] in s and (r.get("do") or "").split()[0] in s), None) if r.get("do") else None
            g_ = realise_words(w, text)
            if not g_: continue
            rows.append(dict(k=k, req=req, gen=g_, src=src, plan=f"{r['subj']} | {r['verb']} | {r.get('obj')} | {r.get('place')}"))
    json.dump(rows, open("r27_g2b_outputs.json" if G2B else "r27_g2_outputs.json" if G2 else "r27_g1_outputs.json", "w", encoding="utf-8"), indent=0)
    print(f"G1 generated {len(rows)} sentences ({time.time() - t0:.0f} s)")
    for r in rows[:15]: print(f"  PLAN {r['plan']}\n   GEN {r['gen']}\n   SRC {r['src']}")
    if "--score" in ARGV0:
        from r27_fluency import judge_ctx_many, judge_bits
        def grams(t): w = [x.lower() for x in re.findall(r"[A-Za-z']+", t)]; return [tuple(w[i:i + 3]) for i in range(len(w) - 2)]
        nov = []; inv = []; jg = []; js = []
        for r in rows:
            text = st_[r["k"]]["text"]; sg = set(grams(text)); g = grams(r["gen"])
            nov.append(sum(1 for x in g if x not in sg) / max(1, len(g)))
            sw = {x.lower() for x in re.findall(r"[A-Za-z']+", text)}
            inv.append(any(w.lower() not in sw and w.lower() not in FUNCSET for w in re.findall(r"[A-Za-z']+", r["gen"])))
            if r["src"]:
                jg.append(judge_ctx_many(text + "\n\n", [r["gen"]])[0]); before = text[:text.find(r["src"])]
                js.append(judge_ctx_many(before, [r["src"]])[0] if before.strip() else judge_bits(r["src"]))
        print(f"G1 novelty {st.mean(nov):.3f}; sentences with an invented content word {sum(inv)} / {len(inv)}; judge in context: generated {st.mean(jg):.3f} vs the story's own sentence {st.mean(js):.3f} over {len(jg)}")
