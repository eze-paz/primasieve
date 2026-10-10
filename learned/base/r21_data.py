"""R21: the exact reader as a LEARNED reader. Training pairs from the generator's exact events: for each sentence of a
story, prompt = the story so far (context for pronouns) + the sentence; answer = its event lines
'agent | verb | patient | place | recipient' ('-' for an empty slot; 'none' when the sentence has no event).
Run: python learned/base/r21_data.py  -> r21_train.json (finetune.py --data r21_train.json), r21_heldout.json (100 fresh stories)"""
import os, sys, json, random, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import worldstate as WS


def pairs(story):
    sents = [x.strip() for x in WS.SENT.split(story["text"]) if x.strip()]; out = []
    for k, sent in enumerate(sents):
        evs = [e for e in story["events"] if e[0] == k]
        ans = "; ".join(f"{a} | {v} | {p or '-'} | {place or '-'} | {rec or '-'}" for (_, a, v, p, place, rec) in evs) or "none"
        prev = " ".join(sents[:k]) if k else "(start)"                      # run 2: the whole story so far (pronouns can reach back two sentences)
        out.append(dict(prompt=f"Text: {prev}\nSentence: {sent}\nEvents:", answer=ans, sent=sent, prev=prev, events=evs))
    return out


if __name__ == "__main__":
    data = json.load(open(os.path.join(HERE, "stories_train_v2.json"), encoding="utf-8"))
    train = [dict(prompt=x["prompt"], answer=x["answer"]) for s in data if s.get("events") for x in pairs(s)]
    json.dump(train, open(os.path.join(HERE, "r21_train.json"), "w", encoding="utf-8"), indent=0)
    # held-out generator stories: a fresh seed, never trained on
    import stories_gen as SG
    ROOT = os.path.dirname(os.path.dirname(HERE))
    names = json.load(open(os.path.join(ROOT, "learned", "cache", "names.json"), encoding="utf-8"))["pool"]
    first = {g: [x for x in names[g] if x.isalpha() and 3 <= len(x) <= 9] for g in "fm"}
    R = random.Random(777); held = []; used = set()
    def P(g):
        g = g if g in ("f", "m") else R.choice("fm")
        while True:
            x = R.choice(first[g])
            if x not in used: used.add(x); return x, g
    while len(held) < 100:
        used.clear()
        for item in SG.skeletons(R, P):
            if len(item) > 2 and item[2]: held.append(dict(text=item[0], qs=item[1], events=item[2]))
    held = held[:100]
    json.dump(held, open(os.path.join(HERE, "r21_heldout.json"), "w", encoding="utf-8"), indent=0)
    print(f"train pairs {len(train)} (none: {sum(1 for x in train if x['answer'] == 'none')}); held-out stories {len(held)}")
    print(train[0]); print(train[1])
