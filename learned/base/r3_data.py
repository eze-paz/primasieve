"""R3 data: long texts (dozens of generated stories concatenated, plus planted statements that contradict world
knowledge), questions whose answers live in one sentence somewhere in the text, and the engine's trace: query -> hits ->
answer. The answer is "unknown" when no hit holds it. Also the two R3 test sets:
  r3_b6long.json    -- the 20 B6 stories each buried in a long text of training-style stories; the 100 B6 questions
  r3_counter.json   -- 100 facts from facts_probe.json with their answers swapped, planted in long texts; the
                       question is the fact's question and the gold is the planted (wrong-in-the-world) answer
Run: python learned/base/r3_data.py  -> learned/base/{r3_train.json, r3_b6long.json, r3_counter.json}"""
import os, json, random, re
from store import Store, render, query_for

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
QUESTION = {"The capital of": "What is the capital of", "The author of": "Who is the author of", "The currency of": "What is the currency of",
            "The language spoken in": "What language is spoken in", "The composer of": "Who is the composer of", "The painter of": "Who is the painter of",
            "The founder of": "Who is the founder of"}


def counter_facts(R):
    """facts whose answers are swapped among facts of the same template (capital of Japan -> Rome)"""
    facts = json.load(open(os.path.join(HERE, "facts_probe.json"), encoding="utf-8")); out = []
    by = {}
    for p, g in facts:
        for pre, q in QUESTION.items():
            if p.startswith(pre): by.setdefault(pre, []).append((p, g)); break
    for pre, items in by.items():
        golds = [g[0] for _, g in items]
        for p, g in items:
            wrong = R.choice([x for x in golds if x != g[0]])
            subj = re.sub(r"\s+(is|was|are|were)(\s+the)?$", "", p[len(pre):].strip())
            out.append(dict(statement=f"{p} {wrong.title()}.", question=f"{QUESTION[pre]} {subj}?", gold=[wrong], world=g))
    return out


def trace(store, question, gold):
    query = query_for(question); hits = store.grep(query, 3)
    found = any(any(re.sub(r"[^a-z0-9 ]", " ", g.lower()).strip() in re.sub(r"[^a-z0-9 ]", " ", s.lower()) for g in gold) for _, s in hits)
    return dict(prompt=render(question, query, hits), answer=gold[0] if found else "unknown", found=found, hits=[i for i, _ in hits])


def main():
    R = random.Random(3); stories = json.load(open(os.path.join(HERE, "stories_train.json"), encoding="utf-8"))
    cf = counter_facts(R); print(len(cf), "counterfactual statements")
    # ---- training: 3000 long texts of 25 stories (+ a few counterfactual statements as their own sentences); 1 question each
    train = []
    while len(train) < 3000:
        chunk = R.sample(stories, 25); planted = R.sample(cf, 3)
        parts = [s["text"] for s in chunk]
        for c in planted: parts.insert(R.randrange(len(parts) + 1), c["statement"])
        text = " ".join(parts); st = Store(text)
        if R.random() < 0.25:
            c = R.choice(planted); q, gold = c["question"], c["gold"]
        elif R.random() < 0.15:
            other = R.choice(stories); q, gold = R.choice(other["qs"]); gold = ["unknown"] if other not in chunk else gold
        else:
            s = R.choice(chunk); q, gold = R.choice(s["qs"])
        tr = trace(st, q, gold)
        if gold == ["unknown"]: tr["answer"] = "unknown"
        train.append(dict(prompt=tr["prompt"], answer=tr["answer"]))
    json.dump(train, open(os.path.join(HERE, "r3_train.json"), "w", encoding="utf-8"), indent=0)
    print(len(train), "training traces;", sum(t["answer"] == "unknown" for t in train), "unknown")
    # ---- test 1: B6 stories buried in long texts
    b6 = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]; R2 = random.Random(11); test = []
    for s in b6:
        parts = [x["text"] for x in R2.sample(stories, 40)]; parts.insert(R2.randrange(len(parts) + 1), s["text"]); st = Store(" ".join(parts))
        for q, gold in s["qs"]:
            tr = trace(st, q, gold); test.append(dict(story=s["id"], q=q, gold=gold, prompt=tr["prompt"], found=tr["found"]))
    json.dump(test, open(os.path.join(HERE, "r3_b6long.json"), "w", encoding="utf-8"), indent=1)
    print("B6-long:", len(test), "questions; grep finds the gold sentence in", sum(t["found"] for t in test))
    # ---- test 2: counterfactual facts planted in long texts (a different swap seed from training)
    cf2 = counter_facts(random.Random(99)); test = []
    for c in cf2:
        parts = [x["text"] for x in R2.sample(stories, 40)]; parts.insert(R2.randrange(len(parts) + 1), c["statement"]); st = Store(" ".join(parts))
        tr = trace(st, c["question"], c["gold"]); test.append(dict(q=c["question"], gold=c["gold"], world=c["world"], prompt=tr["prompt"], found=tr["found"]))
    json.dump(test, open(os.path.join(HERE, "r3_counter.json"), "w", encoding="utf-8"), indent=1)
    print("counterfactual:", len(test), "questions; grep finds the planted sentence in", sum(t["found"] for t in test))


if __name__ == "__main__":
    main()
