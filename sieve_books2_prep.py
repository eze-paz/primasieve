"""BOOKS2 (sieve_lang_prereg.md BOOKS2): the books corpus rebuilt with capitals and punctuation.
Source: the same Gutenberg files as books (_nldata/gutenberg + _nldata/gutenberg_more), cleaned the same way (learned/data.py
clean), one doc per file. Tokens: words (letters with inner apostrophes: don't, o'clock), and , ; : ! ? " ( ) -- as their own
tokens; "." ends the sentence (the boundary 0, as in books) and inner periods (Mr.) are dropped; ! and ? stay as tokens before
the boundary. Capitals: truecased -- a word at the start of a sentence or quote, or written in all capitals, takes its most
common form inside sentences (so The -> the, He -> he, but Mary and I stay); then any capitalised form whose lower-case form
is at least 10 times as common is mapped to it (sentence starts the splitter missed). Digits dropped, as in books.
Then MT.build with the training cut set to the same number of words as books (27,000,000 words; tokens are more), MT.count,
the 8-gram copy index and the word classes. Run: py -3.12 -I sieve_books2_prep.py  -> mtest/books2_*.npz"""
import os, sys, re, json, time, array
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "learned"))
os.environ.setdefault("MT_SIZE", "27000000")
import sieve_mtest as MT, data as D0
C = "books2"; T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
SENT = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"']))(?<!Dr\.)(?<!Mr\.)(?<!Mrs\.)(?<!St\.)\s+(?=[A-Z\"'(])")
TOK = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*|--|[,;:!?\"().]")
PUN = set(',;:!?"().') | {"--"}
def prep():
    files = []
    for d in ("gutenberg", "gutenberg_more"):
        D = os.path.join(HERE, "_nldata", d); files += [os.path.join(D, f) for f in sorted(os.listdir(D)) if f.endswith(".txt")]
    wid = {}; tok = array.array("i"); ini = bytearray(); sid = array.array("i"); doc = array.array("i"); k = 0
    for di, f in enumerate(files):
        text = D0.clean(open(f, encoding="utf-8", errors="replace", newline="").read())
        text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("—", " -- ").replace("_", "")
        for para in text.split("\n"):
            for s in SENT.split(para):
                t = TOK.findall(s)
                t = [x for x in t if x != "."]                                                                 # sentence-final and inner periods
                if sum(1 for x in t if x not in PUN) < 2: continue
                first = True; q = 0
                for x in t:
                    if x == '"': q += 1; first = first or (q % 2 == 1)
                    tok.append(wid.setdefault(x, len(wid) + 1)); ini.append(1 if (first and x not in PUN) else 0)
                    sid.append(k); doc.append(di)
                    if x not in PUN: first = False
                k += 1
        if di % 200 == 0: log(f"{di + 1}/{len(files)} files, {len(tok):,} tokens")
    words = [""] + list(wid); tok = np.frombuffer(tok, np.int32).astype(np.int64); ini = np.frombuffer(bytes(ini), np.uint8).astype(bool)
    # truecase: most common surface form among inside-sentence, not-all-caps occurrences of each lower-case form
    low = {}; lid = np.zeros(len(words), np.int64)
    for i, w in enumerate(words[1:], 1): lid[i] = low.setdefault(w.lower(), len(low))
    caps = np.array([len(w) > 1 and w.isupper() for w in words]); inside = ~ini & ~caps[tok]
    cnt = np.bincount(tok[inside], minlength=len(words)); best = np.full(len(low), -1); bc = np.zeros(len(low))
    for i in np.nonzero(cnt)[0]:
        if cnt[i] > bc[lid[i]]: bc[lid[i]] = cnt[i]; best[lid[i]] = i
    fix = np.arange(len(words)); need = ini | caps[tok]
    for i in np.unique(tok[need]):
        b = best[lid[i]]
        if b >= 0: fix[i] = b                                                                                   # its common inside-sentence form
        elif words[i].lower() in wid: fix[i] = wid[words[i].lower()]                                            # else lower case when that form exists
    tok = np.where(need, fix[tok], tok)
    tot = np.bincount(tok, minlength=len(words)); fix2 = np.arange(len(words))                                    # leftover capitals (missed sentence starts): Cap -> lower when lower is 10x as common
    for i, w in enumerate(words[1:], 1):
        if w[:1].isupper() and w.lower() in wid and tot[wid[w.lower()]] >= 10 * max(tot[i], 1): fix2[i] = wid[w.lower()]
    tok = fix2[tok]
    nw = int((~np.isin(tok, [wid[p] for p in PUN if p in wid])).sum())
    np.savez(MT.fp(C, "raw"), words=np.array(words), tok=tok, sid=np.frombuffer(sid, np.int32).astype(np.int64), doc=np.frombuffer(doc, np.int32).astype(np.int64))
    log(f"BOOKS2 prep: {len(files)} files, {len(tok):,} tokens ({nw:,} words), {k:,} sentences, {len(words) - 1:,} surface forms")
    return len(tok) / nw
if __name__ == "__main__":
    ratio = prep() if not os.path.exists(MT.fp(C, "raw")) or "--prep" in sys.argv else None
    if ratio is None:
        z = np.load(MT.fp(C, "raw")); w = z["words"]; pun = np.array([x in PUN for x in w]); ratio = len(z["tok"]) / int((~pun[z["tok"]]).sum())
    MT.NTR = int(27_000_000 * ratio); MT.NEVT = int(2_500_000 * ratio); MT.SIZE = MT.NTR; MT.SUF = ""; log(f"training cut {MT.NTR:,} tokens (27,000,000 words)")
    MT.build(C); MT.count(C)
    z = np.load(MT.fp(C, "data")); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); P = np.arange(ntr - 8)
    def k4(p):
        k = np.zeros(len(p), np.uint64)
        for i in range(4): k = (k << np.uint64(16)) | S[p + i].astype(np.uint64)
        return k
    a = k4(P); b = k4(P + 4)
    with np.errstate(over="ignore"): h8 = np.sort((a * np.uint64(0x9E3779B97F4A7C15)) ^ b)
    np.savez(MT.fp(C, "sw_index"), H8=h8); log("copy index"); del a, b, h8, S
    import sieve_ms_cls as MC; MC.run(C); log("word classes; BOOKS2 done")
