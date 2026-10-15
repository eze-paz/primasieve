"""R27 P5: the system's own network chooses among candidate wordings of each answer sentence (R27_prereg.md).
Run: py -3.12 r27_choose.py"""
import os, sys, re, json, math, random, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--threads", "4", "--groups-file", "r25_classes_wnx.json"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
torch, gw, unk2, _uni, _cnt, UNKG, vi = (R[k] for k in "torch gw unk2 _uni _cnt UNKG vi".split())
net = R["RNet"](); net.load_state_dict(torch.load("r25_ch.pt")); net.eval(); rnn = net.rnn
from r27_answer import sentence, PAST
BASE_OF = {v: k for k, v in PAST.items()}
def own_bits(s):
    w = [x.lower() for x in re.findall(r"[A-Za-z]+", s)]
    if len(w) < 2: return 99.0
    ids = torch.tensor([[vi.get(x, 0) for x in w]])
    with torch.no_grad(): lp = torch.log_softmax(net.out(net.out_ln(rnn(net.inp(net.emb(ids)), None)[0][0])), -1)
    b = 0.0
    for k in range(1, len(w)):
        g = gw(w[k]); b -= lp[k - 1, g].item() / math.log(2); b -= math.log2((_uni[w[k]] + 0.5) / _cnt[g]) if g != UNKG else -unk2(w[k])
    return b / (len(w) - 1)
PREP = {"at", "in", "on", "to", "into", "by", "near", "under", "behind", "from", "with"}
def candidates(s, a):
    out = {s}; body = s.rstrip(".")
    if a and a in body:
        rest = (body.replace(a, " ", 1)).split(); toks = body.split()
        out.add(" ".join(rest) + " " + a + ".")                                                   # answer at the end
        vpos = next((i for i, t in enumerate(rest) if t.lower() in BASE_OF or t.lower().endswith("ed")), None)
        if vpos is not None: out.add(" ".join(rest[:vpos + 1] + [a] + rest[vpos + 1:]) + ".")    # answer right after the verb
        if a.split()[0].lower() in PREP: out.add(body.replace(a, " ".join(a.split()[1:]), 1) + ".")   # without its preposition
    m = re.match(r"^((?:At|By|In|On|During) [^,]+), (.*)$", body)
    if m: out.add(m.group(2)[0].upper() + m.group(2)[1:] + " " + m.group(1)[0].lower() + m.group(1)[1:] + ".")   # un-fronted
    for p, b in BASE_OF.items():
        if re.search(rf"\b{p}\b", body): out.add(re.sub(rf"\b{p}\b", b, body, count=1) + ".")       # base form instead of past
    return [re.sub(r"\s+", " ", c).strip().replace(" .", ".") for c in out]
if __name__ == "__main__":
    from r27_fluency import judge_bits, sentence_form
    rows = [r for r in json.load(open("r27_p1_sentences.json", encoding="utf-8")) if r["s"] and r["story"]]
    random.Random(0).shuffle(rows); rows = rows[:300]
    chosen = []
    for r in rows:
        c = candidates(r["s"], r["a"]); best = min(c, key=own_bits); chosen.append(best)
    changed = sum(1 for r, c in zip(rows, chosen) if c != r["s"])
    j1 = st.mean(judge_bits(r["s"]) for r in rows); j2 = st.mean(judge_bits(c) for c in chosen)
    f1 = st.mean(sentence_form(r["s"]) for r in rows); f2 = st.mean(sentence_form(c) for c in chosen)
    print(f"P5 changed {changed} of {len(rows)} sentences; judge P1c {j1:.3f} -> own-model choice {j2:.3f}; form {f1:.3f} -> {f2:.3f}", flush=True)
    for r, c in list(zip(rows, chosen))[:40]:
        if c != r["s"]: print("  ", r["s"], "=>", c)
