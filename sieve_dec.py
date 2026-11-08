"""Local decoder for the generation rounds (TEMP, MIX, ...): MS/EXR's A4 sampler (books 27M, 3,072 reversed-prefix
candidates, weight exp(4 x m4), boundaries allowed, copy cap), per-word distribution p(w), optional factors, temperature.
  cfg keys: T (temperature, p^(1/T)); topic (lambda: content words x (P_T(w)/P_U(w))^lambda, trigger over the last 50
  content words of the text, MT's trigger counts); cache (kappa: content words x (1 + kappa x share of w among the text's
  content words / P_U(w))^(1/2)); norep (bool: forbid a trigram already in the text); nounk (bool: never write UNK); depth (D: weight by consecutive exact matches up to D words, not m4).
Index: 8-word reversed prefix (MIX onward; TEMP used 4 words). doc (delta: candidates inside the ndoc (100) training
  passages most similar to the text get weight x e^delta; passages = 1,000-word chunks, tf-idf over content words); cap (6: also no 6-word window from training; needs DEC_H6=1);
  gender (x: pronouns contradicting the held third-person gender of the last 60 words get e^-x); stick (x: inside a clause, the
  candidate continuing the previous word's source passage gets e^x);
  nextsent (k: at a sentence boundary, add as candidates the starts of the sentences that followed the k training sentences most
  similar (tf-idf) to the sentence just written, with weight e^(4 x nsbonus) relative to the best 4-word match; nsctx = sentences used for similarity; needs DEC_SENT=1);
  nclause (k: after a clause word, add the positions after the same word inside the k training sentences most similar to the
  sentence so far, weight e^4 over the best 4-word match; needs DEC_SENT=1);
  tpl (x: with nextsent, hold the class skeleton of the follower of the most similar sentence; matching class at word k x e^x,
  boundary x e^x once the skeleton is used up);
  search ({B, H, C, v}: B rollouts of H words from the same sampler, commit the first C words of the best by verifier v).
Run: py -3.12 -I sieve_dec.py TAG '{"ARM": {cfg}, ...}' [PART]  (PART of DEC_NPARTS: prompts pid % NPARTS == PART)  -> mtest/<tag>_gen.json (40 SW prompts, 50 words, same seed per prompt)"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
C = "books"; NP, LP, LG, HC = int(os.environ.get("DEC_NP", 40)), 30, 50, 1536; M64 = np.uint64(0x9E3779B97F4A7C15); T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def pack4(Q):
    k = np.zeros(len(Q), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | Q[:, i].astype(np.uint64)
    return k
class Dec:
    def __init__(s):
        z = np.load(MT.fp(C, "data")); s.S = S = z["S"].astype(np.int64); s.ntr = ntr = int(z["ntr"]); s.vw = z["vw"]; s.V = len(s.vw) - 1
        PA = np.arange(9, ntr); K1 = pack4(np.stack([S[PA - 1 - i] for i in range(4)], 1)); K2 = pack4(np.stack([S[PA - 5 - i] for i in range(4)], 1)); o = np.lexsort((K2, K1))   # MIX: 8-word reversed prefix
        s.KA = K1[o]; s.KB = K2[o]; s.OA = PA[o]; del K1, K2, o
        s.H8 = np.load(MT.fp(C, "sw_index"))["H8"]; g = np.load(MT.fp(C, "ngram")); n1 = g["n1"].astype(float); s.pU = (n1 + 0.5) / (n1.sum() + 0.5 * len(n1))
        t = np.load(MT.fp(C, "trig")); s.tu, s.tn = t["u"], t["n"]; s.rc = np.bincount(s.tu // MT.VV, weights=s.tn, minlength=MT.VV)
        if os.environ.get("DEC_H6"):                                                                                                     # COH: 6-word copy cap
            St = S[:ntr].astype(np.uint64); n6 = len(St) - 5; a6 = np.zeros(n6, np.uint64); b6 = np.zeros(n6, np.uint64)
            for i in range(4): a6 = (a6 << np.uint64(16)) | St[i:i + n6]
            for i in range(2): b6 = (b6 << np.uint64(16)) | St[4 + i:4 + i + n6]
            with np.errstate(over="ignore"): s.H6 = np.sort((a6 * M64) ^ b6)
            del a6, b6, St
        s.FINE = np.load(os.path.join(MT.OUT, "kaggle_ms", "data", f"{C}_cls.npz"))["fine"]
        wid = {str(w): i for i, w in enumerate(s.vw)}; s.MALE = {wid[w] for w in ("he", "him", "his", "himself") if w in wid}; s.FEM = {wid[w] for w in ("she", "her", "hers", "herself") if w in wid}
        s.CLAUSE = {wid[w] for w in "and but or who which that when while where if because though as so then".split() if w in wid}; s._src = None
        if os.environ.get("DEC_SENT"):                                                                                                   # NSENT: sentence index
            sid = np.cumsum(S[:ntr] == 0); s.sid = sid; s.sstart = np.nonzero(S[:ntr] == 0)[0] + 1; s.sstart = s.sstart[s.sstart < ntr - 1]   # sentence k starts at sstart[k-1]
            cm2 = (S[:ntr] > 100) & (S[:ntr] <= s.V); kk_ = sid[cm2] * MT.VV + S[:ntr][cm2]; u2_, n2_ = np.unique(kk_, return_counts=True); sw_ = u2_ % MT.VV; ss_ = u2_ // MT.VV
            ns_ = int(sid[-1]) + 1; df2 = np.bincount(sw_, minlength=MT.VV); s.sidf = np.log(ns_ / np.maximum(df2, 1)); v2 = s.sidf[sw_]; nr2 = np.sqrt(np.bincount(ss_, weights=v2 ** 2, minlength=ns_)); v2 = v2 / np.maximum(nr2[ss_], 1e-9)
            o2 = np.argsort(sw_, kind="stable"); s.qw, s.qs, s.qv = sw_[o2], ss_[o2], v2[o2]; s.qst = np.searchsorted(s.qw, np.arange(MT.VV + 1)); s.nsent = ns_; del kk_, u2_, n2_, sw_, ss_, v2, o2
        s.CH = 1000; pc = np.arange(ntr); cm = (S[:ntr] > 100) & (S[:ntr] <= s.V); ck = (pc[cm] // s.CH) * MT.VV + S[:ntr][cm]; u_, n_ = np.unique(ck, return_counts=True)   # DOC: passage index (1,000-word chunks)
        ch, w_ = u_ // MT.VV, u_ % MT.VV; nch = ntr // s.CH + 1; df = np.bincount(w_, minlength=MT.VV); idf = np.log(nch / np.maximum(df, 1)); val = np.log1p(n_) * idf[w_]
        nrm = np.sqrt(np.bincount(ch, weights=val ** 2, minlength=nch)); val = val / np.maximum(nrm[ch], 1e-9); o_ = np.argsort(w_, kind="stable")
        s.pw, s.pch, s.pval = w_[o_], ch[o_], val[o_]; s.pst = np.searchsorted(s.pw, np.arange(MT.VV + 1)); s.idf = idf; s.nch = nch
        st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; s.prompts = st[np.linspace(0, len(st) - 1, NP).astype(int)]; log("decoder ready")
    def h8v(s, w7, nx):
        a = np.uint64(0); b = np.uint64(0)
        for i in range(4): a = (a << np.uint64(16)) | np.uint64(w7[i])
        for i in range(3): b = (b << np.uint64(16)) | np.uint64(w7[4 + i])
        with np.errstate(over="ignore"): return (a * M64) ^ ((b << np.uint64(16)) | nx.astype(np.uint64))
    def dist(s, text, cfg):
        S = s.S; r = np.array(text[::-1][:8] + [0] * max(0, 8 - len(text))); q1 = pack4(r[None, :4])[0]; q2 = pack4(r[None, 4:8])[0]
        lo = int(np.searchsorted(s.KA, q1, "left")); hi = int(np.searchsorted(s.KA, q1, "right")); i0 = lo + int(np.searchsorted(s.KB[lo:hi], q2)) if hi > lo else lo
        pos = s.OA[max(i0 - HC, 0):min(i0 + HC, len(s.OA))]; m4 = sum((S[pos - 1 - j] == text[-1 - j]).astype(float) for j in range(4))
        if cfg.get("depth"):
            ok = np.ones(len(pos), bool); dep = np.zeros(len(pos))
            for j in range(cfg["depth"]): ok &= S[pos - 1 - j] == text[-1 - j]; dep += ok
            sc = dep
        else: sc = m4
        if cfg.get("doc"):
            top = s.topchunks(text, cfg.get("ndoc", 100)); sc = sc + cfg["doc"] / 4 * np.isin(pos // s.CH, top)              # DOC: bonus for candidates inside the most similar passages
        if cfg.get("nextsent") and text[-1] == 0:                                                                                  # NSENT: start the next sentence the way similar sentences were followed
            j = len(text) - 2
            for _ in range(cfg.get("nsctx", 1)):                                                                                       # NS3: how many sentences back
                j -= 1 if text[j] == 0 and j < len(text) - 2 else 0
                while j >= 0 and text[j] != 0: j -= 1
            last = [w for w in text[j + 1:-1] if 100 < w <= s.V]
            if last:
                u, n = np.unique(last, return_counts=True); sc_ = np.zeros(s.nsent)
                for w in u:
                    a, b = s.qst[w], s.qst[w + 1]; np.add.at(sc_, s.qs[a:b], s.sidf[w] * s.qv[a:b])
                top = np.argpartition(-sc_, cfg["nextsent"])[:cfg["nextsent"]]; top = top[sc_[top] > 0]
                nxt = top + 1                                                                                                        # the sentence after each similar sentence
                st_ = s.sstart[np.minimum(nxt - 1, len(s.sstart) - 1)]; st_ = st_[(st_ > 9) & (st_ < s.ntr - 1)]
                if len(st_): pos = np.r_[pos, st_]; m4 = np.r_[m4, np.zeros(len(st_))]; sc = np.r_[sc, np.full(len(st_), sc.max() + cfg.get("nsbonus", 1.0))]
                if cfg.get("tpl") and len(top):                                                                                     # TPL: hold the follower sentence's class skeleton
                    k0 = int(top[np.argmax(sc_[top])]); a = s.sstart[min(k0, len(s.sstart) - 1)]; b = a
                    while b < s.ntr and S[b] != 0: b += 1
                    s._tpl = s.FINE[S[a:b]]
        if cfg.get("nclause") and text[-1] in s.CLAUSE:                                                                            # NCL: continue the clause as similar sentences did
            j = len(text) - 2
            while j >= 0 and text[j] != 0: j -= 1
            cur = [w for w in text[j + 1:-1] if 100 < w <= s.V]
            if cur:
                u, n = np.unique(cur, return_counts=True); sc_ = np.zeros(s.nsent)
                for w in u:
                    a, b = s.qst[w], s.qst[w + 1]; np.add.at(sc_, s.qs[a:b], s.sidf[w] * s.qv[a:b])
                top = np.argpartition(-sc_, cfg["nclause"])[:cfg["nclause"]]; top = top[sc_[top] > 0]; add = []
                for k_ in top:
                    a = s.sstart[k_ - 1] if k_ > 0 else 0; b = s.sstart[k_] - 1 if k_ < len(s.sstart) else s.ntr
                    hit = np.nonzero(S[a:b] == text[-1])[0] + a + 1; add.extend(hit[(hit > 9) & (hit < s.ntr - 1)].tolist())
                if add: add = np.array(add); pos = np.r_[pos, add]; m4 = np.r_[m4, np.zeros(len(add))]; sc = np.r_[sc, np.full(len(add), sc.max() + 1.0)]
        if cfg.get("stick") and getattr(s, "_src", None) is not None and text[-1] != 0 and text[-1] not in s.CLAUSE:
            sc = sc + cfg["stick"] / 4 * (pos == s._src + 1)                                                                   # ENT: keep the clause's source passage
        wpos = np.exp(4 * (sc - sc.max())); s._pos, s._wpos = pos, wpos
        uw, inv = np.unique(S[pos], return_inverse=True); p = np.bincount(inv, weights=wpos); s._inv = inv
        hv = s.h8v(text[-7:], uw); bad = s.H8[np.minimum(np.searchsorted(s.H8, hv), len(s.H8) - 1)] == hv
        if (~bad).any(): p = p * ~bad
        if cfg.get("cap") == 6:
            a = np.uint64(0); b = np.uint64(0)
            for i in range(4): a = (a << np.uint64(16)) | np.uint64(text[-5 + i])
            b = np.uint64(text[-1]) << np.uint64(16)
            with np.errstate(over="ignore"): hv6 = (a * M64) ^ (b | uw.astype(np.uint64))
            b6 = s.H6[np.minimum(np.searchsorted(s.H6, hv6), len(s.H6) - 1)] == hv6
            if (~b6).any() and (p * ~b6).sum() > 0: p = p * ~b6
        if cfg.get("gender"):                                                                                                       # ENT: held referent gender
            last = text[-60:]; m = sum(w in s.MALE for w in last); f = sum(w in s.FEM for w in last)
            if m > 0 and f == 0: p = p * np.where(np.isin(uw, list(s.FEM)), np.exp(-cfg["gender"]), 1.0)
            elif f > 0 and m == 0: p = p * np.where(np.isin(uw, list(s.MALE)), np.exp(-cfg["gender"]), 1.0)
        if cfg.get("tpl") and text[-1] == 0 and not cfg.get("nextsent"): s._tpl = None
        if cfg.get("tpl") and getattr(s, "_tpl", None) is not None:
            k = 0
            while k < len(text) and text[-1 - k] != 0: k += 1                                                                      # words written since the boundary
            if k < len(s._tpl): p = p * np.where(s.FINE[uw] == s._tpl[k], np.exp(cfg["tpl"]), 1.0)
            else: p = p * np.where(uw == 0, np.exp(cfg["tpl"]), 1.0)
        if cfg.get("nounk") and (uw <= s.V).any(): p = p * (uw <= s.V)
        con = (uw > 100) & (uw <= s.V)
        if cfg.get("topic") and con.any():
            W = [w for w in text if 100 < w <= s.V][-50:]; W = [w for w in W if s.rc[w] > 0]
            if W:
                pT = np.zeros(con.sum())
                for w in W: pT += MT.look(s.tu, s.tn, w * MT.VV + uw[con]) / s.rc[w]
                p[con] *= ((pT / len(W) + 1e-6) / (s.pU[uw[con]] + 1e-6)) ** cfg["topic"]
        if cfg.get("cache") and con.any():
            hist = [w for w in text if 100 < w <= s.V]
            if hist:
                u_, n_ = np.unique(hist, return_counts=True); sh = MT.look(u_, n_, uw[con]) / len(hist); p[con] *= np.sqrt(1 + cfg["cache"] * sh / s.pU[uw[con]])
        if cfg.get("norep"):
            seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}; rep = np.array([(text[-2], text[-1], int(w)) in seen for w in uw])
            if (~rep).any() and (p * ~rep).sum() > 0: p = p * ~rep
        p = p ** (1.0 / cfg.get("T", 1.0)) if cfg.get("T", 1.0) != 1.0 else p
        return uw, p / p.sum()
    def topchunks(s, text, k):
        """the k training passages (1,000-word chunks) most similar (tf-idf cosine) to the text's content words; cached per 10 words"""
        key = len(text) // 10
        if getattr(s, "_tk", None) == (key, id(text)): return s._tc
        cw = [w for w in text if 100 < w <= s.V]; u, n = np.unique(cw, return_counts=True); q = np.log1p(n) * s.idf[u]; sc = np.zeros(s.nch)
        for w, qv in zip(u, q):
            a, b = s.pst[w], s.pst[w + 1]; np.add.at(sc, s.pch[a:b], qv * s.pval[a:b])
        s._tk = (key, id(text)); s._tc = np.argpartition(-sc, k)[:k]; return s._tc
    def verify(s, text, R, kind):
        """SRCH verifier for rollouts R (list of word lists): topic = mean log(P_T / P_U) of the rollout's content words given the
        text's last 50 content words (trigger counts); both = topic + 4 x share of the rollout's trigrams (2 words of context) seen in training"""
        if not hasattr(s, "u3"): s.u3 = np.load(MT.fp(C, "ngram"))["u3"]
        W = [w for w in text if 100 < w <= s.V][-50:]; W = [w for w in W if s.rc[w] > 0]; out = np.zeros(len(R))
        for i, r in enumerate(R):
            y = np.array([w for w in r if 100 < w <= s.V])
            if len(y) and W:
                pT = np.zeros(len(y))
                for w in W: pT += MT.look(s.tu, s.tn, w * MT.VV + y) / s.rc[w]
                out[i] = np.log((pT / len(W) + 1e-6) / (s.pU[y] + 1e-6)).mean()
            if kind == "both":
                e = list(text[-2:]) + list(r); k = np.array([(e[j] * MT.VV + e[j + 1]) * MT.VV + e[j + 2] for j in range(len(r))], np.int64)
                out[i] += 4 * float((MT.look(s.u3, np.ones(len(s.u3), np.int64), k) > 0).mean())
        return out
    def gen(s, prompt, cfg, seed):
        g = np.random.default_rng(seed); text = list(prompt); sr = cfg.get("search"); s._src = None; s._tpl = None
        while len(text) - len(prompt) < LG:
            if not sr:
                uw, p = s.dist(text, cfg); k = int(g.choice(len(uw), p=p)); text.append(int(uw[k]))
                cand = np.nonzero(s._inv == k)[0]; s._src = int(s._pos[cand[g.choice(len(cand), p=s._wpos[cand] / s._wpos[cand].sum())]]) if len(cand) else None   # ENT: source of the written word
                continue
            R = []
            for _ in range(sr["B"]):
                t2 = list(text)
                for _ in range(sr["H"]):
                    uw, p = s.dist(t2, cfg); t2.append(int(uw[g.choice(len(uw), p=p)]))
                R.append(t2[len(text):])
            text.extend(R[int(np.argmax(s.verify(text, R, sr["v"])))][:sr["C"]])
        return text[len(prompt):len(prompt) + LG]
    def words(s, ids): return " ".join("." if i == 0 else "<unk>" if i > s.V else str(s.vw[i]) for i in ids).replace(" .", ".")
