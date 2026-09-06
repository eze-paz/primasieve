"""PRE-EMPTIVE RESEARCH -- form the attributed lexicon for the whole dictionary ahead of time. ZERO LLM.

    python em_preempt.py --offline          every WordNet adjective+noun lemma through the sources that are on disk
    python em_preempt.py --online N         deep research (Wiktionary/Wikidata/ConceptNet) for the N best candidates
                                            WordNet could not settle; paced, cached, RESUMABLE, incremental writes

Two passes because of what is honest and what is feasible: the offline pass is exact and instant; the online pass
is rate-limited by the sources (Wikimedia returns 429 under load), so a whole dictionary online is days, not
minutes. Candidates for the online pass are chosen by a PREFILTER -- a WordNet gloss that mentions a predicate word
(used only to decide WHICH words are worth a remote probe; glosses are never a certificate) -- ordered by WordNet's
tag-sense count (commonness). Results merge into attributed_lexicon.json with provenance, chain and examples; the
chat server reloads it on /api/reload. Contested and unresolved words are recorded too, so the server can say
"researched already, sources disagree" without probing again."""
import os, sys, json, time, re, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import wn_acquire as ACQ
import kb_sources as KB
import en_chat as C
from core.verdict import ATTRIBUTED, attribute

OUT_JSON = os.path.join(HERE, "attributed_lexicon.json")
LOG = os.path.join(HERE, "em_preempt.log")


def log(s):
    print(s, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")


def load_lex():
    d = json.load(open(OUT_JSON, encoding="utf-8")) if os.path.exists(OUT_JSON) else {"words": {}}
    d.setdefault("words", {}); d.setdefault("contested", {}); d.setdefault("unresolved", {}); d.setdefault("runs", [])
    return d


def save_lex(d):
    tmp = OUT_JSON + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), indent=0)
    os.replace(tmp, OUT_JSON)


def anchors_from(lex, d):
    a = dict(lex)
    for w, v in d["words"].items(): a.setdefault(w, v["pred"])
    return a


_GLOSS = {}


def _glosses(word, pos):
    """glosses of the word's synsets in sense order, from an offset->gloss map parsed ONCE (the per-call rescan in
    wn_acquire._synsets_with_gloss made the candidate prefilter over 21k adjectives take longer than the probes)."""
    if pos not in _GLOSS:
        m = {}
        p = os.path.join(ACQ.DICT, f"data.{pos}")
        if os.path.exists(p):
            for line in open(p, encoding="latin-1"):
                if line.startswith(" "): continue
                head, _, gloss = line.partition("|")
                m[head[:8]] = gloss.strip()
        _GLOSS[pos] = m
    return [_GLOSS[pos].get(o, "") for o in ACQ._index(pos).get(word, [])]


def _tagsense(word, pos):
    """WordNet's tag-sense count for the lemma (a commonness proxy), 0 if absent."""
    p = os.path.join(ACQ.DICT, f"index.{pos}")
    if not hasattr(_tagsense, "cache"): _tagsense.cache = {}
    key = (pos,)
    if key not in _tagsense.cache:
        m = {}
        if os.path.exists(p):
            for line in open(p, encoding="latin-1"):
                if line.startswith(" "): continue
                f = line.split()
                if len(f) < 6: continue
                # lemma pos synset_cnt p_cnt [ptr_symbols...] sense_cnt tagsense_cnt offsets...
                try:
                    pc = int(f[3]); m[f[0]] = int(f[5 + pc])
                except Exception: pass
        _tagsense.cache[key] = m
    return _tagsense.cache[key].get(word, 0)


NOUN_ATTRIBUTE = 7          # WordNet lexicographer file noun.attribute: where colour/size/shape NOUNS live
_LEXFILE = {}


def lexfile(pos):
    """synset offset -> lexicographer file number, parsed ONCE (wn_acquire._synsets_with_gloss rescans the 15 MB
    data file per call, which turned a 2-second pass into a >10-minute one)."""
    if pos not in _LEXFILE:
        m = {}
        p = os.path.join(ACQ.DICT, f"data.{pos}")
        if os.path.exists(p):
            for line in open(p, encoding="latin-1"):
                if line.startswith(" "): continue
                h = line.split(" ", 2)
                try: m[h[0]] = int(h[1])
                except (ValueError, IndexError): pass
        _LEXFILE[pos] = m
    return _LEXFILE[pos]


