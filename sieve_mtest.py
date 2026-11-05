"""MT (meaning test, 2026-11-05): does counting learn meaning, on books vs Wikipedia, at the same size?
Standalone of the TC2 program. Each corpus: same tokenizer (r24_tlm TOK/SENT, letters only, lowercased, sentences of >= 2
words), whole documents held out for eval until >= 2.5M tokens (books: ~60 books, not the program's 3), training = the
first 27M tokens of the other documents, own vocabulary = top 60,000 training words (rest = UNK). Targets = content words
(outside the top 100, not UNK) at 120,000 eval positions spread over the held-out documents.
Models (all counted on training only, except the oracle):
  U = unigram; L = interpolated absolute-discount trigram (local);
  T = trigger: mean over the last W=50 content words before t-2 (same document) of P(y | that word), counted on 2M
      training targets (the counting counterpart for meaning);
  C = document cache: frequency of y among the document's content words before t-2;
  O = ceiling: the document's own word frequencies, y left out (sees the rest of the document).
Test A (meaning only, last 2 words hidden): U, U+T, U+C, U+T+C, U+O. Test B (full): L, L+T, L+C, L+T+C, L+O.
Mixture weights by EM on odd positions; bits reported on even positions.
Run: py -3.12 -I sieve_mtest.py prep books|wiki ; build <c> ; count <c> ; eval <c>"""
import os, sys, re, io, json, time, zipfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); LX = os.path.join(HERE, "learned", "lx"); OUT = os.path.join(HERE, "mtest"); os.makedirs(OUT, exist_ok=True)
T0 = time.time(); V = 60000; VV = V + 2; UNK = V + 1; NTR = 27_000_000; NEVT = 2_500_000; NEV = 120_000; W = 50; NCNT = 2_000_000; D = 0.75
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def fp(c, k): return os.path.join(OUT, f"{c}_{k}.npz")
def prep_books():
    z = np.load(os.path.join(LX, "lx_tokens.npz")); dd = np.load(os.path.join(LX, "lx_docs.npz")); L = np.load(os.path.join(LX, "lx_library.npz")); lb = np.load(os.path.join(LX, "lx_library_books.npz"))
    tok = np.r_[z["tr"], L["lib"]].astype(np.int64); tok[tok > 94501] = -1                               # lx UNK stays UNK
    np.savez(fp("books", "raw"), tok=tok, sid=np.r_[z["trs"], L["libs"].astype(np.int64) + int(z["trs"].max()) + 1], doc=np.r_[dd["trb"], lb["book"].astype(np.int64) + 1000]); log(f"MT prep books: {len(tok):,} tokens")
def prep_wiki():
    TOK = re.compile(r"[A-Za-z][A-Za-z'-]*|[.,;!?]"); SENT = re.compile(r"(?<=[.!?])(?<!Dr\.)(?<!Mr\.)(?<!Mrs\.)(?<!St\.)\s+(?=[A-Z\"'])"); TIT = re.compile(r"^= [^=].* =$")
    zf = zipfile.ZipFile(os.path.join(HERE, "data_wiki", "wt103_raw.zip")); f = io.TextIOWrapper(zf.open("wikitext-103-raw/wiki.train.raw"), encoding="utf-8")
    wid = {}; tok = []; sid = []; doc = []; k = 0; di = -1; LIM = NTR + NEVT + 1_500_000
    for line in f:
        st = line.strip()
        if not st: continue
        if TIT.match(st): di += 1; continue                                                            # article title
        if st.startswith("= =") or di < 0: continue                                                    # section headings
        for s in SENT.split(st):
            w = [x.lower() for x in TOK.findall(s) if x.isalpha()]
            if len(w) < 2: continue
            tok.extend(wid.setdefault(x, len(wid) + 1) for x in w); sid.extend([k] * len(w)); doc.extend([di] * len(w)); k += 1
        if len(tok) >= LIM: break
    np.savez(fp("wiki", "raw"), tok=np.array(tok, np.int64), sid=np.array(sid, np.int64), doc=np.array(doc, np.int64)); log(f"MT prep wiki: {len(tok):,} tokens, {di + 1:,} articles")
