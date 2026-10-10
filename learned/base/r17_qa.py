"""R17-a: a question layer over the INDUCED grammar's parses. Induce the grammar from the complete silver forms
(r17_convert), parse the window sentences of a validation story with it, and answer a question by role: for
'Who V X?' the agent of a clause whose verb lemma matches V; for 'What did A V?' its theme; 'Where did A V?' its
location. No hand-written sentence shapes; only the question-to-role map and the lemma match.
Run: python learned/base/r17_qa.py"""
import os, sys, re, json, random
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from cogs_gram import induce, generate
import r17_convert as C
from b6_rwkv import hit
from induced_reader import lemma, same_verb

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
PRED = re.compile(r"(\w+) \. (agent|theme|location) \( x _ (\d+) , (x _ \d+|[A-Z]\w*) \)")
NOUN = re.compile(r"(?:\* )?(\w+) \( x _ (\d+) \)")


def clauses(lf):
    """-> list of dict(verb, agent, theme, location) with fillers as surface words"""
    nouns = {m.group(2): m.group(1) for m in NOUN.finditer(lf)}
    out = {}
    for verb, role, iv, filler in PRED.findall(lf):
        f = nouns.get(filler[4:], None) if filler.startswith("x _") else filler
        out.setdefault(iv, dict(verb=verb))[role] = f
    return list(out.values())


def ask(model, window, question):
    m = re.match(r"Who (\w+) (.+)\?$", question); role = verb = None
    if m and m.group(1).lower() not in ("was", "were", "is", "are", "did", "had", "has"): role, verb = "agent", m.group(1)
    m2 = re.match(r"(What|Where) did (.+?) (\w+)(?: .*)?\?$", question)
    if m2 and m2.group(3).lower() not in ("do",): role, verb = ("theme" if m2.group(1) == "What" else "location"), m2.group(3)
    if role is None: return None
    for s in SENT.split(window):
        toks = C.TOK.findall(s)
        if not toks: continue
        if toks[-1] != ".": toks = toks + ["."] if toks[-1] not in ".!?" else toks[:-1] + ["."]
        lf = generate(model, " ".join(toks))
        if lf is None: continue
        for c in clauses(lf):
            if same_verb(c["verb"], verb) and c.get(role): return c[role]
    return None


def main():
    corpus = json.load(open(os.path.join(HERE, "lf_corpus.json"), encoding="utf-8"))["stories"]
    by_sent = {}
    for e in corpus:
        if e["verified"]: by_sent.setdefault(e["sentence"], []).append(e)
    rows = []
    for s, evs in by_sent.items():
        evs = sorted(evs, key=lambda e: s.find(e["agent"]))
        for k in (1, 2):
            f = C.form_of(s, evs[:k])
            if f: rows.append((f[0], f[1], "in_distribution")); break
    model = induce(rows); print(f"induced from {len(rows)} complete forms", flush=True)
    matched = right = 0; n = 0
    for name in ("val_stories.json", "val_fables.json"):
        for s in json.load(open(os.path.join(HERE, name), encoding="utf-8"))["stories"]:
            sents = [x.strip() for x in SENT.split(s["text"]) if x.strip()]; wins = [" ".join(sents[max(0, k - 1):k + 1]) for k in range(len(sents))]
            for q, gold in s["qs"]:
                n += 1; ans = None
                for w in wins:
                    ans = ask(model, w, q)
                    if ans: break
                if ans is not None:
                    matched += 1; ok = hit(ans, gold); right += ok
                    print(f"  {'ok' if ok else 'WRONG'}: {q} -> {ans!r} (gold {gold[0]})".encode("ascii", "replace").decode())
    print(f"induced reader on validation: matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f}); R17-a bar: matched >= 43 at >= 0.95")


if __name__ == "__main__":
    main()
