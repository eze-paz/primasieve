"""HP0 (sieve_lang_prereg.md): gauge Sieve-style counting on enwik8. Lossless split into a lowercase word stream + a
skeleton (everything else, with 1-byte case placeholders), then an online count model's ideal code length on the word
stream. Run: py -3.12 -I sieve_hp.py split <nbytes> ; py -3.12 -I sieve_hp.py model <nbytes> [W]"""
import os, sys, re, time, json, lzma
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data_enwik"); OUT = os.path.join(HERE, "mtest", "hp"); os.makedirs(OUT, exist_ok=True)
T0 = time.time(); D = 0.75; LOWER, CAP, UPPER = b"\x01", b"\x02", b"\x03"
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def tag(n): return f"{n // 1_000_000}M"
def split(n):
    data = open(os.path.join(DATA, "enwik8"), "rb").read()[:n]; assert not any(b in data for b in (LOWER, CAP, UPPER))
    words, pos = [], []
    def rep(m):
        w = m.group()
        if w.islower(): cl = LOWER
        elif w[:1].isupper() and (len(w) == 1 or w[1:].islower()): cl = CAP
        elif w.isupper(): cl = UPPER
        else: return w                                                                                  # mixed case: stays in the skeleton
        words.append(w.lower()); pos.append(m.start()); return cl
    skel = re.sub(rb"[A-Za-z]+", rep, data)
    it = iter(words)                                                                                    # byte-exact reconstruction check
    def back(m):
        w = next(it); c = m.group()
        return w if c == LOWER else (w[:1].upper() + w[1:]) if c == CAP else w.upper()
    assert re.sub(rb"[\x01\x02\x03]", back, skel) == data
    vocab = {}; ids = np.array([vocab.setdefault(w, len(vocab)) for w in words], np.int64)
    pg = np.array([m.start() for m in re.finditer(rb"<page>", data)]); doc = np.searchsorted(pg, np.array(pos), side="right")
    newl = b"\n".join(vocab.keys()); wtxt = b" ".join(words); t = tag(n)
    for nm, b in (("slice", data), ("skel", skel), ("words", wtxt), ("newwords", newl)): open(os.path.join(OUT, f"{t}_{nm}.bin"), "wb").write(b)
    np.savez(os.path.join(OUT, f"{t}_stream.npz"), ids=ids, doc=doc)
    xz = {nm: len(lzma.compress(b, preset=9 | lzma.PRESET_EXTREME)) for nm, b in (("slice", data), ("skel", skel), ("words", wtxt), ("newwords", newl))} if n <= 10_000_000 else {nm: len(lzma.compress(b, preset=9)) for nm, b in (("skel", skel), ("newwords", newl))}
    json.dump(dict(bytes=n, words=len(ids), distinct=len(vocab), skel_bytes=len(skel), xz=xz), open(os.path.join(OUT, f"{t}_split.json"), "w"), indent=1)
    log(f"HP split {t}: {len(ids):,} words, {len(vocab):,} distinct, skeleton {len(skel):,} bytes; xz {xz}")
def before(k, t=None):
    """for each i: how many earlier entries (smaller time) have the same key"""
    t = np.arange(len(k)) if t is None else t; o = np.lexsort((t, k)); ks = k[o]; ts = t[o]; st = np.r_[0, np.nonzero(ks[1:] != ks[:-1])[0] + 1]
    gs = np.repeat(st, np.diff(np.r_[st, len(k)])); r = np.empty(len(k), np.int64)
    rank = np.arange(len(k)) - gs; r[o] = rank; return r
def distinct_before(ctx, pairc):
    """distinct continuations of ctx seen before i: sum of first-occurrence flags of (ctx, y) earlier in the ctx group"""
    f = (pairc == 0).astype(np.int64); o = np.argsort(ctx, kind="stable"); cs = np.cumsum(f[o]); st = np.r_[0, np.nonzero(ctx[o][1:] != ctx[o][:-1])[0] + 1]
    base = np.repeat(np.r_[0, cs[st[1:] - 1]] if len(st) > 1 else np.zeros(1, np.int64), np.diff(np.r_[st, len(ctx)])); r = np.empty(len(ctx), np.int64); r[o] = cs - f[o] - base; return r
def absdisc(ctx, y, lower):
    pc = before(hashpair(ctx, y)); cc = before(ctx); n1 = distinct_before(ctx, pc)
    return np.where(cc > 0, np.maximum(pc - D, 0) / np.maximum(cc, 1) + D * n1 / np.maximum(cc, 1) * lower, lower)
M64 = np.uint64(0x9E3779B97F4A7C15)
def hashpair(a, b):
    with np.errstate(over="ignore"): return ((a.astype(np.uint64) * M64) ^ (b.astype(np.uint64) + np.uint64(0x632BE59BD9B4E019))).astype(np.int64)
