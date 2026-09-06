"""OFFLINE KNOWLEDGE BASES -- downloaded once, read locally, no rate limits. ZERO LLM, pure stdlib.

    KAIKKI   Wiktionary, English adjectives, pre-parsed by wiktextract (kaikki.org), 456 MB JSONL, one entry per
             line: word, senses[{glosses, examples[{text}], synonyms[{word}]}], synonyms[{word}]. Indexed ONCE into
             a compact JSON (word -> defs, synonyms, examples) so the chat never touches the 456 MB again.
    MOBY     Moby Thesaurus II (Project Gutenberg #3202, public domain), 24 MB: one line per headword,
             "head,syn1,syn2,...". Loose synonymy -- a headword's list is BROAD -- so it is a CORROBORATING source:
             it reads by lemma equality only (an anchor listed as a synonym), and em_preempt admits a word to the
             pre-emptive lexicon only when two independent sources agree.

Both plug into kb_sources.SOURCES with the same certificate discipline (span verbatim in the source text; the
reading rule equals the claim) and the same reading rule (exactly one predicate, negation guard)."""
import os, sys, json, re, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NLDATA = os.path.join(ROOT, "_nldata")
KAIKKI_RAW = os.path.join(NLDATA, "kaikki-English-adj.jsonl")
KAIKKI_IDX = os.path.join(NLDATA, "kaikki_adj_index.json")
MOBY_RAW = os.path.join(NLDATA, "files", "mthesaur.txt")
_CACHE = {}


def kaikki_index(rebuild=False, verbose=True):
    """word -> {defs:[str], syn:[str], ex:[str]}; built once from the raw JSONL (a few minutes), then loaded."""
    if "kaikki" in _CACHE: return _CACHE["kaikki"]
    if os.path.exists(KAIKKI_IDX) and not rebuild:
        _CACHE["kaikki"] = json.load(open(KAIKKI_IDX, encoding="utf-8")); return _CACHE["kaikki"]
    if not os.path.exists(KAIKKI_RAW): _CACHE["kaikki"] = None; return None
    t0 = time.time(); idx = {}; n = 0
    with open(KAIKKI_RAW, encoding="utf-8") as f:
        for line in f:
            n += 1
            try: e = json.loads(line)
            except Exception: continue
            w = e.get("word", "").lower()
            if not w or not re.fullmatch(r"[a-z][a-z\-]*", w): continue
            defs, ex, syn = [], [], []
            for s in e.get("senses", [])[:6]:
                g = s.get("glosses") or s.get("raw_glosses") or []
                if g: defs.append(re.sub(r"\s+", " ", g[-1]).strip())
                for x in s.get("examples", [])[:2]:
                    if x.get("text"): ex.append(x["text"].strip())
                syn += [y["word"].lower() for y in s.get("synonyms", []) if y.get("word")]
            syn += [y["word"].lower() for y in e.get("synonyms", []) if y.get("word")]
            if not defs: continue
            d = idx.setdefault(w, {"defs": [], "syn": [], "ex": []})
            d["defs"] += defs[:6]; d["ex"] += ex[:4]; d["syn"] += syn
            d["syn"] = list(dict.fromkeys(d["syn"]))[:12]; d["defs"] = d["defs"][:8]; d["ex"] = d["ex"][:4]
            if verbose and n % 50000 == 0: print(f"  kaikki: {n} lines, {len(idx)} words, {time.time()-t0:.0f}s", flush=True)
    json.dump(idx, open(KAIKKI_IDX, "w", encoding="utf-8"))
    if verbose: print(f"  kaikki index: {len(idx)} adjectives from {n} lines in {time.time()-t0:.0f}s -> {os.path.basename(KAIKKI_IDX)}", flush=True)
    _CACHE["kaikki"] = idx
    return idx


def moby_index():
    """head -> [synonyms] (lowercase, single- and multi-word), parsed once (~1 s)."""
    if "moby" in _CACHE: return _CACHE["moby"]
    if not os.path.exists(MOBY_RAW): _CACHE["moby"] = None; return None
    m = {}
    with open(MOBY_RAW, encoding="latin-1") as f:
        for line in f:
            parts = [p.strip().lower() for p in line.rstrip("\n").split(",") if p.strip()]
            if len(parts) > 1: m[parts[0]] = parts[1:]
    _CACHE["moby"] = m
    return m


# ---------------------------------------------------------------- sources in kb_sources' shape: -> [(span, text)] | None
def src_kaikki(word):
    idx = kaikki_index(verbose=False)
    if idx is None: return None                             # not downloaded: unavailable, reported as such
    e = idx.get(word.lower())
    if not e: return []
    text = "\n".join(e["defs"])
    return [(d, text) for d in e["defs"]]


def kaikki_detail(word):
    """for deep chasing: definitions, the words they mention, synonyms, examples -- the offline twin of
    kb_sources.wikt_detail."""
    idx = kaikki_index(verbose=False)
    e = idx.get(word.lower()) if idx else None
    if not e: return None
    links = [[t for t in re.findall(r"[a-z]+", d.lower())] for d in e["defs"]]
    return dict(defs=e["defs"], links=links, synonyms=e["syn"], examples=e["ex"])


def src_moby(word, anchors=None):
    """MUTUAL synonymy only (V3): an anchor in the word's list counts only if the word is also in the anchor's
    list. Moby's lists are broad by design ('fragile' lists 'small'); one direction alone corroborated hundreds of
    wrong 'small's. Each admitted anchor is its own span (verbatim in the list = the source text)."""
    m = moby_index()
    if m is None: return None
    syn = m.get(word.lower())
    if not syn: return []
    text = ", ".join(syn)
    if anchors is None: return [(text, text)]
    mutual = [s for s in syn if s in anchors and word.lower() in set(m.get(s, []))]
    if len({anchors[s] for s in mutual}) > 1:
        return []           # Moby lists 'enormous' as mutual with both big- and small-words: INCOHERENT for this
                            # word, so Moby abstains rather than manufacturing a contest against a clear definition
    return [(s, text) for s in mutual]


def moby_read(span, anchors):
    """MOBY's reading rule: the span is a single lemma; lemma EQUALITY (never token-in-phrase)."""
    s = span.strip()
    return {anchors[s]} if s in anchors else set()


if __name__ == "__main__":
    print("building offline indexes ...")
    k = kaikki_index(rebuild="--rebuild" in sys.argv)
    m = moby_index()
    print(f"kaikki: {len(k) if k else 'NOT DOWNLOADED'} adjectives   moby: {len(m) if m else 'NOT DOWNLOADED'} headwords")
    for w in sys.argv[1:] or ["slender", "enormous", "teal", "topmost"]:
        if w.startswith("--"): continue
        print(f"\n{w}: kaikki {src_kaikki(w)[:2] if src_kaikki(w) else None}")
        print(f"{w}: moby {str(src_moby(w))[:200] if src_moby(w) else None}")
