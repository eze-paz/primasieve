"""R8: the old engine's discipline over the learned proposer. A reply is COMMITTED only if its text occurs in one of the
hits the engine was shown (the answer must be read, not produced); otherwise the engine says "unknown". Applied offline
to saved evaluation files (the prompt holds the hits, the reply is the proposal), so no model runs.
Run: python learned/base/guard.py r3_b6real_v3_ckpt_read5_s400.json [more files]"""
import os, sys, re, json
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
sys.path.insert(0, HERE)
from b6_rwkv import hit

STOP = set("the a an of to in on at and or for with by from as is was were be it he she they his her their this that".split())


def norm(s): return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def hits_of(prompt):
    body = prompt.split("Hits:\n", 1)[1].rsplit("\nAnswer:", 1)[0]
    return [re.sub(r"^\[\d+\] ", "", l) for l in body.splitlines() if l.strip() and l != "(no hits)"]


def guarded(reply, prompt):
    """commit the reply if every content word of it occurs in one hit; else unknown"""
    r = norm(reply)
    if not r or "unknown" in r: return "unknown"
    words = [w for w in r.split() if w not in STOP] or r.split()
    for h in hits_of(prompt):
        hn = norm(h)
        if all(w in hn.split() for w in words): return reply
    return "unknown"


def with_prompts(path):
    """saved evaluation items carry no prompt: join them, by index, with the test set they were run on
    (r3_<set>_<ckpt>.json -> r3_<set>.json)"""
    d = json.load(open(path, encoding="utf-8")); items = d["items"]
    m = re.match(r"(r3_[a-z0-9]+(?:_v3e?)?)_", os.path.basename(path))
    if m and not all("prompt" in x for x in items):
        test = json.load(open(m.group(1) + ".json", encoding="utf-8"))
        assert len(test) == len(items) and all(t["q"] == x["q"] for t, x in zip(test, items)), "test/result mismatch"
        for t, x in zip(test, items): x["prompt"] = t["prompt"]; x.setdefault("found", t.get("found"))
    return items


def score(path):
    items = with_prompts(path)
    raw = sum(x["hit"] for x in items); n = len(items)
    g_right = g_unk = 0; nf = [x for x in items if x.get("found") is False]; nf_unk_raw = nf_unk_g = 0
    wrong_raw = wrong_g = 0
    for x in items:
        g = guarded(x["reply"], x["prompt"]) if "prompt" in x else x["reply"]
        ok = hit(g, x["gold"]); g_right += ok; g_unk += "unknown" in g.lower()
        if x.get("found") is False: nf_unk_raw += "unknown" in x["reply"].lower(); nf_unk_g += "unknown" in g.lower()
        wrong_raw += (not x["hit"]) and "unknown" not in x["reply"].lower(); wrong_g += (not ok) and "unknown" not in g.lower()
    print(f"{os.path.basename(path)}: raw {raw}/{n} (wrong answers {wrong_raw}, unknown on not-found {nf_unk_raw}/{len(nf)}) -> "
          f"guarded {g_right}/{n} (wrong answers {wrong_g}, unknown on not-found {nf_unk_g}/{len(nf)}, unknown total {g_unk})")
    return dict(file=os.path.basename(path), raw=raw, guarded=g_right, n=n, wrong_raw=wrong_raw, wrong_guarded=wrong_g, nf=len(nf), nf_unk_raw=nf_unk_raw, nf_unk_guarded=nf_unk_g)


if __name__ == "__main__":
    out = [score(p) for p in sys.argv[1:]]
    json.dump(out, open("guard_results.json", "w"), indent=1)
