"""TH reference library (LX_prereg.md, TH1): the 400 extra Gutenberg books (none held out, none training), tokenised
like the training text (lowercase words, sentences of >= 2 words, every paragraph), as vocabulary ids (unknown =
one id). Duplicate check: share of held-out 8-grams (inside sentences) found in the library vs in the training books.
Writes lx_library.npz (untracked cache). Run: py -3.12 lx_library.py"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
sys.path.insert(0, BASE); sys.path.insert(0, os.path.dirname(BASE))
import r24_tlm as T, data as D0
t0 = time.time(); MORE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_nldata", "gutenberg_more")
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); wid = {w: i + 1 for i, w in enumerate(V["words"])}; UNK = len(V["words"]) + 1
ids, sid = [], []; k = 0
for f in sorted(os.listdir(MORE)):
    if not f.endswith(".txt"): continue
    text = D0.clean(open(os.path.join(MORE, f), encoding="utf-8", errors="replace", newline="").read())
    for p in text.split("\n"):
        p = p.replace('"', "").replace("“", "").replace("”", "").replace("’", "'").strip()
        for s in T.SENT.split(p):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: ids += [wid.get(x, UNK) for x in w]; sid += [k] * len(w); k += 1
lib = np.array(ids, np.int32); libs = np.array(sid, np.int32)
print(f"library: {len(lib):,} tokens, {k:,} sentences ({time.time() - t0:.0f} s)", flush=True)
def grams(tok, s, n=8):
    tok = tok.astype(np.uint64); h = np.zeros(len(tok) - n + 1, np.uint64)
    for j in range(n): h = h * np.uint64(1000003) + tok[j:len(tok) - n + 1 + j]
    ok = s[n - 1:] == s[:len(s) - n + 1]; return h[ok]
z = np.load(os.path.join(HERE, "lx_tokens.npz")); d = np.load(os.path.join(HERE, "lx_docs.npz"))
held = np.r_[grams(z["te"], z["tes"]), grams(d["dv"], d["dvs"])]
for nm, (tk, ss) in (("library", (lib, libs)), ("training books", (z["tr"], z["trs"]))):
    print(f"held-out 8-grams found in the {nm}: {np.isin(held, grams(tk, ss)).mean():.4f} of {len(held):,}")
np.savez(os.path.join(HERE, "lx_library.npz"), lib=lib, libs=libs)
print(f"done ({time.time() - t0:.0f} s)")
