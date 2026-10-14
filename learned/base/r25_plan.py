"""R25-cy: meaning first, words after -- rung 1: a topic signal carried ahead of the words.
Generation as R25-cx (book-scope group network + fast counter, 300 candidates, top-p 0.9), plus a topic vector: the
decayed average (0.97 per word) of the learner's vectors of the content words read or written so far (content = not
among the 300 most frequent words). Each candidate content word's blended probability is multiplied by
exp(lam * cosine(word, topic)) and renormalised -- the passage's meaning steers which words are chosen.
Judges (not part of the engine): (a) the language model's bits per word on the 40 generated words given the prompt
(lower = more natural and coherent to it); (b) cosine between the mean vector of generated content words and the
prompt paragraph's content words (higher = on topic). 12 prompts (openings of held-out paragraphs 500, 520, ...,
720; the first 25 words), 2 seeds each, lam in {0 (base), 2, 4, 8}. PASS for the topic signal if some lam > 0 improves
both judges over lam = 0. Run: py -3.12 r25_plan.py"""
import os, sys, math, random
import numpy as np
WITHIN = "--within" in sys.argv; PLAN = "--plan" in sys.argv; HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
src = open("r25_generate.py", encoding="utf-8").read(); src = src[:src.index("from rwkv7 import")]
exec(compile(src, "r25_generate.py", "exec"))
z = np.load("r25_vectors_all.npz"); VEC = {w: v / (np.linalg.norm(v) + 1e-9) for w, v in zip(z["vocab"].tolist(), z["vecs"])}
func = set(w for w, _ in KN["uni"].most_common(300))
WV = np.stack([VEC.get(w, np.zeros(z["vecs"].shape[1])) for w in words]); content = np.array([(w not in func) and (w in VEC) for w in words])
PAIRS = None
def plan_words(prompt, k=6):                                                                  # R25-da: rarest prompt words -> their strongest associates
    global PAIRS
    if PAIRS is None:
        tsrc = open("r25_trigger.py", encoding="utf-8").read(); tsrc = tsrc[tsrc.index("t0 = time.time(); uni = g"):tsrc.index("def ptrig")]
        T_ = {"g": KN["g"], "np": np, "time": __import__("time")}; exec(tsrc, T_); PAIRS = T_
    uni_, vid, pk, pn, cn = PAIRS["uni"], PAIRS["vid"], PAIRS["pk"], PAIRS["pn"], PAIRS["cn"]; inv = {i: w for w, i in vid.items()}
    rare = sorted({w for w in prompt if w in vid and w not in func}, key=lambda w: uni_[w])[:5]; score = {}
    for c in rare:
        c_id = vid[c]; lo = np.searchsorted(pk, c_id << 20); hi = np.searchsorted(pk, (c_id + 1) << 20)
        for kk, nn_ in zip(pk[lo:hi], pn[lo:hi]):
            w = inv[int(kk & ((1 << 20) - 1))]
            if w not in func and w not in prompt and w in vi: score[w] = score.get(w, 0) + nn_ / cn[c_id]
    return [w for w, _ in sorted(score.items(), key=lambda x: -x[1])[:k]]
def gen(prompt, n, seed, lam):
    rng = random.Random(seed); h = None; ctx = [0]; topic = np.zeros(WV.shape[1])
    def upd(w):
        nonlocal topic
        topic = 0.97 * topic + (VEC[w] if (w in VEC and w not in func) else 0)
    for w in prompt: upd(w); pg, h = step(vi.get(w, 0), h); ctx.append(KN["wid"].get(w, KN["RARE"]))
    out = []; planned = set(plan_words(prompt)) if PLAN else set()
    for _ in range(n):
        pw = (pg[gids] * share).numpy(); top = np.argsort(-pw)[:300]
        if PLAN and planned: top = np.unique(np.concatenate([top, [vi[w] - 1 for w in planned]]))      # planned words are always candidates
        kn = np.array([KN["prob"](ctx[-5:], KN["wid"].get(words[i], KN["RARE"]))[0] for i in top])
        mix = 0.55 * pw[top] / pw[top].sum() + 0.45 * kn / kn.sum()
        if PLAN and lam > 0 and planned:
            boost = np.array([math.exp(lam) if words[i] in planned else 1.0 for i in top]); gg = gids[top].numpy(); new = mix * boost
            for gv in np.unique(gg):
                m_ = gg == gv; new[m_] *= mix[m_].sum() / new[m_].sum()
            mix = new / new.sum()
        elif (not PLAN) and lam > 0 and np.linalg.norm(topic) > 0:
            cos = WV[top] @ (topic / np.linalg.norm(topic)); boost = np.where(content[top], np.exp(lam * cos), 1.0)
            if WITHIN:                                                            # R25-cz: each group keeps its mass; the topic only chooses among its words
                gg = gids[top].numpy(); new = mix * boost
                for gv in np.unique(gg):
                    m_ = gg == gv; new[m_] *= mix[m_].sum() / new[m_].sum()
                mix = new
            else: mix = mix * boost
            mix /= mix.sum()
        w = words[sample(mix, top, rng)]; out.append(w); upd(w); planned.discard(w)
        pg, h = step(vi.get(w, 0), h); ctx.append(KN["wid"].get(w, KN["RARE"]))
    return out
from rwkv7 import RWKV7, tokenizer
lm = RWKV7.load("ckpt_read1b.pth"); lm.eval(); tok = tokenizer()
def lm_bits(prompt, cont):
    pieces = [tok.encode(" " + w if i else w) for i, w in enumerate(prompt + cont)]; ids = [t for p in pieces for t in p]
    lp = torch.log_softmax(lm(torch.tensor([ids]), lm.new_state())[0].float(), -1); pos = sum(len(p) for p in pieces[:len(prompt)]); tot = 0.0
    for p in pieces[len(prompt):]:
        for j, t in enumerate(p): tot -= lp[pos + j - 1, t].item() / math.log(2)
        pos += len(p)
    return tot / len(cont)
def topic_sim(ref, cont):
    a = [VEC[w] for w in ref if w in VEC and w not in func]; b = [VEC[w] for w in cont if w in VEC and w not in func]
    if not a or not b: return 0.0
    a = np.mean(a, 0); b = np.mean(b, 0); return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
tep = KN["g"]["tep"]; res = {}
for lam in ((0, 1, 2, 3) if PLAN else (0, 2, 4, 8)):
    L, S = [], []
    for pi in range(500, 740, 20):
        para = [x for s in tep[pi] for x in s]; prompt = para[:25]
        for seed in (0, 1):
            c = gen(prompt, 40, seed, lam); L.append(lm_bits(prompt, c)); S.append(topic_sim(para, c))
    res[lam] = (np.mean(L), np.mean(S)); print(f"R25-cy lam {lam}: judge bits/word {res[lam][0]:.3f} | topic similarity {res[lam][1]:.3f} ({len(L)} samples)", flush=True)
    if PLAN and lam == 0: print(f"   plan for prompt 500: {plan_words([x for s in tep[500] for x in s][:25])}", flush=True)
    if lam in (0, 4, 2): print(f"   e.g. {' '.join(gen([x for s in tep[500] for x in s][:25], 40, 0, lam))}", flush=True)
