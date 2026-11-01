"""TH2 online dictionary (LX_prereg.md): parts of speech from Wiktionary (English section) for the unknown previous
words WordNet lacks (lr_think_nopos_A/B.json). Batch API: 50 page titles (word, Word) per request, wikitext parsed for
the English section's part-of-speech headings; a refused request (HTTP 429) is retried after a pause, never cached as
"no entry". Uses curl (Python's certificate store here rejects the site). Cached in lr_wikt.json.
Run: py -3.12 lr_wikt.py"""
import os, re, json, time, subprocess, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); fn = os.path.join(HERE, "lr_wikt.json")
POS = {"Noun", "Proper noun", "Verb", "Adjective", "Adverb", "Interjection", "Preposition", "Pronoun", "Conjunction", "Numeral", "Article", "Determiner", "Particle"}
want = sorted(set(json.load(open(os.path.join(HERE, "lr_think_nopos_A.json")))) | set(json.load(open(os.path.join(HERE, "lr_think_nopos_B.json")))))
cache = json.load(open(fn, encoding="utf-8")) if os.path.exists(fn) else {}
cache = {w: v for w, v in cache.items() if isinstance(v, dict)}                                      # drop the old per-word format (429s were cached as empty)
def fetch(titles):
    q = urllib.parse.urlencode(dict(action="query", prop="revisions", rvprop="content", rvslots="main", format="json", formatversion=2, titles="|".join(titles)))
    for attempt in range(6):
        r = subprocess.run(["curl", "-s", "-m", "30", "-w", "\n%{http_code}", "-A", "primasieve-research/0.1 (offline experiment; batched dictionary lookups)",
                            "https://en.wiktionary.org/w/api.php?" + q], capture_output=True, text=True, encoding="utf-8")
        body, _, code = r.stdout.rpartition("\n")
        if code == "200": return json.loads(body)
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"Wiktionary kept refusing (last HTTP {code})")
def english_pos(text):
    m = re.search(r"^==English==\s*$(.*?)(?=^==[^=]|\Z)", text, re.M | re.S)
    return sorted({h for h in re.findall(r"^===+\s*([^=]+?)\s*===+\s*$", m.group(1), re.M) if h in POS}) if m else []
t0 = time.time(); todo = [w for w in want if w not in cache]
for a in range(0, len(todo), 25):
    batch = todo[a:a + 25]; titles = [f for w in batch for f in (w, w.capitalize())]
    d = fetch(titles); pages = {p["title"]: p for p in d["query"]["pages"]}
    norm = {n["from"]: n["to"] for n in d["query"].get("normalized", [])}
    for w in batch:
        got = {}
        for f in (w, w.capitalize()):
            p = pages.get(norm.get(f, f), {})
            if p.get("missing") or "revisions" not in p: continue
            got[f] = english_pos(p["revisions"][0]["slots"]["main"]["content"])
        cache[w] = got
    json.dump(cache, open(fn, "w", encoding="utf-8")); time.sleep(2)
found = {w: sorted({x for v in cache[w].values() for x in v}) for w in want if any(cache[w].values())}
print(f"{len(want)} words; Wiktionary gives an English part of speech for {len(found)}; e.g. " + ", ".join(f"{w}: {'/'.join(v)}" for w, v in list(found.items())[:14]) + f" ({time.time() - t0:.0f} s)")
