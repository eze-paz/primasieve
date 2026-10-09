"""The learned line's first battery number: B6 story questions (tests/battery/stories.json, 20 stories, 100 questions)
answered by a pretrained recurrent model reading the story -- the store is the story, the model reads the hit and
answers. Scoring is the battery's: a reply counts if it contains a gold form (case-blind). Hand-rule baseline: 71/100.
Run: python learned/base/b6_rwkv.py [ckpt]  -> learned/base/b6_rwkv.json"""
import os, sys, json, re, time, torch
from rwkv7 import RWKV7, tokenizer

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
CK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "rwkv7", "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth")


def hit(reply, gold):                       # battery.py's rule
    r = re.sub(r"[^a-z0-9 ]", " ", reply.lower())
    return any(re.sub(r"[^a-z0-9 ]", " ", g.lower()).strip() in r for g in gold)


def main():
    m = RWKV7.load(CK); m.eval(); tok = tokenizer()
    stories = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]
    out = []; right = n = 0; T0 = time.time()
    for s in stories:
        for q, gold in s["qs"]:
            prompt = f"Story: {s['text']}\n\nQuestion: {q}\nAnswer:"
            ids = torch.tensor([tok.encode(prompt)])
            with torch.no_grad():
                for _ in range(8):                                   # greedy, stop at a newline
                    nxt = m(ids)[0, -1].argmax().item(); ids = torch.cat([ids, torch.tensor([[nxt]])], 1)
                    if "\n" in tok.decode([nxt]): break
            reply = tok.decode(ids[0, len(tok.encode(prompt)):].tolist()).strip().split("\n")[0]
            ok = hit(reply, gold); right += ok; n += 1
            out.append(dict(story=s["id"], q=q, gold=gold, reply=reply, hit=ok))
            print(f"[{'ok' if ok else '--'}] {q} -> {reply!r}  (gold {gold[0]})", flush=True)
    print(f"\nB6 {os.path.basename(CK)}: {right}/{n}  (hand rules 71/100)  {time.time() - T0:.0f} s")
    json.dump(dict(ckpt=os.path.basename(CK), right=right, n=n, items=out), open(os.path.join(HERE, "b6_rwkv.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
