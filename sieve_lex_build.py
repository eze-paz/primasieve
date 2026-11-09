"""LEX1 (sieve_lang_prereg.md LEX1): build the lexicon sentence store from mtest/lex1/lex_*.json.
Every entry (definition, senses, usage sentences) is split into sentences; a sentence is kept once (deduplicated across
entries) and dropped if any word is outside Sieve's vocabulary. Writes mtest/lex1/store/lex_tokens.npy (9 boundary
tokens, then each sentence's ids followed by the boundary 0) and lex_index.json (word -> sentence numbers: every
sentence sits under every vocabulary word it contains, so a sentence using moon and stars is under both, stored once)."""
import os, sys, json, glob, re
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
z = np.load(MT.fp("books", "data")); vw = z["vw"]; V = len(vw) - 1; wid = {str(w): i for i, w in enumerate(vw) if i > 0}
D = os.path.join(MT.OUT, "lex1"); OUT = os.path.join(D, os.environ.get("LEX_OUT", "store")); os.makedirs(OUT, exist_ok=True)
seen, sents, drop, heads = set(), [], 0, 0
for f in sorted(glob.glob(os.path.join(D, os.environ.get("LEX_GLOB", "lex_[0-9].json")))):
    for head, e in json.load(open(f, encoding="utf-8")).items():
        heads += 1; txt = [e.get("definition", ""), e.get("senses", "")] + list(e.get("sentences", []))
        for part in txt:
            for sn in re.split(r"[.!?;:]+", str(part).lower()):
                ws = re.sub(r"[^a-z ]+", " ", sn).split()
                if len(ws) < 3: continue
                key = " ".join(ws)
                if key in seen: continue
                seen.add(key)
                if any(w not in wid or wid[w] > V for w in ws): drop += 1; continue
                sents.append([wid[w] for w in ws])
tok = [0] * 9
for sn in sents: tok += sn + [0]
tok = np.array(tok, np.int32); np.save(os.path.join(OUT, "lex_tokens.npy"), tok)
idx = {}
for k, sn in enumerate(sents):
    for w in set(sn): idx.setdefault(str(vw[w]), []).append(k)
json.dump(idx, open(os.path.join(OUT, "lex_index.json"), "w"))
print(json.dumps(dict(entries=heads, sentences=len(sents), dropped_oov=drop, tokens=int(len(tok)), indexed_words=len(idx),
                      mean_words_indexed_per_sentence=round(float(np.mean([len(set(s)) for s in sents])) if sents else 0, 2))))
