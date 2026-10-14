"""R25-ar: a small attention network over the learner's own word vectors (owner's go-ahead, 2026-10-12, item 5).
Next-word prediction at paragraph scope: up to CTX earlier words of the paragraph are read by a 2-layer causal
self-attention model; word embeddings start from the learner's vectors (r25_vectors_all.npz, 100 dims) and are tuned.
Trained on the training books' paragraphs (CPU, a fixed time budget, checkpoint saved); scored on the held-out books'
paragraphs on exactly the predictions R25-ap scores (every word after the first of its sentence), in bits per word.
Words outside the vocabulary are mapped to one unknown token and charged the unigram share of the unknown mass, as
the count models' unseen-word handling does in spirit. Run: python r25_attn.py [--minutes M]"""
import os, sys, json, math, time, random, collections
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import numpy as np, torch, torch.nn as nn
import r24_tlm as T, r24_books as B, data as D0
torch.manual_seed(0); random.seed(0)
MIN = float(ARGV[ARGV.index("--minutes") + 1]) if "--minutes" in ARGV else 90
opt_ = lambda k, d: type(d)(ARGV[ARGV.index(k) + 1]) if k in ARGV else d
CTX, D, H, LAYERS, BATCH = 64, opt_("--width", 128), 4, opt_("--layers", 2), 32
OUT = opt_("--out", "r25_attn.pt")                                                        # R25-av: separate weights file


def paras_of(paras):
    out = []
    for p in paras:
        ss = []
        for s in T.SENT.split(p["text"]):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: ss.append(w)
        if ss: out.append(ss)
    return out


t0 = time.time()
tr_b, te_b = D0.books(); tep = paras_of(B.paragraphs(te_b, 20000))
if os.environ.get("R26_RANGE"):                                                             # R26 T39: another range of held-out paragraphs; outputs to R26_OUTDIR
    _a, _b = map(int, os.environ["R26_RANGE"].split(":")); tep = tep[_a:_b]; _od = os.environ.get("R26_OUTDIR")
    if _od:
        os.makedirs(_od, exist_ok=True); _sv = np.savez
        def _savez(f, *a, **k): return _sv(f if (os.path.isabs(str(f)) or os.path.dirname(str(f))) else os.path.join(_od, f), *a, **k)
        np.savez = _savez
trp = paras_of([dict(text=p.replace(chr(8217), "'")) for b in tr_b for p in D0.read(b).split(chr(10)) if p.strip()] if "--all-text" in ARGV else B.paragraphs(tr_b, 1000000))   # R25-av: every paragraph of the training books
z = np.load("r25_vectors_all.npz"); vocab = z["vocab"].tolist()[:20000]; vi = {w: i + 1 for i, w in enumerate(vocab)}   # 0 = unknown
uni = collections.Counter(x for p in trp for s in p for x in s); N = sum(uni.values())
unk_words = sum(c for w, c in uni.items() if w not in vi); n_unk_types = sum(1 for w in uni if w not in vi) + 1
def unk_bits(w): return -math.log2(max((uni[w] + 0.5) / (unk_words + 0.5 * n_unk_types), 1e-12))     # share of the unknown mass
def encode(p):
    ids, mask = [], []
    for s in p:
        for i, x in enumerate(s): ids.append(vi.get(x, 0)); mask.append(1 if i >= 1 else 0)
    return ids, mask
train = [encode(p) for p in trp]; train = [(a, m) for a, m in train if len(a) >= 3]
print(f"R25-ar data: {len(train)} training paragraphs, {sum(len(a) for a, _ in train)} tokens; vocabulary {len(vocab)} + unknown ({time.time() - t0:.0f} s)", flush=True)


