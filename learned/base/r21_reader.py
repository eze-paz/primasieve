"""R21: the learned reader -- the fine-tuned 0.4B maps (previous sentence, sentence) -> event lines, parsed into the
InducedWorld's exact-event dicts; the induced table from R20 is used as is.
Run: python learned/base/r21_reader.py [--ckpt ckpt_r21.pth] [--heldout N]   -> R21-a on held-out generator stories,
R21-b on val_timespace (learned reader -> induced world), results in r21_results.json"""
import os, sys, re, json, time, torch
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from rwkv7 import RWKV7, tokenizer
import r20_induce as RI
import worldstate as WS
from b6_rwkv import hit


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


class LearnedReader:
    def __init__(self, m, tok): self.m = m; self.tok = tok; self.last_agent = None; self.last_patient = None

    def lines(self, prev, sent):
        prompt = f"Text: {prev}\nSentence: {sent}\nEvents:"
        out = self.tok.decode(self.m.greedy(torch.tensor([self.tok.encode(prompt)]), 60, tok=self.tok)).strip().split("\n")[0]
        return out.strip()

    @staticmethod
    def parse(line):
        if line.strip() == "none": return []
        evs = []
        for part in line.split(";"):
            f = [x.strip() for x in part.split("|")]
            if len(f) != 5 or not f[0] or not f[1]: continue
            evs.append(dict(agent=f[0], verb=f[1], patient=None if f[2] == "-" else f[2], place=None if f[3] == "-" else f[3], rec=None if f[4] == "-" else f[4], status="realis"))
        return evs

    def cache(self, text):
        """(sentence, events) per sentence, as InducedWorld.read expects"""
        sents = [x.strip() for x in WS.SENT.split(text) if x.strip()]; out = []
        for k, s in enumerate(sents):
            out.append((s, self.parse(self.lines(" ".join(sents[:k]) if k else "(start)", s))))
        return out


def main():
    ck = arg("--ckpt", "ckpt_r21.pth"); m = RWKV7.load(os.path.join(HERE, ck)); m.eval(); tok = tokenizer(); LR = LearnedReader(m, tok)
    table = json.load(open(os.path.join(HERE, "r20_joint_table.json")))
    # R21-a: held-out generator sentences, exact line match
    held = json.load(open(os.path.join(HERE, "r21_heldout.json"), encoding="utf-8"))[:arg("--heldout", 40)]
    from r21_data import pairs
    ok = n = 0; shown = 0; T0 = time.time()
    for s in held:
        for x in pairs(s):
            got = LR.lines(x["prev"], x["sent"]); n += 1; ok += (got == x["answer"])
            if got != x["answer"] and shown < 8: shown += 1; print(f"  MISS: {x['sent']}\n     want {x['answer']}\n     got  {got}", flush=True)
    print(f"R21-a: exact event lines on held-out generator sentences {ok}/{n} = {ok / max(1, n):.2f} (bar >= 0.80) [{(time.time() - T0) / 60:.1f} min]", flush=True)
    # R21-b: val_timespace, learned reader -> induced world
    val = json.load(open(os.path.join(HERE, "val_timespace.json"), encoding="utf-8"))["stories"]; matched = right = q_n = 0
    for s in val:
        c = LR.cache(s["text"]); print("  events:", [(e["agent"], e["verb"], e["patient"], e["place"]) for _, evs in c for e in evs], flush=True)
        W = RI.InducedWorld(LR, table); W.read(s["text"], c)
        for q, g in s["qs"]:
            q_n += 1; a = W.ask(q)
            if a is not None: matched += 1; right += hit(a, g)
            if a is not None and not hit(a, g): print(f"  XX {q} | gold {g} | got {a}", flush=True)
    print(f"R21-b: learned reader -> induced world on val_timespace: matched {matched}/{q_n}, right {right} (precision {right / max(1, matched):.2f}); bar >= 18 at >= 0.85 (hand reader: 21 at 0.90)")
    json.dump(dict(ckpt=ck, r21a=(ok, n), r21b=(matched, right, q_n)), open(os.path.join(HERE, "r21_results.json"), "w"))


if __name__ == "__main__":
    main()
