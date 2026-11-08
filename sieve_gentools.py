"""Reusable generation-evaluation tools (TEMP and later rounds).
  py -3.12 -I sieve_gentools.py blind TAG GEN.json         -> mtest/kaggle_<tag>/blind/<tag>_blind_items.json + sieve_<tag>_blind_key.json
  py -3.12 -I sieve_gentools.py judge TAG GEN.json         -> Kaggle dataset primasieve-<tag>-gen + kernel primasieve-<tag>-judge (Pythia-410m),
                                                              waits, downloads mtest/kaggle_<tag>/judge_out/<tag>_pythia.json
  py -3.12 -I sieve_gentools.py pairs TAG GEN.json A:B,A:C  -> side-by-side items (first/second in random order)
  py -3.12 -I sieve_gentools.py pairscore TAG A:B,A:C       -> sieve_<tag>_pair_scores.json (+1 = second arm of the comparison preferred)
  py -3.12 -I sieve_gentools.py score TAG GEN.json BASEARM -> sieve_<tag>_gen_scores.json (per-arm means, arm minus BASEARM intervals over prompts,
                                                              copied 8-word windows, repeated trigrams)"""
import os, sys, json, time, shutil, subprocess
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
def kd(tag): return os.path.join(HERE, "mtest", f"kaggle_{tag}")
def kg(*a):
    r = subprocess.run(["py", "-3.13", "-m", "kaggle", *a], capture_output=True, text=True); return (r.stdout + r.stderr).strip()
def blind(tag, gen):
    G = json.load(open(gen)); g = np.random.default_rng(abs(hash(tag)) % 1000); o = g.permutation(len(G)); items, key = [], {}
    for i, j in enumerate(o):
        u = f"U{i:03d}"; items.append(dict(id=u, prompt=G[j]["prompt"], continuation=G[j]["text"])); key[u] = [G[j]["pid"], G[j]["B"]]
    d = os.path.join(kd(tag), "blind"); os.makedirs(d, exist_ok=True); json.dump(items, open(os.path.join(d, f"{tag}_blind_items.json"), "w"), indent=0)
    json.dump(key, open(os.path.join(HERE, f"sieve_{tag}_blind_key.json"), "w")); print(f"{len(items)} blind items -> {d}")
def judge(tag, gen):
    d = kd(tag); gd = os.path.join(d, "gen"); jd = os.path.join(d, "judge"); os.makedirs(gd, exist_ok=True); os.makedirs(jd, exist_ok=True)
    shutil.copy(gen, os.path.join(gd, "sw_gen.json")); json.dump(dict(title=f"primasieve-{tag}-gen", id=f"ezequieldepaz/primasieve-{tag}-gen", licenses=[dict(name="CC0-1.0")]), open(os.path.join(gd, "dataset-metadata.json"), "w"))
    src = open(os.path.join(HERE, "sieve_sw_judge_kernel.py")).read().replace("/kaggle/working/sw_pythia.json", f"/kaggle/working/{tag}_pythia.json"); open(os.path.join(jd, "pyj.py"), "w").write(src)
    json.dump(dict(id=f"ezequieldepaz/primasieve-{tag}-judge", title=f"primasieve {tag} judge", code_file="pyj.py", language="python", kernel_type="script", is_private=True, enable_gpu=True, enable_internet=True, dataset_sources=[f"ezequieldepaz/primasieve-{tag}-gen"]), open(os.path.join(jd, "kernel-metadata.json"), "w"))
    print(kg("datasets", "create", "-p", gd)[-200:])
    for _ in range(60):
        if "ready" in kg("datasets", "status", f"ezequieldepaz/primasieve-{tag}-gen"): break
        time.sleep(10)
    print(kg("kernels", "push", "-p", jd)[-200:])
    for _ in range(120):
        s = kg("kernels", "status", f"ezequieldepaz/primasieve-{tag}-judge")
        if any(x in s for x in ("COMPLETE", "ERROR", "CANCEL")): break
        time.sleep(20)
    print(s); od = os.path.join(d, "judge_out"); os.makedirs(od, exist_ok=True); kg("kernels", "output", f"ezequieldepaz/primasieve-{tag}-judge", "-p", od); print(os.listdir(od))
