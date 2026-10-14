"""R25-cs: combining operators over full distributions. Event space: the 65,534 most frequent training words plus one
rare bucket (a rare target then pays its share of the rare mass, the same for every operator). Components, all
reading the held-out paragraphs in order: K (Kneser-Ney o5mxa, from its saved context index), B (static network
r25_ch), D (the same network adapted by one SGD step per read paragraph, step 0.3), copy memories Y (0.99), Z (0.9999),
keyed by the previous word V (0.9999) and U (0.999), by two words N2 and three words N3 (0.9999). A memory whose key
is new is inactive and its weight goes to the others. Operators (power mean of order alpha, then normalised over the
whole vocabulary): alpha 1 (linear), 0.5 (square root), 0.25, and 0 (geometric / log-linear: exp of a weighted sum
of natural logs; sparse memories are first floored with 1% of K so no word gets zero). Weights fit on a sample of
600 predictions of paragraphs 0-499; scored exactly on every prediction of 500-999. Run: py -3.12 r25_logmix.py"""
import os, sys, math, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--threads", "4", "--groups-file", "r25_classes_wnx.json"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
torch, nn, g, encode, gw, unk2, _uni, _cnt, UNKG, NG = (R[k] for k in "torch nn g encode gw unk2 _uni _cnt UNKG NG".split())
import numpy as np
np.seterr(over="ignore", divide="ignore"); t0 = time.time()
X = np.load("r25_kn2_o5mxax_index.npz") if os.path.exists("r25_kn2_o5mxax_index.npz") else np.load("r25_kn2_o5mxa_index.npz")
top = X["words"].tolist(); V = len(top) + 1; RB = V - 1; eid = {w: i for i, w in enumerate(top)}               # event ids: words 0..65533, rare bucket 65534
NMAX = int(X["nmax"]); TOT1 = float(X["TOT1"]); C1disc = float(X["C1disc"]); MUL = np.uint64(0x9E3779B97F4A7C15)
Dn = {n: X[f"D{n}"] for n in range(1, NMAX + 1)}
c1 = X["cnt1"]; p1 = np.full(65536, C1disc / TOT1 / 65536); np.add.at(p1, X["wd1"].astype(np.int64), np.maximum(c1 - Dn[1][np.minimum(c1, 3) - 1], 0) / TOT1)
IX = {n: (X[f"ctx{n}"], X[f"wd{n}"].astype(np.int64), X[f"cnt{n}"], X[f"hu{n}"], X[f"tot{n}"], X[f"dm{n}"]) for n in range(2, NMAX + 1)}
print(f"R25-cs-t index loaded ({time.time() - t0:.0f} s)", flush=True)
def hlist(ids):
    h = np.uint64(0)
    for j, x in enumerate(ids): h = (h ^ np.uint64(x)) * MUL + np.uint64(j + 1)
    return h
def kn_full(prev):                                                                         # prev: kn word ids (1..65535), 0 = paragraph start
    p = p1.copy()
    for n in range(2, NMAX + 1):
        if len(prev) < n - 1: break
        hc = hlist(prev[-(n - 1):]); ctx, wd, cnt, hu, tot, dm = IX[n]; i = np.searchsorted(hu, hc)
        if i >= len(hu) or hu[i] != hc: break
        lo, hi = np.searchsorted(ctx, hc, "left"), np.searchsorted(ctx, hc, "right"); c = cnt[lo:hi]
        p *= dm[i] / tot[i]; p[wd[lo:hi]] += np.maximum(c - Dn[n][np.minimum(c, 3) - 1], 0) / tot[i]
    return p[1:]                                                                            # kn ids 1..65535 -> events 0..65534 (65535 = rare = event 65534)
# network: event -> group and within-group factor; rare bucket through its words' groups
grp = np.array([gw(w) for w in top]); fac = np.array([(_uni[w] + 0.5) / _cnt[gw(w)] if gw(w) != UNKG else 2 ** -unk2(w) for w in top])
Srare = np.zeros(NG)
for w in _uni:
    if w not in eid: gg = gw(w); Srare[gg] += (_uni[w] + 0.5) / _cnt[gg] if gg != UNKG else 2 ** -unk2(w)
