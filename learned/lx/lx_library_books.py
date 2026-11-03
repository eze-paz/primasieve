"""Book id of every library token (lx_library.npz has only sentence ids). Re-tokenises the 400 files exactly as
lx_library.py does and records each file's token count; asserts the total equals lx_library.npz. Writes
lx_library_books.npz (book = int16 per token, names = file names in order). Run: py -3.12 lx_library_books.py"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
sys.path.insert(0, BASE); sys.path.insert(0, os.path.dirname(BASE))
import r24_tlm as T, data as D0
t0 = time.time(); MORE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_nldata", "gutenberg_more")
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); wid = {w: i + 1 for i, w in enumerate(V["words"])}
names, lens = [], []
for f in sorted(os.listdir(MORE)):
    if not f.endswith(".txt"): continue
    text = D0.clean(open(os.path.join(MORE, f), encoding="utf-8", errors="replace", newline="").read()); n = 0
    for p in text.split("\n"):
        p = p.replace('"', "").replace("“", "").replace("”", "").replace("’", "'").strip()
        for s in T.SENT.split(p):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: n += len(w)
    names.append(f); lens.append(n)
lens = np.array(lens); z = np.load(os.path.join(HERE, "lx_library.npz")); assert lens.sum() == len(z["lib"]), (lens.sum(), len(z["lib"]))
book = np.repeat(np.arange(len(lens), dtype=np.int16), lens)
np.savez(os.path.join(HERE, "lx_library_books.npz"), book=book, names=np.array(names), lens=lens)
print(f"{len(lens)} books, {lens.sum():,} tokens, median {int(np.median(lens)):,} tokens/book; last 10 books {lens[-10:].sum():,} tokens ({time.time() - t0:.0f} s)")
