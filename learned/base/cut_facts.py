"""R4: apply the R2b cut. Rank channel-mix neurons of layers 6-23 by fact selectivity (closed-book fact prompts vs
reading prompts, as in neuron_ablate.py) on the given checkpoint, zero the value columns of the top share, and save the
cut checkpoint. Run: python learned/base/cut_facts.py <ckpt> [--share 0.02]  -> <ckpt stem>_cut.pth"""
import os, sys, json, torch
from rwkv7 import RWKV7, tokenizer
from neuron_ablate import activations

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ck = sys.argv[1]; share = float(sys.argv[sys.argv.index("--share") + 1]) if "--share" in sys.argv else 0.02
    tok = tokenizer(); m = RWKV7.load(ck); m.eval()
    facts = json.load(open(os.path.join(HERE, "facts_probe.json"), encoding="utf-8"))
    train = json.load(open(os.path.join(HERE, "stories_train_v2.json"), encoding="utf-8"))[:100]
    fa = activations(m, tok, [p for p, _ in facts]); ra = activations(m, tok, [f"Story: {d['text']}\n\nQuestion: {d['qs'][0][0]}\nAnswer:" for d in train])
    sel = []
    for i in range(6, m.n_layer):
        f = fa[i] / (fa[i].mean() + 1e-6); r = ra[i] / (ra[i].mean() + 1e-6)
        for j in range(len(f)): sel.append(((f[j] - r[j]).item(), i, j))
    sel.sort(reverse=True); n = int(share * len(sel))
    for _, i, j in sel[:n]: m.blocks[i].ffn.value.weight.data[:, j] = 0
    out = os.path.splitext(ck)[0] + "_cut.pth"
    torch.save({k: v.detach().to(torch.bfloat16) for k, v in m.state_dict().items()}, out)
    json.dump([(i, j) for _, i, j in sel[:n]], open(os.path.splitext(ck)[0] + "_cut_neurons.json", "w"))
    print(f"zeroed {n} neurons ({share:.0%}) -> {out}")


if __name__ == "__main__":
    main()
