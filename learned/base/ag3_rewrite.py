"""AG3: the pretrained model rewrites a story into short canonical clauses; the engine's translator checks each clause
parses to an event; unparsed clauses are sent back once for a simpler rewrite. Run: py -3.12 ag3_rewrite.py [--limit N] [--ckpt path]"""
import os, sys, json, time, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
from rwkv7 import RWKV7, tokenizer
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
CK = sys.argv[sys.argv.index("--ckpt") + 1] if "--ckpt" in sys.argv else os.path.join("rwkv7", "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth")
OUT = "ag3_rewrites.json" if LIMIT is None else "ag3_sample.json"
PROMPT = ("Instruction: Rewrite the story as a numbered list of short, simple sentences. One fact per sentence. "
          "Keep every name, object, place and time. Use no pronouns.\n\nStory: {text}\n\nSimple sentences:\n1.")

@torch.no_grad()
def gen(m, tok, prompt, n=220):
    st = m.new_state(); logits = m(torch.tensor([tok.encode(prompt)]), st); out = []
    for _ in range(n):
        nxt = logits[0, -1].argmax().item(); out.append(nxt); s = tok.decode(out)
        if "\n\n" in s: break
        logits = m(torch.tensor([[nxt]]), st)
    return tok.decode(out).split("\n\n")[0]

def clauses(text):
    import re
    out = []
    for line in ("1." + text).split("\n"):
        line = re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
        if line: out.append(line)
    return out

def main():
    m = RWKV7.load(CK); m.eval(); tok = tokenizer()
    stories = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    done = {it["id"]: it for it in json.load(open(OUT, encoding="utf-8"))} if os.path.exists(OUT) else {}
    out = []; t0 = time.time()
    for k, s in enumerate(stories):
        if LIMIT and k >= LIMIT: break
        if s["id"] in done: out.append(done[s["id"]]); continue
        rw = gen(m, tok, PROMPT.format(text=s["text"]))
        out.append(dict(id=s["id"], text=s["text"], clauses=clauses(rw)))
        if k % 20 == 0: json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1); print(f"  {k} stories ({time.time() - t0:.0f} s)", flush=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1); print(f"AG3 rewrites: {len(out)} stories in {time.time() - t0:.0f} s -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
