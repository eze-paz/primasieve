"""KNOWLEDGE-BASE RESEARCH -- the loop that runs BEFORE an abstention reaches the chat. ZERO LLM, stdlib + certifi.

Owner's rule (2026-09-06): the engine may abstain internally, but it must not abstain to the user until it has
RESEARCHED. So an unknown word triggers a pass over every designated source, cheapest first, and the abstention
surfaces only when all of them have been consulted -- and then it says which ones.

Every source is an ATTRIBUTED-rung source (core.verdict): what it returns is held on ITS word, with the verbatim
span as certificate, never as verified. Sources, in order:
    WORDNET-adj   offline; first-listed sense only (E-8's rule -- any-sense drifted 'blue' to 'sad')
    WORDNET-noun  offline; first-listed sense only (colour nouns: 'teal' -> 'bluish green blue green teal')
    WIKTIONARY    online; definition lines under the English Adjective/Noun headers
    WIKIDATA      online; the description of entries whose label IS the word
    CONCEPTNET    online; IsA / Synonym / RelatedTo edges (was returning 502 when this was written; handled)
Reading rule (one for all): tokens of the span, mapped through the anchors (world-learned words + attributed
synonyms) to predicates; EXACTLY ONE distinct predicate -> that meaning; several -> CONTESTED (ask, never pick);
a predicate word preceded by 'not'/'no'/'never' within two tokens is dropped (the 'not small' trap). Remote calls
are cached on disk and paced (Wikimedia returned 429 during development)."""
import os, sys, json, re, time, ssl, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import wn_acquire as ACQ
from core.verdict import ATTRIBUTED, attribute

CACHE_PATH = os.path.join(HERE, "kb_cache.json")
_CACHE = json.load(open(CACHE_PATH, encoding="utf-8")) if os.path.exists(CACHE_PATH) else {}
_LAST_CALL = [0.0]
PACE = 2.0                     # seconds between remote calls (a deep chase of ~10 probes tripped 429 at 1.2s)
UA = {"User-Agent": "primasieve/0.1 (rejection-first research engine; local experiment)"}
NEG = {"not", "no", "never", "non", "un"}
_CTX = None


def _ctx():
    global _CTX
    if _CTX is None:
        try:
            import certifi; _CTX = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            _CTX = ssl.create_default_context()
    return _CTX


def _fetch(key, url):
    """cached, paced GET -> text or None (None = source unavailable; reported, never treated as 'no result')."""
    if key in _CACHE: return _CACHE[key]
    wait = PACE - (time.time() - _LAST_CALL[0])
    if wait > 0: time.sleep(wait)
    _LAST_CALL[0] = time.time()
    try:
        txt = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10, context=_ctx()).read().decode("utf-8", "replace")
    except Exception as e:
        return None
    _CACHE[key] = txt
    try: json.dump(_CACHE, open(CACHE_PATH, "w", encoding="utf-8"))
    except Exception: pass
    return txt


def tokens(text):
    return re.findall(r"[a-z]+", text.lower())


import en_world as _W

