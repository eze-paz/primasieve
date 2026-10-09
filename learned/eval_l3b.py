"""L3b_prereg.md: the surname probe with frequency-matched distractors and the context-lift measure, on the existing
checkpoints. Run: python learned/eval_l3b.py --control ssm2 --model ssm3  -> learned/L3b_probe.json"""
import os, sys, json, random, collections, re, numpy as np
import torch
from data import BPE, CACHE, books, read
import eval_l3

HERE = os.path.dirname(os.path.abspath(__file__))
NEUTRAL = "It was late in the evening when they came to the house of"


def main():
    a = sys.argv; control = a[a.index("--control") + 1]; model = a[a.index("--model") + 1]
    tok = BPE.load(); probes = json.load(open(os.path.join(CACHE, "name_probes.json"), encoding="utf-8"))
    names = json.load(open(os.path.join(CACHE, "names.json"), encoding="utf-8")); pool = names["pool"]; per_book = names["names"]
    train, _ = books(); count = collections.Counter()
    for b in train: count.update(w for w in re.findall(r"[A-Z][a-z]+", read(b)))
    R = random.Random(7); matched = []; dropped = 0
    for p in probes:
        own = per_book[p["book"]]; c = count[p["last"]]; cls = own[p["last"]]
        cand = [n for n in pool[cls] if n != p["last"] and n not in own]
        ok = [n for n in cand if 0.5 * c <= count[n] <= 2 * c]
        if len(ok) < 10: ok = [n for n in cand if c / 3 <= count[n] <= 3 * c]
        if len(ok) < 10: dropped += 1; continue
        matched.append(dict(p, distractors=R.sample(ok, 10), true_count=c))
    print(f"{len(matched)} probes with frequency-matched distractors ({dropped} dropped)", flush=True)
    neutral = [dict(p, context=NEUTRAL) for p in matched]
    out = dict(n=len(matched), dropped=dropped)
    for tag in (control, model):
        b = eval_l3.probe(tag, matched, tok); n = eval_l3.probe(tag, neutral, tok)
        out[tag] = dict(book=b, neutral=n, lift_top1=b["top1"] - n["top1"], lift_win=b["win_rate"] - n["win_rate"])
        print(f"{tag}: book win {b['win_rate']:.3f} top1 {b['top1']:.3f} | neutral win {n['win_rate']:.3f} top1 {n['top1']:.3f} | "
              f"lift top1 {out[tag]['lift_top1']:+.3f} win {out[tag]['lift_win']:+.3f}", flush=True)
    json.dump(out, open(os.path.join(HERE, "L3b_probe.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
