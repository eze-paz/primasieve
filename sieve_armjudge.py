"""General blind judging for one generation file. build TAG GEN BASE ARM1,ARM2,..: pair items (each ARM vs BASE, one
batch of 80 per comparison, A/B order random) and grammar items (BASE, the ARMs and truth; three batches by prompt
thirds, every arm in every batch). score TAG: pairwise shares (sieve_pairscore.py), grammatical share per arm with a
bootstrap over prompts, per batch, and a paired bootstrap of each arm against BASE.
Files: mtest/kaggle_<TAG>j/{p<i>,g<i>}/..., sieve_<TAG>_{gen,key,ratings,scores}.json, sieve_gram<TAG>_*.json"""
import os, sys, json, subprocess, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
def D(tag): return os.path.join(HERE, "mtest", f"kaggle_{tag}j")
def build(tag, gen, base, arms):
    for f in (os.path.join(HERE, f"sieve_{tag}_key.json"), os.path.join(HERE, f"sieve_gram{tag}_key.json"), D(tag)):     # file names are case-insensitive on Windows: never build over an existing tag
        if os.path.exists(f): sys.exit(f"tag {tag} already used ({f}); pick another tag")
    g = json.load(open(gen, encoding="utf-8")); arms = arms.split(","); G = {k: g[k] for k in [base] + arms + ["truth"]}; NP = len(G[base]["gens"])
    for B in G: assert [x["pid"] for x in G[B]["gens"]] == list(range(NP)), B
    json.dump(dict(G, _meta=dict(base=base, arms=arms)), open(os.path.join(HERE, f"sieve_{tag}_gen.json"), "w", encoding="utf-8"), indent=0); rng = np.random.default_rng(sum(map(ord, tag))); key = {}
    for b, X in enumerate(arms):
        items = []
        for p in rng.permutation(NP):
            a, c = (X, base) if rng.random() < 0.5 else (base, X); u = f"Q{b}{len(items):03d}"; key[u] = [int(p), a, c]
            items.append(dict(id=u, prompt=G[a]["gens"][p]["prompt"], A=G[a]["gens"][p]["text"], B=G[c]["gens"][p]["text"]))
        os.makedirs(os.path.join(D(tag), f"p{b}"), exist_ok=True); json.dump(items, open(os.path.join(D(tag), f"p{b}", "pair_items.json"), "w", encoding="utf-8"), indent=0)
    json.dump(key, open(os.path.join(HERE, f"sieve_{tag}_key.json"), "w")); gk = {}; cuts = np.array_split(np.arange(NP), 3); names = [base] + arms + ["truth"]
    for b, pr in enumerate(cuts):
        items = [(int(p), B) for p in pr for B in names]; items = [items[i] for i in rng.permutation(len(items))]; out = []
        for p, B in items:
            s = [x.strip(" .") for x in G[B]["gens"][p]["text"].split(". ")]; s = [x for x in s if x]; u = f"G{b}{len(out):03d}"; gk[u] = [p, B, len(s)]; out.append(dict(id=u, sentences=s))
        os.makedirs(os.path.join(D(tag), f"g{b}"), exist_ok=True); json.dump(out, open(os.path.join(D(tag), f"g{b}", "gram_items.json"), "w", encoding="utf-8"), indent=0)
    json.dump(gk, open(os.path.join(HERE, f"sieve_gram{tag}_key.json"), "w")); print("built", len(key), "pairs in", len(arms), "batches;", len(gk), "grammar items in 3 batches of", len(gk) // 3)
    for X in arms: print(X, "texts differing from", base, sum(G[X]["gens"][p]["text"] != G[base]["gens"][p]["text"] for p in range(NP)))
def score(tag):
    G = json.load(open(os.path.join(HERE, f"sieve_{tag}_gen.json"), encoding="utf-8")); base, arms = G["_meta"]["base"], G["_meta"]["arms"]; NP = len(G[base]["gens"]); R = {}
    for b in range(len(arms)): R.update(json.load(open(os.path.join(D(tag), f"p{b}", "pair_ratings.json"))))
    json.dump(R, open(os.path.join(HERE, f"sieve_{tag}_ratings.json"), "w"))
    subprocess.run(["py", "-3.12", "-I", os.path.join(HERE, "sieve_pairscore.py"), os.path.join(HERE, f"sieve_{tag}_ratings.json"), os.path.join(HERE, f"sieve_{tag}_key.json"), os.path.join(HERE, f"sieve_{tag}_gen.json"), str(NP), os.path.join(HERE, f"sieve_{tag}_scores.json")] + [f"{X}:{base}" for X in arms])
    gk = json.load(open(os.path.join(HERE, f"sieve_gram{tag}_key.json"))); GR = {}
    for b in range(3): GR.update(json.load(open(os.path.join(D(tag), f"g{b}", "gram_ratings.json"))))
    json.dump(GR, open(os.path.join(HERE, f"sieve_gram{tag}_ratings.json"), "w")); per = {}
    for u, (p, B, n) in gk.items(): assert len(GR[u]) == n, u; per[(p, B)] = (sum(GR[u]), n)
    cuts = np.array_split(np.arange(NP), 3); g = np.random.default_rng(0); out = {}; I = [g.integers(0, NP, NP) for _ in range(4000)]
    def share(B, idx): return sum(per[(p, B)][0] for p in idx) / max(sum(per[(p, B)][1] for p in idx), 1)
    for B in [base] + arms + ["truth"]:
        bs = [share(B, i) for i in I]; out[B] = dict(share=round(share(B, range(NP)), 3), sentences=sum(per[(p, B)][1] for p in range(NP)), interval=[round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)], batch=[round(share(B, c), 3) for c in cuts])
        if B in arms: d = [share(B, i) - share(base, i) for i in I]; out[B]["paired_vs_base"] = [round(float(np.percentile(d, 2.5)), 3), round(float(np.percentile(d, 97.5)), 3)]
        print(B, out[B])
    json.dump(out, open(os.path.join(HERE, f"sieve_gram{tag}_scores.json"), "w"), indent=1)
if __name__ == "__main__":
    if sys.argv[1] == "build": build(*sys.argv[2:6])
    else: score(sys.argv[2])
