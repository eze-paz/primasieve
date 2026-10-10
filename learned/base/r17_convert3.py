"""R17 step 4: a CONSISTENT role scheme (R17 arc item 1) and epsilon-tolerant induction (item 2).
Roles are now decided by surface position only, never by meaning: the noun phrase right after the verb is `theme`;
every prepositional phrase gets the preposition itself as its role name (`at`, `with`, `for`, `behind`, ...); a leading
time phrase is `when`; a trailing adverb is `manner`. The same surface always yields the same form, which is what the
inducer needs. Then the inducer is run with its own epsilon (noise tolerance) at several settings.
Run: python learned/base/r17_convert3.py"""
import os, sys, re, json, random
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from cogs_gram import induce, generate, reproduce
from cogs_lf import norm_lf
import r17_convert as C, r17_convert2 as C2, r17_qa as Q
from b6_rwkv import hit

TOK, NAMES = C.TOK, C.NAMES
PREPS = C.PLACE_P | set(C2.ROLE_P) | {"by", "after", "before", "until", "during", "across", "along", "past", "toward"}


def form_of(sentence, events):
    toks = TOK.findall(sentence)
    if not toks or toks[-1] != ".": return None
    if any(t in ";:\"!?" for t in toks): return None
    if "," in toks and (toks.count(",") > 1 or not C2.TIME_OPEN.match(sentence)): return None
    n = len(toks) - 1; used = [False] * n; defs = []; parts = []
    def bind(i, kind, head):
        if kind == "name": return head
        if kind == "def": defs.append(f"* {head} ( x _ {i} )")
        else: parts.append(f"{head} ( x _ {i} )")
        return f"x _ {i}"
    i = 0; time_span = None
    m = C2.TIME_OPEN.match(sentence)
    if m:
        k = len(TOK.findall(m.group(0))); time_span = (0, k); i = k
        for t in range(k): used[t] = True
    clause = 0
    for e in events:
        verb = e["verb"]; surface = e.get("surface")
        if not surface: return None
        a = C2.np_at(toks, i)
        if a is None: return None
        a_end, a_kind, a_head = a
        for k in range(i, a_end): used[k] = True
        if a_end >= n or toks[a_end] != surface: return None
        iv = a_end; used[iv] = True
        parts.append(f"{verb} . agent ( x _ {iv} , {bind(a_end - 1, a_kind, a_head)} )")
        if time_span and clause == 0:
            th = time_span[1] - 1; parts.append(f"{toks[th].lower()} ( x _ {th} )"); parts.append(f"{verb} . when ( x _ {iv} , x _ {th} )")
        j = iv + 1; got_theme = False
        for _ in range(3):
            if j >= n: break
            t = toks[j]
            if t in PREPS:
                p = C2.np_at(toks, j + 1, allow_bare=True)
                if p is None: return None
                parts.append(f"{verb} . {t} ( x _ {iv} , {bind(p[0] - 1, p[1], p[2])} )"); used[j] = True
                for k in range(j + 1, p[0]): used[k] = True
                j = p[0]; continue
            if t.lower() in C2.ADV and t.isalpha():
                parts.append(f"{t.lower()} ( x _ {j} )"); parts.append(f"{verb} . manner ( x _ {iv} , x _ {j} )"); used[j] = True; j += 1; continue
            if not got_theme:
                p = C2.np_at(toks, j, allow_bare=True)
                if p is None: return None
                parts.append(f"{verb} . theme ( x _ {iv} , {bind(p[0] - 1, p[1], p[2])} )")
                for k in range(j, p[0]): used[k] = True
                j = p[0]; got_theme = True; continue
            break
        i = j
        if i < n and toks[i] == "and" and clause == 0 and len(events) > 1: used[i] = True; i += 1; clause += 1; continue
        break
    if not all(used[:i]) or i != n: return None
    return " ".join(toks), (" ; ".join(defs) + " ; " if defs else "") + " AND ".join(parts)


def rows_from(corpus):
    by_sent = {}
    for e in corpus:
        if e["verified"]: by_sent.setdefault(e["sentence"], []).append(e)
    rows = []
    for s, evs in by_sent.items():
        evs = sorted(evs, key=lambda e: s.find(e["agent"]))
        for k in (1, 2):
            f = form_of(s, evs[:k])
            if f: rows.append((f[0], f[1], "in_distribution")); break
    return rows, len(by_sent)


def score(model, te, val_stories):
    cov = em = 0
    for s, gold, _ in te:
        pred = generate(model, s); cov += pred is not None; em += (pred == norm_lf(gold)) if pred else 0
    parsed = total = 0; vq = matched = right = 0
    for s in val_stories:
        sents = [x.strip() for x in Q.SENT.split(s["text"]) if x.strip()]
        for sent in sents:
            toks = TOK.findall(sent); total += 1
            if toks and toks[-1] not in ".!?": toks.append(".")
            parsed += generate(model, " ".join(toks)) is not None
        wins = [" ".join(sents[max(0, k - 1):k + 1]) for k in range(len(sents))]
        for q, gold in s["qs"]:
            vq += 1; ans = None
            for w in wins:
                ans = Q.ask(model, w, q)
                if ans: break
            if ans is not None: matched += 1; right += hit(ans, gold)
    return dict(held=(cov, em, len(te)), val_parsed=(parsed, total), qa=(matched, right, vq))


def main():
    corpus = json.load(open(os.path.join(HERE, "lf_corpus.json"), encoding="utf-8"))["stories"]
    rows, total = rows_from(corpus); random.Random(2).shuffle(rows)
    print(f"complete forms v3 (consistent roles): {len(rows)} of {total} ({100 * len(rows) / total:.0f}%)", flush=True)
    tr, te = rows[: int(len(rows) * 0.85)], rows[int(len(rows) * 0.85):]
    val = json.load(open(os.path.join(HERE, "val_stories.json"), encoding="utf-8"))["stories"] + json.load(open(os.path.join(HERE, "val_fables.json"), encoding="utf-8"))["stories"]
    out = {}
    for eps in (None, 0.05, 0.15):
        try: model = induce(tr, force_eps=eps)
        except TypeError: model = induce(tr)
        ok, wrong, nopar = reproduce(model, tr); sc = score(model, te, val)
        print(f"eps={eps}: train ok {ok} wrong {wrong} no-parse {nopar} | held-out coverage {sc['held'][0]}/{sc['held'][2]} exact {sc['held'][1]} | "
              f"validation sentences parsed {sc['val_parsed'][0]}/{sc['val_parsed'][1]} | QA matched {sc['qa'][0]}/{sc['qa'][2]} right {sc['qa'][1]}", flush=True)
        out[str(eps)] = dict(train=(ok, wrong, nopar), **sc)
    json.dump(dict(rows=len(rows), total=total, runs=out), open(os.path.join(HERE, "r17_convert3_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
