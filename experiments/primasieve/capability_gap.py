"""Capability-gap test: a task where the BIG model's features should beat the
SMALL model's (truth classification). Does the stitch transplant the big model's
EXTRA capability, or is it BOUNDED by the small model's features?

  native_small = head trained+tested on SMALL features   (small's ceiling)
  native_big   = head trained+tested on BIG features      (big's ceiling)
  transplant   = BIG-trained head on stitch(SMALL feats)  (derived from SMALL feats)

Data-processing inequality predicts: transplant ~ native_small (NOT native_big),
because anything computed from the small model's features can't beat what those
features contain about truth. If native_big >> native_small and transplant stays
near native_small -> bound CONFIRMED.
"""
import time, random as _r
import torch, torch.nn as nn, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10); torch.manual_seed(0); rng = _r.Random(0)

# ---- truth dataset (statement, 1=true / 0=false) ----
CAPS = {"France":"Paris","Japan":"Tokyo","Germany":"Berlin","Italy":"Rome","Spain":"Madrid",
        "Russia":"Moscow","China":"Beijing","Egypt":"Cairo","Canada":"Ottawa","Brazil":"Brasilia",
        "Kazakhstan":"Astana","Bhutan":"Thimphu","Mongolia":"Ulaanbaatar","Kyrgyzstan":"Bishkek",
        "Turkmenistan":"Ashgabat","Suriname":"Paramaribo","Eritrea":"Asmara","Laos":"Vientiane",
        "Malawi":"Lilongwe","Botswana":"Gaborone","Lesotho":"Maseru","Guyana":"Georgetown",
        "Belize":"Belmopan","Moldova":"Chisinau","Armenia":"Yerevan","Georgia":"Tbilisi",
        "Nepal":"Kathmandu","Oman":"Muscat","Zambia":"Lusaka","Rwanda":"Kigali"}
PAIRS = [
    ("Water is composed of hydrogen and oxygen.", "Water is composed of nitrogen and oxygen."),
    ("The Earth orbits the Sun.", "The Sun orbits the Earth."),
    ("Humans have 46 chromosomes.", "Humans have 12 chromosomes."),
    ("Light travels faster than sound.", "Sound travels faster than light."),
    ("The heart pumps blood.", "The liver pumps blood."),
    ("Oxygen is a gas at room temperature.", "Oxygen is a solid at room temperature."),
    ("The Pacific is the largest ocean.", "The Arctic is the largest ocean."),
    ("Photosynthesis occurs in plants.", "Photosynthesis occurs in rocks."),
    ("A triangle has three sides.", "A triangle has five sides."),
    ("7 is a prime number.", "8 is a prime number."),
    ("A dozen means twelve.", "A dozen means twenty."),
    ("Ice is frozen water.", "Ice is frozen oxygen."),
    ("The Sun is a star.", "The Sun is a planet."),
    ("Bats are mammals.", "Bats are reptiles."),
    ("World War II ended in 1945.", "World War II ended in 1975."),
    ("The Great Wall is in China.", "The Great Wall is in Peru."),
    ("Gold is a metal.", "Gold is a gas."),
    ("Spiders have eight legs.", "Spiders have six legs."),
    ("The Amazon is a river.", "The Amazon is a mountain."),
    ("Shakespeare wrote Hamlet.", "Newton wrote Hamlet."),
]
def build():
    d = []
    for c, cap in CAPS.items():
        d.append((f"The capital of {c} is {cap}.", 1))
        wrong = rng.choice([v for k, v in CAPS.items() if k != c])
        d.append((f"The capital of {c} is {wrong}.", 0))
    for t, f in PAIRS:
        d.append((t, 1)); d.append((f, 0))
    rng.shuffle(d); return d
DATA = build()
texts = [s for s, _ in DATA]; Y = torch.tensor([y for _, y in DATA])
print(f"dataset: {len(DATA)} statements ({int(Y.sum())} true / {len(Y)-int(Y.sum())} false)", flush=True)

def encode(mid):
    print(f"  embedding {mid} ...", flush=True); t0 = time.time()
    tok = AutoTokenizer.from_pretrained(mid, trust_remote_code=True)
    if tok.pad_token is None: tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(mid, dtype=torch.float32,
                                             output_hidden_states=True, trust_remote_code=True).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), 8):
            ids = tok(texts[i:i+8], return_tensors="pt", padding=True, truncation=True, max_length=64)
            h = ids.attention_mask.unsqueeze(-1).float() * m(**ids).hidden_states[-1]
            out.append(h.sum(1) / ids.attention_mask.sum(1, keepdim=True).clamp(min=1))
    del m; print(f"    done {time.time()-t0:.0f}s dim={out[0].shape[1]}", flush=True)
    return torch.cat(out)

BIG = encode("Qwen/Qwen2.5-1.5B-Instruct")
SM  = encode("LiquidAI/LFM2.5-350M")
n = len(Y); ntr = int(0.75 * n); Yr, Yt = Y[:ntr], Y[ntr:]

def train_head(X):
    mu, sd = X[:ntr].mean(0), X[:ntr].std(0) + 1e-6
    h = nn.Sequential(nn.Linear(X.shape[1], 128), nn.GELU(), nn.Dropout(0.1), nn.Linear(128, 2))
    o = torch.optim.AdamW(h.parameters(), lr=1e-3, weight_decay=1e-2); Xn = (X[:ntr]-mu)/sd
    for _ in range(500):
        i = torch.randperm(ntr)[:64]; loss = F.cross_entropy(h(Xn[i]), Yr[i])
        o.zero_grad(); loss.backward(); o.step()
    h.eval(); return h, mu, sd
def ev(h, mu, sd, X):
    with torch.no_grad(): return (h((X[ntr:]-mu)/sd).argmax(-1) == Yt).float().mean().item()

hs, mus, sds = train_head(SM); native_small = ev(hs, mus, sds, SM)
hb, mub, sdb = train_head(BIG); native_big = ev(hb, mub, sdb, BIG)
# stitch SMALL -> BIG, apply BIG head to stitched small feats
def aug(X): return torch.cat([X, torch.ones(len(X),1)],1)
W = torch.linalg.lstsq(aug(SM[:ntr]), BIG[:ntr]).solution
BIG_from_SM = aug(SM) @ W
transplant = ev(hb, mub, sdb, BIG_from_SM)

print("\n" + "=" * 60)
print("CAPABILITY-GAP: does the stitch transplant EXTRA capability?")
print("=" * 60)
print(f"  native_small (head on LFM-350M feats)  : {native_small:.3f}")
print(f"  native_big   (head on Qwen-1.5B feats) : {native_big:.3f}")
print(f"  TRANSPLANT   (big head on stitch(small)): {transplant:.3f}")
print("=" * 60)
gap = native_big - native_small
print(f"  capability gap (big - small): {gap:+.3f}")
print(f"  transplant tracks: {'SMALL (bound CONFIRMED)' if abs(transplant-native_small) < abs(transplant-native_big) else 'BIG (bound VIOLATED!)'}")
