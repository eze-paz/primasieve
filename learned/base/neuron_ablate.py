"""R2b: the finer instrument. Per-neuron attribution inside the channel-mix: for every hidden neuron of every layer,
its mean activation (relu(key x)^2) at the answer position of closed-book fact prompts versus at the answer position of
reading prompts (a story in the prompt). Neurons that fire for facts and not for reading are "fact neurons"; zeroing the
top share of them (their value columns) removes recall while, if the thesis holds, reading survives.
Run: python learned/base/neuron_ablate.py <ckpt>  -> learned/base/neuron_<ckpt>.json"""
import os, sys, json, time, torch
from rwkv7 import RWKV7, tokenizer
from ablate import recall, b6

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))


def activations(m, tok, prompts):
    """mean relu(key x)^2 per (layer, neuron) at the last prompt position"""
    acts = [torch.zeros(b.ffn.key.weight.shape[0]) for b in m.blocks]; hooks = []
    for i, b in enumerate(m.blocks):
        def hook(mod, inp, out, i=i): acts[i] += (torch.relu(out[0, -1]) ** 2).detach()
        hooks.append(b.ffn.key.register_forward_hook(hook))
    with torch.no_grad():
        for p in prompts: m(torch.tensor([tok.encode(p)]))
    for h in hooks: h.remove()
    return [a / len(prompts) for a in acts]


def main():
    ck = sys.argv[1]; tok = tokenizer(); m = RWKV7.load(ck); m.eval(); T0 = time.time()
    facts = json.load(open(os.path.join(HERE, "facts_probe.json"), encoding="utf-8"))
    stories = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]
    train = json.load(open(os.path.join(HERE, "stories_train_v2.json"), encoding="utf-8"))[:100]     # reading prompts from TRAINING stories (B6 untouched)
    fa = activations(m, tok, [p for p, _ in facts])
    ra = activations(m, tok, [f"Story: {d['text']}\n\nQuestion: {d['qs'][0][0]}\nAnswer:" for d in train])
    print(f"activations collected ({time.time() - T0:.0f} s)", flush=True)
    # selectivity: fact activation minus reading activation, each normalised by the layer's mean, over layers 6-23
    sel = []
    for i in range(6, m.n_layer):
        f = fa[i] / (fa[i].mean() + 1e-6); r = ra[i] / (ra[i].mean() + 1e-6)
        for j in range(len(f)): sel.append(((f[j] - r[j]).item(), i, j))
    sel.sort(reverse=True); total = len(sel)
    saved = {i: m.blocks[i].ffn.value.weight.data.clone() for i in range(m.n_layer)}
    res = [dict(share=0.0, n=0, recall=recall(m, tok, facts), b6=b6(m, tok, stories))]; print(res[0], flush=True)
    for share in (0.02, 0.05, 0.10, 0.20, 0.35):
        for i in saved: m.blocks[i].ffn.value.weight.data.copy_(saved[i])
        n = int(share * total)
        for _, i, j in sel[:n]: m.blocks[i].ffn.value.weight.data[:, j] = 0
        r = dict(share=share, n=n, recall=recall(m, tok, facts), b6=b6(m, tok, stories)); res.append(r)
        print(f"zero top {share:.0%} fact-selective neurons ({n}): recall {r['recall']:.2f}  B6 {r['b6']:.2f}  ({time.time() - T0:.0f} s)", flush=True)
        json.dump(res, open(os.path.join(HERE, f"neuron_{os.path.basename(ck).split('.')[0]}.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
