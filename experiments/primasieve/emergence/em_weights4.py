"""EMERGENCE E-12 -- (1) THE MORPHOLOGY SWEEP: every inflectional feature the morphology table names, tested as a
translation in Qwen2.5-0.5B's embedding table (leave-one-out nearest neighbour, shuffled-pair knockout, tolerance
core); survivors become VERIFIED OPERATORS in the geometry source the stdlib engine reads. (2) THE CAUSAL MAP: for
every surviving operator with a natural prompt family, inject it at each layer and record where (if anywhere) it
steers the model's next word to the predicted form, against a random direction and the negated operator.

Pre-registered, before running:
  P1 Survivors (accuracy >= 0.50, knockout <= 0.05, >= 40 pairs): plural, 3rd-person singular, present participle,
     comparative, superlative; past tense and past participle borderline (0.29 measured for past at n=400).
  P2 Each survivor has a layer where injection flips >= 8/20 prompts with random <= 2/20; the best layer is LATE
     (>= 14 of 24) for all of them, because the plural's was 18. If one operator is early and another late, the
     model stages morphology; if none flips, the geometry is a lexicon fact and not the mechanism.
  P3 The operators are not one direction: pairwise cosines between survivors' d vectors are below 0.5, or two
     features share one direction and the model does not distinguish them geometrically (reported either way).
Knockouts beside every number; nothing tuned; the bar is in this docstring."""
import os, sys, json, random, sqlite3, time, itertools
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qwen_fwd import Qwen
from em_weights import morphology_pairs, UNIMORPH

SNAP = r"C:/Users/aezequiel/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B/snapshots/060db6499f32faf8b98477b0a26969ef7d8b9987"
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_nldata", "qwen_geometry.sqlite")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "em_weights4_result.json")
rng = random.Random(5)
m = Qwen(SNAP)
E = m.w["model.embed_tokens.weight"].numpy(); vocab = m.tok.get_vocab()
words = {t[1:]: i for t, i in vocab.items() if t.startswith("Ġ") and t[1:].isalpha() and t[1:].islower()}
inv = {i: w for w, i in words.items()}; ids = np.array(sorted(words.values()))
U = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)


