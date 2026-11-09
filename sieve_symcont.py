"""SYM entity continuity: for each arm of a generation file, the share of generated sentences that mention a prompt
referent (noun by word or pronoun group), and the share whose subject is a prompt referent (PARSE's tagger + parser).
Run: py -3.12 sieve_symcont.py GEN_JSON"""
import sys, json, numpy as np
exec(open("sieve_parse.py", encoding="utf-8").read().split("# ---- sanity")[0])
PRONG = {w: g for g, ws in dict(HE="he him his himself", SHE="she her hers herself", THEY="they them their theirs themselves", IT="it its itself", I="i me my mine myself", YOU="you your yours yourself", WE="we us our ours ourselves").items() for w in ws.split()}
def refs(words):
    tg, _ = tag(words); _, hd = parse(tg); out, subj = set(), set()
    for j, (w, t) in enumerate(zip(words, tg)):
        r = w if TAGS[t] in ("NOUN", "PROPN") else PRONG.get(w)
        if r is None: continue
        out.add(r); h = hd[j]
        if h > 0 and TAGS[tg[h - 1]] in ("VERB", "AUX") and j + 1 < h: subj.add(r)
    return out, subj
def split(text): return [x.split() for x in text.replace(" .", ".").split(". ") if x.strip(" .")]
G = json.load(open(sys.argv[1], encoding="utf-8")); R = {}
for arm in [k for k in G if not k.startswith("_")]:
    m = s_ = n = 0
    for g in G[arm]["gens"]:
        pr = set().union(*[refs(x)[0] for x in split(g["prompt"])] or [set()])
        for sent in split(g["text"]):
            o, su = refs(sent); n += 1; m += bool(o & pr); s_ += bool(su & pr)
    R[arm] = dict(sentences=n, mention_prompt_referent=round(m / max(n, 1), 4), subject_is_prompt_referent=round(s_ / max(n, 1), 4)); print(arm, R[arm], flush=True)
json.dump(R, open(sys.argv[1].replace("_gen.json", "_cont.json"), "w"), indent=1)
