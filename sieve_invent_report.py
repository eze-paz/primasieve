"""invent_prereg.md verdicts from a kernel's scoring outputs (kaggle_invent/results_<tag>/bits_<state>_<ctx>.npz: pos, y,
bits). Base / hand / search on the 50,114 positions with paragraph-bootstrap intervals (ST1 recipe) and on the fresh
books; the lever-1 bucket "content word never in book" and the other word kinds per program (attributes from
kaggle_fair_control/sieve_residual_attrs.npz). Run: py -3.12 -W ignore sieve_invent_report.py <tag>"""
import os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); tag = sys.argv[1] if len(sys.argv) > 1 else "b"; R = os.path.join(HERE, "kaggle_invent", f"results_{tag}")
S = np.load(os.path.join(HERE, "learned", "lx", "lr_c12_bits_scored.npz")); para = S["para"]; A = np.load(os.path.join(HERE, "kaggle_fair_control", "sieve_residual_attrs.npz"))
UNK = int(A["y"].max()) if A["y"].max() > 94501 else 94502
names = {"sieve_onto_base": "base (from scratch, SH2)", "sieve_onto_all": "hand (SO offers)", f"sieve_invent_{tag}": f"search {tag}"}
M = {}; Fr = {}
for st, nm in names.items():
    e = np.load(os.path.join(R, f"bits_{st}_eval.npz")); assert len(e["pos"]) == len(A["pos"]) and np.array_equal(np.minimum(e["y"], UNK), np.minimum(A["y"], UNK)); M[nm] = e["bits"]   # eval positions are offset by the training length
    f = os.path.join(R, f"bits_{st}_fresh.npz"); Fr[nm] = np.load(f)["bits"] if os.path.exists(f) else None
net = A["net"]; sieve_prev = A["sieve"]
u, inv = np.unique(para, return_inverse=True); rng = np.random.default_rng(0); B = 2000; cnt = np.bincount(inv); draws = rng.integers(0, len(u), (B, len(u)))
iv = {}
print(f"{tag}: 50,114 positions (fresh environment: last 10 library books out of the counted history)")
for nm, v in M.items():
    sums = np.bincount(inv, weights=v); bs = np.array([sums[d].sum() / cnt[d].sum() for d in draws]); iv[nm] = np.quantile(bs, [0.025, 0.975])
    print(f"   {nm:28s} eval {v.mean():.4f} bits/word [{iv[nm][0]:.4f} - {iv[nm][1]:.4f}]" + (f";  fresh {Fr[nm].mean():.4f} on {len(Fr[nm]):,}" if Fr[nm] is not None else ""))
print(f"   {'previous Sieve best (L4+L7)':28s} eval {sieve_prev.mean():.4f} (full library);  net 7.4423;  Stack 8.1507;  LM 6.0261")
h, s_ = M["hand (SO offers)"], M[f"search {tag}"]
A_pass = s_.mean() <= h.mean() and (Fr[f"search {tag}"] is None or Fr[f"search {tag}"].mean() <= Fr["hand (SO offers)"].mean())
sep = s_.mean() < iv["hand (SO offers)"][0]
print(f"   PASS A (search <= hand on eval and fresh): {A_pass}; search mean below hand's interval: {sep}")
kind = np.where(A["y"] == UNK, "unknown", np.where(A["dist"] >= 0, "repeat in book", np.where(A["y"] <= 150, "function word", "content word")))
print("   by word kind (base / hand / search / net):")
for kd in ("content word", "repeat in book", "function word", "unknown"):
    m = kind == kd; print(f"      {kd:15s} {m.sum():6,}: " + " / ".join(f"{v[m].mean():.3f}" for v in M.values()) + f" / {net[m].mean():.3f}")
st = json.load(open(os.path.join(R, f"sieve_invent_{tag}.json"))) if os.path.exists(os.path.join(R, f"sieve_invent_{tag}.json")) else None
if st:
    import collections
    kinds = collections.Counter(json.loads(k).get("kind", "vote") for k in st["mem"] + st["lift"]); print(f"   program: {len(st['mem'])} Votes, {len(st['lift'])} lifts; kinds {dict(kinds)}; runs {st['run']}; bandit {st['strat']}")
    for line in st.get("logi", []): print("      " + line)