def features():
    c = {}
    for line in open(UNIMORPH, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 3: c[p[2]] = c.get(p[2], 0) + 1
    return [f for f, n in sorted(c.items(), key=lambda kv: -kv[1]) if n >= 200 and f not in ("N;SG", "ADJ", "V;NFIN;IMP+SBJV")]


def nn0(q, exclude):
    s = U[ids] @ (q / (np.linalg.norm(q) + 1e-9)); s[np.searchsorted(ids, exclude)] = -9
    return ids[int(np.argmax(s))]


def sweep(feat, cap=400):
    pairs = morphology_pairs(words, feat)
    if len(pairs) < 40: return None
    rng.shuffle(pairs); pairs = pairs[:cap]
    offs = np.stack([E[words[f]] - E[words[l]] for l, f in pairs])
    def acc(prs, offs_):
        h = 0
        for k, (l, f) in enumerate(prs):
            d = (offs_.sum(0) - offs_[k]) / (len(prs) - 1)
            h += nn0(E[words[l]] + d, words[l]) == words[f]
        return h / len(prs)
    a = acc(pairs, offs)
    sh = [(l, pairs[(k + 7) % len(pairs)][1]) for k, (l, _) in enumerate(pairs)]
    a_sh = acc(sh, np.stack([E[words[f]] - E[words[l]] for l, f in sh]))
    d = offs.mean(0); dist = np.linalg.norm(offs - d, axis=1)
    rp = [(rng.choice(list(words)), rng.choice(list(words))) for _ in range(len(pairs))]
    rdist = np.linalg.norm(np.stack([E[words[b]] - E[words[a_]] for a_, b in rp]) - d, axis=1)
    core = float((dist <= np.percentile(rdist, 5)).mean())
    return dict(feature=feat, pairs=len(pairs), acc=a, knockout=a_sh, core=core, d=d, forms={f for _, f in morphology_pairs(words, feat)})


print("(1) MORPHOLOGY SWEEP over every feature with >= 40 single-token pairs\n")
res = {}
for feat in features():
    r = sweep(feat)
    if r is None: continue
    ok = r["acc"] >= 0.5 and r["knockout"] <= 0.05
    res[feat] = r
    print(f"  {feat:22s} pairs {r['pairs']:4d}  accuracy {r['acc']:.3f}  knockout {r['knockout']:.3f}  core {r['core']:.3f}   {'VERIFIED' if ok else 'below bar'}")
survivors = {f: r for f, r in res.items() if r["acc"] >= 0.5 and r["knockout"] <= 0.05}
print(f"\nsurvivors: {sorted(survivors)}")
# P3: are they distinct directions?
names = sorted(survivors)
if len(names) > 1:
    print("pairwise cosine between operator directions:")
    for a_, b in itertools.combinations(names, 2):
        da, db = survivors[a_]["d"], survivors[b]["d"]
        print(f"    {a_:20s} {b:20s} {float(da @ db / (np.linalg.norm(da) * np.linalg.norm(db))):+.3f}")

# write the verified operators into the geometry source: op table gets one row per (word, feature) with rank 0
con = sqlite3.connect(DB)
con.execute("create table if not exists verified_op (feature text primary key, accuracy real, knockout real, core real, pairs integer)")
con.execute("delete from verified_op")
for f, r in survivors.items():
    con.execute("insert into verified_op values (?,?,?,?,?)", (f, r["acc"], r["knockout"], r["core"], r["pairs"]))
    con.execute("delete from op where op=?", (f,))
    Q = E[ids] + r["d"]; Qn = Q / (np.linalg.norm(Q, axis=1, keepdims=True) + 1e-9)
    rows = []
    for s in range(0, len(ids), 2048):
        blk = Qn[s:s + 2048] @ U[ids].T
        for k in range(blk.shape[0]):
            i = s + k; blk[k, i] = -1; rows.append((inv[ids[i]], f, inv[ids[int(np.argmax(blk[k]))]], 0))
    con.executemany("insert into op values (?,?,?,?)", rows)
con.commit(); con.close()
print(f"geometry source: {len(survivors)} verified operators written (feature, accuracy, knockout, core) + their applications to every word\n")

# ---------------------------------------------------------------- (2) the causal map
PROMPTS = {
    "N;PL": ["I looked at the", "She picked up the", "He pointed at the", "We talked about the", "They found the",
             "There was a problem with the", "I need to buy a new", "Please pass me the", "The child drew a", "Yesterday I saw a",
             "He wrote about his", "She thanked her", "We visited the old", "Tell me about your", "The museum displayed a",
             "I forgot my", "He lost his", "The teacher praised the", "My neighbour owns a", "In the garden there is a"],
    "V;PST": ["Every morning I", "They usually", "We always", "On Sundays we", "Most people", "The children often",
              "Before dinner they", "After work I", "My parents", "The students", "Every year we", "In the evening she",
              "At the meeting they", "Whenever it rains we", "During the summer I", "Once a week they", "The dogs",
              "Every night he", "The team", "Each morning the birds"],
    "V;PRS;3;SG": ["Every morning I", "They usually", "We always", "On Sundays we", "Most people", "The children often",
                   "Before dinner they", "After work I", "My parents", "The students", "Every year we", "In the evening they",
                   "At the meeting they", "Whenever it rains we", "During the summer I", "Once a week they", "The dogs",
                   "Every night they", "The team members", "Each morning the birds"],
    "V;V.PTCP;PRS": ["Every morning I", "They usually", "We always", "On Sundays we", "Most people", "The children often",
                     "Before dinner they", "After work I", "My parents", "The students", "Every year we", "In the evening she",
                     "At the meeting they", "Whenever it rains we", "During the summer I", "Once a week they", "The dogs",
                     "Every night he", "The team", "Each morning the birds"],
    "ADJ;CMPR": ["The road was very", "This box is quite", "Her voice sounded", "The water felt", "The mountain looked",
                 "His answer was", "The soup tastes", "The new model is", "The old bridge seemed", "The room was",
                 "The lesson was", "The path grew", "The night became", "Their house is", "The price seems",
                 "The weather turned", "The story got", "The task is", "The music was", "The car is"],
    "ADJ;SPRL": ["The road was very", "This box is quite", "Her voice sounded", "The water felt", "The mountain looked",
                 "His answer was", "The soup tastes", "The new model is", "The old bridge seemed", "The room was",
                 "The lesson was", "The path grew", "The night became", "Their house is", "The price seems",
                 "The weather turned", "The story got", "The task is", "The music was", "The car is"],
}


def residual_norms(ids_p):
    import math
    w = m.w; T = len(ids_p); x = w["model.embed_tokens.weight"][torch.tensor(ids_p)]; pos = torch.arange(T); mask = torch.full((T, T), float("-inf")).triu(1); out = {}
    with torch.no_grad():
        for l in range(m.L):
            p = f"model.layers.{l}."; h = m.rms(x, w[p + "input_layernorm.weight"])
            q = (h @ w[p + "self_attn.q_proj.weight"].T + w[p + "self_attn.q_proj.bias"]).view(T, m.H, m.hd)
            k = (h @ w[p + "self_attn.k_proj.weight"].T + w[p + "self_attn.k_proj.bias"]).view(T, m.KV, m.hd)
            v = (h @ w[p + "self_attn.v_proj.weight"].T + w[p + "self_attn.v_proj.bias"]).view(T, m.KV, m.hd)
            q, k = m.rope(q, pos), m.rope(k, pos); rep = m.H // m.KV; k = k.repeat_interleave(rep, 1); v = v.repeat_interleave(rep, 1)
            att = torch.softmax(torch.einsum("thd,shd->hts", q, k) / math.sqrt(m.hd) + mask, -1)
            x = x + torch.einsum("hts,shd->thd", att, v).reshape(T, m.D) @ w[p + "self_attn.o_proj.weight"].T
            h = m.rms(x, w[p + "post_attention_layernorm.weight"])
            x = x + (torch.nn.functional.silu(h @ w[p + "mlp.gate_proj.weight"].T) * (h @ w[p + "mlp.up_proj.weight"].T)) @ w[p + "mlp.down_proj.weight"].T
            out[l] = float(x[-1].norm())
    return out


def top1(ids_p, inject):
    lg = m.logits(ids_p, inject); return int(torch.argmax(lg))


print("(2) CAUSAL MAP: injection at the last position after layer L, scaled to the residual norm; flips = top-1 becomes a form of the feature\n")
cmap = {}
norms = residual_norms(m.encode("I looked at the"))
for feat in [f for f in names if f in PROMPTS]:
    d = survivors[feat]["d"]; forms = survivors[feat]["forms"]
    rand = np.random.RandomState(7).randn(*d.shape).astype(np.float32); rand *= np.linalg.norm(d) / np.linalg.norm(rand)
    row = {}
    for L in (6, 10, 14, 16, 18, 20, 22):
        scale = norms[L] / np.linalg.norm(d)
        counts = {}
        for name, vec in (("op", d), ("random", rand), ("neg", -d)):
            flips = 0
            for pr in PROMPTS[feat]:
                ip = m.encode(pr); t0 = top1(ip, None); t1 = top1(ip, (L, torch.tensor(vec * scale), len(ip) - 1))
                flips += (t1 != t0) and (inv.get(t1) in forms)
            counts[name] = flips
        row[L] = counts
    best = max(row.items(), key=lambda kv: kv[1]["op"] - kv[1]["random"])
    cmap[feat] = dict(by_layer=row, best_layer=best[0], best=best[1])
    print(f"  {feat:16s} " + "  ".join(f"L{L}:{c['op']:2d}/{c['random']}/{c['neg']}" for L, c in row.items()) + f"   best L{best[0]} op {best[1]['op']}/20 random {best[1]['random']}/20 neg {best[1]['neg']}/20")
print("\n  (cells: flips for operator / random direction / negated operator, out of 20 prompts)")
verdict = {f: (c["best"]["op"] >= 8 and c["best"]["random"] <= 2) for f, c in cmap.items()}
late = {f: c["best_layer"] >= 14 for f, c in cmap.items() if verdict[f]}
print(f"\nE12: operators that STEER the model (>= 8/20, random <= 2): {[f for f, v in verdict.items() if v]}   not at the bar: {[f for f, v in verdict.items() if not v]}")
print(f"     best layers: { {f: c['best_layer'] for f, c in cmap.items()} }   all late (>= 14) as predicted: {all(late.values()) if late else None}")
json.dump(dict(sweep={f: {k: v for k, v in r.items() if k not in ("d", "forms")} for f, r in res.items()}, survivors=sorted(survivors),
               causal={f: dict(best_layer=c["best_layer"], best=c["best"], by_layer={str(k): v for k, v in c["by_layer"].items()}) for f, c in cmap.items()},
               steer=verdict), open(OUT, "w"), indent=1)
print(f"-> {os.path.basename(OUT)}")