# ------------------------------------------------ the SHAPES-WORLD VERIFIER (DEMOTED -- no_paradigm_prereg.md)
# read()/FAMILY/CUES below map a definition onto a predicate of ONE attached world (en_world). They used to be THE
# meaning space: every researched meaning had to reduce to a colour/size/position or come back "none", which is why
# the attributed lexicon is 435 colour/size words and nothing else. That paradigm is retired: meaning is now the set
# of cited READINGS a source returns (wikt_readings / research_gloss / src_wordnet, all senses). This block is only an
# OPTIONAL VERIFIER, applied when a candidate reading happens to name a predicate of the attached world, to eliminate
# against that world. HONESTY: the CUES lists were written AFTER seeing 322/381 words wrongly land on 'small' (fitted
# to the outcome; prereg overclaim-watch f). They remain only because the grounded thread (em_preempt/em_attributed,
# a peer session) still consumes them; an ablation gate (remove the cues, re-derive the published numbers) is OWED.
# TYPE CUES (V3 rule, after the corroborated bulk pass put 322 of 381 words on 'small' through 'little' and 'of
# small importance'): a definition vouches for a predicate only if it also names WHAT KIND of property it is.
# 'small in size' reads; 'of small importance' does not. The cue lists are about property KINDS, not about any
# target word, and are the same for every source. Recorded in em_preempt.py's log as V2 -> V3.
FAMILY = {}
for _p in _W.COLOURS: FAMILY[_p] = "colour"
for _p in _W.SIZES: FAMILY[_p] = "size"
for _p in _W.SHAPES: FAMILY[_p] = "shape"
for _p in _W.HZONES + _W.VZONES: FAMILY[_p] = "zone"
CUES = {"colour": {"colour", "color", "coloured", "colored", "hue", "shade", "tint", "tinge", "tinged", "dye", "pigment", "ish"},
        "size": {"size", "sized", "dimension", "dimensions", "extent", "stature", "bulk", "magnitude", "height", "width",
                 "breadth", "length", "tall", "wide", "large", "big", "small", "little", "tiny", "huge", "thin", "narrow", "broad"},
        "shape": {"shape", "shaped", "form", "sides", "angles", "square", "rectangular", "wide", "tall", "broad", "thin", "narrow"},
        "zone": {"position", "positioned", "located", "situated", "placed", "top", "bottom", "side", "left", "right",
                 "upper", "lower", "middle", "centre", "center", "edge", "end", "part", "highest", "lowest", "nearest"}}


def read(span, anchors, typed=True):
    """-> set of predicates the span vouches for (negation guard; with typed=True the span must also carry a cue
    for the predicate's property KIND). Empty = says nothing we can use."""
    toks = tokens(span); preds = set(); tokset = set(toks)
    for i, t in enumerate(toks):
        if t in anchors and not (set(toks[max(0, i - 2):i]) & NEG):
            p = anchors[t]
            if typed and p in FAMILY:
                cues = CUES[FAMILY[p]] - {t}                   # the anchor itself is not its own cue
                if not (tokset & cues) and not any(x.endswith("ish") for x in tokset if FAMILY[p] == "colour"):
                    continue
            preds.add(p)
    return preds


# ---------------------------------------------------------------- sources: each -> [(span, text)] candidates
def src_wordnet(word, pos):
    idx, dat = ACQ._index(pos), ACQ._data(pos)
    offs = [o for o in idx.get(word.lower(), []) if o in dat]
    if not offs: return []
    # EVERY synset. The file's order carries no authority (prereg NP-3: sense #1 is not disambiguation); callers
    # receive the whole set and must not privilege the first.
    return [(" ".join(l.lower() for l in dat[o][0]),) * 2 for o in offs]


def _strip_wiki(s):
    """Plain text of a wikitext line WITH the template data kept as text, not deleted. Templates are typed
    relational edges, not noise: {{alternative spelling of|mul|x}} is the ALIAS edge that makes x -> x-times
    reachable, {{lb|mul|arithmetic}} is a DOMAIN tag. The old reader stripped every {{...}} before the chase could
    see them -- the paradigm that made the multiplication sense of 'x' unreachable (prereg audit #3)."""
    s = re.sub(r"\{\{(?:alternative spelling of|alt sp|alt form|alternative form of|altform)\s*\|[^|}]*\|([^|}]+)[^}]*\}\}",
               r"alternative spelling of \1", s)
    s = re.sub(r"\{\{(?:lb|label|lbl)\|[^|}]*\|([^}]*)\}\}", lambda m: "[" + m.group(1).replace("|", ", ") + "]", s)
    s = re.sub(r"\{\{(?:ng|n-g|non-gloss definition|non-gloss)\|([^}]*)\}\}", r"\1", s)
    s = re.sub(r"\{\{(?:ux|uxi)\|[^|}]*\|([^|}]*)[^}]*\}\}", r"e.g. \1", s)
    s = re.sub(r"\{\{[^{}]*\}\}", " ", s)                      # anything else: drop the markup only
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)     # [[link|text]] -> text
    return re.sub(r"\s+", " ", s.replace("'" * 3, "").replace("'" * 2, "")).strip()


