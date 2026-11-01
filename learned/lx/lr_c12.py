"""C2 copy register and C1 breakdown (LX_prereg.md, TH section). Copy: "what followed this word earlier in this book"
-- P = (1 - lam) P_before + lam * (share of the true word among the previous word's earlier followers), lam per
bucket of how many followers were seen, fitted on the other fold; added to the stack and to stack + library lookup
(per-position bits saved by lr_think.py). C1: fold A word bits by word kind for each model and the language model.
Run: py -3.12 lr_c12.py"""
import numpy as np
from lr_common import *
LLM = -np.log2(np.load(os.path.join(BASE, "r25_llm_book_probs.npz"))["p"])
def copy_stats(F):
    n = np.zeros(F.n); c = np.zeros(F.n); seen = np.zeros(F.n, bool); k = 0; pb = -1
    tok, x, book, m = F.tok.tolist(), F.x.tolist(), F.book.tolist(), F.m.tolist()
    for t in range(len(tok)):
        if book[t] != pb: pb = book[t]; fol = {}; used = set()
        if m[t]:
            d = fol.get(x[t - 1])
            if d: n[k] = d["_n"]; c[k] = d.get(tok[t], 0)
            seen[k] = x[t] in used; k += 1
            d = fol.setdefault(x[t - 1], {"_n": 0}); d["_n"] += 1; d[tok[t]] = d.get(tok[t], 0) + 1
        used.add(x[t])
    return n, c, seen
EDG = np.array([1, 2, 4, 10, 30])
def fit(base_bits, n, c):
    p = 2.0 ** -base_bits; q = c / np.maximum(n, 1); b = np.searchsorted(EDG, n, "right"); on = n > 0; lam = np.full(6, 0.1)
    for _ in range(60):
        resp = np.where(on, lam[b] * q / np.maximum((1 - lam[b]) * p + lam[b] * q, 1e-300), 0)
        lam = np.bincount(b, weights=resp, minlength=6) / np.maximum(np.bincount(b, weights=on, minlength=6), 1)
    return lam
def apply(base_bits, n, c, lam):
    p = 2.0 ** -base_bits; q = c / np.maximum(n, 1); l = np.where(n > 0, lam[np.searchsorted(EDG, n, "right")], 0); return -np.log2((1 - l) * p + l * q)
CS = {F.name: copy_stats(F) for F in (FA, FD)}; BT = {F.name: np.load(os.path.join(HERE, f"lr_think_bits_{F.name}.npz")) for F in (FA, FD)}
log("copy register built")
out = {}
for fold, Ff, Fs in FOLDS:
    row = {}
    for base in ("stack", "lookall"):
        lam = fit(BT[Ff.name][base], *CS[Ff.name][:2]); row[base] = BT[Fs.name][base]; row[base + " + copy"] = apply(BT[Fs.name][base], *CS[Fs.name][:2], lam)
    out[Fs.name] = row
    log(f"fold {fold} (fit {Ff.name}, score {Fs.name}) word bits: stack {row['stack'].mean():.4f}; stack + copy {row['stack + copy'].mean():.4f}; "
        f"stack + library lookup {row['lookall'].mean():.4f}; stack + lookup + copy {row['lookall + copy'].mean():.4f}; copy weights by followers seen {np.round(lam, 3).tolist()}")
np.savez(os.path.join(HERE, "lr_c12_bits_scored.npz"), best=out["scored"]["lookall + copy"], llm=LLM, y=FA.y, para=FA.ppara, book=FA.book[FA.pos])   # ST1: per-position bits
F = FA; r = out["scored"]; n, c, seen = CS["scored"]; base = base_bits(F)
kind = np.where(F.y == UNK, "unknown", np.where(seen, "repeat in book", np.where(F.y <= 150, "function word", "content word")))
print("C1 breakdown, fold A, mean word bits [total bits]:")
for kd in ("repeat in book", "function word", "content word", "unknown"):
    m = kind == kd
    print(f"   {kd:15s} {m.sum():6,} positions: local {base[m].mean():.3f} [{base[m].sum():,.0f}]; stack {r['stack'][m].mean():.3f} [{r['stack'][m].sum():,.0f}]; "
          f"+ lookup + copy {r['lookall + copy'][m].mean():.3f} [{r['lookall + copy'][m].sum():,.0f}]; language model {LLM[m].mean():.3f} [{LLM[m].sum():,.0f}]")
print(f"   all             {F.n:6,} positions: local {base.mean():.3f} [{base.sum():,.0f}]; stack {r['stack'].mean():.3f} [{r['stack'].sum():,.0f}]; "
      f"+ lookup + copy {r['lookall + copy'].mean():.3f} [{r['lookall + copy'].sum():,.0f}]; language model {LLM.mean():.3f} [{LLM.sum():,.0f}]")
