"""TOK1B (sieve_lang_prereg.md, BIG1B): tokenize PG-19 train shards 0..11 (whole shards) the same way as BIG's tok.py
(same regexes, same MT ids, same 8-word contamination filter, computed with out-of-vocabulary words as UNK exactly as
before), but with an extended vocabulary: the 5,533 most frequent out-of-MT-vocabulary words over these shards get ids
60002..65534 (keys stay 16-bit). Other words = UNK (60001). Kaggle CPU kernel with internet. Writes
/kaggle/working/tok1b_<shard>.npz (S uint16, doclen int32), tok1b_vocab.json (ext words in id order), tok1b_stats.json.
Smoke: T1_SMOKE=1 T1_DATA=.. T1_PARQUET=<local parquet> T1_OUT=.."""
import os, re, json, time, glob, numpy as np
from collections import Counter
SMOKE = bool(os.environ.get("T1_SMOKE")); T0 = time.time(); V = 60000; UNK = V + 1; NEXT = 65535 - (V + 2); TMP0 = 1 << 16; M64 = np.uint64(0x9E3779B97F4A7C15)
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("T1_OUT", ".")
TOK = re.compile(r"[A-Za-z][A-Za-z'-]*|[.,;!?]"); SENT = re.compile(r"(?<=[.!?])(?<!Dr\.)(?<!Mr\.)(?<!Mrs\.)(?<!St\.)\s+(?=[A-Z\"'])"); PARA = re.compile(r"\n\s*\n")
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def h8(a):
    a = a.astype(np.uint64); n = len(a) - 7
    if n <= 0: return np.zeros(0, np.uint64)
    x = np.zeros(n, np.uint64); y = np.zeros(n, np.uint64)
    for i in range(4): x = (x << np.uint64(16)) | a[i:i + n]; y = (y << np.uint64(16)) | a[4 + i:4 + i + n]
    with np.errstate(over="ignore"): return (x * M64) ^ y
dp = glob.glob("/kaggle/input/**/books_data.npz", recursive=True) or [os.path.join(os.environ.get("T1_DATA", "."), "books_data.npz")]
z = np.load(dp[0]); vw = z["vw"]; ntr = int(z["ntr"]); voc = {str(w): i for i, w in enumerate(vw) if i > 0}; EV = np.unique(h8(z["S"][ntr:])); log(f"vocabulary {len(voc):,}, eval windows {len(EV):,}")
def shard_files():
    if SMOKE: yield 0, os.environ["T1_PARQUET"]; return
    import requests
    from huggingface_hub import HfApi
    names = sorted(f for f in HfApi().list_repo_files("emozilla/pg19", repo_type="dataset") if f.startswith("data/train-"))[:12]; os.makedirs("/kaggle/temp", exist_ok=True)
    for k, nm in enumerate(names):
        fn = "/kaggle/temp/shard.parquet"
        with requests.get(f"https://huggingface.co/datasets/emozilla/pg19/resolve/main/{nm}", stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(fn, "wb") as f:
                for ch in r.iter_content(1 << 22): f.write(ch)
        log(f"downloaded {nm}"); yield k, fn
class JsonPF:                                                                                              # smoke stand-in for a parquet file (one row group)
    def __init__(s, fn): s.t = json.load(open(fn)); s.num_row_groups = 1
    def read_row_group(s, g, columns): return type("T", (), {"column": lambda _, i: type("C", (), {"to_pylist": lambda __: s.t})()})()
if not SMOKE: import pyarrow.parquet as pq
oov = {}; cnt = Counter(); SHARDS = {}; ST = dict(shards={})
for k, fn in shard_files():
    pf = JsonPF(fn) if SMOKE else pq.ParquetFile(fn); out, lens, kept, dropped = [], [], 0, 0
    for g in range(pf.num_row_groups):
        texts = pf.read_row_group(g, columns=["text"]).column(0).to_pylist()
        if SMOKE: texts = texts[:40]
        for text in texts:
            toks = []
            for para in PARA.split(text):
                p = para.replace("\n", " ").strip()
                if not p: continue
                for s in SENT.split(p):
                    w = [x.lower() for x in TOK.findall(s) if x.isalpha()]
                    if len(w) < 2: continue
                    toks.append(0)
                    for x in w:
                        i = voc.get(x)
                        if i is None: i = oov.setdefault(x, TMP0 + len(oov)); cnt[x] += 1
                        toks.append(i)
            if len(toks) < 9: continue
            a = np.array(toks, np.uint32); h = h8(np.minimum(a, UNK)); j = np.minimum(np.searchsorted(EV, h), len(EV) - 1)   # filter exactly as before (OOV = UNK)
            if (EV[j] == h).mean() > 0.02: dropped += 1; continue
            out.append(a); lens.append(len(a)); kept += 1
    SHARDS[k] = (np.concatenate(out), np.array(lens, np.int32)); ST["shards"][k] = dict(kept=kept, dropped=dropped, tokens=int(len(SHARDS[k][0])))
    log(f"shard {k}: kept {kept:,}, dropped {dropped:,}, tokens {len(SHARDS[k][0]):,}, OOV types so far {len(oov):,}")
ext = [w for w, _ in cnt.most_common(NEXT)]; lut = np.full(TMP0 + len(oov), UNK, np.uint16); lut[:TMP0] = np.arange(TMP0, dtype=np.uint64).astype(np.uint16)
for r, w in enumerate(ext): lut[oov[w]] = V + 2 + r
tot = sum(len(s) for s, _ in SHARDS.values()); old_unk = 0; new_unk = 0; words = 0
for k, (s, l) in SHARDS.items():
    words += int((s != 0).sum()); old_unk += int((s >= TMP0).sum()); t = lut[s]; new_unk += int((t == UNK).sum())
    np.savez(os.path.join(OUTD, f"tok1b_{k}.npz"), S=t, doclen=l)
ST.update(tokens=tot, words=words, unk_old_vocab=old_unk / words, unk_ext_vocab=new_unk / words, ext=len(ext), oov_types=len(oov), ext_last_count=int(cnt[ext[-1]]) if ext else 0)
json.dump(ext, open(os.path.join(OUTD, "tok1b_vocab.json"), "w")); json.dump(ST, open(os.path.join(OUTD, "tok1b_stats.json"), "w"), indent=1); log(f"saved: {ST}")