def wikt_edges(line):
    """The TYPED EDGES on one definition line -> dict(alias=[targets], domain=[tags], usage=[examples]).
    An ALIAS edge is what deep_research follows to its target page (x -> the times sign)."""
    return dict(
        alias=[t.strip() for t in re.findall(r"\{\{(?:alternative spelling of|alt sp|alt form|alternative form of|altform)\s*\|[^|}]*\|([^|}]+)", line)],
        domain=[t.strip() for m in re.findall(r"\{\{(?:lb|label|lbl)\|[^|}]*\|([^}]*)\}\}", line) for t in m.split("|")],
        usage=[_strip_wiki(u) for u in re.findall(r"\{\{(?:ux|uxi)\|[^|}]*\|([^|}]*)", line)])


WIKT_POS = (r"(?:Adjective|Noun|Verb|Symbol|Letter|Numeral|Conjunction|Particle|Adverb|Preposition|Pronoun|"
            r"Interjection|Determiner|Prefix|Suffix|Proper noun|Phrase|Number|Abbreviation)")


def _wikitext(word):
    url = ("https://en.wiktionary.org/w/api.php?action=query&prop=revisions&rvprop=content&rvslots=main&format=json"
           "&formatversion=2&titles=" + urllib.parse.quote(word))
    txt = _fetch("wiktw:" + word, url)
    if txt is None: return None
    try:
        return json.loads(txt)["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
    except Exception:
        return ""


def wikt_readings(word):
    """EVERY definition line on the page as a structured READING: dict(def, lang, pos, alias, domain, usage).
    No language section is privileged and no POS block is whitelisted -- the two authored filters that made the
    Translingual `Symbol` sense of 'x' (multiplication, via an ALIAS edge) unreachable are gone. Sense ORDER is the
    page's editorial order and carries no authority: callers get the whole set (prereg NP-3)."""
    wt = _wikitext(word)
    if wt is None: return None
    out = []
    for lm in re.finditer(r"(?:^|\n)==([^=\n]+)==\n(.*?)(?=\n==[^=]|\Z)", wt, re.S):
        lang, body = lm.group(1).strip(), lm.group(2)
        for pm in re.finditer(r"===+(" + WIKT_POS + r")===+\n(.*?)(?=\n===+[^=]|\Z)", body, re.S):
            pos, block = pm.group(1), pm.group(2)
            for l in block.split("\n"):
                if l.startswith("# "):
                    d = _strip_wiki(l[2:])
                    if d:
                        e = wikt_edges(l)
                        out.append({"def": d, "lang": lang, "pos": pos, "alias": e["alias"], "domain": e["domain"], "usage": []})
                elif l.startswith("#:") and out and out[-1]["lang"] == lang:
                    out[-1]["usage"] += wikt_edges(l)["usage"]
    return out


def src_wiktionary(word):
    """-> [(span, text)] over EVERY reading on the page (all languages, all POS). The certificate text is the
    cleaned definition list, i.e. exactly what was read."""
    rs = wikt_readings(word)
    if rs is None: return None
    defs = [r["def"] for r in rs]
    text = "\n".join(defs)
    return [(d, text) for d in defs]


def src_wikidata(word):
    url = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&language=en&format=json&limit=7&search="
           + urllib.parse.quote(word))
    txt = _fetch("wd:" + word, url)
    if txt is None: return None
    try: items = json.loads(txt)["search"]
    except Exception: return []
    descs = [x["description"] for x in items if x.get("label", "").lower() == word.lower() and x.get("description")]
    return [(d, "\n".join(descs)) for d in descs]