def score(tag, gen, basearm):
    import sieve_mtest as MT
    G = json.load(open(gen)); arms = list(dict.fromkeys(g["B"] for g in G)); npid = len({g["pid"] for g in G})
    import glob as _g
    RF = sorted(_g.glob(os.path.join(kd(tag), "blind", f"{tag}_blind_ratings*.json"))); RS = [json.load(open(f)) for f in RF]; key = json.load(open(os.path.join(HERE, f"sieve_{tag}_blind_key.json")))
    assert all(len(r) == len(key) == len(G) for r in RS); R = {u: {m: float(np.mean([r[u][m] for r in RS])) for m in ("coherence", "fluency")} for u in key}   # mean over raters
    print(f"raters: {[os.path.basename(f) for f in RF]}")
    for f, r in zip(RF, RS): print(os.path.basename(f), {B: round(float(np.mean([r[u]["fluency"] for u, (p, b) in key.items() if b == B])), 3) for B in dict.fromkeys(g["B"] for g in G)})
    P = {(g["pid"], g["B"]): g["bits_per_token"] for g in json.load(open(os.path.join(kd(tag), "judge_out", f"{tag}_pythia.json")))}
    v = {(pid, B): dict(R[u], pythia=P[(pid, B)]) for u, (pid, B) in key.items()}; g = np.random.default_rng(0); out = {}
    for m in ("fluency", "coherence", "pythia"):
        out[m] = {B: round(float(np.mean([v[(p, B)][m] for p in range(npid)])), 4) for B in arms}
        for B in arms:
            if B in (basearm, "truth"): continue
            d = np.array([v[(p, B)][m] - v[(p, basearm)][m] for p in range(npid)]); s = [d[g.integers(0, npid, npid)].mean() for _ in range(2000)]
            out[m][f"{B} minus {basearm}"] = [round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]
        print(m, out[m], flush=True)
    H8 = np.load(MT.fp("books", "sw_index"))["H8"]; M64 = np.uint64(0x9E3779B97F4A7C15); out["stats"] = {}
    def h8(w):
        a = np.uint64(0); b = np.uint64(0)
        for i in range(4): a = (a << np.uint64(16)) | np.uint64(w[i]); b = (b << np.uint64(16)) | np.uint64(w[4 + i])
        with np.errstate(over="ignore"): return (a * M64) ^ b
    z = np.load(MT.fp("books", "data")); St = z["S"][:int(z["ntr"])].astype(np.uint64); n6 = len(St) - 5; a6 = np.zeros(n6, np.uint64); b6 = np.zeros(n6, np.uint64)
    for i in range(4): a6 = (a6 << np.uint64(16)) | St[i:i + n6]
    for i in range(2): b6 = (b6 << np.uint64(16)) | St[4 + i:4 + i + n6]
    with np.errstate(over="ignore"): H6 = np.sort((a6 * M64) ^ b6)
    del a6, b6, St
    def h6(w):
        a = np.uint64(0); b = np.uint64(0)
        for i in range(4): a = (a << np.uint64(16)) | np.uint64(w[i])
        for i in range(2): b = (b << np.uint64(16)) | np.uint64(w[4 + i])
        with np.errstate(over="ignore"): return (a * M64) ^ b
    for B in arms:
        cp, rp, c6 = [], [], []
        for x in (q for q in G if q["B"] == B):
            ids = x["ids"]; hs = np.array([h8(ids[i:i + 8]) for i in range(len(ids) - 7)]); cp.append(float((H8[np.minimum(np.searchsorted(H8, hs), len(H8) - 1)] == hs).mean()))
            tg = [tuple(ids[j:j + 3]) for j in range(len(ids) - 2)]; rp.append(1 - len(set(tg)) / len(tg))
            h_ = np.array([h6(ids[i:i + 6]) for i in range(len(ids) - 5)]); c6.append(float((H6[np.minimum(np.searchsorted(H6, h_), len(H6) - 1)] == h_).mean()))
        out["stats"][B] = dict(copy8=round(float(np.mean(cp)), 4), copy6=round(float(np.mean(c6)), 4), repeat3=round(float(np.mean(rp)), 4))
    print("stats", out["stats"]); json.dump(out, open(os.path.join(HERE, f"sieve_{tag}_gen_scores.json"), "w"), indent=1)
def pairs(tag, gen, comps):
    """side-by-side items: for each prompt and each comparison A:B, the two continuations in random order"""
    G = json.load(open(gen)); by = {(g["pid"], g["B"]): g for g in G}; npid = len({g["pid"] for g in G}); rng = np.random.default_rng(len(tag)); items, key = [], {}
    for a, b in comps:
        for p in range(npid):
            x, y = (a, b) if rng.random() < 0.5 else (b, a); u = f"P{len(items):03d}"
            items.append(dict(id=u, prompt=by[(p, x)]["prompt"], first=by[(p, x)]["text"], second=by[(p, y)]["text"])); key[u] = [p, x, y]
    o = rng.permutation(len(items)); items = [items[i] for i in o]
    d = os.path.join(kd(tag), "blind"); os.makedirs(d, exist_ok=True); json.dump(items, open(os.path.join(d, f"{tag}_pair_items.json"), "w"), indent=0)
    json.dump(key, open(os.path.join(HERE, f"sieve_{tag}_pair_key.json"), "w")); print(f"{len(items)} pair items -> {d}")
def pairscore(tag, comps):
    import glob as _g
    key = json.load(open(os.path.join(HERE, f"sieve_{tag}_pair_key.json"))); RF = sorted(_g.glob(os.path.join(kd(tag), "blind", f"{tag}_pair_ratings*.json"))); RS = [json.load(open(f)) for f in RF]; out = {}; g = np.random.default_rng(0)
    for a, b in comps:
        for m in ("coherence", "fluency"):
            sc = {}
            for u, (p, x, y) in key.items():
                if {x, y} != {a, b}: continue
                v = np.mean([{"first": 1, "second": -1, "tie": 0}[r[u][m]] for r in RS]); sc[p] = v if x == b else -v           # +1 = b preferred
            d = np.array([sc[p] for p in sorted(sc)]); s = [d[g.integers(0, len(d), len(d))].mean() for _ in range(2000)]
            out[f"{b} vs {a} {m}"] = dict(b_wins=float((d > 0).mean()), a_wins=float((d < 0).mean()), mean=round(float(d.mean()), 4), interval=[round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)])
    for k_, v in out.items(): print(k_, v)
    json.dump(dict(raters=[os.path.basename(f) for f in RF], **out), open(os.path.join(HERE, f"sieve_{tag}_pair_scores.json"), "w"), indent=1)
if __name__ == "__main__":
    if sys.argv[1] in ("pairs", "pairscore"):
        cs = [tuple(x.split(":")) for x in sys.argv[-1].split(",")]
        (pairs(sys.argv[2], sys.argv[3], cs) if sys.argv[1] == "pairs" else pairscore(sys.argv[2], cs)); sys.exit()
    cmd = sys.argv[1]; dict(blind=lambda: blind(sys.argv[2], sys.argv[3]), judge=lambda: judge(sys.argv[2], sys.argv[3]), score=lambda: score(sys.argv[2], sys.argv[3], sys.argv[4]))[cmd]()
