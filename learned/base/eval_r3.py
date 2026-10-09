"""R3 gates: the model answers from grep hits over a long text.
Run: python learned/base/eval_r3.py <ckpt> [--set b6long|counter|both]  -> learned/base/r3_<set>_<ckpt>.json"""
import os, sys, json, re, time, torch
from rwkv7 import RWKV7, tokenizer
from b6_rwkv import hit

HERE = os.path.dirname(os.path.abspath(__file__))


def run(m, tok, items, label):
    right = n = world = unknown = 0; out = []; T0 = time.time()
    for it in items:
        reply = tok.decode(m.greedy(torch.tensor([tok.encode(it["prompt"])]), 10, tok=tok)).strip().split("\n")[0]
        ok = hit(reply, it["gold"]); right += ok; n += 1
        if "world" in it: world += hit(reply, it["world"]) and not ok
        unknown += "unknown" in reply.lower()
        out.append(dict(q=it["q"], gold=it["gold"], reply=reply, hit=ok, found=it.get("found")))
    extra = f", answered from world knowledge instead {world}" if any("world" in it for it in items) else ""
    print(f"{label}: {right}/{n} (unknown replies {unknown}{extra})  {time.time() - T0:.0f} s", flush=True)
    return dict(right=right, n=n, unknown=unknown, world=world, items=out)


def main():
    ck = sys.argv[1]; which = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "both"
    m = RWKV7.load(ck); m.eval(); tok = tokenizer(); tag = os.path.basename(ck).split(".")[0]
    for name in (["b6long", "counter"] if which == "both" else [which]):
        items = json.load(open(os.path.join(HERE, f"r3_{name}.json"), encoding="utf-8"))
        res = run(m, tok, items, f"R3 {name} {tag}")
        json.dump(res, open(os.path.join(HERE, f"r3_{name}_{tag}.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