def build(c):
    z = np.load(fp(c, "raw")); tok, sid, doc = z["tok"], z["sid"], z["doc"]; g = np.random.default_rng(0)
    ud, st = np.unique(doc, return_index=True); o = np.argsort(st); ud = ud[o]; st = st[o]; en = np.r_[st[1:], len(doc)]; ln = en - st          # docs are contiguous
    perm = g.permutation(len(ud)); cum = np.cumsum(ln[perm]); ne = int(np.searchsorted(cum, NEVT)) + 1; ev = perm[:ne]; trd = perm[ne:]
    ctr = np.cumsum(ln[trd]); nt = int(np.searchsorted(ctr, NTR)) + 1; trd = trd[:nt]
    def cat(ds, cap=None):
        ix = np.concatenate([np.arange(st[d], en[d]) for d in ds]); ix = ix[:cap] if cap else ix; return ix
    itr = cat(trd, NTR); iev = cat(ev); ix = np.r_[itr, iev]; t, s_, d_ = tok[ix], sid[ix], doc[ix]
    cnt = np.bincount(np.maximum(tok[itr], 0)); cnt[0] = 0; top = np.argsort(-cnt, kind="stable")[:V]; mp = np.full(max(len(cnt), int(tok.max()) + 1), UNK, np.int64); mp[top] = np.arange(1, V + 1)
    w = np.where(t > 0, mp[np.maximum(t, 0)], UNK); brk = np.r_[True, s_[1:] != s_[:-1]]                # a 0 before every sentence
    pos = np.cumsum(brk) + np.arange(len(w)); S = np.zeros(len(w) + int(brk.sum()), np.int32); S[pos] = w; Dc = np.zeros(len(S), np.int32)
    dd = np.r_[0, np.cumsum(d_[1:] != d_[:-1])]; Dc[pos] = dd; Dc[pos[brk] - 1] = dd[brk]
    ntr = int(pos[len(itr) - 1]) + 1; np.savez(fp(c, "data"), S=S, D=Dc, ntr=ntr, nev_docs=len(ev), ntr_docs=nt)
    log(f"MT build {c}: train {len(itr):,} tokens in {nt:,} docs; eval {len(iev):,} tokens in {len(ev):,} docs; UNK share train {(w[:len(itr)] == UNK).mean():.4f}")
def windows(S, Dc, kp, T, Wn):
    """(row, word) pairs: the last Wn content words before t-2, same document"""
    k = np.searchsorted(kp, T - 2); ds = np.searchsorted(Dc, Dc[T]); kb = np.searchsorted(kp, ds)
    for j in range(Wn):
        ix = k - 1 - j; ok = ix >= kb
        if ok.any(): yield np.nonzero(ok)[0], S[kp[ix[ok]]]
def ukeys(keys):
    u, n = np.unique(keys, return_counts=True); return u, n
def merge(a, b):
    k = np.r_[a[0], b[0]]; n = np.r_[a[1], b[1]]; u, inv = np.unique(k, return_inverse=True); return u, np.bincount(inv, weights=n).astype(np.int64)
def count(c):
    z = np.load(fp(c, "data")); S, Dc, ntr = z["S"].astype(np.int64), z["D"], int(z["ntr"]); con = (S > 100) & (S <= V)
    if not os.path.exists(fp(c, "ngram")):
        t = np.arange(2, ntr); t = t[S[t] != 0]; a, b, y = S[t - 2], S[t - 1], S[t]
        u3, n3 = ukeys((a * VV + b) * VV + y); u2, n2 = ukeys(b * VV + y); n1 = np.bincount(y, minlength=VV)
        np.savez(fp(c, "ngram"), u3=u3, n3=n3, u2=u2, n2=n2, n1=n1); log(f"MT count {c}: n-grams {len(u3):,} trigrams")
    Dtr = Dc[:ntr]; kp = np.nonzero(con[:ntr])[0]; g = np.random.default_rng(1); P = np.sort(g.choice(kp[kp >= 2], NCNT, replace=False)); acc = (np.zeros(0, np.int64), np.zeros(0, np.int64))
    for a0 in range(0, len(P), 200_000):
        Tq = P[a0:a0 + 200_000]; y = S[Tq]; ks = [cw * VV + y[r] for r, cw in windows(S[:ntr], Dtr, kp, Tq, W)]; acc = merge(acc, ukeys(np.concatenate(ks)))
    np.savez(fp(c, "trig"), u=acc[0], n=acc[1]); log(f"MT count {c}: trigger pairs {len(acc[0]):,} from {NCNT:,} targets x {W} words")
