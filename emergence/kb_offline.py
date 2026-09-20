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
KAIKKI_RAW = os.path.join(NLDATA, "kaikki-English-adj.jsonl")          # the old adjective-only snapshot (rect-world artifact)
KAIKKI_IDX = os.path.join(NLDATA, "kaikki_adj_index.json")
KAIKKI_ALL_RAW = os.path.join(NLDATA, "kaikki-English-all.jsonl")      # ALL of English Wiktionary (every POS), 3.2 GB
KAIKKI_ALL_DB = os.path.join(NLDATA, "kaikki_all.sqlite")              # indexed once into sqlite: O(1) lookup, no load time
MOBY_RAW = os.path.join(NLDATA, "files", "mthesaur.txt")
_CACHE = {}


class _SqliteIndex:
    """dict-like view over the sqlite index: get / in / iter / len, so every caller of kaikki_index() works
    unchanged whether the index is the old JSON dict or the full-dictionary database."""
    def __init__(self, path):
        import sqlite3
        self.c = sqlite3.connect(path, check_same_thread=False)
    def get(self, w, default=None):
        r = self.c.execute("select v from e where w=?", (w,)).fetchone()
        return json.loads(r[0]) if r else default
    def __contains__(self, w): return self.c.execute("select 1 from e where w=?", (w,)).fetchone() is not None
    def __iter__(self):
        for (w,) in self.c.execute("select w from e"): yield w
    def __len__(self): return self.c.execute("select count(*) from e").fetchone()[0]
    def df(self, t):
        try:
            r = self.c.execute("select n from df where t=?", (t.lower(),)).fetchone()
        except Exception:
            return 0
        return r[0] if r else 0


def kaikki_build_all(verbose=True):
    """Stream the full English Wiktionary JSONL once into sqlite. Per word: defs (every sense, every POS, with the
    POS kept per sense), syn, ex, pos list. Nothing is filtered by part of speech: the adjective-only snapshot was
    the rect world baked into data (no_paradigm_prereg audit), and 'what is a dog' needs the nouns."""
    import sqlite3
    if not os.path.exists(KAIKKI_ALL_RAW): return None
    t0 = time.time(); n = 0; acc = {}
    with open(KAIKKI_ALL_RAW, encoding="utf-8") as f:
        for line in f:
            n += 1
            try: e = json.loads(line)
            except Exception: continue
            w = e.get("word", "").lower(); pos = e.get("pos", "")
            if not w or not re.fullmatch(r"[a-z][a-z\-' ]*", w): continue
            d = acc.setdefault(w, {"defs": [], "senses": [], "syn": [], "ex": [], "pos": []})
            if pos and pos not in d["pos"]: d["pos"].append(pos)
            for s_ in e.get("senses", [])[:8]:
                g = s_.get("glosses") or s_.get("raw_glosses") or []
                if not g: continue
                gl = re.sub(r"\s+", " ", g[-1]).strip()
                if len(d["defs"]) < 12: d["defs"].append(gl); d["senses"].append({"pos": pos, "gloss": gl})
                for x in s_.get("examples", [])[:2]:
                    if x.get("text") and len(d["ex"]) < 4: d["ex"].append(x["text"].strip())
                d["syn"] += [y["word"].lower() for y in s_.get("synonyms", []) if y.get("word")]
            d["syn"] += [y["word"].lower() for y in e.get("synonyms", []) if y.get("word")]
            d["syn"] = list(dict.fromkeys(d["syn"]))[:16]
            if verbose and n % 200000 == 0: print(f"  kaikki-all: {n} lines, {len(acc)} words, {time.time()-t0:.0f}s", flush=True)
    # document frequency of every token over every definition: the resolver's specificity key, widened from
    # WordNet's 118k glosses to Wiktionary's -- computed once here, stored beside the entries.
    df = {}
    for d in acc.values():
        for gl in d["defs"]:
            for t in set(re.findall(r"[a-z]+", gl.lower())): df[t] = df.get(t, 0) + 1
    tmp = KAIKKI_ALL_DB + ".tmp"
    if os.path.exists(tmp): os.remove(tmp)
    c = sqlite3.connect(tmp); c.execute("create table e (w text primary key, v text)"); c.execute("create table df (t text primary key, n integer)")
    c.executemany("insert into e values (?,?)", ((w, json.dumps(d, ensure_ascii=False)) for w, d in acc.items() if d["defs"]))
    c.executemany("insert into df values (?,?)", df.items())
    c.commit(); c.close()
    if os.path.exists(KAIKKI_ALL_DB): os.remove(KAIKKI_ALL_DB)
    os.replace(tmp, KAIKKI_ALL_DB)
    if verbose: print(f"  kaikki-all index: {sum(1 for d in acc.values() if d['defs'])} words from {n} lines in {time.time()-t0:.0f}s -> {os.path.basename(KAIKKI_ALL_DB)}", flush=True)
    return _SqliteIndex(KAIKKI_ALL_DB)


def kaikki_df(token):
    """definitions in the full Wiktionary index mentioning `token` (0 when only the adjective snapshot exists)."""
    idx = kaikki_index(verbose=False)
    return idx.df(token) if isinstance(idx, _SqliteIndex) else 0


def kaikki_entry(word):
    """the full entry for `word` (defs, senses with POS, syn, ex, pos) or None -- the lookup the kind-cue reader
    and the resolver use."""
    idx = kaikki_index(verbose=False)
    return idx.get(word.lower()) if idx is not None else None


def kaikki_index(rebuild=False, verbose=True):
    """word -> {defs:[str], syn:[str], ex:[str], ...}. Prefers the FULL dictionary (sqlite, every POS); falls back
    to the old adjective-only JSON index when the full file has not been downloaded."""
    if "kaikki" in _CACHE: return _CACHE["kaikki"]
    if os.path.exists(KAIKKI_ALL_DB) and not rebuild:
        _CACHE["kaikki"] = _SqliteIndex(KAIKKI_ALL_DB); return _CACHE["kaikki"]
    if os.path.exists(KAIKKI_ALL_RAW):
        _CACHE["kaikki"] = kaikki_build_all(verbose=verbose); return _CACHE["kaikki"]
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
    print(f"kaikki: {len(k) if k else 'NOT DOWNLOADED'} words ({'full dictionary' if isinstance(k, _SqliteIndex) else 'adjectives only'})   moby: {len(m) if m else 'NOT DOWNLOADED'} headwords")
    for w in sys.argv[1:] or ["slender", "enormous", "teal", "topmost"]:
        if w.startswith("--"): continue
        print(f"\n{w}: kaikki {src_kaikki(w)[:2] if src_kaikki(w) else None}")
        print(f"{w}: moby {str(src_moby(w))[:200] if src_moby(w) else None}")
