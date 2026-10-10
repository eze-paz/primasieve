"""The learned line's first battery number: B6 story questions (tests/battery/stories.json, 20 stories, 100 questions)
answered by a pretrained recurrent model reading the story -- the store is the story, the model reads the hit and
answers. Scoring is the battery's: a reply counts if it contains a gold form (case-blind). Hand-rule baseline: 71/100.
Run: python learned/base/b6_rwkv.py [ckpt]  -> learned/base/b6_rwkv.json"""
import os, sys, json, re, time, torch
from rwkv7 import RWKV7, tokenizer

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
CK = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(HERE, "rwkv7", "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth")


def hit(reply, gold):                       # battery.py's rule
    r = re.sub(r"[^a-z0-9 ]", " ", reply.lower())
    return any(re.sub(r"[^a-z0-9 ]", " ", g.lower()).strip() in r for g in gold)


def main():
    m = RWKV7.load(CK); m.eval(); tok = tokenizer()
    sfile = sys.argv[sys.argv.index("--stories") + 1] if "--stories" in sys.argv else os.path.join(ROOT, "tests", "battery", "stories.json")
    stories = json.load(open(sfile, encoding="utf-8"))["stories"]
    mismatch = "--mismatch" in sys.argv                      # R1c: each question gets a different story; the right reply is "unknown"
    out = []; right = n = 0; T0 = time.time()
    for i, s in enumerate(stories):
        for q, gold in s["qs"]:
            text = stories[(i + 7) % len(stories)]["text"] if mismatch else s["text"]
            if mismatch: gold = ["unknown"]
            prompt = f"Story: {text}\n\nQuestion: {q}\nAnswer:"
            ids = torch.tensor([tok.encode(prompt)])
            reply = tok.decode(m.greedy(ids, 8, tok=tok)).strip().split("\n")[0]
            ok = hit(reply, gold); right += ok; n += 1
            out.append(dict(story=s["id"], q=q, gold=gold, reply=reply, hit=ok))
            print(f"[{'ok' if ok else '--'}] {q} -> {reply!r}  (gold {gold[0]})".encode("ascii", "replace").decode(), flush=True)
    label = "mismatch(unknown)" if mismatch else "B6"
    print(f"\n{label} {os.path.basename(CK)}: {right}/{n}  (hand rules 71/100)  {time.time() - T0:.0f} s")
    name = "b6_rwkv" + ("_mismatch" if mismatch else "") + ("_val" if "--stories" in sys.argv else "") + ("" if len(sys.argv) < 2 or sys.argv[1].startswith("--") else "_" + os.path.basename(CK).split(".")[0]) + ".json"
    json.dump(dict(ckpt=os.path.basename(CK), mismatch=mismatch, right=right, n=n, items=out), open(os.path.join(HERE, name), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
