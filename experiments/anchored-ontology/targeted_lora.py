# Does single-layer LoRA install a capability BEST at that capability's crystal depth?
# Train a rank-4 residual adapter at ONE layer (rest frozen) to make LFM output
# Yes/No for answerable/unanswerable questions (the uncertainty capability, whose
# READ crystal peaks at layer 8). Sweep the injection layer; if install accuracy
# peaks near 8 (or just before), crystal-localization tells you where to inject.
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM
torch.set_num_threads(10); torch.manual_seed(0)

MID = "LiquidAI/LFM2.5-350M"
tok = AutoTokenizer.from_pretrained(MID, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token = tok.eos_token
model = AutoModelForCausalLM.from_pretrained(MID, dtype=torch.float32, trust_remote_code=True).eval()
for p in model.parameters(): p.requires_grad_(False)
layers = model.model.layers; nL = len(layers); dim = model.config.hidden_size

KNOWN = ["What is the capital of France?","How many legs does a spider have?","Who wrote Romeo and Juliet?",
 "What gas do plants absorb?","Largest planet in the solar system?","Chemical symbol for gold?",
 "What is the largest ocean?","Currency of Japan?","How many days in a week?","What is 7 times 8?",
 "Who painted the Mona Lisa?","What organ pumps blood?","Capital of Italy?","What do bees make?",
 "How many continents are there?","Freezing point of water?","First US president?","What planet do we live on?"]
UNKNOWN = ["Capital of Zorbland?","Moons of planet Xelphar?","Population of Glimmerhold?","Atomic number of flarium?",
 "King of the Mplix Empire?","GDP of the nation Vandoria?","Currency of the Kappa Republic?","Height of Mount Brindle?",
 "Author of the book Vex Codex?","Capital of the Yolen Islands?","Length of the Fern River?","Leader of the Drome Federation?",
 "Population of Tril…are?","Ruler of Casterly Marches?","Depth of Lake Vunn?","Mass of the moon Qibb?",
 "Currency in the land of Espen?","Height of the Grix Tower?"]
CUE = "\nAnswerable (Yes/No):"
yes_id = tok(" Yes", add_special_tokens=False).input_ids[0]
no_id  = tok(" No", add_special_tokens=False).input_ids[0]

def batch(prompts):
    enc = tok([p + CUE for p in prompts], return_tensors="pt", padding=True)
    last = enc.attention_mask.sum(1) - 1                      # index of final real token
    return enc, last

def split(lst): return lst[:len(lst)-8], lst[len(lst)-8:]
ktr, kte = split(KNOWN); utr, ute = split(UNKNOWN)
tr_p = ktr + utr; tr_y = torch.tensor([yes_id]*len(ktr) + [no_id]*len(utr))
te_p = kte + ute; te_y = torch.tensor([yes_id]*len(kte) + [no_id]*len(ute))
tr_enc, tr_last = batch(tr_p); te_enc, te_last = batch(te_p)

class Adapter:
    def __init__(self):
        self.A = nn.Parameter(torch.randn(dim, 2) * 0.02); self.B = nn.Parameter(torch.zeros(2, dim))
    def hook(self, mod, inp, out):
        h = out[0] if isinstance(out, tuple) else out
        h = h + (h @ self.A) @ self.B
        return (h,) + out[1:] if isinstance(out, tuple) else h

def run_layer(j, steps=25):
    ad = Adapter(); opt = torch.optim.Adam([ad.A, ad.B], lr=1e-2)
    hnd = layers[j].register_forward_hook(ad.hook)
    try:
        for s in range(steps):
            logits = model(**tr_enc).logits
            sel = logits[torch.arange(len(tr_p)), tr_last]     # (N, vocab)
            loss = F.cross_entropy(sel[:, [no_id, yes_id]],
                                   (tr_y == yes_id).long())
            opt.zero_grad(); loss.backward(); opt.step()
        with torch.no_grad():
            sel = model(**te_enc).logits[torch.arange(len(te_p)), te_last]
            pred = sel[:, [no_id, yes_id]].argmax(1)
            acc = (pred == (te_y == yes_id).long()).float().mean().item()
    finally:
        hnd.remove()
    return acc

# baseline: no adapter
with torch.no_grad():
    sel = model(**te_enc).logits[torch.arange(len(te_p)), te_last]
    base = (sel[:, [no_id, yes_id]].argmax(1) == (te_y == yes_id).long()).float().mean().item()
print(f"cold baseline acc = {base:.2f}  (uncertainty READ-crystal peaks at layer 8/16)")
print("inject_layer  install_acc")
for j in range(0, nL):
    print(f"  {j:2d}          {run_layer(j):.2f}", flush=True)
