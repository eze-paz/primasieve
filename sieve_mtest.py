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
SIZE = int(os.environ.get("MT_SIZE", NTR)); SUF = "" if SIZE == NTR else f"_{SIZE // 1_000_000}M"           # MT5: count on a training prefix
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def fp(c, k): return os.path.join(OUT, f"{c}_{k}.npz")
def prep_books():
    z = np.load(os.path.join(LX, "lx_tokens.npz")); dd = np.load(os.path.join(LX, "lx_docs.npz")); L = np.load(os.path.join(LX, "lx_library.npz")); lb = np.load(os.path.join(LX, "lx_library_books.npz"))
    tok = np.r_[z["tr"], L["lib"]].astype(np.int64); tok[tok > 94501] = -1                               # lx UNK stays UNK
    words = np.array([""] + json.load(open(os.path.join(LX, "lx_vocab.json"), encoding="utf-8"))["words"])
    np.savez(fp("books", "raw"), words=words, tok=tok, sid=np.r_[z["trs"], L["libs"].astype(np.int64) + int(z["trs"].max()) + 1], doc=np.r_[dd["trb"], lb["book"].astype(np.int64) + 1000]); log(f"MT prep books: {len(tok):,} tokens")
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
    np.savez(fp("wiki", "raw"), words=np.array([""] + list(wid)), tok=np.array(tok, np.int64), sid=np.array(sid, np.int64), doc=np.array(doc, np.int64)); log(f"MT prep wiki: {len(tok):,} tokens, {di + 1:,} articles")
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
    ntr = int(pos[len(itr) - 1]) + 1; np.savez(fp(c, "data"), vw=np.r_[[""], z["words"][top]], S=S, D=Dc, ntr=ntr, nev_docs=len(ev), ntr_docs=nt)
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
    z = np.load(fp(c, "data")); S, Dc, ntr = z["S"].astype(np.int64), z["D"], int(int(z["ntr"]) * SIZE / NTR); con = (S > 100) & (S <= V); NC_ = int(NCNT * SIZE / NTR)
    if not os.path.exists(fp(c, "ngram" + SUF)):
        t = np.arange(2, ntr); t = t[S[t] != 0]; a, b, y = S[t - 2], S[t - 1], S[t]
        u3, n3 = ukeys((a * VV + b) * VV + y); u2, n2 = ukeys(b * VV + y); n1 = np.bincount(y, minlength=VV)
        np.savez(fp(c, "ngram" + SUF), u3=u3, n3=n3, u2=u2, n2=n2, n1=n1); log(f"MT count {c}: n-grams {len(u3):,} trigrams")
    Dtr = Dc[:ntr]; kp = np.nonzero(con[:ntr])[0]; g = np.random.default_rng(1); P = np.sort(g.choice(kp[kp >= 2], NC_, replace=False)); acc = (np.zeros(0, np.int64), np.zeros(0, np.int64))
    for a0 in range(0, len(P), 200_000):
        Tq = P[a0:a0 + 200_000]; y = S[Tq]; ks = [cw * VV + y[r] for r, cw in windows(S[:ntr], Dtr, kp, Tq, W)]; acc = merge(acc, ukeys(np.concatenate(ks)))
    np.savez(fp(c, "trig" + SUF), u=acc[0], n=acc[1]); log(f"MT count {c}{SUF}: trigger pairs {len(acc[0]):,} from {NC_:,} targets x {W} words")
def look(u, n, k):
    i = np.minimum(np.searchsorted(u, k), len(u) - 1); return np.where(u[i] == k, n[i], 0)
MODE = os.environ.get("MT_EVAL", "content"); MSUF = "" if MODE == "content" else "_all"                       # PH: all-word targets
def targets(S, ntr, con, mode=None):
    mode = mode or MODE; m = con[ntr:] if mode == "content" else (S[ntr:] != 0) & (S[ntr:] != UNK)
    T = np.nonzero(m)[0] + ntr; T = T[T >= ntr + 2]; return T[np.linspace(0, len(T) - 1, NEV).astype(int)]