class Net(nn.Module):
    def __init__(s):
        super().__init__()
        E = np.zeros((len(vocab) + 1, 100), dtype=np.float32); E[1:] = z["vecs"][:len(vocab)]
        s.emb = nn.Embedding(len(vocab) + 1, 100); s.emb.weight.data = torch.tensor(E)
        s.inp = nn.Linear(100, D); s.pos = nn.Embedding(CTX, D)
        s.blocks = nn.ModuleList([nn.TransformerEncoderLayer(D, H, 4 * D, dropout=0.1, batch_first=True, norm_first=True) for _ in range(LAYERS)])
        s.out_ln = nn.LayerNorm(D); s.out = nn.Linear(D, len(vocab) + 1)
    def forward(s, x):
        L = x.shape[1]; h = s.inp(s.emb(x)) + s.pos(torch.arange(L))
        m = torch.triu(torch.full((L, L), float("-inf")), 1)
        for b in s.blocks: h = b(h, src_mask=m)
        return s.out(s.out_ln(h))


if "--threads" in ARGV: torch.set_num_threads(int(ARGV[ARGV.index("--threads") + 1]))
net = Net(); opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=0.01); lossf = nn.CrossEntropyLoss(reduction="none")
if "--resume" in ARGV and os.path.exists(OUT): net.load_state_dict(torch.load(OUT)); print(f"R25-ar resumed from {OUT}", flush=True)
print(f"R25-ar model: {sum(p.numel() for p in net.parameters()):,} parameters", flush=True)
def windows(ids, mask):
    for st in range(0, max(1, len(ids) - 1), CTX):
        a = ids[max(0, st - 1):st + CTX]; m = mask[max(0, st - 1):st + CTX]
        if len(a) >= 2: yield a, m
pool = [w for a, m in train for w in windows(a, m)]; step = 0; net.train(); t_train = time.time()
while time.time() - t0 < MIN * 60:
    batch = random.sample(pool, BATCH); L = max(len(a) for a, _ in batch)
    x = torch.zeros((BATCH, L - 1), dtype=torch.long); y = torch.zeros((BATCH, L - 1), dtype=torch.long); w8 = torch.zeros((BATCH, L - 1))
    for i, (a, m) in enumerate(batch):
        x[i, :len(a) - 1] = torch.tensor(a[:-1]); y[i, :len(a) - 1] = torch.tensor(a[1:]); w8[i, :len(a) - 1] = 1.0
    out = net(x); loss = (lossf(out.reshape(-1, out.shape[-1]), y.reshape(-1)) * w8.reshape(-1)).sum() / w8.sum()
    opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step(); step += 1
    if "--decay" in ARGV:                                                                 # R25-az: learning rate falls linearly to zero over the time budget
        for g_ in opt.param_groups: g_["lr"] = 1e-3 * max(0.0, 1 - (time.time() - t_train) / (MIN * 60))
    if step % 200 == 0: print(f"  step {step}: training loss {loss.item() / math.log(2):.3f} bits/token ({time.time() - t0:.0f} s)", flush=True)
    if step % 500 == 0: torch.save(net.state_dict(), OUT)
torch.save(net.state_dict(), OUT); net.eval()
tot = 0.0; n = 0
with torch.no_grad():
    for p in tep:
        ids, mask = encode(p); words = [x for s in p for x in s]
        stride = CTX // 2; lo = 0
        while True:                                                                      # half-overlapping windows: every target predicted once, with 32-63 words of context
            seq = ids[lo:lo + CTX]
            if len(seq) >= 2:
                lp = torch.log_softmax(net(torch.tensor([seq[:-1]]))[0], -1)
                k0 = 1 if lo == 0 else lo + stride
                for k in range(max(k0, lo + 1), lo + len(seq)):
                    if not mask[k]: continue
                    j = k - lo - 1; b = -lp[j, seq[j + 1]].item() / math.log(2)
                    if seq[j + 1] == 0: b += unk_bits(words[k])
                    tot += b; n += 1
            if lo + CTX >= len(ids): break
            lo += stride
print(f"R25-ar attention network after {step} steps: held-out paragraphs {tot / n:.4f} bits/word over {n} predictions ({time.time() - t0:.0f} s)", flush=True)
