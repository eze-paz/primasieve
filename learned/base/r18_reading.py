"""R18: comprehension vs input form (see R18_prereg.md). Run: python learned/base/r18_reading.py"""
import os, sys, re, json, torch
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from rwkv7 import RWKV7, tokenizer
from b6_rwkv import hit
import battery

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")


def notes_for(R, text):
    out = []; R.last_agent = None; R.last_patient = None
    for s in SENT.split(text):
        try: evs = R.read(s)
        except Exception: evs = []
        for e in evs:
            if e.get("agent") and e.get("verb") and e.get("patient") and e.get("status") == "realis":
                surf = re.findall(r"[A-Za-z']+", s)[e["pos"]] if e.get("pos") is not None else e["verb"]
                out.append(f"{e['agent']} {surf} {e['patient']}")
    return out


def answer(m, tok, prompt):
    return tok.decode(m.greedy(torch.tensor([tok.encode(prompt)]), 8, tok=tok)).strip().split("\n")[0]


def run(m, tok, R, stories, label):
    score = dict(chunk=0, windows=0, chunk_notes=0, notes_only=0); n = 0
    for s in stories:
        sents = [x.strip() for x in SENT.split(s["text"]) if x.strip()]; wins = [" ".join(sents[max(0, k - 1):k + 1]) for k in range(len(sents))]
        notes = notes_for(R, s["text"]); note_txt = "\n".join("- " + x for x in notes) if notes else "- (none)"
        for q, gold in s["qs"]:
            n += 1
            a = answer(m, tok, f"Story: {s['text']}\n\nQuestion: {q}\nAnswer:"); score["chunk"] += hit(a, gold)
            got = False
            for w in wins:
                a = answer(m, tok, f"Story: {w}\n\nQuestion: {q}\nAnswer:")
                if a and "unknown" not in a.lower(): got = hit(a, gold); break
            score["windows"] += got
            a = answer(m, tok, f"Story: {s['text']}\n\nNotes:\n{note_txt}\n\nQuestion: {q}\nAnswer:"); score["chunk_notes"] += hit(a, gold)
            a = answer(m, tok, f"Story: {note_txt}\n\nQuestion: {q}\nAnswer:"); score["notes_only"] += hit(a, gold)
    print(f"{label} ({n}): " + "  ".join(f"{k} {v}" for k, v in score.items()), flush=True)
    return score, n


def main():
    m = RWKV7.load(os.path.join(HERE, "ckpt_read1b.pth")); m.eval(); tok = tokenizer(); R = battery.door().events.reader
    val = json.load(open(os.path.join(HERE, "val_stories.json"), encoding="utf-8"))["stories"] + json.load(open(os.path.join(HERE, "val_fables.json"), encoding="utf-8"))["stories"]
    v, n = run(m, tok, R, val, "validation"); res = dict(validation=v)
    if v["chunk_notes"] >= v["chunk"] + 5:
        print("R18-a PASS -> B6 once:")
        res["b6"], _ = run(m, tok, R, json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"], "B6")
    else: print("R18-a MISS -> B6 not run")
    json.dump(res, open(os.path.join(HERE, "r18_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
