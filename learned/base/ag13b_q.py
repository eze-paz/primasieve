"""AG13b (AG_prereg.md): new question lines for when / why / whose / how questions with their own few-shot; story lines
from AG13. Writes ag13b_lines.json and scores it with the syntax rule. Run: py -3.12 ag13b_q.py"""
import os, sys, json, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
sys.argv = [sys.argv[0], "--score", "--grammar"]
import torch
import ag10_slots as G
from ag3_canon import content
import ag1_translator as A
Q_PROMPT2 = ("Instruction: Write the question as one line of slots. Put ? in the slot that is asked. Use only words from the question. Write - for an empty slot.\n\n"
             "Question: When did Rosa take the key?\nWHO: Rosa | DID: take | WHAT: the key | WHERE: - | WHEN: ? | WHY: -\n\n"
             "Question: Why did the farmer sell the cow?\nWHO: the farmer | DID: sell | WHAT: the cow | WHERE: - | WHEN: - | WHY: ?\n\n"
             "Question: When was the bridge finished?\nWHO: the bridge | DID: was finished | WHAT: - | WHERE: - | WHEN: ? | WHY: -\n\n"
             "Question: Why was the door open?\nWHO: the door | DID: was | WHAT: open | WHERE: - | WHEN: - | WHY: ?\n\n"
             "Question: Whose hat blew away?\nWHO: ? | DID: blew away | WHAT: hat | WHERE: - | WHEN: - | WHY: -\n\n"
             "Question: How many eggs did the hen lay?\nWHO: the hen | DID: lay | WHAT: ? | WHERE: - | WHEN: - | WHY: -\n\n"
             "Question: {q}\n")
KINDS = ("when", "why", "whose", "how")


def main():
    from rwkv7 import RWKV7, tokenizer
    m = RWKV7.load(G.CKPT); m.eval(); tok = tokenizer()
    D = json.load(open("ag13_lines.json", encoding="utf-8")); stats = collections.Counter(D.pop("_stats", {})); t0 = time.time(); n = 0
    for sid, rec in D.items():
        for qq in rec["qs"]:
            if not qq["q"].lower().startswith(KINDS): continue
            n += 1; allowed = set(content(qq["q"])) | {A.lemma(w) for w in content(qq["q"])} | {"the", "a", "an"}
            qd = None
            for d in G.parse(G.gen(m, tok, Q_PROMPT2.format(q=qq["q"]), n=60)):
                if sum(1 for v in d.values() if v == "?") > 1: stats["q13b:blanks"] += 1; continue      # AG13c: zero "?" allowed; the syntax rule places it
                if not d["DID"] or d["DID"] == "?": stats["q13b:no did"] += 1; continue
                if not G.provenance_ok(d, allowed): stats["q13b:invented"] += 1; continue
                qd = d; stats["q13b:kept"] += 1; break
            qq["qline13b"] = qd; qq["qline"] = qd or qq["qline"]
            print(f"  {n} {qq['q']} -> {qd} ({time.time() - t0:.0f} s)".encode("ascii", "replace").decode(), flush=True)
    D["_stats"] = dict(stats); json.dump(D, open("ag13c_lines.json", "w", encoding="utf-8"), indent=1)
    print(f"AG13b: {n} question lines rewritten ({time.time() - t0:.0f} s) {dict(stats)}", flush=True)
    G.OUT = "ag13c_lines.json"; G.score()


if __name__ == "__main__":
    main()
