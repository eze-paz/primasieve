"""R27 F0: the fluency score (R27_prereg.md). judge bits/word under the stock RWKV-7 0.4B model, repetition, sentence form.
Import: from r27_fluency import score; or run for the calibration: py -3.12 r27_fluency.py"""
import os, sys, re, math, random, json
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import torch
from rwkv7 import RWKV7, tokenizer
import r24_dict as Dct
torch.set_num_threads(4)
_M = {}
PREFIX = "Here is a passage of plain English prose.\n\n"
def _model():
    if not _M:
        m = RWKV7.load(os.path.join(HERE, "rwkv7", "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth")); m.eval(); _M["m"] = m; _M["tok"] = tokenizer()
    return _M["m"], _M["tok"]
def judge_bits(text):
    m, tok = _model(); p = tok.encode(PREFIX); t = tok.encode(text)
    if not t: return float("nan")
    with torch.no_grad(): lp = torch.log_softmax(m(torch.tensor([p + t]), m.new_state())[0].float(), -1)
    bits = -sum(lp[len(p) + j - 1, x].item() for j, x in enumerate(t)) / math.log(2)
    return bits / max(1, len(re.findall(r"[A-Za-z']+", text)))
def repetition(text):
    w = [x.lower() for x in re.findall(r"[A-Za-z']+", text)]; g = [tuple(w[i:i + 3]) for i in range(len(w) - 2)]
    return sum(1 for i, x in enumerate(g) if x in set(g[:i])) / max(1, len(g))
def sentence_form(text):
    S = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not S: return 0.0
    ok = 0
    for s in S:
        w = re.findall(r"[A-Za-z']+", s)
        if 4 <= len(w) <= 30 and s.strip()[-1] in ".!?" and any(Dct.mainly_verb(x) or Dct.verb_base(x.lower()) in ("be", "have") for x in w): ok += 1
    return ok / len(S)
def score(text): return dict(judge=round(judge_bits(text), 3), rep=round(repetition(text), 3), form=round(sentence_form(text), 3))
if __name__ == "__main__":
    os.chdir(HERE)
    import r24_books as B, data as D0
    _, te_b = D0.books(); paras = [p["text"] for p in B.paragraphs(te_b, 20000)[3000:]]
    paras = [p for p in paras if 40 <= len(p.split()) <= 120][:40]
    def lower(t): return " ".join(x.lower() for x in re.findall(r"[A-Za-z']+", t))
    def shuf(t): w = t.split(); random.Random(0).shuffle(w); return " ".join(w)
    rows = {"human": paras, "human, lower case no punctuation": [lower(p) for p in paras], "human words shuffled (floor)": [shuf(lower(p)) for p in paras]}
    import statistics as st
    res = {}
    for name, texts in rows.items():
        sc = [score(t) for t in texts]; res[name] = {k: round(st.mean(s[k] for s in sc), 3) for k in ("judge", "rep", "form")}
        print(f"F0 {name}: {res[name]} over {len(texts)} paragraphs", flush=True)
    json.dump(res, open("r27_f0_calibration.json", "w"))


def order_gain(text, n=3):
    """F1: judge bits/word with the sentences shuffled (mean of n fixed shuffles) minus in the original order"""
    S = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if len(S) < 3: return float("nan")
    base = judge_bits(text); sh = []
    for k in range(n):
        T = S[:]; random.Random(k + 1).shuffle(T)
        if T == S: T = S[1:] + S[:1]
        sh.append(judge_bits(" ".join(T)))
    return sum(sh) / len(sh) - base
def entity_continuity(text):
    S = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if len(S) < 2: return float("nan")
    stop = {"the", "a", "an", "and", "then", "later", "after", "that", "in", "end", "he", "she", "it", "they", "his", "her", "was", "were", "of", "to", "at", "on", "with"}
    seen = set(); hits = 0
    for i, s in enumerate(S):
        w = {x.lower() for x in re.findall(r"[A-Za-z']+", s) if x.lower() not in stop and len(x) > 2}
        if i > 0 and (w & seen or re.search(r"\b(he|she|they|it|him|her|them|his|their)\b", s, re.I)): hits += 1
        seen |= w
    return hits / (len(S) - 1)


def judge_ctx(prefix, text):
    """F2: judge bits/word of text given a prefix (the story and the question)"""
    m, tok = _model(); p = tok.encode(prefix); t = tok.encode(text)
    if not t: return float("nan")
    p = p[-3000:]
    with torch.no_grad(): lp = torch.log_softmax(m(torch.tensor([p + t]), m.new_state())[0].float(), -1)
    bits = -sum(lp[len(p) + j - 1, x].item() for j, x in enumerate(t)) / math.log(2)
    return bits / max(1, len(re.findall(r"[A-Za-z']+", text)))
