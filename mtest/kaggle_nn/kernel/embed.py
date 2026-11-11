import glob, gzip, os, time, numpy as np, torch
from transformers import AutoTokenizer, AutoModel
print("cuda", torch.cuda.is_available(), flush=True); assert torch.cuda.is_available()
d = os.path.dirname(glob.glob("/kaggle/input/**/config.json", recursive=True)[0]); tk = AutoTokenizer.from_pretrained(d); md = AutoModel.from_pretrained(d).half().cuda().eval()
allf = [f for f in glob.glob("/kaggle/input/**/*", recursive=True) if os.path.isfile(f)]; print(allf, flush=True)
for c in ("books", "wiki"):
    t0 = time.time(); fn = [f for f in allf if os.path.basename(f).startswith(c + "_ctx")][0]
    tx = (gzip.open(fn, "rt", encoding="utf-8") if fn.endswith(".gz") else open(fn, encoding="utf-8")).read().split("\n")
    tx = tx[:-1] if tx[-1] == "" else tx
    o = np.argsort([len(x) for x in tx]); X = np.zeros((len(tx), 384), np.float16)
    for b0 in range(0, len(tx), 1024):
        j = o[b0:b0 + 1024]; b = tk([tx[k] for k in j], padding=True, truncation=True, max_length=128, return_tensors="pt").to("cuda")
        with torch.no_grad():
            h = md(**b).last_hidden_state.float(); m = b["attention_mask"].unsqueeze(-1).float(); v = torch.nn.functional.normalize((h * m).sum(1) / m.sum(1), dim=1)
        X[j] = v.cpu().numpy().astype(np.float16)
    np.save(f"/kaggle/working/{c}_X.npy", X); print(c, len(tx), f"{time.time() - t0:.0f} s", flush=True)
