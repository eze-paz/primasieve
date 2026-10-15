"""R27 P11: a linear sentence selector learned from 60 passage / summary pairs, tested on the 15 test passages."""
import os, sys, re, json, math, collections, statistics as st
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r24_dict as Dct
STOP = set("the a an and or but of to in on at by for with from was were is are be been had has have did do does he she it they his her their its him them i you we my your our this that these those as so then there when while not no would could should said one all what which who mr mrs".split())
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
def toks(t): return [(Dct.verb_base(w) or w) for w in (x.lower() for x in re.findall(r"[A-Za-z']+", t)) if w not in STOP and len(w) > 2]
def feats(S, i, f, name):
    t = toks(S[i]); n = len(S); L = max(1, len(S[i].split()))
    cen = sum(f[w] for w in t) / math.sqrt(L); first = set(toks(S[0])); rest = collections.Counter(w for j, s in enumerate(S) if j != i for w in toks(s))
    return [1.0, i / max(1, n - 1), float(i == 0), float(i == n - 1), L / 30, cen / 10, float(bool(name and name.lower() in S[i].lower())), len(set(t) & first) / max(1, len(set(t))), sum(rest[w] > 0 for w in set(t)) / max(1, len(set(t)))]
def passage_rows(p, H):
    S = [s for s in SENT.split(p["text"]) if s.strip()]; f = collections.Counter(toks(p["text"]))
    names = collections.Counter(re.findall(r"\b[A-Z][a-z]{2,}\b", p["text"])); name = next((w for w, _ in names.most_common() if w not in ("The", "She", "He", "They", "But", "And", "When", "Then", "There", "This", "That", "It", "His", "Her")), None)
    h = set(toks(H[p["k"]])) if H else set()
    X = [feats(S, i, f, name) for i in range(len(S))]; y = [len(set(toks(S[i])) & h) / max(1, len(h)) for i in range(len(S))]
    return S, np.array(X), np.array(y)
TR = json.load(open("r27_long_passages_train.json", encoding="utf-8")); HT = {r["k"]: r["summary"] for r in json.load(open("r27_long_human_summaries_train.json", encoding="utf-8"))}
TE = json.load(open("r27_long_passages.json", encoding="utf-8")); HE = {r["k"]: r["summary"] for r in json.load(open("r27_long_human_summaries.json", encoding="utf-8"))}
Xs, ys = [], []
for p in TR:
    if p["k"] in HT: _, X, y = passage_rows(p, HT); Xs.append(X); ys.append(y)
X = np.concatenate(Xs); y = np.concatenate(ys); w = np.linalg.lstsq(X, y, rcond=None)[0]
print("P11 weights:", dict(zip(["bias", "position", "first", "last", "length", "centrality", "main name", "overlap first", "overlap rest"], w.round(3))))
def cover(t, k): h = set(toks(HE[k])); return len(h & set(toks(t))) / max(1, len(h))
COMP = "--compress" in sys.argv
def compress(s):
    if not COMP: return s
    cut = len(s)
    for pat in (";", ":", " -- ", "--", ", which", ", who", ", where", ", and then"):
        k = s.find(pat)
        if 0 < k < cut: cut = k
    t = s[:cut].rstrip(" ,;:-")
    if len(t.split()) >= 6 and any(Dct.mainly_verb(w) or Dct.verb_base(w.lower()) in ("be", "have") for w in t.split()): return t + ("" if t.endswith((".", "!", "?")) else ".")
    return s
cs, cl, ws, OUT = [], [], [], {}
for p in TE:
    S, Xp, _ = passage_rows(p, HE); sc = Xp @ w; lead = []
    for s in S:
        lead.append(s)
        if len(" ".join(lead).split()) >= 110: break
    m = len(" ".join(lead).split()); pick = []
    for i in np.argsort(-sc):
        if len(" ".join(compress(S[j]) for j in pick + [i]).split()) > m and pick: continue
        pick.append(i)
        if len(" ".join(compress(S[j]) for j in pick).split()) >= m - 5: break
    out = " ".join(compress(S[j]) for j in sorted(pick)); OUT[p["k"]] = out; cs.append(cover(out, p["k"])); cl.append(cover(" ".join(lead), p["k"])); ws.append((len(out.split()), m))
json.dump(OUT, open("r27_p12_outputs.json" if COMP else "r27_p11_outputs.json", "w", encoding="utf-8"), indent=0)
print(f"P11{'/P12 compressed' if COMP else ''} learned selector coverage {st.mean(cs):.3f} ({st.mean(a for a, _ in ws):.0f} words) vs length-matched lead {st.mean(cl):.3f} ({st.mean(b for _, b in ws):.0f} words) on {len(TE)} test passages")