def _first_sense_span(w, pos, anchors):
    """the first-sense lemma list as a span, or None. ADJECTIVES: read by token (E-8's first-sense rule).
    NOUNS: only synsets in noun.attribute, and only if a lemma EQUALS an anchor -- a multi-word noun that merely
    CONTAINS a colour word names a thing ('red gram', 'world wide web'), not a property. The first offline pass
    read those by token and produced dhal->red and utah->wide; recorded here so it is not repeated."""
    idx, dat = ACQ._index(pos), ACQ._data(pos)
    offs = idx.get(w, [])
    if not offs or offs[0] not in dat: return None
    lemmas = [l.lower() for l in dat[offs[0]][0]]
    if pos == "noun" and lexfile(pos).get(offs[0]) != NOUN_ATTRIBUTE: return None
    # BOTH directions of the first-sense rule (E-8): the candidate's first sense must be this synset AND the
    # anchor must vouch through ITS OWN first sense. One direction only gave downhearted->blue (blue's sad sense),
    # chickenhearted->yellow, egocentric->centred.
    ok = [l for l in lemmas if l in anchors and (idx.get(l) or [None])[0] == offs[0]]
    if not ok: return None
    return " ".join(lemmas)


def offline_pass(lex, d):
    """every lemma of every downloaded dictionary through the ON-DISK sources: WordNet (first sense, both ways),
    KAIKKI (Wiktionary definitions, token reading), MOBY (synonym lists, lemma equality).

    CORROBORATION RULE for bulk admission (no human is watching): a word enters the pre-emptive lexicon only when
    TWO independent sources agree on the predicate and none disagrees. A word one source alone vouches for goes to
    d["single"]: the chat may still hold it ATTRIBUTED on demand -- with its single citation visible to the user --
    but it is not pre-loaded silently. Disagreement -> d["contested"]."""
    import kb_offline as OFF
    # V3: bulk reading anchors ONLY on world-learned words. V2 chained through attributed words ('little',
    # 'slight') and, with one-directional Moby and untyped definitions, put 322 of 381 corroborated words on
    # 'small' (punctual, horrible, versatile ...). Recorded here; V2 output was discarded.
    anchors = dict(lex)
    kai = OFF.kaikki_index(verbose=True) or {}
    mob = OFF.moby_index() or {}
    lemmas = set(ACQ._index("adj")) | set(ACQ._index("noun")) | set(kai) | set(mob)
    lemmas = sorted(w for w in lemmas if w.isalpha() and w not in anchors)
    d.setdefault("single", {})
    t0 = time.time(); n_new = n_con = n_single = 0
    for i, w in enumerate(lemmas):
        cites = {}
        readers = [("WORDNET-adj", "adj", None), ("WORDNET-noun", "noun", None), ("KAIKKI", None, None), ("MOBY", None, OFF.moby_read)]
        for sid, pos, rd in readers:
            if pos:
                span = _first_sense_span(w, pos, anchors)
                cands = [(span, span)] if span else []
            else:
                cands = (OFF.src_kaikki(w) if sid == "KAIKKI" else OFF.src_moby(w, anchors)) or []
            for span, text in cands:
                if pos:
                    idx_ = ACQ._index(pos); off0 = idx_[w][0]
                    preds = {anchors[l] for l in span.split() if l in anchors and (idx_.get(l) or [None])[0] == off0}
                else:
                    preds = (rd or KB.read)(span, anchors)
                if len(preds) == 1:
                    p = next(iter(preds))
                    _, st, _ = attribute((w, p), sid, text, span, lambda s: (w, next(iter(KB.read(s, anchors)))) if len(KB.read(s, anchors)) == 1 else None)
                    if st == ATTRIBUTED: cites.setdefault(p, []).append((sid, span[:120]))
                elif len(preds) > 1:
                    cites.setdefault("/".join(sorted(preds)), []).append((sid, span[:120]))
        single = {k: v for k, v in cites.items() if "/" not in k}
        if len(single) == 1 and len(cites) == 1:
            p = next(iter(single)); srcs = sorted({s for s, _ in single[p]})
            entry = dict(pred=p, source="+".join(srcs), span=single[p][0][1], chain=[], cites=single[p][:3], depth=1,
                         how="offline, corroborated" if len(srcs) >= 2 else "offline, single source",
                         examples=(kai.get(w, {}).get("ex", [])[:2] if kai else []))
            if len(srcs) >= 2:
                d["words"][w] = entry; n_new += 1                 # NOT added to anchors: no chaining in bulk (V3)
            else:
                d["single"][w] = entry; n_single += 1
        elif cites:
            d["contested"][w] = {k: v[:2] for k, v in cites.items()}; n_con += 1
        if i and i % 20000 == 0: log(f"  ... {i}/{len(lemmas)} ({time.time()-t0:.0f}s)")
    log(f"offline pass: {len(lemmas)} lemmas scanned in {time.time()-t0:.1f}s -> {n_new} corroborated (2+ sources), "
        f"{n_single} single-source (on demand only), {n_con} contested; lexicon now {len(d['words'])} words")
    return d


