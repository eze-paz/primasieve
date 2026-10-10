"""R17 feasibility probe: feed English (sentence, silver logical form) rows to the project's grammar inducer
(cogs_gram.induce / generate / reproduce) and see what it learns. Rows come from lf_corpus.json's verified story events
whose fillers are a name or a determiner + noun; the logical form uses COGS's own syntax with token positions.
Run: python learned/base/r17_probe.py"""
import os, sys, re, json, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT)
from cogs_gram import induce, generate, reproduce
from cogs_lf import norm_lf

TOK = re.compile(r"[A-Za-z][\w'-]*|[.,;:!?\"]")
DETS = {"the": True, "a": False, "an": False}


def span_head(toks, span):
    """token index of a filler's head and whether it is definite, or None when the filler is not a name / det + noun"""
    words = span.split()
    if len(words) == 1 and words[0][:1].isupper():                             # a name
        for i, t in enumerate(toks):
            if t == words[0]: return i, "name"
        return None
    if len(words) == 2 and words[0].lower() in DETS and words[1][:1].islower():
        for i in range(len(toks) - 1):
            if toks[i].lower() == words[0].lower() and toks[i + 1] == words[1]: return i + 1, ("def" if DETS[words[0].lower()] else "indef")
    return None


def row_of(e):
    toks = TOK.findall(e["sentence"])
    if not toks or toks[-1] != ".": return None
    if any(t in ",;:\"!?" for t in toks): return None                        # simple sentences only for the probe
    a = span_head(toks, e["agent"]); p = span_head(toks, e["patient"]); v = e.get("surface")
    if a is None or p is None or not v: return None
    try: iv = toks.index(v)
    except ValueError: return None
    verb = e["verb"]; defs = []; parts = []
    def noun(idx, kind, word):
        if kind == "name": return word
        if kind == "def": defs.append(f"* {word} ( x _ {idx} )")
        else: parts.append(f"{word} ( x _ {idx} )")
        return f"x _ {idx}"
    av = noun(a[0], a[1], toks[a[0]]); pv = noun(p[0], p[1], toks[p[0]])
    parts.append(f"{verb} . agent ( x _ {iv} , {av} )"); parts.append(f"{verb} . theme ( x _ {iv} , {pv} )")
    lf = (" ; ".join(defs) + " ; " if defs else "") + " AND ".join(parts)
    return (" ".join(toks), lf, "in_distribution")


def main():
    corpus = json.load(open(os.path.join(HERE, "lf_corpus.json"), encoding="utf-8"))["stories"]
    rows = [r for r in (row_of(e) for e in corpus if e["verified"]) if r]
    random.Random(0).shuffle(rows); seen = set(); uniq = []
    for r in rows:
        if r[0] not in seen: seen.add(r[0]); uniq.append(r)
    train, test = uniq[:1500], uniq[1500:1800]
    print(f"rows {len(uniq)} unique from {len(rows)}; train {len(train)} test {len(test)}")
    for s, lf, _ in train[:3]: print("  ", s, "|", lf)
    model = induce(train)
    ok, wrong, nopar = reproduce(model, train)
    print(f"reproduce on train: ok {ok} wrong {wrong} no-parse {nopar}")
    em = cov = 0
    for s, gold, _ in test:
        pred = generate(model, s)
        if pred is not None: cov += 1; em += (pred == norm_lf(gold))
    print(f"held-out story sentences: coverage {cov}/{len(test)}, exact {em}/{len(test)}")
    real = json.load(open(os.path.join(HERE, "lf_corpus.json"), encoding="utf-8"))["real"]
    rc = 0; shown = 0
    for x in real[:200]:
        toks = TOK.findall(x["sentence"])
        if not toks or toks[-1] != ".": continue
        pred = generate(model, " ".join(toks))
        if pred is not None:
            rc += 1
            if shown < 5: shown += 1; print("  real:", x["sentence"][:80], "->", pred[:120])
    print(f"real book sentences (200): parsed {rc}")


if __name__ == "__main__":
    main()