def src_conceptnet(word):
    url = f"https://api.conceptnet.io/c/en/{urllib.parse.quote(word)}?limit=60"
    txt = _fetch("cn:" + word, url)
    if txt is None: return None
    try: edges = json.loads(txt)["edges"]
    except Exception: return None                              # a 502 body is not a result
    out = []
    for e in edges:
        rel = e.get("rel", {}).get("label", "")
        if rel not in ("IsA", "Synonym", "RelatedTo", "SimilarTo"): continue
        other = e["end"]["label"] if e["start"]["label"].lower() == word.lower() else e["start"]["label"]
        out.append(f"{word} {rel} {other}")
    text = "\n".join(out)
    return [(s, text) for s in out]


import kb_offline as OFF

# (source id, fetch, reader). OFFLINE sources first -- exact, instant, no rate limit; the online ones are the
# fallback for words the downloaded resources do not settle. MOBY reads by lemma equality (its lists are broad).
SOURCES = [("WORDNET-adj", lambda w: src_wordnet(w, "adj"), None), ("WORDNET-noun", lambda w: src_wordnet(w, "noun"), None),
           ("KAIKKI", OFF.src_kaikki, None), ("MOBY", OFF.src_moby, OFF.moby_read),
           ("WIKTIONARY", src_wiktionary, None), ("WIKIDATA", src_wikidata, None), ("CONCEPTNET", src_conceptnet, None)]
# DECLARED per-source metadata (prereg audit #13): the loop reads these flags, never a source's NAME.
#   offline   -- no network; consulted first (cost order is a measured lesson, cost-ordered adoption)
#   anchored  -- the source's lookup takes the anchor set (a mutual-synonymy source needs it); others take the word
SOURCE_META = {"WORDNET-adj": dict(offline=True, anchored=False), "WORDNET-noun": dict(offline=True, anchored=False),
               "KAIKKI": dict(offline=True, anchored=False), "MOBY": dict(offline=True, anchored=True),
               "WIKTIONARY": dict(offline=False, anchored=False), "WIKIDATA": dict(offline=False, anchored=False),
               "CONCEPTNET": dict(offline=False, anchored=False)}
OFFLINE = {sid for sid, m in SOURCE_META.items() if m["offline"]}


def family(sid):
    """independence for corroboration: KAIKKI is a snapshot of WIKTIONARY, so they count once."""
    return "WIKTIONARY" if sid in ("KAIKKI", "WIKTIONARY") else sid


def research(word, anchors, stop_when_unique=True):
    """Consult every source for `word`. -> dict(status: attributed|contested|none, preds, cites, consulted,
    unavailable). Each admitted certificate passed core.verdict.attribute (span verbatim in the fetched text,
    reading equals the claim). With stop_when_unique, offline sources that already give ONE predicate end the
    search early (cheapest-first). A contest is never settled by vote: if two sources disagree the word is
    reported CONTESTED with both citations, and the chat asks. Only the world (or the user) settles it."""
    cites = {}; consulted = []; unavailable = []; refused = 0
    for sid, fn, reader in SOURCES:
        rd = reader or read
        cands = fn(word, anchors) if SOURCE_META[sid]["anchored"] else fn(word)
        if cands is None: unavailable.append(sid); continue
        consulted.append(sid)
        for span, text in cands:
            preds = rd(span, anchors)
            if len(preds) != 1:
                if len(preds) > 1: cites.setdefault(frozenset(preds), []).append((sid, span[:120]))
                continue
            p = next(iter(preds))
            claim, state, prov = attribute((word, p), sid, text, span, lambda s, w=word: (w, next(iter(rd(s, anchors)))) if len(rd(s, anchors)) == 1 else None)
            if state == ATTRIBUTED: cites.setdefault(frozenset([p]), []).append((sid, span[:120]))
            else: refused += 1
        distinct = {p for k in cites for p in k}
        if stop_when_unique and len(distinct) == 1 and OFFLINE <= set(consulted) | set(unavailable):
            break                                              # every declared OFFLINE source seen and they agree: no remote call
    distinct = {p for k in cites for p in k}
    base = dict(consulted=consulted, unavailable=unavailable, refused=refused)
    if not distinct: return dict(status="none", preds=set(), cites={}, **base)
    if len(distinct) == 1: return dict(status="attributed", preds=distinct, cites={next(iter(cites)): cites[next(iter(cites))]}, **base)
    return dict(status="contested", preds=distinct, cites=cites, **base)


