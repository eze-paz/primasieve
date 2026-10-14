"""R25-cv: fetch more public-domain books (owner's OK, 2026-10-14) with the project's existing polite Gutenberg fetcher
(emergence/kb_gutenberg.py: robot harvest endpoint, 2 s pacing, identified user agent), into a SEPARATE folder
_nldata/gutenberg_more so the existing training / held-out split and every test set stay unchanged. Books whose id is
already in _nldata/gutenberg are skipped. Run: py -3.12 r25_fetch_more.py --books 400"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "emergence")); import kb_gutenberg as K
K.OUT = os.path.join(ROOT, "_nldata", "gutenberg_more"); os.makedirs(K.OUT, exist_ok=True)
old = {f[:-4] for f in os.listdir(os.path.join(ROOT, "_nldata", "gutenberg")) if f.endswith(".txt")}
cat = os.path.join(K.OUT, "catalog.json")
if not os.path.exists(cat): json.dump({b: {"title": "existing corpus (skip)", "words": 0} for b in old}, open(cat, "w"))
n = int(sys.argv[sys.argv.index("--books") + 1]) if "--books" in sys.argv else 400
sys.argv = ["kb_gutenberg.py", "--books", str(len(old) + n)]; K.main()
print("R25-cv fetched:", len([f for f in os.listdir(K.OUT) if f.endswith(".txt")]), "new books", flush=True)
