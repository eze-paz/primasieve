"""BOOKS2 rater files: merge the books and books2 generations on the shared prompts and show every text in the books format
(lowercase, words and periods; books2's other punctuation dropped, its contractions kept lowercase), so raters judge word
choice, not formatting. Writes mtest/<tag>_gen.json (all), <tag>a/<tag>b halves. Run: py -3.12 -I sieve_books2_merge.py TAG"""
import os, sys, json, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
tag = sys.argv[1]; PUN = set(',;:!?"()') | {"--"}
vw = {c: np.load(MT.fp(c, "data"))["vw"] for c in ("books", "books2")}
def fmt(c, ids):
    V = len(vw[c]) - 1; out = []
    for i in ids:
        if i == 0: out.append(".")
        elif i > V: out.append("<unk>")
        else:
            w = str(vw[c][i])
            if w not in PUN: out.append(w.lower())
    return " ".join(out).replace(" .", ".").replace("..", ".")
P = json.load(open(os.path.join(MT.OUT, "books2_prompts.json"))); G = []
for c, f in (("books", f"{tag}_old"), ("books2", f"{tag}_new")):
    for fn in sorted(glob.glob(os.path.join(MT.OUT, f"{f}_gen_p*.json"))):
        for g in json.load(open(fn)):
            if g["B"] == "truth" and c == "books2": continue
            G.append(dict(pid=g["pid"], B=g["B"] + ("2" if c == "books2" else ""), prompt=fmt("books", P[g["pid"]]["books"]["prompt"]), text=fmt(c, g["ids"]), ids=g["ids"], corpus=c, native=g["text"]))
G.sort(key=lambda g: (g["pid"], g["B"])); json.dump(G, open(os.path.join(MT.OUT, f"{tag}_gen.json"), "w"), indent=0)
n = len(P) // 2
for h in (0, 1): json.dump([dict(g, pid=g["pid"] - n * h) for g in G if (g["pid"] >= n) == bool(h)], open(os.path.join(MT.OUT, f"{tag}{'ab'[h]}_gen.json"), "w"), indent=0)
print(len(G), "items")
