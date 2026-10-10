"""R17 step 3: converter v2 -- wider complete forms. Adds to r17_convert: bare nouns as themes and objects of
prepositions ("kept bees"), trailing prepositional adjuncts with their own roles (with -> instrument, for/to ->
beneficiary, place prepositions -> location, up to two), trailing single adverbs as manner ("first", "anyway"), and
time-phrase openings ("One summer", "The next morning", "On Friday", "In return") as a time role. Then induces the
grammar, reports completeness and held-out exactness, how many validation sentences parse, and the question layer's
score on validation (R17-a). Run: python learned/base/r17_convert2.py"""
import os, sys, re, json, random
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from cogs_gram import induce, generate, reproduce
from cogs_lf import norm_lf
import r17_convert as C
import r17_qa as Q
from b6_rwkv import hit

TOK, DETS, NAMES = C.TOK, C.DETS, C.NAMES
PLACE_P = C.PLACE_P
ROLE_P = {"with": "instrument", "for": "beneficiary", "to": "beneficiary", "about": "topic", "of": "topic", "without": "manner_of"}
FUNC = {"and", "or", "but", "that", "which", "who", "when", "while", "because", "so", "if", "as", "than", "then", "there", "here", "not", "no", "very", "too", "also",
        "he", "she", "it", "they", "him", "her", "them", "his", "their", "its", "this", "these", "those", "was", "were", "is", "are", "be", "been", "had", "has", "have",
        "did", "do", "does", "will", "would", "could", "should", "can", "may", "might", "must", "every", "each", "all", "some", "any", "one", "two", "three", "four", "five"}
ADV = {"first", "anyway", "together", "twice", "everywhere", "instead", "late", "early", "again", "away", "home", "upstairs", "downstairs", "softly", "quietly",
       "slowly", "quickly", "carefully", "alone", "back", "over", "out", "up", "down", "off", "on"}
TIME_OPEN = re.compile(r"^(One (?:summer|winter|spring|autumn|morning|evening|afternoon|night|day|foggy evening|year)|The next (?:morning|day|evening|week)|"
                       r"On (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|In (?:return|the (?:morning|evening|afternoon|spring|autumn|summer|winter|rainy season))|"
                       r"Every (?:morning|evening|day|noon|night|winter|summer|Tuesday|Thursday)|After (?:a year|a week|supper|dinner|lunch|that)|A week later|At noon|At dawn|Later|Soon|Then|Now|By autumn|By nightfall)\b,?\s*")


def np_at(toks, i, allow_bare=False):
    r = C.np_at(toks, i)
    if r: return r
    if allow_bare and i < len(toks) and toks[i][:1].islower() and toks[i].isalpha() and toks[i] not in FUNC and toks[i] not in ADV and not C.PLACE_P.__contains__(toks[i]) and toks[i] not in ROLE_P and not toks[i].endswith("ed") and not toks[i].endswith("ing"):
        return i + 1, "bare", toks[i]
    return None


def form_of(sentence, events):
    toks = TOK.findall(sentence)
    if not toks or toks[-1] != ".": return None
    if any(t in ";:\"!?" for t in toks): return None
    if "," in toks:                                                      # one leading time phrase with a comma is allowed; other commas are not
        if toks.count(",") > 1 or not TIME_OPEN.match(sentence): return None
    n = len(toks) - 1; used = [False] * n; defs = []; parts = []
    def bind(i, kind, head):
        if kind == "name": return head
        if kind == "def": defs.append(f"* {head} ( x _ {i} )")
        else: parts.append(f"{head} ( x _ {i} )")
        return f"x _ {i}"
    i = 0; time_span = None
    m = TIME_OPEN.match(sentence)
    if m:
        k = len(TOK.findall(m.group(0))); time_span = (0, k); i = k
        for t in range(k): used[t] = True
    clause = 0
    for e in events:
        verb = e["verb"]; surface = e.get("surface")
        if not surface: return None
        a = np_at(toks, i)
        if a is None: return None
        a_end, a_kind, a_head = a
        for k in range(i, a_end): used[k] = True
        if a_end >= n or toks[a_end] != surface: return None
        iv = a_end; used[iv] = True
        parts.append(f"{verb} . agent ( x _ {iv} , {bind(a_end - 1, a_kind, a_head)} )")
        if time_span and clause == 0:
            th = time_span[1] - 1; parts.append(f"{toks[th].lower()} ( x _ {th} )"); parts.append(f"{verb} . time ( x _ {iv} , x _ {th} )")
        j = iv + 1; got_theme = False
        for _ in range(3):                                               # theme, then up to two adjuncts, in any order
            if j >= n: break
            t = toks[j]
            if t in PLACE_P or t in ROLE_P:
                p = np_at(toks, j + 1, allow_bare=True)
                if p is None: return None
                role = "location" if t in PLACE_P else ROLE_P[t]
                parts.append(f"{verb} . {role} ( x _ {iv} , {bind(p[0] - 1, p[1], p[2])} )"); used[j] = True
                for k in range(j + 1, p[0]): used[k] = True
                j = p[0]; continue
            if t.lower() in ADV and t.isalpha():
                parts.append(f"{t.lower()} ( x _ {j} )"); parts.append(f"{verb} . manner ( x _ {iv} , x _ {j} )"); used[j] = True; j += 1; continue
            if not got_theme:
                p = np_at(toks, j, allow_bare=True)
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
    random.Random(2).shuffle(rows); print(f"complete forms v2: {len(rows)} of {len(by_sent)} sentences ({100 * len(rows) / len(by_sent):.0f}%)", flush=True)
    for r in rows[:3]: print("  ", r[0], "|", r[1][:120])
    tr, te = rows[: int(len(rows) * 0.85)], rows[int(len(rows) * 0.85):]
    model = induce(tr); ok, wrong, nopar = reproduce(model, tr); print(f"train reproduce ok {ok} wrong {wrong} no-parse {nopar}", flush=True)
    cov = em = 0
    for s, gold, _ in te:
        pred = generate(model, s); cov += pred is not None; em += (pred == norm_lf(gold)) if pred else 0
    print(f"held-out: coverage {cov}/{len(te)} exact {em}/{len(te)}", flush=True)
    parsed = total = 0; vq = 0; matched = right = 0
    for name in ("val_stories.json", "val_fables.json"):
        for s in json.load(open(os.path.join(HERE, name), encoding="utf-8"))["stories"]:
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
    print(f"validation sentences parsed {parsed}/{total}; questions matched {matched}/{vq}, right {right} (precision {right / max(1, matched):.2f}); R17-a bar: >= 43 at >= 0.95")
    json.dump(dict(rows=len(rows), total=len(by_sent), train=(ok, wrong, nopar), held=(cov, em, len(te)), val_parsed=(parsed, total), qa=(matched, right, vq)),
              open(os.path.join(HERE, "r17_convert2_results.json"), "w"))


if __name__ == "__main__":
    main()
