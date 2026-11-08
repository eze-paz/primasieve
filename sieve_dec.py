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
  holdw (x: hold the content words that followed the training sentence most similar to the prompt, head word x e^x until
  written, released after 12 words; needs DEC_SENT=1);
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
        s.PRON = {wid[w] for w in "he she they i we it you".split() if w in wid}; s._msn = 0; s._mst = 0
        if os.environ.get("DEC_SENT"):                                                                                                   # NSENT: sentence index
            sid = np.cumsum(S[:ntr] == 0); s.sid = sid; s.sstart = np.nonzero(S[:ntr] == 0)[0] + 1; s.sstart = s.sstart[s.sstart < ntr - 1]   # sentence k starts at sstart[k-1]
            cm2 = (S[:ntr] > 100) & (S[:ntr] <= s.V); kk_ = sid[cm2] * MT.VV + S[:ntr][cm2]; u2_, n2_ = np.unique(kk_, return_counts=True); sw_ = u2_ % MT.VV; ss_ = u2_ // MT.VV
            ns_ = int(sid[-1]) + 1; df2 = np.bincount(sw_, minlength=MT.VV); s.sidf = np.log(ns_ / np.maximum(df2, 1)); v2 = s.sidf[sw_]; nr2 = np.sqrt(np.bincount(ss_, weights=v2 ** 2, minlength=ns_)); v2 = v2 / np.maximum(nr2[ss_], 1e-9)
            o2 = np.argsort(sw_, kind="stable"); s.qw, s.qs, s.qv = sw_[o2], ss_[o2], v2[o2]; s.qst = np.searchsorted(s.qw, np.arange(MT.VV + 1)); s.nsent = ns_; del kk_, u2_, n2_, sw_, ss_, v2, o2
        s.CH = 1000; pc = np.arange(ntr); cm = (S[:ntr] > 100) & (S[:ntr] <= s.V); ck = (pc[cm] // s.CH) * MT.VV + S[:ntr][cm]; u_, n_ = np.unique(ck, return_counts=True)   # DOC: passage index (1,000-word chunks)
        ch, w_ = u_ // MT.VV, u_ % MT.VV; nch = ntr // s.CH + 1; df = np.bincount(w_, minlength=MT.VV); idf = np.log(nch / np.maximum(df, 1)); val = np.log1p(n_) * idf[w_]
        nrm = np.sqrt(np.bincount(ch, weights=val ** 2, minlength=nch)); val = val / np.maximum(nrm[ch], 1e-9); o_ = np.argsort(w_, kind="stable")
        s.pw, s.pch, s.pval = w_[o_], ch[o_], val[o_]; s.pst = np.searchsorted(s.pw, np.arange(MT.VV + 1)); s.idf = idf; s.nch = nch
        if os.environ.get("DEC_HS"):                                                                                                     # HGH: learned oscillator states (sieve_hs_part.py)
            hd = os.environ["DEC_HS"]; s.HS = np.load(os.path.join(hd, "hs_states.npy"), mmap_mode="r"); pz = np.load(os.path.join(hd, "hs_proj.npz")); s.HSmu = pz["mu"].astype(np.float32)
            os.environ["HARM_ARMS"] = ""; os.environ.setdefault("HARM_DATA", MT.fp(C, "data")); import torch, sieve_harm_kernel as HK; s.torch, s.HK = torch, HK
            HK.PROJ = torch.from_numpy(pz["proj"]); s.hb = HK.OLM("HBlearn"); s.hb.load_state_dict(torch.load(os.environ["DEC_HB"], map_location="cpu")); s.hb.eval(); torch.set_num_threads(4)
            s._hgc = []; s._hgs = []
        st = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; s.prompts = st[np.minimum(np.linspace(0, len(st) - 1, NP).astype(int) + int(os.environ.get("DEC_POFF", 0)), len(st) - 1)]; log("decoder ready")
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
        wpos = np.exp(4 * (sc - sc.max())); cs = None
        if cfg.get("hh") or cfg.get("hg") or cfg.get("hgcal"):                                                                      # HGH: cosine of each source's state with the text's
            v = s.tstate(text); X = s.HS[pos - 1].astype(np.float32) - s.HSmu
            if cfg.get("hgw"):                                                                                                     # JT: learned readout W
                if getattr(s, "_Wp", None) != cfg["hgw"]: s._Wp = cfg["hgw"]; s._W = np.load(cfg["hgw"]).astype(np.float32)
                X = X @ s._W.T; v = s._W @ v
            cs = X @ v / (np.linalg.norm(X, axis=1) * np.linalg.norm(v) + 1e-9)
            if cfg.get("hh"): wpos = wpos * np.exp(cfg["hh"] * (cs - cs.mean()) / (cs.std() + 1e-9))
        s._pos, s._wpos = pos, wpos
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
        if cfg.get("holdw") and getattr(s, "_plan", None):                                                                         # HOLDW: the held planned word
            while s._plan and s._held_for >= 12: s._plan.pop(0); s._held_for = 0
            if s._plan:
                h = s._plan[0]
                if h in uw: p = p * np.where(uw == h, np.exp(cfg["holdw"]), 1.0)
                elif cfg.get("inject"):                                                                                                # HW2: bigram-licensed injection
                    if not hasattr(s, "u2"): g_ = np.load(MT.fp(C, "ngram")); s.u2, s.n2 = g_["u2"], g_["n2"]
                    if MT.look(s.u2, s.n2, np.array([text[-1] * MT.VV + h]))[0] >= 2 and not (s.H8[min(np.searchsorted(s.H8, s.h8v(text[-7:], np.array([h]))[0]), len(s.H8) - 1)] == s.h8v(text[-7:], np.array([h]))[0]):
                        uw = np.r_[uw, h]; p = np.r_[p, p.max()]
        if cfg.get("nounk") and (uw <= s.V).any(): p = p * (uw <= s.V)
        con = (uw > 100) & (uw <= s.V)
        if cfg.get("ms") and con.any():                                                                                             # MEAN: license new content words by the held ones
            E = s.held_entities(text); U = s._msU
            if len(U):
                for i in np.nonzero(con)[0]:
                    c = int(uw[i])
                    if c in E or s.idf[c] < 2: continue                                                                              # held, or a very common word: licensed
                    sl = s.pch[s.pst[c]:s.pst[c + 1]]; co = int((U[np.minimum(np.searchsorted(U, sl), len(U) - 1)] == sl).sum()); ex = len(sl) * len(U) / s.nch
                    if (co + 1) / (ex + 1) < cfg.get("mslift", 1.0): p[i] *= np.exp(-cfg["ms"]); s._msn += 1
                s._mst += int(con.sum())
        if (cfg.get("hg") or cfg.get("hgcal")) and con.any():                                                                     # HG: licence by the oscillator state
            E = s.held_entities(text); cc = np.bincount(inv, weights=cs, minlength=len(uw)) / np.maximum(np.bincount(inv, minlength=len(uw)), 1)
            el = np.array([bool(con[i]) and int(uw[i]) not in E and s.idf[int(uw[i])] >= 2 for i in range(len(uw))])
            if cfg.get("hgcal"):
                nx = cfg["hgcal"][0]
                if nx in uw and el[np.searchsorted(uw, nx)]: s._hgc.append(float(cc[np.searchsorted(uw, nx)]))
                q = p * el
                if q.sum() > 0: s._hgs.append(float(cc[cfg["hgcal"][1].choice(len(uw), p=q / q.sum())]))
            if cfg.get("hg"):
                bad = el & (cc < cfg["hgtau"]); p = p * np.where(bad, np.exp(-cfg["hg"]), 1.0); s._msn += int(bad.sum()); s._mst += int(con.sum())
        if cfg.get("msubj") and text[-1] == 0:                                                                                      # MEAN: keep the subject of the last sentence
            j = len(text) - 2
            while j >= 0 and text[j] != 0: j -= 1
            if j + 1 < len(text) - 1:
                subj = text[j + 1]
                if (subj in s.PRON or 100 < subj <= s.V) and subj in uw: p = p * np.where(uw == subj, np.exp(cfg["msubj"]), 1.0)
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
    def tstate(s, text):
        if getattr(s, "_tsk", None) == tuple(text): return s._tsv
        with s.torch.no_grad(): f = s.HK.hstate(s.hb, s.torch.as_tensor([min(w, s.V + 1) for w in text])[None])[0, -1].float().numpy()
        s._tsk = tuple(text); s._tsv = f - s.HSmu; return s._tsv
    def held_entities(s, text):
        """MEAN: held content words = those with passage idf >= 2 among the text's last 60 content words; U = sorted ids of the
        1,000-word training passages containing any of them (cached until the set changes). A new content word is licensed when
        it occurs in those passages at least as often as chance: (co + 1) / (expected + 1) >= mslift."""
        E = frozenset(w for w in [w for w in text if 100 < w <= s.V][-60:] if s.idf[w] >= 2)
        if getattr(s, "_msE", None) != E:
            s._msE = E; s._msU = np.unique(np.concatenate([s.pch[s.pst[w]:s.pst[w + 1]] for w in E])) if E else np.zeros(0, np.int64)
        return E
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
        g = np.random.default_rng(seed); text = list(prompt); sr = cfg.get("search"); s._src = None; s._tpl = None; s._plan = None; s._held_for = 0
        if cfg.get("holdw"):                                                                                                         # HOLDW: plan from the most similar training sentence's follower
            cw = [w for w in prompt if 100 < w <= s.V]; u = np.unique(cw); sc_ = np.zeros(s.nsent)
            for w in u:
                a, b = s.qst[w], s.qst[w + 1]; np.add.at(sc_, s.qs[a:b], s.sidf[w] * s.qv[a:b])
            k0 = int(np.argmax(sc_)); st0 = s.sstart[min(k0, len(s.sstart) - 1)]; fol = s.S[st0:min(st0 + 60, s.ntr)]
            s._plan = [int(w) for w in fol if 100 < w <= s.V]; s._plan0 = list(s._plan)
        while len(text) - len(prompt) < LG:
            if not sr:
                uw, p = s.dist(text, cfg); k = int(g.choice(len(uw), p=p)); text.append(int(uw[k]))
                if s._plan:
                    if text[-1] == s._plan[0]: s._plan.pop(0); s._held_for = 0
                    else: s._held_for += 1
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
            if cfg.get("hg"): G[-1]["hg_penalized"] = d._msn; G[-1]["hg_content_cands"] = d._mst; d._msn = d._mst = 0
            if cfg.get("ms"): G[-1]["ms_penalized"] = d._msn; G[-1]["ms_content_cands"] = d._mst; d._msn = d._mst = 0
            if cfg.get("holdw"): G[-1]["plan"] = d.words(d._plan0); G[-1]["plan_written"] = float(np.mean([w in ids for w in d._plan0])) if d._plan0 else 0.0
        if pid % 10 == 0: log(f"prompt {pid}: " + " | ".join(f"{x['B']}: {x['text'][:60]}" for x in G[-len(arms):]))
        if part is not None: json.dump(G, open(os.path.join(MT.OUT, f"{tag}_gen_p{part}.json"), "w"), indent=0)
    out = os.path.join(MT.OUT, f"{tag}_gen.json" if part is None else f"{tag}_gen_p{part}.json"); json.dump(G, open(out, "w"), indent=0); log(f"saved {out}: {len(G)} items")
def hgcal():
    """HG calibration: tau = median cosine of the true next content word over true continuations (B's candidate sets);
    also the median for words sampled from B's distribution over the same eligible candidates"""
    d = Dec(); cfg = {"T": 0.35, "nounk": 1, "norep": 1}; g = np.random.default_rng(0)
    if os.environ.get("DEC_HGW"): cfg["hgw"] = os.environ["DEC_HGW"]
    for pid, t in enumerate(d.prompts):
        pr = d.S[t:t + LP + LG].tolist()
        for j in range(LP, LP + LG): d.dist(pr[:j], dict(cfg, hgcal=(pr[j], g)))
        if pid % 10 == 0: log(f"cal prompt {pid}: true {len(d._hgc)} median {np.median(d._hgc):.4f}; sampled median {np.median(d._hgs):.4f}")
    out = dict(tau=float(np.median(d._hgc)), n_true=len(d._hgc), sampled_median=float(np.median(d._hgs)), n_sampled=len(d._hgs))
    json.dump(out, open(os.path.join(HERE, "sieve_jt_tau.json" if os.environ.get("DEC_HGW") else "sieve_hgh_tau.json"), "w"), indent=1); log(json.dumps(out))
if __name__ == "__main__" and sys.argv[1] == "hgcal": hgcal(); sys.exit()
if __name__ == "__main__": run(sys.argv[1], json.loads(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else None)
