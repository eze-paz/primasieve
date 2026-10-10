"""R17 step 2: complete silver logical forms. From the hand reader's event (agent, verb, patient) plus the sentence's
place and time phrases (the merge layer's adjunct patterns), emit a COGS-syntax form that accounts for every content
span: agent, theme, location (preposition + noun), time (a time phrase), and a second clause joined by 'and' when the
reader gives two events. Sentences with unexplained spans are dropped (the inducer needs complete forms).
Names must be in the name pool (reader noise such as 'Miss' is dropped). Then induce and measure held-out coverage.
Run: python learned/base/r17_convert.py"""
import os, sys, re, json, random
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from cogs_gram import induce, generate, reproduce
from cogs_lf import norm_lf

TOK = re.compile(r"[A-Za-z][\w'-]*|[.,;:!?\"]")
DETS = {"the": True, "a": False, "an": False, "his": True, "her": True, "their": True, "its": True}
PLACE_P = {"to", "at", "in", "on", "behind", "under", "across", "near", "into", "toward", "towards", "over", "through", "beside", "from"}
NAMES = set()
try:
    _n = json.load(open(os.path.join(ROOT, "learned", "cache", "names.json"), encoding="utf-8"))["pool"]; NAMES = set(_n["f"]) | set(_n["m"]) | set(_n["o"])
except Exception: pass


def np_at(toks, i):
    """a noun phrase starting at token i: name -> (end, 'name'), det + noun -> (end, def/indef); else None"""
    if toks[i][:1].isupper() and toks[i] in NAMES: return i + 1, "name", toks[i]
    if toks[i].lower() in DETS and i + 1 < len(toks) and toks[i + 1][:1].islower() and toks[i + 1].isalpha():
        j = i + 1
        if j + 1 < len(toks) and toks[j + 1][:1].islower() and toks[j + 1].isalpha() and toks[j + 1] not in PLACE_P and not toks[j + 1].endswith("ed") and toks[j + 1] not in ("and", "with", "for", "of"):
            # two-word noun phrase ("church tower"): the head is the last word; the first is an adjective/noun modifier
            return j + 2, ("def" if DETS[toks[i].lower()] else "indef"), toks[j + 1]
        return j + 1, ("def" if DETS[toks[i].lower()] else "indef"), toks[j]
    return None


def form_of(sentence, events):
    """-> (tokens, lf) when every token is explained; else None"""
    toks = TOK.findall(sentence)
    if not toks or toks[-1] != "." or any(t in ",;:\"!?" for t in toks): return None
    n = len(toks) - 1; used = [False] * n; defs = []; parts = []
    def bind(i, kind, head):
        if kind == "name": return head
        if kind == "def": defs.append(f"* {head} ( x _ {i} )")
        else: parts.append(f"{head} ( x _ {i} )")
        return f"x _ {i}"
    i = 0; clause = 0
    for e in events:
        verb = e["verb"]; surface = e.get("surface")
        if not surface: return None
        a = np_at(toks, i)
        if a is None: return None
        a_end, a_kind, a_head = a; a_head_idx = a_end - 1
        for k in range(i, a_end): used[k] = True
        if toks[a_end] != surface: return None
        iv = a_end; used[iv] = True
        parts.append(f"{verb} . agent ( x _ {iv} , {bind(a_head_idx, a_kind, a_head)} )")
        j = iv + 1
        if j < n and toks[j] in PLACE_P:                                  # verb + preposition + np: a location
            p = np_at(toks, j + 1)
            if p is None: return None
            parts.append(f"{verb} . location ( x _ {iv} , {bind(p[0] - 1, p[1], p[2])} )"); used[j] = True
            for k in range(j + 1, p[0]): used[k] = True
            j = p[0]
        else:
            p = np_at(toks, j) if j < n else None
            if p is None: return None
            parts.append(f"{verb} . theme ( x _ {iv} , {bind(p[0] - 1, p[1], p[2])} )")
            for k in range(j, p[0]): used[k] = True
            j = p[0]
            if j < n and toks[j] in PLACE_P:                              # theme then a place
                p2 = np_at(toks, j + 1)
                if p2 is None: return None
                parts.append(f"{verb} . location ( x _ {iv} , {bind(p2[0] - 1, p2[1], p2[2])} )"); used[j] = True
                for k in range(j + 1, p2[0]): used[k] = True
                j = p2[0]
        i = j
        if i < n and toks[i] == "and" and clause == 0 and len(events) > 1: used[i] = True; i += 1; clause += 1; continue
        break
    if not all(used[:i]) or i != n: return None
    return " ".join(toks), (" ; ".join(defs) + " ; " if defs else "") + " AND ".join(parts)


def main():
    corpus = json.load(open(os.path.join(HERE, "lf_corpus.json"), encoding="utf-8"))["stories"]
    by_sent = {}
    for e in corpus:
        if e["verified"]: by_sent.setdefault(e["sentence"], []).append(e)
    rows = []
    for s, evs in by_sent.items():
        evs = sorted(evs, key=lambda e: s.find(e["agent"]))
        for k in (1, 2):
            f = form_of(s, evs[:k])
            if f: rows.append((f[0], f[1], "in_distribution")); break
    random.Random(2).shuffle(rows); print(f"complete forms: {len(rows)} of {len(by_sent)} sentences")
    for r in rows[:4]: print("  ", r[0], "|", r[1])
    tr, te = rows[: int(len(rows) * 0.85)], rows[int(len(rows) * 0.85):]
    model = induce(tr); ok, wrong, nopar = reproduce(model, tr); print(f"train reproduce ok {ok} wrong {wrong} no-parse {nopar}")
    cov = em = 0
    for s, gold, _ in te:
        pred = generate(model, s); cov += pred is not None; em += (pred == norm_lf(gold)) if pred else 0
    print(f"held-out: coverage {cov}/{len(te)} exact {em}/{len(te)}")
    real = json.load(open(os.path.join(HERE, "lf_corpus.json"), encoding="utf-8"))["real"]; rc = 0; shown = 0
    for x in real[:300]:
        toks = TOK.findall(x["sentence"])
        if not toks or toks[-1] != ".": continue
        pred = generate(model, " ".join(toks))
        if pred is not None:
            rc += 1
            if shown < 6: shown += 1; print("  real:", x["sentence"][:70], "->", pred[:110])
    print(f"real book sentences (300): parsed {rc}")
    json.dump(dict(rows=len(rows), train=(ok, wrong, nopar), held=(cov, em, len(te)), real_parsed=rc), open(os.path.join(HERE, "r17_convert_results.json"), "w"))


if __name__ == "__main__":
    main()