def net_full(lp_row):
    pg = np.exp(lp_row); return np.r_[pg[grp] * fac, pg @ Srare]
rare_tot = float(X["rare_mass"]) + 0.5 * float(X["n_rare"])
def rare_bits(w): return -math.log2(max((_uni.get(w, 0) + 0.5) / rare_tot, 1e-12))
# copy memories over events
class Plain:
    def __init__(s, dec): s.dec, s.m, s.tot, s.sc = dec, np.zeros(V), 0.0, 1.0
    def full(s, hist): return s.m / s.tot if s.tot else None
    def add(s, hist, e):
        s.sc /= s.dec; s.m[e] += s.sc; s.tot += s.sc
        if s.sc > 1e200: s.m /= s.sc; s.tot /= s.sc; s.sc = 1.0
class Keyed:
    def __init__(s, dec, n): s.dec, s.n, s.d, s.t, s.sc = dec, n, collections.defaultdict(dict), collections.defaultdict(float), 1.0
    def full(s, hist):
        if len(hist) < s.n: return None
        k = tuple(hist[-s.n:])
        if not s.t.get(k): return None
        v = np.zeros(V); d = s.d[k]; v[list(d)] = np.array(list(d.values())) / s.t[k]; return v
    def add(s, hist, e):
        if len(hist) < s.n: return
        k = tuple(hist[-s.n:]); s.sc /= s.dec; s.d[k][e] = s.d[k].get(e, 0.0) + s.sc; s.t[k] += s.sc
        if s.sc > 1e200:
            for kk in s.d:
                for ee in s.d[kk]: s.d[kk][ee] /= s.sc
                s.t[kk] /= s.sc
            s.sc = 1.0
NAMES = ["K", "B", "D", "Y", "Z", "V", "U", "N2", "N3"]; SPARSE = set(NAMES[3:])
mems = [Plain(0.99), Plain(0.9999), Keyed(0.9999, 1), Keyed(0.999, 1), Keyed(0.9999, 2), Keyed(0.9999, 3)]
ALPHAS = [1.0, 0.5, 0.25, 0.0]; LAM = 0.01
def combine(P, act, w, a):                                                                  # P: list of full vectors (None = inactive); w: weights for all
    ws = np.array([w[i] if act[i] else 0.0 for i in range(len(P))]); ws /= ws.sum()
    if a == 0:
        lq = sum(ws[i] * np.log((P[i] + LAM * P[0]) / (1 + LAM) if NAMES[i] in SPARSE else P[i]) for i in range(len(P)) if act[i])
        lq -= lq.max(); q = np.exp(lq)
    else: q = sum(ws[i] * P[i] ** a for i in range(len(P)) if act[i]) ** (1 / a)
    return q / q.sum()
# networks
nets = []
for _ in range(2):
    torch.manual_seed(0); n_ = R["RNet"](); n_.load_state_dict(torch.load("r25_ch.pt")); n_.eval(); nets.append(n_)
