"""Builds the DRAFT test sets of the fluency battery (FLUENCY_LOOP_PLAN.md, P0) that are generated rather than written:
B2 (500 questions in ordinary phrasing, from the chat gate's answerable questions) and B10 (500 open-domain questions over
the crawl store's HELD-OUT entities). Deterministic (seeded). The owner reviews the drafts before they are frozen.

    python build_battery.py"""
import os, sys, json, random, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import symbols
from core.verdict import COMMIT, ATTRIBUTED
import chat as CH

OUT = os.path.join(HERE, "tests", "battery")
PREFIX = ["could you tell me", "do you know", "please tell me", "i wonder", "quick question:", "hey,"]


def typo(w, rng):
    if len(w) < 5: return w
    i = rng.randrange(1, len(w) - 2); return w[:i] + w[i + 1] + w[i] + w[i + 2:]


def b2():
    from textmodel import wordnet
    rng = random.Random(17); wn = wordnet(); syn = collections.defaultdict(set); by = collections.defaultdict(set)
    for w, ss in wn.items():
        for s in ss: by[s].add(w)
    for s, ws in by.items():
        for w in ws: syn[w] |= ws - {w}
    worlds, df = CH.build_worlds(); D = CH.Door(worlds, df, seed=3); items = []
    for text, typ, gold in CH.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D.turn(text)
        if rec["kind"] in (COMMIT, ATTRIBUTED) and rec["values"] and CH.score(rec, typ, gold, worlds[0].label) == "correct":
            items.append((text, [str(v) for v in rec["values"]]))
    name_words = set()
    for wld in worlds:
        for t in getattr(getattr(wld, "recs", None), "tables", {}).values():
            for vals in t.values.values(): name_words |= {str(v).lower() for v in vals}
    for text, gold in items:
        fr = CH.reason(text, worlds, df, cats="LN")
        name_words |= {" ".join(fr["syms"][r[0]:r[1]]) for r in fr.get("readings", []) if r[2] in ("E", "F") and r[1] - r[0] == 1}
    out = []
    for text, gold in items:
        w = text.split()
        content = [i for i, x in enumerate(w) if len(x) > 3 and x not in ("what", "which", "who", "many")]
        forms = [f"{rng.choice(PREFIX)} {text}", (text.replace("what is", "what's", 1) if "what is" in text else text + "?")]
        if content:
            i = rng.choice(content); forms.append(" ".join(w[:i] + [typo(w[i], rng)] + w[i + 1:]))
            # honesty_prereg.md: never swap a word a world reads as a name or a filter value (gadget -> widget is another product)
            alts = sorted(a for a in syn.get(w[i], ()) if a.isalpha()) if w[i] not in name_words else []
            forms.append(" ".join(w[:i] + [rng.choice(alts)] + w[i + 1:]) if alts else f"{text} please")
        if w[0] in ("what", "who") and len(w) > 3 and w[1] == "is": forms.append(" ".join(w[2:]) + " is " + w[0])
        else: forms.append(f"tell me {text}")
        for f in forms[:5]: out.append(dict(q=f, gold=gold, source=text))
    json.dump(dict(note="B2 DRAFT: ordinary phrasings (prefixes, contractions, one typo, one WordNet synonym, moved question word) of the chat gate's answerable questions; gold = the original answer. Review before freezing.", items=out[:500]),
              open(os.path.join(OUT, "questions.json"), "w", encoding="utf-8"), indent=0)
    return len(out[:500])


def b10():
    from kb_guess import load_entities, labels
    from guess import held_out
    rng = random.Random(23); ents = [e for e in load_entities() if held_out(e[0])]
    props = ["country", "capital", "continent", "official language", "currency", "instance of", "occupation", "country of citizenship"]
    pool = [(l, p, sorted(set(c[p]))[:5]) for q, l, c in ents for p in props if c.get(p) and l.isascii() and len(l.split()) <= 4]
    rng.shuffle(pool); out = [dict(q=f"what is the {p} of {l.lower()}", gold=[g for g in vals], entity=l, property=p) for l, p, vals in pool[:500]]
    json.dump(dict(note="B10 DRAFT: open-domain questions over the crawl store's HELD-OUT entities (guess_prereg.md's split); gold = the store's values. Review before freezing.", items=out),
              open(os.path.join(OUT, "open_domain.json"), "w", encoding="utf-8"), indent=0)
    return len(out)


def check_dialogues():
    """prints the engine's offline answer beside each drafted gold, for the owner's (and the builder's) review"""
    worlds, df = CH.build_worlds(); d = json.load(open(os.path.join(OUT, "dialogues.json"), encoding="utf-8"))
    for dl in d["dialogues"]:
        D = CH.Door(worlds, df, seed=3)
        for turn, gold in dl["turns"]:
            r = D.turn(turn); ok = any(g.lower() in r["reply"].lower() for g in gold)
            print(f"  {dl['id']} {'ok ' if ok else 'MISS'} {turn!r:48s} gold {gold} | {r['reply'][:90]}".encode("ascii", "replace").decode())


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    print("B2", b2()); print("B10", b10())
    check_dialogues()
