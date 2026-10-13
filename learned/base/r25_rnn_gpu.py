"""R25-aw: a brain-like next-word network -- a running state read word by word, plus a small sparse look-up.
Owner's order (2026-10-12): replace the 8-hour attention run with this. Same word vectors as starting embeddings, same
filtered training text (13.0M tokens), same width (128), same vocabulary and unknown-word charge, same held-out
predictions as R25-ar. Two layers of recurrent state (GRU) read the words in order; the look-up (--lookup K) lets the
current state fetch the K best-matching earlier moments of the same paragraph by a single similarity match (one cue,
sparse, like cue-based retrieval in reading), and adds what it fetched to the state. --lookup 0 = running state only.
Held-out paragraphs are read whole (the state carries through the paragraph; the look-up sees every earlier word).
Then the language model's 47,478 matched predictions (sentence scope). Run: py -3.12 r25_rnn.py --minutes M --lookup K --out F"""
import os, sys, math, time, random
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]  # data, vocabulary, unknown-word charge
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
np, torch, nn, T, B, D0 = g["np"], g["torch"], g["nn"], g["T"], g["B"], g["D0"]
vocab, z, vi, unk_bits, encode, train, tep, t0 = g["vocab"], g["z"], g["vi"], g["unk_bits"], g["encode"], g["train"], g["tep"], g["t0"]
opt_ = lambda k, d: type(d)(ARGV[ARGV.index(k) + 1]) if k in ARGV else d
MIN, K, OUT = opt_("--minutes", 75.0), opt_("--lookup", 4), opt_("--out", "r25_rnn.pt")
GROUPS = "--groups" in ARGV                                                                 # R25-be: the network predicts the learner's word group; a count table picks the word in it
if GROUPS:
    import json as _json, collections
    _cl = _json.load(open(opt_("--groups-file", "r25_classes.json"), encoding="utf-8")); _ids = sorted(set(_cl.values())); _gi = {c: i for i, c in enumerate(_ids)}
    REST, UNKG = len(_ids), len(_ids) + 1; NG = len(_ids) + 2; _uni = g["uni"]
    G = torch.tensor([UNKG] + [_gi.get(_cl.get(w), REST) for w in vocab], dtype=torch.long)
    _cnt = collections.Counter()
    for i, w in enumerate(vocab): _cnt[int(G[i + 1])] += _uni[w] + 0.5
    LW = torch.tensor([0.0] + [math.log((_uni[w] + 0.5) / _cnt[int(G[i + 1])]) for i, w in enumerate(vocab)])
    G, LW = G.to(DEV), LW.to(DEV)
CTX, D, LAYERS, BATCH = 64, 128, 2, 32
HS, STEPS = opt_("--hidden", 128), opt_("--steps", 0)                                       # R25-bb: a wider running state (projected back to 128); a fixed step budget
torch.manual_seed(0); random.seed(0)
DEV = torch.device("cuda" if torch.cuda.is_available() else "cpu")                 # GPU copy (Colab)
if "--threads" in ARGV: torch.set_num_threads(opt_("--threads", 6))


class RNet(nn.Module):
    def __init__(s):
        super().__init__()
        E = np.zeros((len(vocab) + 1, 100), dtype=np.float32); E[1:] = z["vecs"][:len(vocab)]
        s.emb = nn.Embedding(len(vocab) + 1, 100); s.emb.weight.data = torch.tensor(E)
        s.inp = nn.Linear(100, D); s.rnn = nn.GRU(D, HS, LAYERS, batch_first=True, dropout=0.1)
        if HS != D: s.proj = nn.Linear(HS, D)
        s.q = nn.Linear(D, D); s.k = nn.Linear(D, D); s.v = nn.Linear(D, D); s.mix = nn.Linear(D, D)
        s.out_ln = nn.LayerNorm(D); s.out = nn.Linear(D, NG if GROUPS else len(vocab) + 1); s.drop = nn.Dropout(0.1)
    def forward(s, x):
        h, _ = s.rnn(s.drop(s.inp(s.emb(x))))                                             # the running state, word by word
        if HS != D: h = s.proj(h)
        if K > 0:
            L = x.shape[1]; sc = (s.q(h) @ s.k(h).transpose(1, 2)) / math.sqrt(D)
            sc = sc.masked_fill(torch.triu(torch.ones(L, L, dtype=torch.bool), 1), float("-inf"))
            kk = min(K, L); top = sc.topk(kk, -1)                                          # only the K best-matching earlier moments
            keep = torch.full_like(sc, float("-inf")).scatter(-1, top.indices, top.values)
            h = h + s.mix(torch.softmax(keep, -1) @ s.v(h))
        return s.out(s.out_ln(h))