# ---------------------------------------------------------------- DEEP research: chase the unknowns a definition leads to
STOP = set("a an the of or and to in on at by for with from as is are be being been very more most quite rather "
           "somewhat having has have that which who whose one ones thing things someone something not no".split())


def wikt_detail(word):
    """-> dict(defs=[str], links=[[w..] per def], synonyms=[w], examples=[str]) for the chase, over EVERY reading
    (all languages, all POS). ALIAS edge targets are added to each definition's links so deep_research follows
    x -> its alias page the same way it follows any linked word. None if the page is unreachable."""
    rs = wikt_readings(word)
    if rs is None: return None
    out = dict(defs=[], links=[], synonyms=[], examples=[])
    for r in rs:
        out["defs"].append(r["def"])
        out["links"].append([t for t in re.findall(r"[a-z]+", r["def"].lower())] + r["alias"])
        out["examples"] += r["usage"]
    wt = _wikitext(word) or ""
    out["synonyms"] = re.findall(r"\{\{(?:syn|l)\|[a-z]+\|([a-z\- ]+)", wt)[:20]
    return out


# ---------------------------------------------------------------- DEEP research: chase the unknowns a definition leads to
STOP = set("a an the of or and to in on at by for with from as is are be being been very more most quite rather "
           "somewhat having has have that which who whose one ones thing things someone something not no".split())


def deep_research(word, anchors, depth=2, budget=None, trace=None, tried=None):
    """research(word); if that yields nothing, CHASE: the words a definition links to, and the listed synonyms,
    become probes of their own (depth-limited, a shared probe budget). A child that resolves to one predicate
    becomes a temporary anchor and the parent's definitions are re-read through it; the provenance chain records
    every hop. Usage examples are collected and SHOWN, never used to decide. -> research dict + trace + chain."""
    budget = budget if budget is not None else [10]
    trace = trace if trace is not None else []
    tried = tried if tried is not None else set()
    tried.add(word)
    r = research(word, anchors)
    r["trace"] = trace; r["chain"] = {}; r["examples"] = []
    det = OFF.kaikki_detail(word) or (wikt_detail(word) if r["status"] == "none" else None)   # offline first
    if det: r["examples"] = det["examples"][:3]
    if r["status"] != "none" or depth <= 0 or not det: return r
    children = []
    for links in det["links"][:3]:
        children += [w for w in links if w not in anchors and w not in tried and w not in STOP and w.isalpha() and len(w) > 2]
    children += [s for s in det["synonyms"] if s not in anchors and s not in tried and s.isalpha()]
    children = list(dict.fromkeys(children))[:8]
    temp = dict(anchors)
    for child in children:
        if budget[0] <= 0: trace.append(f"budget exhausted before '{child}'"); break
        budget[0] -= 1
        cr = deep_research(child, temp, depth - 1, budget, trace, tried)
        # a CHASED child becomes an anchor only if CORROBORATED (2+ sources) or vouched by WordNet's strict
        # first-sense synonymy: one loose definition deep in a chain is how 'nearest' -> small reached 'topmost'.
        if cr["status"] == "attributed":
            c_cites = next(iter(cr["cites"].values()))
            c_srcs = {family(s) for s, _ in c_cites}          # KAIKKI *is* Wiktionary: one family, not two sources
            if len(c_srcs) < 2 and "WORDNET-adj" not in c_srcs:
                trace.append(f"'{word}' -> chased '{child}' -> {next(iter(cr['preds']))} but single-source; not used as an anchor")
                continue
            p = next(iter(cr["preds"])); temp[child] = p
            r["chain"][child] = dict(pred=p, cites=next(iter(cr["cites"].values()))[:2], chain=cr.get("chain", {}))
            trace.append(f"'{word}' -> chased '{child}' -> {p}")
        else:
            trace.append(f"'{word}' -> chased '{child}' -> {cr['status']}")
    if not r["chain"]: return r
    cites = {}
    for d in det["defs"][:5]:                              # re-read the parent through the resolved children
        preds = read(d, temp)
        if preds: cites.setdefault(frozenset(preds), []).append(("WIKTIONARY", d[:120]))
    distinct = {p for k in cites for p in k}
    if len(distinct) == 1:
        r.update(status="attributed", preds=distinct, cites={next(iter(cites)): cites[next(iter(cites))]})
    elif len(distinct) > 1:
        r.update(status="contested", preds=distinct, cites=cites)
    return r


