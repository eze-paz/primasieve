"""R25-at: the trained attention network on exactly the language model's next-word predictions (R25-ao):
the first N held-out sentences, each read on its own (sentence scope), words 2.. predicted from the earlier words of
the same sentence, in bits per word; words outside the network's vocabulary are charged their share of the unknown
mass, as in r25_attn.py. Run: python r25_attn_eval.py [--weights r25_attn.pt] [--subset 3000]"""
import os, sys, math, collections
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]                                              # reuse the network definition and vocabulary without training
import importlib.util, torch
N = int(ARGV[ARGV.index("--subset") + 1]) if "--subset" in ARGV else 3000
W = ARGV[ARGV.index("--weights") + 1] if "--weights" in ARGV else "r25_attn.pt"
src = open(os.path.join(HERE, "r25_attn.py"), encoding="utf-8").read()
src = src[:src.index("pool = [w for a, m in train")]                                        # definitions, data and model only
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
net, vi, unk_bits, T, B, D0 = g["net"], g["vi"], g["unk_bits"], g["T"], g["B"], g["D0"]
net.load_state_dict(torch.load(W)); net.eval()
def sents_of(paras):
    for p in paras:
        for s in T.SENT.split(p["text"]):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: yield w
_, te_b = D0.books(); te = list(sents_of(B.paragraphs(te_b, 20000)))[:N]
tot = 0.0; n = 0
with torch.no_grad():
    for w in te:
        ids = [vi.get(x, 0) for x in w]
        lp = torch.log_softmax(net(torch.tensor([ids[:min(len(ids), 64) - 1]]))[0], -1)
        for j in range(min(len(ids), 64) - 1):
            b = -lp[j, ids[j + 1]].item() / math.log(2)
            if ids[j + 1] == 0: b += unk_bits(w[j + 1])
            tot += b; n += 1
        for k in range(64, len(ids)):                                                    # rare long sentences: the last 63 words as context
            lpk = torch.log_softmax(net(torch.tensor([ids[k - 63:k]]))[0, -1], -1)
            b = -lpk[ids[k]].item() / math.log(2)
            if ids[k] == 0: b += unk_bits(w[k])
            tot += b; n += 1
print(f"R25-at attention network ({W}) on the first {N} held-out sentences, sentence scope: {tot / n:.4f} bits/word over {n} predictions", flush=True)