def look(u, n, k):
    i = np.minimum(np.searchsorted(u, k), len(u) - 1); return np.where(u[i] == k, n[i], 0)
def evaluate(c):
    z = np.load(fp(c, "data")); S, Dc, ntr = z["S"].astype(np.int64), z["D"], int(z["ntr"]); con = (S > 100) & (S <= V)
    T = np.nonzero(con[ntr:])[0] + ntr; T = T[T >= ntr + 2]; T = T[np.linspace(0, len(T) - 1, NEV).astype(int)]; y = S[T]
    g = np.load(fp(c, "ngram")); u3, n3, u2, n2, n1 = g["u3"], g["n3"], g["u2"], g["n2"], g["n1"]
    pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV)
    b2 = u2 // VV; cb = np.bincount(b2, weights=n2, minlength=VV); db = np.bincount(b2, minlength=VV); b = S[T - 1]; a = S[T - 2]
    c2 = look(u2, n2, b * VV + y); p2 = np.where(cb[b] > 0, np.maximum(c2 - D, 0) / np.maximum(cb[b], 1) + D * db[b] / np.maximum(cb[b], 1) * pU, pU)
    x3 = u3 // VV; ux, st = np.unique(x3, return_index=True); cx = np.add.reduceat(n3, st); dx = np.diff(np.r_[st, len(u3)])
    ab = a * VV + b; cab = look(ux, cx, ab); dab = look(ux, dx, ab); c3 = look(u3, n3, ab * VV + y)
    pL = np.where(cab > 0, np.maximum(c3 - D, 0) / np.maximum(cab, 1) + D * dab / np.maximum(cab, 1) * p2, p2)
    tg = np.load(fp(c, "trig")); tu, tn = tg["u"], tg["n"]; rc = np.bincount(tu // VV, weights=tn, minlength=VV)
    kp = np.nonzero(con)[0]; pT = np.zeros(len(T)); nw = np.zeros(len(T))
    for r, cw in windows(S, Dc, kp, T, W):
        ok = rc[cw] > 0; pT[r[ok]] += look(tu, tn, cw[ok] * VV + y[r[ok]]) / rc[cw[ok]]; nw[r[ok]] += 1
    pT = pT / np.maximum(nw, 1)
    ck = Dc[kp].astype(np.int64) * VV + S[kp]; cmb = (ck << 26) | kp; o = np.argsort(cmb); cmb = cmb[o]                                   # document cache and oracle
    kt = Dc[T].astype(np.int64) * VV + y; lo = np.searchsorted(cmb, kt << 26); hist = np.searchsorted(cmb, (kt << 26) | (T - 2)) - lo; tot = np.searchsorted(cmb, (kt + 1) << 26) - lo
    ds = np.searchsorted(Dc, Dc[T]); de = np.searchsorted(Dc, Dc[T], side="right"); kb = np.searchsorted(kp, ds); nh = np.searchsorted(kp, T - 2) - kb; nd = np.searchsorted(kp, de) - kb
    pC = hist / np.maximum(nh, 1); pO = (tot - 1) / np.maximum(nd - 1, 1)
    odd = np.arange(len(T)) % 2 == 1; R = dict(eval_positions=int(len(T)), eval_docs=int(z["nev_docs"]), train_docs=int(z["ntr_docs"]), mean_doc_history=float(nh.mean()))
    def mixb(cols):
        M = np.stack(cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(60): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return float(-np.log2(M[~odd] @ w).mean()), [round(float(v), 3) for v in w]
    for test, base, nm in (("A", pU, "U"), ("B", pL, "L")):
        for comp in ((), ("T",), ("C",), ("T", "C"), ("O",)):
            bits, w = mixb([base] + [dict(T=pT, C=pC, O=pO)[k_] for k_ in comp]); key = f"{test} {'+'.join((nm,) + comp)}"; R[key] = dict(bits=bits, weights=w); log(f"MT {c} {key}: {bits:.4f} bits (weights {w})")
    out = os.path.join(HERE, "sieve_mtest.json"); A = json.load(open(out)) if os.path.exists(out) else {}; A[c] = R; json.dump(A, open(out, "w"), indent=1)
if __name__ == "__main__":
    cmd, c = sys.argv[1], sys.argv[2]
    if cmd == "prep": (prep_books if c == "books" else prep_wiki)()
    else: dict(build=build, count=count, eval=evaluate)[cmd](c)
