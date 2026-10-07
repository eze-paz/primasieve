"""Data for core/bookworld.py (bookworld_prereg.md): the event reader's verb tables (kb_events.build), and what is
learned by counting over the TRAINING books (never the held-out ones): the prose closed class, abbreviations,
determiners (closed symbols rarely followed by another closed symbol), verb-chain heads (closed symbols often followed by
a verbal base form). Never imported by core/."""
import os, sys, re, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
from core.bookworld import Book, abbreviations, tokens
import kb_events as KE

GUT = KE.GUT
CACHE = os.path.join(HERE, "..", "_nldata", "bookworld_learned.json")
CONTEXT = "according to {title}, {body}"          # how a book-local proposition is said (English data, not core/)
NARRATOR = "narrator"


def say(p): return Book.say(p, CONTEXT)


def training_texts(n=60):
    for b in KE.books(False)[:n]:
        yield open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()


def learn(R, n=60, n_closed=150):
    if os.path.exists(CACHE): return json.load(open(CACHE, encoding="utf-8"))
    texts = list(training_texts(n)); uni = collections.Counter(); pairs = []
    for t in texts:
        low = [x.lower() for x in tokens(t) if x[:1].isalpha()]; uni.update(low); pairs.append(low)
    closed = sorted({w for w, c in uni.most_common(n_closed)} | set(R.closed))
    cs = set(closed); tot = collections.Counter(); nxt = collections.defaultdict(collections.Counter)
    finc = collections.Counter()
    for f, l in R.verbs.items(): finc[l] += uni.get(f, 0)
    base_verbal = {l for l in R.base if l not in R.verbs and finc[l] >= uni.get(l, 0) > 0}
    open_fin = {f for f in R.verbs if f not in cs}; parts = set(R.participles); auxs = set(getattr(R, "auxiliaries", ()))
    for low in pairs:
        for a, b in zip(low, low[1:]):
            tot[a] += 1
            if a in cs:
                n = nxt[a]; n["closed"] += b in cs; n["base"] += b in base_verbal; n["fin"] += b in open_fin
                n["verbal"] += b in base_verbal or b in parts or b in open_fin
    big = {a for a in cs if tot[a] >= 1000}
    share = lambda a, k: nxt[a][k] / max(1, tot[a])
    # subjects: closed symbols followed by an open-class finite verb >= 15 % of the time
    subj = {a for a in big if share(a, "fin") >= 0.15}
    prev = collections.defaultdict(collections.Counter)
    for low in pairs:
        for a, b in zip(low, low[1:]):
            if b in cs: prev[b]["n"] += 1; prev[b]["subj"] += a in subj
    psub = lambda b: prev[b]["subj"] / max(1, prev[b]["n"])
    verbish = {c for c in cs if (c in R.verbs or c in parts) and prev[c]["n"] >= 50 and psub(c) >= 0.15}
    heads = {a for a in big if share(a, "base") >= 0.25 and share(a, "fin") < 0.05 and psub(a) >= 0.15}
    carriers = heads | auxs | verbish
    pc = collections.Counter()
    for low in pairs:
        for a, b in zip(low, low[1:]):
            if b in cs and a in carriers: pc[b] += 1
    skippable = {a for a in big if share(a, "verbal") >= 0.15 and pc[a] >= 0.3 * prev[a]["n"]}
    det = sorted(a for a in big if share(a, "closed") < 0.15)
    # nouns that share a form with a verb ("schools", "figures"): open finite forms preceded >= 30 % of the time by a
    # determiner-like closed symbol (followed by a closed symbol < 20 % and by an open finite form < 15 % of the time;
    # not a subject, chain head or skippable symbol)
    det2 = {a for a in big if share(a, "fin") < 0.15 and share(a, "closed") < 0.2} - subj - heads - skippable
    pf = collections.Counter(); pft = collections.Counter()
    for low in pairs:
        for a, b in zip(low, low[1:]):
            if b in open_fin: pft[b] += 1; pf[b] += a in det2
    nounish = sorted(f for f in open_fin if pft[f] >= 20 and pf[f] >= 0.3 * pft[f])
    # closed symbols that put a following name OUTSIDE the subject: followed by a closed symbol >= 35 % of the time, and
    # "<c> <Name>" continues with an unambiguous finite verb (verbish or auxiliary) < 15 % of the time
    finite_any = verbish | auxs
    cn = collections.Counter(); cv = collections.Counter()
    for t in texts:
        ts = tokens(t)
        for k in range(1, len(ts) - 2):
            a = ts[k].lower()
            if a in cs and ts[k][:1].islower() and ts[k + 1][:1].isupper() and ts[k + 1].lower() not in cs:
                j = k + 1
                while j < len(ts) and ts[j][:1].isupper(): j += 1
                cn[a] += 1; cv[a] += j < len(ts) and ts[j].lower() in finite_any
    # bookcheck (3), amended before the run: complementizers -- closed symbols (>= 1,000 uses) preceded by a finite verb
    # >= 12 % and followed by a subject symbol or a capitalised name >= 25 % of the time
    pv = collections.Counter(); nsub = collections.Counter(); ctot = collections.Counter()
    for t in texts:
        ts = tokens(t)
        for k in range(1, len(ts) - 1):
            a = ts[k].lower()
            if a in big and ts[k][:1].islower():
                ctot[a] += 1; pv[a] += ts[k - 1].lower() in open_fin or ts[k - 1].lower() in verbish
                nsub[a] += ts[k + 1].lower() in subj or (ts[k + 1][:1].isupper() and ts[k + 1].lower() not in cs)
    comp = sorted(a for a in ctot if pv[a] >= 0.12 * ctot[a] and nsub[a] >= 0.25 * ctot[a])
    # bookcheck (narrator, amended before the run): the first-person symbol -- the subject symbol that most often opens
    # a quotation (the word right after a double quotation mark)
    sp = collections.Counter()
    for t in texts:
        ts = tokens(t)
        for k in range(len(ts) - 1):
            if ts[k] == '"' and ts[k + 1].lower() in subj and (k == 0 or ts[k - 1] in ".!?,;:" or not ts[k - 1][:1].isalnum()): sp[ts[k + 1].lower()] += 1
    speaker = sp.most_common(1)[0][0] if sp else None
    preplike = sorted(a for a in cn if cn[a] >= 50 and cv[a] < 0.15 * cn[a] and share(a, "closed") >= 0.35)
    abbr = sorted(abbreviations(texts, share=0.8))     # amended before the scored run: "Mr" is 87 %
    out = dict(closed=closed, determiners=det, chain_heads=sorted(heads), abbreviations=abbr, subjects=sorted(subj),
               verbish=sorted(verbish), skippable=sorted(skippable), nounish=nounish, preplike=preplike, det2=sorted(det2), complementizers=comp, speaker=speaker)
    json.dump(out, open(CACHE, "w", encoding="utf-8"), indent=0)
    return out


def build():
    from core.textmodel import TextModel
    from textmodel import MODEL
    tm = TextModel.load(MODEL)
    R = KE.build({w for w, c in tm.uni.most_common(200)}, tm.uni)[0]
    L = learn(R)
    return R, L


def title_of(text):
    """the first line written wholly in capitals (two letters or more), else None"""
    for line in text.splitlines()[:80]:
        letters = [c for c in line if c.isalpha()]
        if len(letters) >= 2 and all(c.isupper() for c in letters): return " ".join(line.split()).title()
    return None


def book(bid, R, L, text=None, it=1, knockout=False, chains=True):
    text = text if text is not None else open(os.path.join(GUT, bid + ".txt"), encoding="utf-8", errors="replace").read()
    return Book(bid, text, L["closed"], set(L["abbreviations"]), R, L["determiners"], L["chain_heads"], title=title_of(text),
                verbish=L["verbish"], skippable=L["skippable"], nounish=L["nounish"], preplike=L["preplike"],
                det2=L.get("det2", ()), subjects=L.get("subjects", ()), pronouns=it >= 2, quotes=it >= 2, knockout=knockout,
                version=it, complementizers=L.get("complementizers", ()), chains=chains,
                speaker=L.get("speaker"), narrator_label=NARRATOR)
