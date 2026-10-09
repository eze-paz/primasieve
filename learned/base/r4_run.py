"""R4 runner: cut the fact neurons of a checkpoint and run every gate on the cut model, all from this directory
(immune to the shell's working directory). Run: python learned/base/r4_run.py ckpt_read3b.pth"""
import os, sys, json, re, io, contextlib
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
import torch
from rwkv7 import RWKV7, tokenizer
from ablate import recall
import cut_facts, eval_r3, b6_rwkv

ck = sys.argv[1]; cut = os.path.splitext(ck)[0] + "_cut.pth"
sys.argv = ["cut_facts.py", ck]; cut_facts.main()
lines = []
sys.argv = ["eval_r3.py", cut]; buf = io.StringIO()
with contextlib.redirect_stdout(buf): eval_r3.main()
lines += [l for l in buf.getvalue().splitlines() if l.startswith("R3")]
for extra in ([], ["--mismatch"]):
    sys.argv = ["b6_rwkv.py", cut] + extra; b6_rwkv.CK = cut; buf = io.StringIO()
    with contextlib.redirect_stdout(buf): b6_rwkv.main()
    lines += [l for l in buf.getvalue().splitlines() if l.startswith(("B6", "mismatch"))]
tok = tokenizer(); facts = json.load(open("facts_probe.json", encoding="utf-8"))
def qform(p):
    p = p.rstrip()
    for pre, q in (("The capital of", "What is the capital of"), ("The author of", "Who is the author of"), ("The currency of", "What is the currency of"),
                   ("The language spoken in", "What language is spoken in"), ("The composer of", "Who is the composer of"), ("The painter of", "Who is the painter of"),
                   ("The founder of", "Who is the founder of"), ("The chemical symbol for", "What is the chemical symbol for")):
        if p.startswith(pre):
            subj = re.sub(r"\s+(is|was|are|were)(\s+the)?$", "", p[len(pre):].strip()); return f"Q: {q} {subj}?\nA:"
    return f"Q: {p}?\nA:"
for c in (ck, cut):
    m = RWKV7.load(c); m.eval()
    lines.append(f"recall {c}: completion {recall(m, tok, facts):.2f} question-form {recall(m, tok, [(qform(p), g) for p, g in facts]):.2f}")
open(os.path.splitext(cut)[0] + "_eval.out", "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
