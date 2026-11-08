"""JX judging (from BIG1B judging). build: E2E's BEST (191M) + JX1 / JX3 into sieve_jx_gen.json; pair items (JX1 vs BEST191,
JX3 vs BEST191; one batch of 80 per comparison) and grammar items (BEST191, JX1, JX3, truth; batch 1 = prompts 0-39,
batch 2 = 40-79). score: pairwise shares (sieve_pairscore.py) + grammatical share. Run: py -3.12 -I sieve_jx_judge.py build|score"""
import os, sys, json, subprocess, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "mtest", "kaggle_jxj")
def build():
    e = json.load(open(os.path.join(HERE, "sieve_e2e_gen.json"), encoding="utf-8")); g = json.load(open(os.path.join(HERE, "mtest", "kaggle_jx", "jx", "out", "g1b_jx_gen.json"), encoding="utf-8"))
    G = {"BEST191": e["BEST"], "JX1": g["JX1"], "JX3": g["JX3"], "truth": g["truth"]}
    for B in G: assert [x["pid"] for x in G[B]["gens"]] == list(range(80)), B
    assert all(G["BEST191"]["gens"][p]["prompt"] == G["JX1"]["gens"][p]["prompt"] for p in range(80)); assert all(e["truth"]["gens"][p]["text"] == g["truth"]["gens"][p]["text"] for p in range(80))
    json.dump(G, open(os.path.join(HERE, "sieve_jx_gen.json"), "w", encoding="utf-8"), indent=0); rng = np.random.default_rng(101); key = {}
    for b, (X, Y) in enumerate((("JX1", "BEST191"), ("JX3", "BEST191"))):
        items = []
        for p in rng.permutation(80):
            a, c = (X, Y) if rng.random() < 0.5 else (Y, X); u = f"Q{b}{len(items):03d}"; key[u] = [int(p), a, c]
            items.append(dict(id=u, prompt=G[a]["gens"][p]["prompt"], A=G[a]["gens"][p]["text"], B=G[c]["gens"][p]["text"]))
        os.makedirs(os.path.join(D, f"p{b}"), exist_ok=True); json.dump(items, open(os.path.join(D, f"p{b}", "pair_items.json"), "w", encoding="utf-8"), indent=0)
    json.dump(key, open(os.path.join(HERE, "sieve_jx_key.json"), "w"))
    gk = {}
    for b, pr in enumerate((range(0, 40), range(40, 80))):
        items = [(p, B) for p in pr for B in G]; items = [items[i] for i in rng.permutation(len(items))]; out = []
        for p, B in items:
            s = [x.strip(" .") for x in G[B]["gens"][p]["text"].split(". ")]; s = [x for x in s if x]; u = f"G{b}{len(out):03d}"; gk[u] = [p, B, len(s)]; out.append(dict(id=u, sentences=s))
        os.makedirs(os.path.join(D, f"g{b}"), exist_ok=True); json.dump(out, open(os.path.join(D, f"g{b}", "gram_items.json"), "w", encoding="utf-8"), indent=0)
    json.dump(gk, open(os.path.join(HERE, "sieve_gramjx_key.json"), "w")); print("built", len(key), "pairs,", len(gk), "grammar items")
def score():
    R = {}
    for b in (0, 1): R.update(json.load(open(os.path.join(D, f"p{b}", "pair_ratings.json"))))
    json.dump(R, open(os.path.join(HERE, "sieve_jx_ratings.json"), "w"))
    subprocess.run(["py", "-3.12", "-I", os.path.join(HERE, "sieve_pairscore.py"), os.path.join(HERE, "sieve_jx_ratings.json"), os.path.join(HERE, "sieve_jx_key.json"), os.path.join(HERE, "sieve_jx_gen.json"), "80", os.path.join(HERE, "sieve_jx_scores.json"), "JX1:BEST191", "JX3:BEST191"])
    gk = json.load(open(os.path.join(HERE, "sieve_gramjx_key.json"))); GR = {}
    for b in (0, 1): GR.update(json.load(open(os.path.join(D, f"g{b}", "gram_ratings.json"))))
    json.dump(GR, open(os.path.join(HERE, "sieve_gramjx_ratings.json"), "w")); g = np.random.default_rng(0); out = {}
    for B in ("BEST191", "JX1", "JX3", "truth"):
        per = {}
        for u, (p, b_, n) in gk.items():
            if b_ == B: assert len(GR[u]) == n, u; per[p] = (sum(GR[u]), n)
        ps = np.array(sorted(per)); k = np.array([per[p][0] for p in ps]); n = np.array([per[p][1] for p in ps]); bs = [k[i].sum() / n[i].sum() for i in (g.integers(0, len(ps), len(ps)) for _ in range(2000))]
        out[B] = dict(share=round(float(k.sum() / n.sum()), 3), sentences=int(n.sum()), interval=[round(float(np.percentile(bs, 2.5)), 3), round(float(np.percentile(bs, 97.5)), 3)])
        out[B]["batch"] = {str(bb): round(float(sum(per[p][0] for p in per if (p >= 40) == bb) / sum(per[p][1] for p in per if (p >= 40) == bb)), 3) for bb in (0, 1)}
    print(out); json.dump(out, open(os.path.join(HERE, "sieve_gramjx_scores.json"), "w"), indent=1)
if __name__ == "__main__": dict(build=build, score=score)[sys.argv[1]]()
