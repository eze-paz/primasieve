"""B2b (B_prereg.md): the model's replies with a confidence (mean log2-probability per generated token, and the
probability of the first token) for all 2,510 questions of val_all13.json. Run: py -3.12 b2_conf.py [--limit N]"""
import os, sys, json, time, math, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
from rwkv7 import RWKV7, tokenizer
from b6_rwkv import hit
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
OUT = "b2_conf_answers.json" if LIMIT is None else "b2_conf_sample.json"

@torch.no_grad()
def scored_greedy(m, ids, n, tok):
    st = m.new_state(); logits = m(ids, st); out = []; lps = []
    for _ in range(n):
        lp = torch.log_softmax(logits[0, -1].float(), -1); nxt = lp.argmax().item(); out.append(nxt); lps.append(lp[nxt].item() / math.log(2))
        if "\n" in tok.decode([nxt]): break
        logits = m(torch.tensor([[nxt]]), st)
    return out, lps

def main():
    m = RWKV7.load("ckpt_read1b.pth"); m.eval(); tok = tokenizer()
    stories = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    done = {}
    if os.path.exists(OUT):
        for it in json.load(open(OUT, encoding="utf-8")): done[(it["story"], it["q"])] = it
    out = []; t0 = time.time(); k = 0
    for s in stories:
        for q, gold in s["qs"]:
            k += 1
            if LIMIT and k > LIMIT: break
            if (s["id"], q) in done: out.append(done[(s["id"], q)]); continue
            prompt = f"Story: {s['text']}\n\nQuestion: {q}\nAnswer:"
            toks, lps = scored_greedy(m, torch.tensor([tok.encode(prompt)]), 8, tok)
            reply = tok.decode(toks).strip().split("\n")[0]
            content = [lp for t, lp in zip(toks, lps) if "\n" not in tok.decode([t])] or lps
            out.append(dict(story=s["id"], q=q, gold=gold, reply=reply, hit=hit(reply, gold), mean_lp=sum(content) / len(content), first_lp=lps[0], min_lp=min(content)))
            if k % 50 == 0:
                json.dump(out, open(OUT, "w", encoding="utf-8")); print(f"  {k} questions ({time.time() - t0:.0f} s)", flush=True)
    json.dump(out, open(OUT, "w", encoding="utf-8")); print(f"B2b: {len(out)} questions scored in {time.time() - t0:.0f} s -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
