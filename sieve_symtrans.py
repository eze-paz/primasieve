"""SYM2: how human book text moves its subject between sentences (Centering-style), with SYM's reader.
For each sentence after the first, its subject referent is classified: CONTINUE (= the most salient referent so far),
SHIFT (another referent already in the discourse state), NEW (a new referent or no subject). MT held-out text,
passages away from the bench prompts. Run: py -3.12 sieve_symtrans.py"""
import json, numpy as np
exec(open("sieve_parse.py", encoding="utf-8").read().split("# ---- sanity")[0])
PRONG = {w: g for g, ws in dict(HE="he him his himself", SHE="she her hers herself", THEY="they them their theirs themselves", IT="it its itself", I="i me my mine myself", YOU="you your yours yourself", WE="we us our ours ourselves").items() for w in ws.split()}
z = np.load("mtest/books_data.npz"); S = z["S"]; ntr = int(z["ntr"]); vw = [str(w) for w in z["vw"]]; ev = S[ntr:]
def sents_of(ids):
    out, cur = [], []
    for i in ids:
        if i == 0:
            if cur: out.append(cur)
            cur = []
        else: cur.append(vw[i] if i < len(vw) else "<unk>")
    return out
st = np.nonzero((ev[1:-300] != 0) & (ev[:-301] == 0))[0] + 1; st = st[np.linspace(len(st) // 2, len(st) - 1, 400).astype(int)]   # second half of the eval text
C = dict(CONTINUE=0, SHIFT=0, NEW=0)
for s0 in st:
    ss = sents_of(ev[s0:s0 + 150])[:-1]; sal = {}
    for k, ws in enumerate(ss):
        tg, _ = tag(ws); _, hd = parse(tg); subj = None; got = {}
        for j, (w, t) in enumerate(zip(ws, tg)):
            r = w if TAGS[t] in ("NOUN", "PROPN") else PRONG.get(w)
            if r is None: continue
            h = hd[j]; role = (3.0 if j + 1 < h else 2.0) if h > 0 and TAGS[tg[h - 1]] in ("VERB", "AUX") else 1.0
            got[r] = got.get(r, 0.0) + role
            if role == 3.0 and subj is None: subj = r
        if k > 0 and sal:
            top = max(sal, key=lambda r: sal[r]); C["CONTINUE" if subj == top else "SHIFT" if subj in sal else "NEW"] += 1
        for r in sal: sal[r] *= 0.5
        for r, v in got.items(): sal[r] = sal.get(r, 0.0) + v
n = sum(C.values()); R = {k: round(v / n, 4) for k, v in C.items()}; R["transitions"] = n; print("human subject transitions", R); json.dump(R, open("sieve_symtrans.json", "w"), indent=1)
