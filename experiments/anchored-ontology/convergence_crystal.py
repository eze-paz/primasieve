# #2 purpose-built CONVERGENCE crystal: an INFO-SUFFICIENCY detector (not the
# unfamiliarity gate). Contrast:  (question + SUFFICIENT context) vs
# (question + INSUFFICIENT/irrelevant context).  If a direction separates these,
# it is the stop-signal for a mobilise-retrieve loop: fire retrieval while the
# projection says 'insufficient', stop when it flips to 'sufficient'.
# Crucially the SAME question appears on both sides -> the crystal must encode
# 'do I have what I need', not 'is the topic familiar'.
import torch, torch.nn.functional as F, random
from transformers import AutoTokenizer, AutoModelForCausalLM
torch.set_num_threads(10); torch.manual_seed(0); rng = random.Random(0)

# (question, fact-that-answers-it, irrelevant-fact) over made-up entities
ITEMS = [
 ("What is the capital of Zorbland?","The capital of Zorbland is Kyten.","Zorbland has mild winters."),
 ("How many moons does Xelphar have?","Xelphar has seven moons.","Xelphar orbits a red star."),
 ("What is the population of Glimmerhold?","Glimmerhold has two million people.","Glimmerhold was founded long ago."),
 ("What is the atomic number of flarium?","Flarium has atomic number 118.","Flarium is a silvery metal."),
 ("Who is the king of the Mplix Empire?","The king of the Mplix Empire is Doran.","The Mplix Empire is vast."),
 ("What is the GDP of Vandoria?","Vandoria's GDP is 40 billion.","Vandoria exports grain."),
 ("What is the currency of the Kappa Republic?","The Kappa Republic uses the vell.","The Kappa Republic is coastal."),
 ("How tall is Mount Brindle?","Mount Brindle is 3200 meters tall.","Mount Brindle is often cloudy."),
 ("Who wrote the book Vex Codex?","Vex Codex was written by Lira Fenn.","Vex Codex is very long."),
 ("What is the capital of the Yolen Islands?","The capital of the Yolen Islands is Marn.","The Yolen Islands are tropical."),
 ("How long is the Fern River?","The Fern River is 900 kilometers long.","The Fern River has many fish."),
 ("Who leads the Drome Federation?","The Drome Federation is led by Chancellor Vael.","The Drome Federation is old."),
 ("What is the mass of moon Qibb?","Moon Qibb has a mass of 3e21 kilograms.","Moon Qibb is grey."),
 ("What is the depth of Lake Vunn?","Lake Vunn is 400 meters deep.","Lake Vunn freezes in winter."),
 ("How tall is the Grix Tower?","The Grix Tower is 610 meters tall.","The Grix Tower is famous."),
 ("What is the currency of Espen?","Espen uses the dral.","Espen has a warm climate."),
]

def run(model_id):
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32,
        output_hidden_states=True, trust_remote_code=True).eval()
    nL = m.config.num_hidden_layers
    def enc(ps):
        per = [[] for _ in range(nL + 1)]
        with torch.no_grad():
            for p in ps:
                hs = m(**tok(p, return_tensors="pt")).hidden_states
                for l in range(nL + 1): per[l].append(hs[l][0][-1])   # last token (right before answering)
        return [torch.stack(x) for x in per]
    suf = enc([f"{f} {q}" for q, f, _ in ITEMS])              # sufficient context
    ins = enc([f"{r} {q}" for q, _, r in ITEMS])              # insufficient (topical but no answer)
    del m
    n = len(ITEMS); tr = n - 6
    best = (0, 0.5)
    for l in range(nL + 1):
        allv = torch.cat([suf[l], ins[l]]); mu = allv.mean(0); sd = allv.std(0) + 1e-5
        s = (suf[l] - mu) / sd; i = (ins[l] - mu) / sd
        cr = F.normalize(s[:tr].mean(0) - i[:tr].mean(0), dim=0)  # sufficient direction
        c = (s[:tr].mean(0) + i[:tr].mean(0)) / 2
        ps = (s[tr:] - c) @ cr; pi = (i[tr:] - c) @ cr
        auc = (ps.unsqueeze(1) > pi.unsqueeze(0)).float().mean().item()
        if auc > best[1]: best = (l, auc)
    print(f"{model_id}: best INFO-SUFFICIENCY crystal AUC={best[1]:.2f} at layer {best[0]}/{nL} "
          f"-> {'CONVERGENCE SIGNAL WORKS' if best[1]>0.75 else 'weak'}")

run("LiquidAI/LFM2.5-350M")
run("Qwen/Qwen2.5-1.5B-Instruct")
