"""Step 4 of the subtractive plan: measure the remainder. Zero groups of feed-forward (channel-mix) layers, where facts
are thought to concentrate, and watch two curves: closed-book factual recall (facts_probe.json, 100 completions the base
model is tested on first) and reading (B6, the story is in the prompt). Where recall collapses while reading survives
is the part of the model that is facts, not logic.
Run: python learned/base/ablate.py <ckpt> [--groups]  -> learned/base/ablate_<ckpt>.json"""
import os, sys, json, re, time, torch
from rwkv7 import RWKV7, tokenizer
from b6_rwkv import hit

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))


def recall(m, tok, facts, n_new=6):
    r = 0
    for prompt, gold in facts:
        out = tok.decode(m.greedy(torch.tensor([tok.encode(prompt)]), n_new, tok=tok))
        r += hit(out, gold)
    return r / len(facts)


def b6(m, tok, stories, k=None):
    r = n = 0
    for s in stories[:k] if k else stories:
        for q, gold in s["qs"]:
            out = tok.decode(m.greedy(torch.tensor([tok.encode(f"Story: {s['text']}\n\nQuestion: {q}\nAnswer:")]), 8, tok=tok)).split("\n")[0]
            r += hit(out, gold); n += 1
    return r / n


def main():
    ck = sys.argv[1]; tok = tokenizer()
    facts = json.load(open(os.path.join(HERE, "facts_probe.json"), encoding="utf-8"))
    stories = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]
    m = RWKV7.load(ck); m.eval(); L = m.n_layer
    saved = {i: m.blocks[i].ffn.value.weight.data.clone() for i in range(L)}
    def restore():
        for i in range(L): m.blocks[i].ffn.value.weight.data.copy_(saved[i])
    groups = [("none", [])] + [(f"ffn {a}-{b - 1}", list(range(a, b))) for a, b in ((0, 6), (6, 12), (12, 18), (18, 24))] + [("ffn all", list(range(L)))]
    groups += [(f"ffn {a}-{b - 1}", list(range(a, b))) for a, b in ((0, 12), (12, 24), (6, 18))]
    res = []
    for name, ids in groups:
        restore()
        for i in ids: m.blocks[i].ffn.value.weight.data.zero_()
        t = time.time(); fr = recall(m, tok, facts); br = b6(m, tok, stories)
        res.append(dict(ablated=name, layers=ids, recall=fr, b6=br)); print(f"{name:12s} recall {fr:.2f}  B6 {br:.2f}  ({time.time() - t:.0f} s)", flush=True)
        json.dump(res, open(os.path.join(HERE, f"ablate_{os.path.basename(ck).split('.')[0]}.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
