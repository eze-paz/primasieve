"""AG6 (AG_prereg.md): the model (ckpt_read1b, B2b prompt) answers from the AG4 canonical text instead of the prose,
for the dev block stories 22-101 (400 questions). Writes ag6_answers.json; then compares with b2_conf_answers.json.
Run: py -3.12 ag6_model_canon.py [--report]"""
import os, sys, json, time, math, collections, torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
ARGV = list(sys.argv); sys.argv = [sys.argv[0]]
from b6_rwkv import hit
from b2_conf import scored_greedy
STORIES = list(range(22, 102)); PRACTICE = set(range(22, 62))
OUT = "ag6_answers.json"


def main():
    from rwkv7 import RWKV7, tokenizer
    m = RWKV7.load("ckpt_read1b.pth"); m.eval(); tok = tokenizer()
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; C = json.load(open("ag4_canon.json", encoding="utf-8"))
    done = {(it["story"], it["q"]): it for it in json.load(open(OUT, encoding="utf-8"))} if os.path.exists(OUT) else {}
    out = []; t0 = time.time(); k = 0
    for si in STORIES:
        s = S[si]; text = C[s["id"]]["canon"]
        for q, gold in s["qs"]:
            k += 1
            if (s["id"], q) in done: out.append(done[(s["id"], q)]); continue
            prompt = f"Story: {text}\n\nQuestion: {q}\nAnswer:"
            toks, lps = scored_greedy(m, torch.tensor([tok.encode(prompt)]), 8, tok)
            reply = tok.decode(toks).strip().split("\n")[0]
            content = [lp for t, lp in zip(toks, lps) if "\n" not in tok.decode([t])] or lps
            out.append(dict(story=s["id"], q=q, gold=gold, reply=reply, hit=hit(reply, gold), mean_lp=sum(content) / len(content), first_lp=lps[0], min_lp=min(content)))
            if k % 50 == 0: json.dump(out, open(OUT, "w", encoding="utf-8")); print(f"  {k} questions ({time.time() - t0:.0f} s)", flush=True)
    json.dump(out, open(OUT, "w", encoding="utf-8")); print(f"AG6: {len(out)} questions from canonical text in {time.time() - t0:.0f} s", flush=True)


def report():
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    B = {(it["story"], it["q"]): it for it in json.load(open("b2_conf_answers.json", encoding="utf-8"))}
    G = {(it["story"], it["q"]): it for it in json.load(open(OUT, encoding="utf-8"))}
    def kind(q): return q.split()[0].lower()
    for label, t in (("unthresholded", None), ("thresholded -0.11", -0.11)):
        for set_, idx in (("practice", [k for k in STORIES if k in PRACTICE]), ("untouched", [k for k in STORIES if k not in PRACTICE])):
            res = {}
            for src, D in (("prose", B), ("canonical", G)):
                r = w = 0; byk = collections.defaultdict(lambda: [0, 0])
                for k in idx:
                    for q, g in S[k]["qs"]:
                        it = D.get((S[k]["id"], q))
                        if it is None: continue
                        x = it["reply"].strip()
                        if x.lower() in ("unknown", "") or (t is not None and it["min_lp"] < t): continue
                        ok = hit(x, g); r += ok; w += not ok; byk[kind(q)][0 if ok else 1] += 1
                res[src] = (r - 3 * w, r, w, dict(byk))
            print(f"AG6 {label:18s} {set_:9s} prose {res['prose'][:3]} canonical {res['canonical'][:3]}")
            if set_ == "untouched": print(f"      by kind prose {res['prose'][3]}\n      by kind canon {res['canonical'][3]}")


if __name__ == "__main__":
    report() if "--report" in ARGV else main()
