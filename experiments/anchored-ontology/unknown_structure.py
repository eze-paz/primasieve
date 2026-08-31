# Size & structure of the "unknown/uncertainty" crystal, LFM-350M vs Qwen-1.5B.
# For the tiny-model+RAG vision: is the crystal SMALL, LOW-DIM, and consistent?
#   depth      : per-layer held-out AUC -> where the crystal lives, how strong
#   dimension  : participation ratio of the crystal vector (localized vs spread)
#   one-or-many: cosine between subtype-specific unknown directions
#   magnitude  : ||crystal|| relative to activation scale
#   scaling    : does 1.5B have a bigger crystal than 350M, or the same size?
import torch, torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM
torch.set_num_threads(10); torch.manual_seed(0)

KNOWN = ["What is the capital of France?","How many legs does a spider have?",
 "What color is the sky on a clear day?","What is 7 times 8?","Who wrote Romeo and Juliet?",
 "What gas do plants absorb?","Freezing point of water in Celsius?","Largest planet in the solar system?",
 "What language is spoken in Brazil?","How many days in a week?","Chemical symbol for gold?",
 "What is the largest ocean?","Who painted the Mona Lisa?","Square root of 81?",
 "What organ pumps blood?","Currency of Japan?","How many continents are there?",
 "What is the boiling point of water?","Who was the first US president?","What is the speed of light roughly?",
 "What planet do we live on?","How many sides does a triangle have?","What is the capital of Italy?","What do bees make?"]
SUB = {  # subtypes of "unknown"
 "nonexistent":["Capital of Zorbland?","Moons of planet Xelphar?","Population of Glimmerhold?",
   "Atomic number of flarium?","GDP of the nation Vandoria?","King of the Mplix Empire?"],
 "personal":["What did I eat for breakfast?","My grandmother's phone number?","How many thoughts did I have yesterday?",
   "The secret password to my email?","What am I wearing right now?","What is my middle name?"],
 "future":["Who wins the 2088 championship?","Weather on Mars in 3000 years?","Stock price of Apple in 2075?",
   "Who is president in 2140?","What will I dream tonight?","Next winning lottery numbers?"],
 "nonsense":["What color is the number seven?","How heavy is the concept of justice?","What does Tuesday smell like?",
   "How loud is the color blue?","What is the square root of happiness?","How fast does silence travel?"],
}
UNKNOWN = [p for ps in SUB.values() for p in ps]

def collect(model_id):
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32,
        output_hidden_states=True, trust_remote_code=True).eval()
    nL = m.config.num_hidden_layers; dim = m.config.hidden_size
    def enc(ps):
        per_layer = [[] for _ in range(nL + 1)]
        with torch.no_grad():
            for p in ps:
                hs = m(**tok(p, return_tensors="pt")).hidden_states
                for l in range(nL + 1): per_layer[l].append(hs[l][0].mean(0))
        return [torch.stack(x) for x in per_layer]
    K = enc(KNOWN); U = enc(UNKNOWN); subs = {k: enc(v) for k, v in SUB.items()}
    del m
    return K, U, subs, nL, dim

def auc(u, k):
    return (u.unsqueeze(1) > k.unsqueeze(0)).float().mean().item()

def analyze(model_id):
    K, U, subs, nL, dim = collect(model_id)
    print(f"\n=== {model_id}  layers={nL} dim={dim} ===", flush=True)
    nk = len(KNOWN); nu = len(UNKNOWN); ktr, utr = nk - 8, nu - 8
    best = (-1, 0)
    curve = []
    for l in range(nL + 1):
        allv = torch.cat([K[l], U[l]]); mu = allv.mean(0); sd = allv.std(0) + 1e-5
        k = (K[l] - mu) / sd; u = (U[l] - mu) / sd
        cr = F.normalize(u[:utr].mean(0) - k[:ktr].mean(0), dim=0)
        c = (k[:ktr].mean(0) + u[:utr].mean(0)) / 2
        a = auc((u[utr:] - c) @ cr, (k[ktr:] - c) @ cr)
        curve.append(a)
        if a > best[1]: best = (l, a)
    L = best[0]
    print(f"  layer-AUC by depth (frac): " + " ".join(f"{a:.2f}" for a in curve))
    print(f"  best layer {L}/{nL} (depth {L/nL:.0%})  AUC={best[1]:.2f}")
    # structure at best layer
    allv = torch.cat([K[L], U[L]]); mu = allv.mean(0); sd = allv.std(0) + 1e-5
    kL = (K[L] - mu) / sd; uL = (U[L] - mu) / sd
    cr = F.normalize(uL.mean(0) - kL.mean(0), dim=0)
    pr = (cr.pow(2).sum() ** 2 / cr.pow(4).sum()).item()      # participation ratio
    mag = (uL.mean(0) - kL.mean(0)).norm().item() / (allv.std(0).mean().item() + 1e-9)
    print(f"  crystal participation ratio = {pr:.0f}/{dim} dims ({100*pr/dim:.1f}% -> {'LOCALIZED' if pr/dim<0.15 else 'distributed'})")
    print(f"  crystal magnitude (std-units) = {mag:.2f}")
    # one crystal or many: subtype directions
    names = list(subs.keys())
    dirs = []
    for nm in names:
        s = subs[nm][L]; sN = (s - mu) / sd
        dirs.append(F.normalize(sN.mean(0) - kL.mean(0), dim=0))
    print(f"  subtype-direction cosines (1.0 = one unified crystal):")
    for i in range(len(names)):
        row = "  ".join(f"{names[j][:5]}:{(dirs[i]@dirs[j]).item():+.2f}" for j in range(len(names)))
        print(f"    {names[i]:12s} {row}")
    offdiag = [(dirs[i]@dirs[j]).item() for i in range(len(names)) for j in range(len(names)) if i<j]
    print(f"  mean subtype cosine = {sum(offdiag)/len(offdiag):.2f}  "
          f"({'UNIFIED single crystal' if sum(offdiag)/len(offdiag)>0.5 else 'MULTIPLE distinct crystals'})")

analyze("LiquidAI/LFM2.5-350M")
analyze("Qwen/Qwen2.5-1.5B-Instruct")
