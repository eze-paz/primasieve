"""L7 (sieve_lang_prereg.md): situation ontologies grown by the SH1 rule with other signatures and objectives.
scene: a word is described by the words at offsets +-3, 5, 10, 20 (its surroundings); a split is kept if the class
co-occurrence description at those offsets (class of a word -> class of the word at each offset) saves more bits on the
first 3M training tokens than it costs (1 bit per word type + (1/2) log2 N per new class-pair cell).
frame: described by the words at offsets +1..+5 (what follows within a clause); objective at offsets +1..+5.
Words with < 20 uses go to a 'rare' class. Run: py -3.12 -W ignore sieve_tree2.py grow scene|frame [shuffled] ; check ...
; attrs scene|frame (writes hs1.. / hf1.. attributes)"""
import os, sys, json, math, time
import numpy as np
import sieve_fs2 as F
T0 = time.time(); VIEW = sys.argv[2] if len(sys.argv) > 2 else "scene"; SHUF = len(sys.argv) > 3 and sys.argv[3] == "shuffled"
OFFS = {"scene": (-20, -10, -5, -3, 3, 5, 10, 20), "frame": (1, 2, 3, 4, 5), "scenefull": (-20, -10, -5, -3, 3, 5, 10, 20),   # L8 signatures below (SN block)
        "near": (-3, -2, -1, 1, 2, 3), "f3": (1, 2, 3), "b3": (-3, -2, -1), "far": (-50, -25, 25, 50)}[VIEW]; TAG = VIEW + ("_shuf" if SHUF else "")
TD = os.path.join(F.SC.LX, "sieve_tree"); CK = os.path.join(TD, f"tree_{TAG}.json"); NC = 2000; NOBJ = len(F.tr) if VIEW == "scenefull" else 3_000_000
def stream():
    s = F.tr.copy()
    if SHUF: s = np.random.default_rng(0).permutation(s)
    return s
def signatures(s, words):
    row = np.full(F.Vt, -1); row[words] = np.arange(len(words)); M = np.zeros((len(words), NC + 2), np.float32)
    for o in OFFS:
        a = s[max(0, -o):len(s) - max(0, o)]; b = s[max(0, o):len(s) - max(0, -o)]; r = row[a]; ok = r >= 0; col = np.where(b == 0, NC + 1, np.where(b <= NC, b - 1, NC)); np.add.at(M, (r[ok], col[ok]), 1)
    cs = M.sum(0); tot = cs.sum()
    with np.errstate(all="ignore"): X = np.log(M * tot / np.maximum(M.sum(1, keepdims=True), 1) / np.maximum(cs, 1))
    X = np.where(M > 0, np.maximum(X, 0), 0).astype(np.float32); X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9); return X
def plogp(c): c = c[c > 0].astype(np.float64); return (c * np.log2(c)).sum()
def two_means(X, w):
    i0 = int(np.argmax(w)); i1 = int(np.argmin(X @ X[i0])); cen = X[[i0, i1]].copy()
    for _ in range(10):
        lab = np.argmax(X @ cen.T, 1)
        for k in (0, 1):
            m = lab == k
            if m.any(): v = (X[m] * w[m, None]).sum(0); cen[k] = v / max(np.linalg.norm(v), 1e-9)
    return np.argmax(X @ cen.T, 1)
