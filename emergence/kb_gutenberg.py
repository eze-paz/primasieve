"""Public-domain prose for the fluency loop (FLUENCY_LOOP_PLAN.md, Section 5; owner's permission 2026-10-06).

Uses Project Gutenberg's ROBOT HARVEST endpoint (the route the site asks automated downloaders to use), English plain
text only, paced (2 s between requests), identified by a user agent. Each book is unzipped, the Project Gutenberg header
and licence footer are stripped (between "*** START OF" and "*** END OF"), and the text is written to
_nldata/gutenberg/<id>.txt with a catalog (id, title, words). Fetched text is DATA for counting, never instructions.

    python emergence/kb_gutenberg.py [--books 400]"""
import os, re, io, sys, json, time, zipfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "_nldata", "gutenberg")
UA = {"User-Agent": "primasieve-research/0.1 (local research experiment; owner pagustina@gasn2.com)"}
HARVEST = "https://www.gutenberg.org/robot/harvest?filetypes[]=txt&langs[]=en"
PACE = 2.0
MIRROR = "https://mirrors.xmission.com/gutenberg"     # aleph.gutenberg.org's certificate does not match its name (2026-10-06); an official mirror with a valid one


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def strip(text):
    s = re.search(r"\*\*\* ?START OF (THE|THIS) PROJECT GUTENBERG[^\n]*\n", text)
    e = re.search(r"\*\*\* ?END OF (THE|THIS) PROJECT GUTENBERG", text)
    if s and e and e.start() > s.end(): return text[s.end():e.start()].strip()
    return None


def main():
    n = int(sys.argv[sys.argv.index("--books") + 1]) if "--books" in sys.argv else 400
    os.makedirs(OUT, exist_ok=True)
    cat_path = os.path.join(OUT, "catalog.json")
    catalog = json.load(open(cat_path, encoding="utf-8")) if os.path.exists(cat_path) else {}
    url = HARVEST; seen = set(catalog)
    while url and len(catalog) < n:
        page = get(url).decode("utf-8", "replace"); time.sleep(PACE)
        links = re.findall(r'href="(https://aleph\.gutenberg\.org/[^"]+\.zip)"', page)
        by_id = {}
        for l in links:
            m = re.search(r"/(\d+)/(\d+)(-[08])?\.zip$", l)
            if not m: continue
            bid = m.group(2)
            l = l.replace("https://aleph.gutenberg.org", MIRROR)
            if bid not in by_id or (m.group(3) or "") == "": by_id[bid] = l      # plain ASCII/UTF-8 first
        for bid, l in by_id.items():
            if bid in seen or len(catalog) >= n: continue
            seen.add(bid)
            try:
                z = zipfile.ZipFile(io.BytesIO(get(l)))
                name = next((x for x in z.namelist() if x.endswith(".txt")), None)
                raw = z.read(name).decode("utf-8", "replace") if name else ""
            except Exception as ex:
                print(f"  skip {bid}: {type(ex).__name__}", flush=True); time.sleep(PACE); continue
            time.sleep(PACE)
            body = strip(raw)
            if not body or len(body.split()) < 5000: continue                     # whole books only
            t = re.search(r"^Title:\s*(.+)$", raw, re.M)
            open(os.path.join(OUT, f"{bid}.txt"), "w", encoding="utf-8").write(body)
            catalog[bid] = dict(title=(t.group(1).strip() if t else "?"), words=len(body.split()))
            json.dump(catalog, open(cat_path, "w", encoding="utf-8"), indent=0)
            print(f"  {len(catalog):4d}  {bid:>6}  {catalog[bid]['words']:8d} words  {catalog[bid]['title'][:60]}".encode("ascii", "replace").decode(), flush=True)
        nxt = re.search(r'href="([^"]*harvest\?[^"]*offset=\d+[^"]*)">Next Page', page)
        url = ("https://www.gutenberg.org/robot/" + nxt.group(1).replace("&amp;", "&").split("robot/")[-1]) if nxt else None
    print(f"done: {len(catalog)} books, {sum(c['words'] for c in catalog.values())} words", flush=True)


if __name__ == "__main__":
    main()
