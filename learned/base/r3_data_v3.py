"""R3c data: traces whose hits are two-sentence windows, over texts that are generated stories planted in REAL book
text (training Gutenberg books for training, held-out books for the tests), plus planted counterfactual statements.
Run: python learned/base/r3_data_v3.py  -> r3_train_v3.json, r3_b6real_v3.json, r3_counter_v3.json"""
import os, sys, json, random, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data import books, read
from store import Store, render, query_for, entity_of
from r3_data import counter_facts

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); W = 1


POLICY = "plain"


def trace(store, question, gold):
    query = query_for(question); hits = store.grep(query, 3, window=W, entity=entity_of(question) if POLICY == "entity" else None)
    found = any(any(re.sub(r"[^a-z0-9 ]", " ", g.lower()).strip() in re.sub(r"[^a-z0-9 ]", " ", s.lower()) for g in gold) for _, s in hits)
    return dict(prompt=render(question, query, hits), answer=gold[0] if found else "unknown", found=found)


def passage(R, texts, n_words=1500):
    t = R.choice(texts); paras = [p for p in t.split("\n") if 200 < len(p) < 1500]
    if len(paras) < 3: return passage(R, texts, n_words)
    start = R.randrange(0, max(1, len(paras) - 3)); chunk = []
    while sum(len(p.split()) for p in chunk) < n_words and start + len(chunk) < len(paras): chunk.append(paras[start + len(chunk)])
    return chunk


def main():
    global POLICY
    if "--entity" in sys.argv: POLICY = "entity"
    suffix = "_v3e" if POLICY == "entity" else "_v3"
    train_ids, held_ids = books(); R = random.Random(5)
    train_texts = [read(b) for b in R.sample(train_ids, 60)]; held_texts = [read(b) for b in held_ids]
    stories = json.load(open(os.path.join(HERE, "stories_train_v2.json"), encoding="utf-8")); cf = counter_facts(R)
    out = []
    if "--tests-only" in sys.argv: out = None
    while out is not None and len(out) < 3000:
        chunk = passage(R, train_texts); planted = R.sample(stories, 3); c = R.choice(cf)
        for s in planted: chunk.insert(R.randrange(len(chunk) + 1), s["text"])
        chunk.insert(R.randrange(len(chunk) + 1), c["statement"]); st = Store(" ".join(chunk))
        r = R.random()
        if r < 0.2: q, gold = c["question"], c["gold"]
        elif r < 0.35:
            other = R.choice(stories); q, gold = R.choice(other["qs"]); gold = ["unknown"] if other not in planted else gold
        else: s = R.choice(planted); q, gold = R.choice(s["qs"])
        tr = trace(st, q, gold)
        if gold == ["unknown"]: tr["answer"] = "unknown"
        out.append(dict(prompt=tr["prompt"], answer=tr["answer"]))
    if out is not None:
        json.dump(out, open(os.path.join(HERE, "r3_train_v3.json"), "w", encoding="utf-8"), indent=0)
        print(len(out), "v3 traces;", sum(t["answer"] == "unknown" for t in out), "unknown; mean prompt chars", sum(len(t["prompt"]) for t in out) // len(out))
    # tests: the same B6-in-real-text placement as r3_b6real.json but with window hits; counterfactuals in held-out text
    b6 = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]; R2 = random.Random(21); test = []
    for s in b6:
        chunk = passage(R2, held_texts); chunk.insert(R2.randrange(len(chunk) + 1), s["text"]); st = Store(" ".join(chunk))
        for q, gold in s["qs"]:
            tr = trace(st, q, gold); test.append(dict(story=s["id"], q=q, gold=gold, prompt=tr["prompt"], found=tr["found"]))
    json.dump(test, open(os.path.join(HERE, f"r3_b6real{suffix}.json"), "w", encoding="utf-8"), indent=1)
    print("B6-real v3:", len(test), "questions; grep finds the gold in", sum(t["found"] for t in test))
    cf2 = counter_facts(random.Random(99)); test = []
    for c in cf2:
        chunk = passage(R2, held_texts); chunk.insert(R2.randrange(len(chunk) + 1), c["statement"]); st = Store(" ".join(chunk))
        tr = trace(st, c["question"], c["gold"]); test.append(dict(q=c["question"], gold=c["gold"], world=c["world"], prompt=tr["prompt"], found=tr["found"]))
    json.dump(test, open(os.path.join(HERE, f"r3_counter{suffix}.json"), "w", encoding="utf-8"), indent=1)
    print("counter v3:", len(test), "; grep finds the planted sentence in", sum(t["found"] for t in test))


if __name__ == "__main__":
    main()