def candidates(lex, d, limit):
    """adjective lemmas not yet settled whose WordNet GLOSS mentions an anchor -- worth a remote probe."""
    anchors = anchors_from(lex, d)
    out = []
    for w in ACQ._index("adj"):
        if not w.isalpha() or w in anchors or w in d["contested"] or w in d["unresolved"]: continue
        gl = " ".join(_glosses(w, "adj")[:2])
        if KB.read(gl, anchors):
            out.append((-_tagsense(w, "adj"), w))
    out.sort()
    return [w for _, w in out[:limit]]


def online_pass(lex, d, limit):
    anchors = anchors_from(lex, d)
    cands = candidates(lex, d, limit)
    log(f"online pass: {len(cands)} candidates (gloss mentions a predicate; ordered by commonness). "
        f"~{len(cands) * 3 * KB.PACE / 60:.0f} min at the source pace.")
    t0 = time.time(); n_att = n_con = n_none = 0
    for i, w in enumerate(cands, 1):
        r = KB.deep_research(w, anchors, budget=[6])
        if r["status"] == "attributed":
            p = next(iter(r["preds"])); cites = next(iter(r["cites"].values()))
            d["words"][w] = dict(pred=p, source="+".join(sorted({s for s, _ in cites})), span=cites[0][1], chain=list(r.get("chain", {}).keys()),
                                 cites=cites[:3], depth=1 + len(r.get("chain", {})), how="online deep research",
                                 examples=r.get("examples", [])[:2], trace=r.get("trace", [])[:8])
            anchors[w] = p; n_att += 1
        elif r["status"] == "contested":
            d["contested"][w] = {"/".join(sorted(k)): v[:2] for k, v in r["cites"].items()}; n_con += 1
        else:
            d["unresolved"][w] = dict(consulted=r["consulted"], unavailable=r["unavailable"]); n_none += 1
        if i % 10 == 0 or i == len(cands):
            save_lex(d)
            log(f"  {i}/{len(cands)}  attributed {n_att}  contested {n_con}  unresolved {n_none}  ({time.time()-t0:.0f}s)  last: {w} -> {r['status']}")
    return d


if __name__ == "__main__":
    _, lex, _ = C.build(n=9000, seed=7)
    d = load_lex()
    if "--offline" in sys.argv:
        d = offline_pass(lex, d)
        d["runs"].append(dict(kind="offline", at=time.strftime("%Y-%m-%d %H:%M"), words=len(d["words"])))
        save_lex(d)
    if "--online" in sys.argv:
        n = int(sys.argv[sys.argv.index("--online") + 1]) if len(sys.argv) > sys.argv.index("--online") + 1 else 200
        d = online_pass(lex, d, n)
        d["runs"].append(dict(kind="online", at=time.strftime("%Y-%m-%d %H:%M"), words=len(d["words"])))
        save_lex(d)
    log(f"lexicon: {len(d['words'])} attributed, {len(d['contested'])} contested, {len(d['unresolved'])} unresolved")
