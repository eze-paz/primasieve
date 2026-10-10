"""R19-b/c: the merged engine with the world state in front -- world state -> hand reader (R11 matcher) -> 0.4B model --
on the 30 time/place questions and the 80 story questions. Run: python learned/base/r19_merged.py"""
import os, sys, re, json, torch
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT)
sys.argv = [sys.argv[0], "--v3"]; sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import reader_check as rc
from worldstate import World, SENT
from rwkv7 import RWKV7, tokenizer
from b6_rwkv import hit


def answer(m, tok, prompt):
    return tok.decode(m.greedy(torch.tensor([tok.encode(prompt)]), 8, tok=tok)).strip().split("\n")[0]


def run(m, tok, stories, label, replies=None):
    sc = dict(chunk=0, world=0, merged=0, world_matched=0, world_right=0); n = 0; i = 0
    for s in stories:
        W = World(rc.R); W.read(s["text"])
        sents = [x.strip() for x in SENT.split(s["text"]) if x.strip()]; wins = [" ".join(sents[max(0, k - 1):k + 1]) for k in range(len(sents))]
        prompt_hits = "Hits:\n" + "\n".join(f"[{k}] {w}" for k, w in enumerate(wins)) + "\nAnswer:"
        for q, gold in s["qs"]:
            n += 1
            chunk = replies[i]["reply"] if replies else answer(m, tok, f"Story: {s['text']}\n\nQuestion: {q}\nAnswer:"); i += 1
            sc["chunk"] += hit(chunk, gold)
            w = W.ask(q)
            if w is not None: sc["world_matched"] += 1; sc["world_right"] += hit(w, gold)
            sc["world"] += hit(w, gold) if w is not None else 0
            if w is None:
                committed, ra = rc.check(dict(q=q, gold=gold, prompt=prompt_hits, reply=chunk)); final = ra if ra is not None else chunk
            else: final = w
            sc["merged"] += hit(final, gold)
    print(f"{label} ({n}): chunk {sc['chunk']} | world alone {sc['world']} (matched {sc['world_matched']}, right {sc['world_right']}) | merged world->reader->model {sc['merged']}", flush=True)
    return sc


def main():
    m = RWKV7.load(os.path.join(HERE, "ckpt_read1b.pth")); m.eval(); tok = tokenizer()
    ts = json.load(open(os.path.join(HERE, "val_timespace.json"), encoding="utf-8"))["stories"]
    a = run(m, tok, ts, "time/place (R19-b: merged >= chunk + 8)")
    vs = json.load(open(os.path.join(HERE, "val_stories.json"), encoding="utf-8"))["stories"]; vf = json.load(open(os.path.join(HERE, "val_fables.json"), encoding="utf-8"))["stories"]
    r1 = json.load(open(os.path.join(HERE, "b6_rwkv_val_ckpt_read1b.json"), encoding="utf-8"))["items"]; r2 = json.load(open(os.path.join(HERE, "b6_rwkv_valfables_ckpt_read1b.json"), encoding="utf-8"))["items"]
    b = run(m, tok, vs, "stories (R19-c)", r1); c = run(m, tok, vf, "fables (R19-c)", r2)
    print(f"R19-c: merged with world state on the 80 story questions = {b['merged'] + c['merged']} (bar >= 69)")
    json.dump(dict(timespace=a, stories=b, fables=c), open(os.path.join(HERE, "r19_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
