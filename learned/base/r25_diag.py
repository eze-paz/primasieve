"""R25-ba: why does the running state stall? Score every saved checkpoint of both networks on the same two fixed
samples: 2,000 TRAINING paragraphs (the last 2,000 of the training list) and 2,000 HELD-OUT paragraphs (the first
2,000), each paragraph cut to its first 64 words and read in one pass, every word after the first of its sentence
scored, unknown words charged as in training. Deterministic: no training, fixed samples, single thread.
Overfitting shows as training bits still falling while held-out bits stop; a capacity limit as training bits flat too.
Run: py -3.12 r25_diag.py"""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
def defs(fname, cut, argv):
    sys.argv = argv; src = open(fname, encoding="utf-8").read(); src = src[:src.index(cut)]
    g = {"__name__": fname[:-3] + "_defs", "__file__": os.path.join(HERE, fname)}; exec(compile(src, fname, "exec"), g); return g
R = defs("r25_rnn.py", "net = RNet()", ["r25_rnn.py", "--lookup", "0", "--minutes", "0"])
A = defs("r25_attn.py", "pool = [w for a, m in train", ["r25_attn.py", "--minutes", "0"])
torch = R["torch"]; torch.set_num_threads(1)
tr_s = A["trp"][-2000:]; te_s = A["tep"][:2000]
def score(net, paras, enc, unk):
    tot = 0.0; n = 0
    with torch.no_grad():
        for p in paras:
            ids, mask = enc(p); ids, mask = ids[:64], mask[:64]; words = [x for s in p for x in s][:64]
            if len(ids) < 2: continue
            lp = torch.log_softmax(net(torch.tensor([ids[:-1]]))[0], -1)
            for k in range(1, len(ids)):
                if not mask[k]: continue
                b = -lp[k - 1, ids[k]].item() / math.log(2)
                if ids[k] == 0: b += unk(words[k])
                tot += b; n += 1
    return tot / n
runs = [("running state", R["RNet"], ["r25_rnn_k0_75min.pt", "r25_rnn_k0_255min.pt", "r25_rnn_k0_ay_s17000.pt", "r25_rnn_k0_495min.pt", "r25_rnn_az.pt"]),
        ("attention", A["Net"], ["r25_attn_75min.pt", "r25_attn_ar2.pt", "r25_attn_ar3.pt", "r25_attn_az.pt"])]
for name, cls, files in runs:
    for f in files:
        net = cls(); net.load_state_dict(torch.load(f)); net.eval()
        a = score(net, tr_s, A["encode"], A["unk_bits"]); b = score(net, te_s, A["encode"], A["unk_bits"])
        print(f"R25-ba {name:14s} {f:28s} training sample {a:.4f} | held-out sample {b:.4f} | gap {b - a:+.4f} bits/word", flush=True)