mode = sys.argv[1] if len(sys.argv) > 1 else "grow"
if mode == "grow":
    s = stream(); so = s[:NOBJ]; cnt = np.bincount(s, minlength=F.Vt); words = np.nonzero(cnt >= 20)[0]; words = words[words != 0]
    st = json.load(open(CK)) if os.path.exists(CK) else dict(label={}, queue=[""], leaves=[], tried=0, kept=0)
    paths = sorted(set(st["label"].values()) | {""}); pid = {p: i for i, p in enumerate(paths)}; cls = np.full(F.Vt, len(paths) + 1, np.int64)
    for w in words.tolist(): cls[w] = pid.get(st["label"].get(str(w), ""), 0)
    X = signatures(s, words); half = 0.5 * math.log2(len(so)); F.log(f"L7 {TAG}: {len(words):,} words; {len(st['queue'])} queued; {st['kept']} splits kept")
    pairsA = [(so[max(0, -o):len(so) - max(0, o)], so[max(0, o):len(so) - max(0, -o)]) for o in OFFS]
    while st["queue"] and time.time() - T0 < 240:
        node = st["queue"].pop(0); inn = np.array([st["label"].get(str(w), "") == node for w in words])
        if inn.sum() < 2: st["leaves"].append(node); continue
        sub = two_means(X[inn], cnt[words[inn]].astype(np.float32)); wi = words[inn]; new = cls.copy(); newid = len(paths) + 10; new[wi[sub == 1]] = newid; base = newid + 5
        d = 0.0; dk = 0; isw = np.zeros(F.Vt, bool); isw[wi] = True
        for a, b in pairsA:
            aff = isw[a] | isw[b]; c0 = np.unique(cls[a[aff]] * base + cls[b[aff]], return_counts=True)[1]; c1 = np.unique(new[a[aff]] * base + new[b[aff]], return_counts=True)[1]
            ma0 = plogp(np.bincount(cls[a[isw[a]]])); ma1 = plogp(np.bincount(new[a[isw[a]]])); mb0 = plogp(np.bincount(cls[b[isw[b]]])); mb1 = plogp(np.bincount(new[b[isw[b]]]))
            d += -(plogp(c1) - plogp(c0)) + (ma1 - ma0) + (mb1 - mb0); dk += max(0, len(c1) - len(c0))   # per offset: class pair + both marginals (word-within-class term)
        cost = len(wi) + dk * half; st["tried"] += 1
        if -d > cost:
            st["kept"] += 1
            for w_, sb in zip(wi.tolist(), sub.tolist()): st["label"][str(w_)] = node + str(sb)
            paths.append(node + "1"); pid[node + "1"] = len(paths) - 1; cls[wi[sub == 1]] = pid[node + "1"]; st["queue"] += [node + "0", node + "1"]
            print(f"   split '{node or 'root'}' ({len(wi):,} words): saves {-d:,.0f} bits, costs {cost:,.0f}", flush=True)
        else: st["leaves"].append(node)
    json.dump(st, open(CK, "w")); depth = max((len(p) for p in st["label"].values()), default=0)
    F.log(f"L7 {TAG}: {st['kept']} splits kept of {st['tried']} tried; depth {depth}; {len(st['queue'])} queued" + ("" if st["queue"] else " -- tree complete"))
elif mode == "attrs":
    st = json.load(open(CK)); lab = {int(k): v for k, v in st["label"].items()}; out = {}
    for k in range(1, 14):
        ids = {}; arr = np.full(F.Vt, -1, np.int64)
        for w in range(F.Vt): arr[w] = ids.setdefault(lab[w][:k] if w in lab else "#rare", len(ids))
        out[f"k{k}"] = arr
    np.savez(os.path.join(TD, f"attrs_{VIEW}.npz"), **out); F.log(f"attrs for {VIEW} written")
else:
    import subprocess; sys.argv = [sys.argv[0], "check", VIEW]
    st = json.load(open(CK)); json.dump(st, open(os.path.join(TD, f"tree_{VIEW}_c.json"), "w"))
    words_ = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; lab = {int(k): v for k, v in st["label"].items()}; leaves = {}
    for w, p in lab.items(): leaves.setdefault(p, []).append(w)
    cnt = np.bincount(F.tr, minlength=F.Vt); depth = [len(p) for p in lab.values()] or [0]
    F.log(f"{TAG}: {len(lab):,} words, {len(leaves):,} leaves, depth max {max(depth)}")
    for p in sorted(leaves, key=lambda p: -sum(cnt[w] for w in leaves[p]))[:8]: print(f"   leaf {p}: {', '.join(words_[w - 1] for w in sorted(leaves[p], key=lambda w: -cnt[w])[:10])}")
