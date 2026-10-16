"""AG15 (AG_prereg.md): every question line of the untouched dev block regenerated with the AG13c allowance (zero or one
'?', the syntax rule places it); story lines from AG14. Writes ag15_lines.json and scores it. Run: py -3.12 ag15_q.py"""
import os, sys, json, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
sys.argv = [sys.argv[0], "--score", "--grammar"]
import torch
import ag10_slots as G
from ag13b_q import Q_PROMPT2, KINDS
from ag3_canon import content
import ag1_translator as A


def main():
    from rwkv7 import RWKV7, tokenizer
    m = RWKV7.load(G.CKPT); m.eval(); tok = tokenizer()
    D = json.load(open("ag14_lines.json", encoding="utf-8")); D.pop("_stats", None)
    OUT = "ag15_lines.json"; done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    stats = collections.Counter(done.pop("_stats", {})); t0 = time.time(); n = 0
    for sid, rec in D.items():
        if sid in done: continue
        for qq in rec["qs"]:
            n += 1; q = qq["q"]; allowed = set(content(q)) | {A.lemma(w) for w in content(q)} | {"the", "a", "an"}
            prompt = Q_PROMPT2 if q.lower().startswith(KINDS) else G.Q_PROMPT; qd = None
            for d in G.parse(G.gen(m, tok, prompt.format(q=q), n=60)):
                if sum(1 for v in d.values() if v == "?") > 1: stats["q15:blanks"] += 1; continue
                if not d["DID"] or d["DID"] == "?": stats["q15:no did"] += 1; continue
                if not G.provenance_ok(d, allowed): stats["q15:invented"] += 1; continue
                qd = d; stats["q15:kept"] += 1; break
            if qd is None: stats["q15:none"] += 1
            qq["qline"] = qd
        done[sid] = rec; done["_stats"] = dict(stats); json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1)
        print(f"  {sid} ({n} questions, {time.time() - t0:.0f} s) {dict(stats)}", flush=True)
    print(f"AG15: {n} question lines regenerated ({time.time() - t0:.0f} s)", flush=True)
    G.OUT = OUT; G.score()


if __name__ == "__main__":
    main()