def run(tag, arms, part=None):
    d = Dec(); G = []; nparts = int(os.environ.get("DEC_NPARTS", 1))
    for pid, t in enumerate(d.prompts):
        if part is not None and pid % nparts != part: continue
        pr = d.S[t:t + LP].tolist(); G.append(dict(pid=pid, B="truth", prompt=d.words(pr), text=d.words(d.S[t + LP:t + LP + LG]), ids=d.S[t + LP:t + LP + LG].tolist()))
        for arm, cfg in arms.items():
            ids = d.gen(pr, cfg, 1000 * pid + 7); G.append(dict(pid=pid, B=arm, prompt=d.words(pr), text=d.words(ids), ids=ids))
        if pid % 10 == 0: log(f"prompt {pid}: " + " | ".join(f"{x['B']}: {x['text'][:60]}" for x in G[-len(arms):]))
        if part is not None: json.dump(G, open(os.path.join(MT.OUT, f"{tag}_gen_p{part}.json"), "w"), indent=0)
    out = os.path.join(MT.OUT, f"{tag}_gen.json" if part is None else f"{tag}_gen_p{part}.json"); json.dump(G, open(out, "w"), indent=0); log(f"saved {out}: {len(G)} items")
if __name__ == "__main__": run(sys.argv[1], json.loads(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else None)
