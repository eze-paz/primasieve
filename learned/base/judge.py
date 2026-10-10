"""R15: the model as judge. Candidates are extracted exactly from the hits (capitalised names not at a sentence start,
determiner-led noun phrases); the model is asked to choose a letter; the engine commits the chosen candidate only.
Applied to the merged engine's model share. Run: python learned/base/judge.py  (validation; tests once if R15-a passes)"""
import os, sys, re, json, torch
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT); sys.argv = [sys.argv[0], "--v3"]
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import reader_check as rc
from guard import hits_of, norm
from veto import story_items, trace_items
from rwkv7 import RWKV7, tokenizer

CK = os.path.join(HERE, "ckpt_read5_s400.pth")
NP = re.compile(r"\b(?:the|a|an|his|her|their|its|two|three|four|five|some|every|one)\s+(?:[a-z][\w-]*\s+){0,2}[a-z][\w-]*")
NAME = re.compile(r"(?<![.!?\"']\s)(?<!^)\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b")
LETTERS = "ABCDEFGHIJ"


def candidates(hits, limit=8):
    out = []
    for h in hits:
        for m in NAME.finditer(h):
            c = m.group(1)
            if c.lower() not in ("the", "when", "one", "in", "on", "at", "after", "her", "his", "then", "now", "but", "and") and c not in out: out.append(c)
        for m in NP.finditer(h):
            c = m.group(0)
            if c not in out and len(c) <= 40: out.append(c)
    return out[:limit]


def judge(m, tok, question, hits):
    cands = candidates(hits)
    if not cands: return None
    choices = "\n".join(f"{LETTERS[i]}) {c}" for i, c in enumerate(cands)) + f"\n{LETTERS[len(cands)]}) none of these"
    prompt = "Question: " + question + "\nHits:\n" + "\n".join(f"[{i}] {h}" for i, h in enumerate(hits)) + "\nChoices:\n" + choices + "\nAnswer:"
    out = tok.decode(m.greedy(torch.tensor([tok.encode(prompt)]), 4, tok=tok)).strip()
    mm = re.match(r"\(?([A-J])\)?", out)
    if not mm: return None
    k = LETTERS.index(mm.group(1))
    return cands[k] if k < len(cands) else "unknown"


def run(items, label, m, tok):
    f_right = f_wrong = j_right = j_wrong = share = 0
    for it in items:
        committed, ra = rc.check(it)
        if ra is not None: continue                                          # the reader's share is untouched
        share += 1; hits = hits_of(it["prompt"])
        free = it["reply"]; ok = rc.hit(free, it["gold"]); f_right += ok; f_wrong += (not ok) and "unknown" not in free.lower()
        j = judge(m, tok, it["q"], hits) or "unknown"; ok = rc.hit(j, it["gold"]); j_right += ok; j_wrong += (not ok) and "unknown" not in j.lower()
    print(f"{label}: model share {share} | free-form right {f_right} wrong {f_wrong} | judge right {j_right} wrong {j_wrong}", flush=True)
    return share, f_right, f_wrong, j_right, j_wrong


if __name__ == "__main__":
    m = RWKV7.load(CK); m.eval(); tok = tokenizer(); B = HERE
    val = (story_items(os.path.join(B, "val_stories.json"), os.path.join(B, "b6_rwkv_val_ckpt_read1b.json"))
           + story_items(os.path.join(B, "val_fables.json"), os.path.join(B, "b6_rwkv_valfables_ckpt_read1b.json"))
           + trace_items(os.path.join(B, "r3_val_v3.json"), os.path.join(B, "r3_val_v3_ckpt_read5_s400.json")))
    v = run(val, "validation (130)", m, tok); res = dict(validation=v)
    if v[3] >= v[1] and v[4] <= 0.7 * v[2]:
        print("R15-a PASS -> test once:")
        res["test_real"] = run(trace_items(os.path.join(B, "r3_b6real_v3.json"), os.path.join(B, "r3_b6real_v3_ckpt_read5_s400.json")), "TEST real-text", m, tok)
    else: print("R15-a MISS -> test not run")
    json.dump(res, open(os.path.join(B, "r15_results.json"), "w"), indent=1)
