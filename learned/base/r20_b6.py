"""R20-c: B6 once with the INDUCED world in front (induced world -> reader -> model), same protocol as r19b_b6.py (saved
0.4B replies as the model's share). Run: python learned/base/r20_b6.py"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT)
sys.argv = [sys.argv[0], "--v3"]; sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import reader_check as rc
import r20_induce as RI
from worldstate import SENT
from b6_rwkv import hit

table = json.load(open(os.path.join(HERE, "r20_joint_table.json")))
stories = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]
rep = json.load(open(os.path.join(HERE, "b6_rwkv_ckpt_read1b.json"), encoding="utf-8"))["items"]; i = 0
model = world_m = world_r = merged = 0
for s in stories:
    W = RI.InducedWorld(rc.R, table); W.read(s["text"])
    sents = [x.strip() for x in SENT.split(s["text"]) if x.strip()]; wins = [" ".join(sents[max(0, k - 1):k + 1]) for k in range(len(sents))]
    prompt = "Hits:\n" + "\n".join(f"[{k}] {w}" for k, w in enumerate(wins)) + "\nAnswer:"
    for q, gold in s["qs"]:
        x = rep[i]; i += 1; model += x["hit"]; w = W.ask(q)
        if w is not None: world_m += 1; world_r += hit(w, gold); final = w
        else:
            committed, ra = rc.check(dict(q=q, gold=gold, prompt=prompt, reply=x["reply"])); final = ra if ra is not None else x["reply"]
        merged += hit(final, gold)
print(f"B6 once (R20-c, induced world): model alone {model}/100 | induced world matched {world_m} right {world_r} | merged world->reader->model {merged}/100 (hand world merged: 82; bar >= 85)")
json.dump(dict(model=model, world=(world_m, world_r), merged=merged), open(os.path.join(HERE, "r20_b6_results.json"), "w"))