def model(n, W=20):
    t_ = tag(n); z = np.load(os.path.join(OUT, f"{t_}_stream.npz")); y = z["ids"]; doc = z["doc"]; N = len(y); idx = np.arange(N)
    def cf(nm): return os.path.join(OUT, f"{t_}_c_{nm}.npy")
    def stage(nm, fn):                                                                                  # resumable: one cached array per stage, 5-minute runs
        if os.path.exists(cf(nm)): return np.load(cf(nm))
        if time.time() - T0 > 150: log(f"HP model {t_}: stage {nm} next; rerun"); sys.exit(0)
        a = fn(); np.save(cf(nm), a); log(f"HP model {t_}: stage {nm} done"); return a
    seen = stage("seen", lambda: before(y)); new = seen == 0; d = np.r_[0, np.cumsum(new)[:-1]]               # d = distinct words before i
    esc = (d + 1) / (idx + d + 1); U = seen / np.maximum(idx, 1)
    p = U.copy(); h = np.zeros(N, np.int64)
    for o in range(2, 9):                                                                                # orders 2..8
        prev = np.r_[np.full(o - 1, -1), y][:N]; h = hashpair(h, prev)                                     # word o-1 back
        p = stage(f"L{o}", lambda: absdisc(h, y, p))
    L3, L8 = np.load(cf("L3")), p; cnt = np.bincount(y); top = np.argsort(-cnt)[:100]; fn = np.zeros(len(cnt), bool); fn[top] = True
    kp = np.nonzero(~fn[y])[0]; i1 = np.searchsorted(kp, idx - 1) - 1; c1 = np.where(i1 >= 0, y[kp[np.maximum(i1, 0)]], -1)        # last content word before t-1
    pk1 = stage("K1", lambda: absdisc(c1 + 1, y, U)); K = stage("K", lambda: absdisc(hashpair(c1 + 1, np.r_[-1, y[:-1]]), y, pk1))
    C = stage("C", lambda: before(doc.astype(np.int64) * (int(y.max()) + 2) + y) / np.maximum(idx - np.searchsorted(doc, doc), 1))
    def trig():
        k = np.searchsorted(kp, idx - 1); kb = np.searchsorted(kp, np.searchsorted(doc, doc)); Ts = np.zeros(N); nw = np.zeros(N); keys, tms, cws = [], [], []
        for j in range(W):
            ix = k - 1 - j; ok = ix >= kb; r = np.nonzero(ok)[0]; cw_ = y[kp[ix[ok]]]; keys.append(hashpair(cw_, y[r])); tms.append(r); cws.append(cw_)
        kk = np.concatenate(keys); tt = np.concatenate(tms); cw = np.concatenate(cws); del keys, cws
        pcnt = timed_before(kk, tt); del kk; ccnt = timed_before(cw, tt); ok = ccnt > 0
        np.add.at(Ts, tt[ok], pcnt[ok] / ccnt[ok]); np.add.at(nw, tt, ok.astype(float)); return Ts / np.maximum(nw, 1)
    T = stage(f"T{W}", trig)
    comps = dict(U=U, L3=L3, L8=L8, K=K, C=C, T=T); R = dict(words=N, new=int(new.sum()))
    old = ~new; esc_bits = float(-np.log2(esc[new]).sum() - np.log2(1 - esc[old]).sum())
    for nm, keys_ in (("L3", ("L3",)), ("L8", ("L8",)), ("L8+C", ("L8", "C")), ("L8+K+C", ("L8", "K", "C")), ("L8+K+C+T", ("L8", "K", "C", "T")), ("U+L8+K+C+T", ("U", "L8", "K", "C", "T"))):
        Mx = np.stack([comps[q][old] for q in keys_], 1); w = np.full(Mx.shape[1], 1 / Mx.shape[1]); Ms = Mx[np.random.default_rng(0).choice(len(Mx), min(len(Mx), 1_000_000), replace=False)]
        for _ in range(80): r_ = Ms * w; r_ /= np.maximum(r_.sum(1, keepdims=True), 1e-300); w = r_.mean(0)
        bits = float(-np.log2(np.maximum(Mx @ w, 1e-300)).sum()) + esc_bits + 32 * len(keys_) + 100 * 20
        R[nm] = dict(bytes=bits / 8, bits_per_word=bits / N, weights=[round(float(v), 3) for v in w]); log(f"HP model {t_} W{W} {nm}: word stream {bits / 8:,.0f} bytes ({bits / N:.4f} bits/word, weights {R[nm]['weights']})")
    json.dump(R, open(os.path.join(OUT, f"{t_}_model.json"), "w"), indent=1)
def timed_before(k, t):
    """earlier entries with the same key and a strictly smaller time"""
    o = np.lexsort((t, k)); ks, ts = k[o], t[o]; comb_first = np.r_[0, np.nonzero(ks[1:] != ks[:-1])[0] + 1]; gs = np.repeat(comb_first, np.diff(np.r_[comb_first, len(k)]))
    pos = np.arange(len(k)); same_t_first = pos.copy()
    brk = np.r_[True, (ks[1:] != ks[:-1]) | (ts[1:] != ts[:-1])]; same_t_first = np.maximum.accumulate(np.where(brk, pos, 0))
    r = np.empty(len(k), np.int64); r[o] = same_t_first - gs; return r
if __name__ == "__main__":
    cmd, n = sys.argv[1], int(sys.argv[2])
    split(n) if cmd == "split" else model(n, int(sys.argv[3]) if len(sys.argv) > 3 else 20)