opt = torch.optim.SGD(nets[1].parameters(), lr=0.3); hs = [None, None]
paras = g["tep"][:1000]; SAMPLE_EVERY = 41
samp, res, W = [], {a: [] for a in ALPHAS}, None
pidx = 0; HIST = []
for pi, p in enumerate(paras):
    if pi == 500:                                                                           # fit weights on the sample from 0-499
        LP = torch.tensor(np.stack([s[0] for s in samp]), dtype=torch.float16); ACT = torch.tensor(np.stack([s[1] for s in samp])); TG = torch.tensor([s[2] for s in samp])
        W = {}
        for a in ALPHAS:
            th = torch.zeros(len(NAMES), requires_grad=True); o = torch.optim.Adam([th], lr=0.15)
            for it in range(60):
                o.zero_grad(); tot = 0.0
                for c0 in range(0, len(LP), 100):
                    lp = LP[c0:c0 + 100].float(); act = ACT[c0:c0 + 100]; tg = TG[c0:c0 + 100]
                    lw = th.expand(len(lp), -1).masked_fill(~act, -1e30)
                    lw = lw - torch.logsumexp(lw, 1, keepdim=True)
                    if a == 0:
                        lk = lp[:, 0:1, :]; sp = torch.tensor([nm in SPARSE for nm in NAMES]).view(1, -1, 1)
                        lpf = torch.where(sp, torch.logaddexp(lp, lk + math.log(LAM)) - math.log(1 + LAM), lp).clamp(min=-1e4)
                        lq = (lw.exp().unsqueeze(2) * torch.where(act.unsqueeze(2), lpf, torch.zeros_like(lpf))).sum(1)
                    else:
                        lq = torch.logsumexp(lw.unsqueeze(2) + a * lp, 1) / a
                    nll = -(lq.gather(1, tg.view(-1, 1)).squeeze(1) - torch.logsumexp(lq, 1)).sum() / math.log(2)
                    nll.backward(); tot += nll.item()
                o.step()
            W[a] = torch.softmax(th.detach(), 0).numpy(); print(f"R25-cs-t alpha {a}: sample {tot / len(LP):.4f} bits, weights {dict(zip(NAMES, W[a].round(3)))} ({time.time() - t0:.0f} s)", flush=True)
        del LP
    a_, mask = encode(p); words = [x for s in p for x in s]; x = torch.tensor([a_])
    with torch.no_grad(): o0, hs[0] = nets[0].rnn(nets[0].inp(nets[0].emb(x)), hs[0]); lpB = torch.log_softmax(nets[0].out(nets[0].out_ln(o0))[0], -1).numpy()
    o1, hn = nets[1].rnn(nets[1].inp(nets[1].emb(x)), hs[1]); lpDt = torch.log_softmax(nets[1].out(nets[1].out_ln(o1))[0], -1); lpD = lpDt.detach().numpy()
    kprev = [0]; ev = [eid.get(w, RB) for w in words]; idx = []
    for k in range(len(words)):
        if mask[k] and k >= 1:
            e = ev[k]
            if not (pi >= 500 or pidx % SAMPLE_EVERY == 0): pidx += 1; idx.append(k); kprev.append(ev[k] + 1); [m.add(HIST, ev[k]) for m in mems]; HIST.append(ev[k]); continue
            P = [kn_full(kprev[-(NMAX - 1):]), net_full(lpB[k - 1]), net_full(lpD[k - 1])] + [m.full(HIST) for m in mems]
            act = np.array([q is not None for q in P]); P = [q if q is not None else np.zeros(V) for q in P]
            if pi < 500 and pidx % SAMPLE_EVERY == 0: samp.append((np.stack([np.log(np.maximum(q, 1e-30)) for q in P]).astype(np.float16), act, e))
            if pi >= 500:
                extra = rare_bits(words[k]) if e == RB else 0.0
                for a in ALPHAS: res[a].append(-math.log2(max(combine(P, act, W[a], a)[e], 1e-300)) + extra)
            pidx += 1; idx.append(k)
        kprev.append(ev[k] + 1)
        for m in mems: m.add(HIST, ev[k])
        HIST.append(ev[k])
    if idx:
        loss = -lpDt[[k - 1 for k in idx], [gw(words[k]) for k in idx]].mean(); opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(nets[1].parameters(), 1.0); opt.step()
    hs[1] = hn.detach()
    if pi % 100 == 99: print(f"  paragraph {pi + 1} ({time.time() - t0:.0f} s)" + ("".join(f" | alpha {a}: {np.mean(res[a]):.4f}" for a in ALPHAS) if pi >= 500 else ""), flush=True)
for a in ALPHAS: print(f"R25-cs-t alpha {a}: paragraphs 500-999 {np.mean(res[a]):.4f} bits/word over {len(res[a])} predictions", flush=True)
