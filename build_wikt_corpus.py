"""Build the raw-text corpus for the fluency loop from Wiktionary usage examples already on disk.
kaikki_all.sqlite `ex` -> one sentence per line, segmented by core.seqform.sentences (2..12 symbols), shuffled with a
fixed seed. Output _nldata/wikt_sents.txt (git-ignored like the rest of _nldata). Idempotent."""
import os, sys, json, sqlite3, random, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import sentences

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_nldata", "wikt_sents.txt")

if __name__ == "__main__":
    t = time.time()
    c = sqlite3.connect(os.path.join(HERE, "_nldata", "kaikki_all.sqlite"))
    seen, out = set(), []
    for w, v in c.execute("select w, v from e"):
        for e in json.loads(v).get("ex", []):
            if not isinstance(e, str) or e in seen: continue
            seen.add(e)
            for s in sentences(e):
                out.append(" ".join(s))
    random.Random(0).shuffle(out)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"{len(out)} sentences from {len(seen)} examples -> {OUT} in {time.time()-t:.0f}s")