def evaluate(c):
    z = np.load(fp(c, "data")); S, Dc, ntr = z["S"].astype(np.int64), z["D"], int(z["ntr"]); con = (S > 100) & (S <= V)
    T = targets(S, ntr, con); y = S[T]
    g = np.load(fp(c, "ngram" + SUF)); u3, n3, u2, n2, n1 = g["u3"], g["n3"], g["u2"], g["n2"], g["n1"]
    pU = (n1[y] + 0.5) / (n1.sum() + 0.5 * VV)
    b2 = u2 // VV; cb = np.bincount(b2, weights=n2, minlength=VV); db = np.bincount(b2, minlength=VV); b = S[T - 1]; a = S[T - 2]
    c2 = look(u2, n2, b * VV + y); p2 = np.where(cb[b] > 0, np.maximum(c2 - D, 0) / np.maximum(cb[b], 1) + D * db[b] / np.maximum(cb[b], 1) * pU, pU)
    x3 = u3 // VV; ux, st = np.unique(x3, return_index=True); cx = np.add.reduceat(n3, st); dx = np.diff(np.r_[st, len(u3)])
    ab = a * VV + b; cab = look(ux, cx, ab); dab = look(ux, dx, ab); c3 = look(u3, n3, ab * VV + y)
    pL = np.where(cab > 0, np.maximum(c3 - D, 0) / np.maximum(cab, 1) + D * dab / np.maximum(cab, 1) * p2, p2)
    tg = np.load(fp(c, "trig" + SUF)); tu, tn = tg["u"], tg["n"]; rc = np.bincount(tu // VV, weights=tn, minlength=VV)
    kp = np.nonzero(con)[0]; pT = np.zeros(len(T)); nw = np.zeros(len(T))
    for r, cw in windows(S, Dc, kp, T, W):
        ok = rc[cw] > 0; pT[r[ok]] += look(tu, tn, cw[ok] * VV + y[r[ok]]) / rc[cw[ok]]; nw[r[ok]] += 1
    pT = pT / np.maximum(nw, 1)
    ck = Dc[kp].astype(np.int64) * VV + S[kp]; cmb = (ck << 26) | kp; o = np.argsort(cmb); cmb = cmb[o]                                   # document cache and oracle
    kt = Dc[T].astype(np.int64) * VV + y; lo = np.searchsorted(cmb, kt << 26); hist = np.searchsorted(cmb, (kt << 26) | (T - 2)) - lo; tot = np.searchsorted(cmb, (kt + 1) << 26) - lo
    ds = np.searchsorted(Dc, Dc[T]); de = np.searchsorted(Dc, Dc[T], side="right"); kb = np.searchsorted(kp, ds); nh = np.searchsorted(kp, T - 2) - kb; nd = np.searchsorted(kp, de) - kb
    pC = hist / np.maximum(nh, 1); pO = (tot - 1) / np.maximum(nd - 1, 1)
    comps = dict(T=pT, C=pC, O=pO); combos = [(), ("T",), ("C",), ("T", "C"), ("O",)]; xtra = {}
    if not SUF: np.savez(fp(c, "base_" + MODE), T=T, U=pU, L=pL, Tg=pT, C=pC)                              # RZ: per-position components
    if os.environ.get("MT_BASEONLY"): log(f"MT {c}: base components saved"); return
    bases = [("A", pU, "U"), ("B", pL, "L")]; pf = fp(c, "ph_" + MODE)
    if os.path.exists(pf) and not SUF:                                                                    # PH1-PH5
        zp = np.load(pf); assert np.array_equal(zp["T"], T); comps.update({k_: zp[k_] for k_ in ("K", "G", "R", "P", "P0")}); bases.append(("B8", zp["X"], "L8"))
        combos += ([("P",), ("P0",), ("T", "C", "P"), ("T", "C", "P0")] if MODE == "content" else []) + [("K",), ("G",), ("R",), ("T", "C", "K"), ("T", "C", "K", "G", "R", "P")]
    if os.path.exists(fp(c, "py_" + MODE)) and not SUF:                                                  # PY: Pythia states and Pythia's own bits
        zy = np.load(fp(c, "py_" + MODE)); assert np.array_equal(zy["T"], T); comps.update({k_: zy[k_] for k_ in ("Y1", "Y4", "PY")})
        combos += [("Y1",), ("Y4",), ("T", "C", "Y4"), ("T", "C", "K", "Y4"), ("PY",), ("T", "C", "K", "PY"), ("T", "C", "K", "Y4", "PY")]
    if os.path.exists(fp(c, "nn")) and not SUF and MODE == "content":                                                          # MT3/MT4: MiniLM neighbours (soft) and states (hard)
        zn = np.load(fp(c, "nn")); assert np.array_equal(zn["T"], T); comps["N"] = zn["pN"]; comps["H"] = zn["pH"]; combos += [("N",), ("H",), ("T", "C", "N")]
    if os.path.exists(fp(c, "defvec")) and not SUF and MODE == "content":                                                                  # MT2: definition vectors
        import torch
        E = np.load(fp(c, "defvec"))["E"]; k = E.shape[1]; Cs = np.zeros((len(T), k), np.float32)
        for r, cw in windows(S, Dc, kp, T, W): Cs[r] += E[cw]
        Cs /= np.maximum(np.linalg.norm(Cs, axis=1, keepdims=True), 1e-9); uc = n1[101:V + 1] + 0.5; lU = torch.tensor(np.log(uc / uc.sum()), dtype=torch.float32); Ec = torch.tensor(E[101:V + 1])
        BET = (2.0, 5.0, 10.0, 20.0, 40.0); LP = np.zeros((len(BET), len(T))); yi = torch.tensor(y - 101)
        for a0 in range(0, len(T), 2000):
            Sc = torch.tensor(Cs[a0:a0 + 2000]) @ Ec.T; ar = torch.arange(Sc.shape[0])
            for bi, be in enumerate(BET): Z_ = lU + be * Sc; LP[bi, a0:a0 + 2000] = (Z_[ar, yi[a0:a0 + 2000]] - torch.logsumexp(Z_, 1)).numpy()
        odd_ = np.arange(len(T)) % 2 == 1; bi = int(np.argmax(LP[:, odd_].mean(1))); comps["D"] = np.exp(LP[bi]); combos += [("D",), ("T", "C", "D")] + ([("T", "C", "D", "N")] if "N" in comps else [])
        xtra = dict(def_beta=BET[bi], def_coverage=float((np.abs(E[y]).sum(1) > 0).mean())); log(f"MT {c} definition vectors: beta {BET[bi]}, target coverage {xtra['def_coverage']:.4f}")
    odd = np.arange(len(T)) % 2 == 1; R = dict(**xtra, eval_positions=int(len(T)), eval_docs=int(z["nev_docs"]), train_docs=int(z["ntr_docs"]), mean_doc_history=float(nh.mean()))
    def mixb(cols):
        M = np.stack(cols, 1); w = np.full(M.shape[1], 1 / M.shape[1])
        for _ in range(60): r_ = M[odd] * w; r_ /= r_.sum(1, keepdims=True); w = r_.mean(0)
        return float(-np.log2(M[~odd] @ w).mean()), [round(float(v), 3) for v in w]
    for test, base, nm in bases:
        for comp in combos:
            bits, w = mixb([base] + [comps[k_] for k_ in comp]); key = f"{test} {'+'.join((nm,) + comp)}"; R[key] = dict(bits=bits, weights=w); log(f"MT {c}{SUF}{MSUF} {key}: {bits:.4f} bits (weights {w})")
    out = os.path.join(HERE, "sieve_mtest.json"); A = json.load(open(out)) if os.path.exists(out) else {}; A[c + SUF + MSUF] = R; json.dump(A, open(out, "w"), indent=1)
def defvec(c, K=256):
    """MT2: each vocabulary word's vector from its WordNet definitions only (no corpus statistics): TF-IDF bag of the
    content words in the glosses + synonym lemmas of all its senses (sense rank weight 1/(r+1)), reduced by SVD"""
    import sieve_dict as SD, torch
    z = np.load(fp(c, "data")); vw = z["vw"]; ix = {w: i for i, w in enumerate(vw) if i > 100}; syn, index, exc = SD.parse(); rows, cols, val = [], [], []
    for i in range(101, V + 1):
        for p, bse in SD.base_forms(str(vw[i]), index, exc):
            for r, off in enumerate(index[(bse, p)]):
                s = syn.get((p, off))
                if s is None: continue
                for f in s[3] + [x for lm in s[1] for x in lm.split("_")]:
                    j = ix.get(f)
                    if j is not None: rows.append(i); cols.append(j); val.append(1.0 / (r + 1))
    rows, cols, val = np.array(rows), np.array(cols), np.array(val, np.float32); df = np.bincount(np.unique(rows * VV + cols) % VV, minlength=VV); val *= np.log((V + 1) / (1 + df[cols])).astype(np.float32)
    M = torch.sparse_coo_tensor(np.vstack([rows, cols]), val, (VV, VV)).coalesce(); U_, S_, _ = torch.svd_lowrank(M, q=K, niter=4); E = (U_ * S_).numpy().astype(np.float32)
    E /= np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-9); E[np.abs(E).sum(1) < 1e-6] = 0; np.savez(fp(c, "defvec"), E=E)
    log(f"MT defvec {c}: {len(np.unique(rows)):,} of {V - 100:,} content words have a definition; {len(val):,} entries")
if __name__ == "__main__":
    cmd, c = sys.argv[1], sys.argv[2]
    if cmd == "prep": (prep_books if c == "books" else prep_wiki)()
    else: dict(build=build, count=count, eval=evaluate, defvec=defvec)[cmd](c)
