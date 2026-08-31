# Stage A: collect REAL activations from LFM2.5-350M (residual stream, mid layer).
# Saves (Ntok, dim) tensor for the SAE / selection tests. No ground truth exists
# on a real model, so downstream we measure sparsity + self-consistency, not recall.
import torch, sys
from transformers import AutoTokenizer, AutoModelForCausalLM
torch.set_num_threads(10); torch.manual_seed(0)

MID = "LiquidAI/LFM2.5-350M"
OUT = r"C:\Users\AEZEQU~1\AppData\Local\Temp\claude\C--Users-aezequiel-Desktop-AI-Projects-sandpie\dab889b3-1d18-4c60-a723-3aeeef24454a\scratchpad\lfm_acts.pt"

CORPUS = """The mitochondria produce ATP through oxidative phosphorylation in the cell.
Photosynthesis converts sunlight into chemical energy stored in glucose molecules.
The French Revolution began in 1789 and overthrew the monarchy.
Napoleon crowned himself emperor and reshaped the map of Europe.
To bake sourdough bread you must first cultivate a wild yeast starter.
Whisk the eggs and sugar until the mixture turns pale and fluffy.
The stock market fell sharply as investors feared rising interest rates.
Compound interest allows small investments to grow exponentially over decades.
A recursive function calls itself until it reaches a base case.
The compiler translates source code into machine instructions the CPU executes.
Gravity curves spacetime, bending the path of light around massive stars.
Quantum entanglement links two particles across arbitrary distances instantly.
The Amazon rainforest hosts millions of species yet shrinks every year.
Coral reefs bleach when ocean temperatures rise beyond a critical threshold.
She felt a wave of grief wash over her as the train pulled away.
His anger flared, then softened into a quiet, aching regret.
The orchestra swelled as the violins carried the melody upward.
Jazz improvisation blends structure with spontaneous melodic invention.
The Roman aqueducts carried fresh water across vast stone arches.
Ancient Egyptians embalmed their dead to preserve them for the afterlife.
Machine learning models learn patterns from large labeled datasets.
A neural network adjusts its weights by backpropagating the error gradient.
The immune system produces antibodies to neutralize invading pathogens.
Vaccines train the body to recognize a virus before real infection.
The judge instructed the jury to weigh only the admissible evidence.
Contract law requires an offer, acceptance, and consideration to bind.
Mountains form slowly as tectonic plates collide and crumple the crust.
Rivers carve canyons over millions of years of patient erosion.
The chef seared the scallops until a golden crust formed on each side.
Fermentation transforms sugar into alcohol through the action of yeast.
The poet used metaphor to compare memory to a fading photograph.
Every sonnet follows a strict rhyme scheme across fourteen lines.
Electrons occupy discrete energy levels around the atomic nucleus.
A catalyst lowers the activation energy without being consumed.
The general ordered a flanking maneuver to encircle the enemy.
Supply lines determined the outcome of many long military campaigns.
Interest rates set by the central bank ripple through the whole economy.
Inflation erodes the purchasing power of money held in cash.
The database indexes each row to speed up lookups on large tables.
A hash function maps arbitrary input to a fixed length digest.""".strip().split("\n")

# augment with real English prose from repo markdown to get enough tokens
import glob, os
extra = []
for f in glob.glob(r"C:\Users\aezequiel\.claude\projects\C--Users-aezequiel-Desktop-AI-Projects-sandpie\memory\*.md")[:60]:
    try:
        t = open(f, encoding="utf-8").read()
        for para in t.split("\n"):
            para = para.strip("-# *`[]")
            if len(para) > 60 and not para.startswith("http"):
                extra.append(para[:300])
    except Exception:
        pass
CORPUS = CORPUS + extra
print(f"corpus sentences: {len(CORPUS)}", flush=True)

tok = AutoTokenizer.from_pretrained(MID, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(MID, dtype=torch.float32,
        output_hidden_states=True, trust_remote_code=True).eval()
nlayers = model.config.num_hidden_layers
LAYER = nlayers // 2
print(f"layers={nlayers} hidden={model.config.hidden_size} using layer {LAYER}", flush=True)

chunks = []; total = 0; CAP = 12000
with torch.no_grad():
    for i, text in enumerate(CORPUS):
        ids = tok(text, return_tensors="pt", truncation=True, max_length=96)
        hs = model(**ids).hidden_states[LAYER][0]      # (seq, dim)
        chunks.append(hs); total += hs.shape[0]
        if i % 25 == 0: print(f"  {i}/{len(CORPUS)} tokens={total}", flush=True)
        if total >= CAP: break
X = torch.cat(chunks, 0)
torch.save({"X": X, "layer": LAYER, "dim": X.shape[1]}, OUT)
print(f"saved X {tuple(X.shape)}  mean-norm={X.norm(dim=1).mean():.2f}  to {OUT}")