def research_gloss(word, online=True):
    """RESEARCH PRIMITIVE (reading kind iii in no_paradigm_prereg.md): the researched meaning of `word`, returned
    VERBATIM with its SOURCE, NOT reduced to any world's predicates. This is not a mode and has no flag -- it is
    what the single answer loop calls for any symbol it cannot bind. This is the widening the shapes-reader blocked: the answer is whatever a
    source actually says, so it is as wide as the sources (all of WordNet, plus online lexica). Abstention is
    INTERNAL -- every source is consulted cheapest-first; None comes back only if NO source defines the word, at
    which point the caller may refuse honestly. The citation is the source text itself: the answer is sound
    (never confabulated) and retractable to exactly the source it came from."""
    w = word.lower().strip()
    for pos in ("noun", "verb", "adj"):
        try:
            sg = ACQ._synsets_with_gloss(w, pos)          # the actual DEFINITION gloss, not just synset words
        except Exception:
            sg = None
        if sg:
            # EVERY sense, none privileged (NP-3). A caller that needs one must ask or verify, never take the first.
            senses = [g for _, g in sg]
            gloss = "  |  ".join(f"({i+1}) {g}" for i, g in enumerate(senses)) if len(senses) > 1 else senses[0]
            return dict(word=word, gloss=gloss, readings=senses, source="WORDNET-" + pos, cite=gloss, kind="lexical")
    if online:
        for sid, fn in (("WIKTIONARY", src_wiktionary), ("WIKIDATA", src_wikidata), ("CONCEPTNET", src_conceptnet)):
            try:
                r = fn(w)
            except Exception:
                r = None
            if r:
                senses = [d for d, _ in r]
                text = "  |  ".join(f"({i+1}) {d}" for i, d in enumerate(senses)) if len(senses) > 1 else senses[0]
                return dict(word=word, gloss=text, readings=senses, source=sid, cite=r[0][1], kind="lexical")
    return None


if __name__ == "__main__":
    import en_chat as C
    _, lex, _ = C.build(n=9000, seed=7)
    anchors = dict(lex)
    al = os.path.join(HERE, "attributed_lexicon.json")
    if os.path.exists(al):
        for w, v in json.load(open(al))["words"].items(): anchors.setdefault(w, v["pred"])
    for w in sys.argv[1:] or ["teal", "maroon", "enormous", "slender", "gigantic", "topmost", "sex"]:
        r = deep_research(w, anchors)
        print(f"{w:10s} {r['status']:10s} {sorted(r['preds'])}  consulted {r['consulted']} unavailable {r['unavailable']}")
        for k, v in r["cites"].items(): print(f"    {sorted(k)} <- {v[:3]}")
        for t in r["trace"]: print(f"    trace: {t}")
        if r["chain"]: print(f"    chain: { {c: v['pred'] for c, v in r['chain'].items()} }")
        if r["examples"]: print(f"    examples: {r['examples'][:2]}")
