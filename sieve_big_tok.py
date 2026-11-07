"""BIG (sieve_lang_prereg.md): tokenize one half of one PG-19 / Wikipedia parquet shard into MT word ids (uint16), the same
way MT's prep_wiki tokenizes (lowercased alphabetic words, sentences of >= 2 words, a 0 before each sentence), dropping
documents with > 0.02 of their 8-word windows in the corpus's MT eval text. Kaggle CPU kernel; CORPUS/SHARD/PART set
per kernel copy. Writes /kaggle/working/tok_<c>_<shard>_<part>.npz (S uint16, doclen int32) + stats json."""
import os, re, json, time, glob, numpy as np, requests, pyarrow.parquet as pq
CORPUS, SHARD, PART, NPART = "books", 0, 0, 2
URL = {"books": ["https://huggingface.co/datasets/emozilla/pg19/resolve/main/data/train-00000-of-00023-5263dc4323e881d2.parquet",
                 "https://huggingface.co/datasets/emozilla/pg19/resolve/main/data/train-00001-of-00023-2b13c68dbeba63b5.parquet",
                 "https://huggingface.co/datasets/emozilla/pg19/resolve/main/data/train-00002-of-00023-8e4dd6b70d51dfcf.parquet"],
       "wiki": ["https://huggingface.co/datasets/wikimedia/wikipedia/resolve/main/20231101.en/train-00000-of-00041.parquet",
                "https://huggingface.co/datasets/wikimedia/wikipedia/resolve/main/20231101.en/train-00001-of-00041.parquet"]}
TOK = re.compile(r"[A-Za-z][A-Za-z'-]*|[.,;!?]"); SENT = re.compile(r"(?<=[.!?])(?<!Dr\.)(?<!Mr\.)(?<!Mrs\.)(?<!St\.)\s+(?=[A-Z\"'])"); PARA = re.compile(r"\n\s*\n")
T0 = time.time(); V = 60000; UNK = V + 1; M64 = np.uint64(0x9E3779B97F4A7C15)
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def h8(a):
    a = a.astype(np.uint64); n = len(a) - 7
    if n <= 0: return np.zeros(0, np.uint64)
    x = np.zeros(n, np.uint64); y = np.zeros(n, np.uint64)
    for i in range(4): x = (x << np.uint64(16)) | a[i:i + n]; y = (y << np.uint64(16)) | a[4 + i:4 + i + n]
    with np.errstate(over="ignore"): return (x * M64) ^ y
z = np.load([f for f in glob.glob("/kaggle/input/**/*_data.npz", recursive=True) if os.path.basename(f).startswith(CORPUS)][0]); vw = z["vw"]; ntr = int(z["ntr"])
voc = {str(w): i for i, w in enumerate(vw) if i > 0}; EV = np.unique(h8(z["S"][ntr:])); log(f"{CORPUS}: vocabulary {len(voc):,}, eval 8-gram windows {len(EV):,}")
fn = "/kaggle/temp/shard.parquet"; os.makedirs("/kaggle/temp", exist_ok=True)
with requests.get(URL[CORPUS][SHARD], stream=True, timeout=60) as r:
    r.raise_for_status()
    with open(fn, "wb") as f:
        for ch in r.iter_content(1 << 22): f.write(ch)
pf = pq.ParquetFile(fn); ng = pf.num_row_groups; groups = [g for g in range(ng) if g * NPART // ng == PART]; log(f"downloaded shard {SHARD}: {ng} row groups, this part {groups[0]}..{groups[-1]}")
out, lens, kept, dropped, words = [], [], 0, 0, 0
for g in groups:
    for text in pf.read_row_group(g, columns=["text"]).column(0).to_pylist():
        toks = []
        for para in PARA.split(text):
            p = para.replace("\n", " ").strip()
            if not p: continue
            for s in SENT.split(p):
                w = [x.lower() for x in TOK.findall(s) if x.isalpha()]
                if len(w) < 2: continue
                toks.append(0); toks.extend(voc.get(x, UNK) for x in w)
        if len(toks) < 9: continue
        a = np.array(toks, np.uint16); h = h8(a); i = np.minimum(np.searchsorted(EV, h), len(EV) - 1)
        if (EV[i] == h).mean() > 0.02: dropped += 1; continue
        out.append(a); lens.append(len(a)); kept += 1; words += int((a != 0).sum())
    log(f"row group {g}: kept {kept:,} docs, dropped {dropped:,}, words {words:,}")
np.savez(f"/kaggle/working/tok_{CORPUS}_{SHARD}_{PART}.npz", S=np.concatenate(out), doclen=np.array(lens, np.int32))
json.dump(dict(corpus=CORPUS, shard=SHARD, part=PART, kept=kept, dropped=dropped, words=words), open(f"/kaggle/working/tok_{CORPUS}_{SHARD}_{PART}.json", "w")); log("saved")