net = RNet().to(DEV); optm = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=0.01); lossf = nn.CrossEntropyLoss(reduction="none")
if "--resume" in ARGV and os.path.exists(OUT): net.load_state_dict(torch.load(OUT, map_location=DEV)); print(f"R25-aw resumed from {OUT}", flush=True)
print(f"R25-aw model (look-up {K}): {sum(p.numel() for p in net.parameters()):,} parameters", flush=True)
def windows(ids, mask):
    for st in range(0, max(1, len(ids) - 1), CTX):
        a = ids[max(0, st - 1):st + CTX]; m = mask[max(0, st - 1):st + CTX]
        if len(a) >= 2: yield a, m
pool = [w for a, m in train for w in windows(a, m)]; step = 0; net.train(); t1 = time.time()
while (step < STEPS) if STEPS else (time.time() - t1 < MIN * 60):
    batch = random.sample(pool, BATCH); L = max(len(a) for a, _ in batch)
    x = torch.zeros((BATCH, L - 1), dtype=torch.long); y = torch.zeros((BATCH, L - 1), dtype=torch.long); w8 = torch.zeros((BATCH, L - 1))
    for i, (a, m) in enumerate(batch):
        x[i, :len(a) - 1] = torch.tensor(a[:-1]); y[i, :len(a) - 1] = torch.tensor(a[1:]); w8[i, :len(a) - 1] = 1.0
    x, y, w8 = x.to(DEV), y.to(DEV), w8.to(DEV)
    if GROUPS: y = G[y]
    out = net(x); loss = (lossf(out.reshape(-1, out.shape[-1]), y.reshape(-1)) * w8.reshape(-1)).sum() / w8.sum()
    optm.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.0); optm.step(); step += 1
    if "--decay" in ARGV:                                                                 # R25-az: learning rate falls linearly to zero over the time budget
        for g_ in optm.param_groups: g_["lr"] = 1e-3 * max(0.0, 1 - (time.time() - t1) / (MIN * 60))
    if step % 200 == 0: print(f"  step {step}: training loss {loss.item() / math.log(2):.3f} bits/token ({time.time() - t1:.0f} s)", flush=True)
    if step % 500 == 0: torch.save(net.state_dict(), OUT)
torch.save(net.state_dict(), OUT); net.eval()
tot = 0.0; n = 0
with torch.no_grad():
    for p in tep[:opt_("--eval-paras", len(tep))]:
        ids, mask = encode(p); words = [x for s in p for x in s]
        if len(ids) < 2: continue
        lp = torch.log_softmax(net(torch.tensor([ids[:-1]], device=DEV))[0], -1)
        if GROUPS: lp = lp[:, G] + LW                                                     # word = its group's probability x its share inside the group
        for k in range(1, len(ids)):
            if not mask[k]: continue
            b = -lp[k - 1, ids[k]].item() / math.log(2)
            if ids[k] == 0: b += unk_bits(words[k])
            tot += b; n += 1
print(f"R25-aw network (look-up {K}) after {step} steps: held-out paragraphs {tot / n:.4f} bits/word over {n} predictions ({time.time() - t1:.0f} s training+scoring)", flush=True)
def sents_of(paras):
    for p in paras:
        for s in T.SENT.split(p["text"]):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: yield w
if "--fast" in ARGV: sys.exit(0)
_, te_b = D0.books(); te = list(sents_of(B.paragraphs(te_b, 20000)))[:3000]; tot = 0.0; n = 0
with torch.no_grad():
    for w in te:
        ids = [vi.get(x, 0) for x in w]; lp = torch.log_softmax(net(torch.tensor([ids[:-1]], device=DEV))[0], -1)
        for j in range(len(ids) - 1):
            b = -lp[j, ids[j + 1]].item() / math.log(2)
            if ids[j + 1] == 0: b += unk_bits(w[j + 1])
            tot += b; n += 1
print(f"R25-aw network (look-up {K}) matched predictions, sentence scope: {tot / n:.4f} bits/word over {n} predictions", flush=True)
