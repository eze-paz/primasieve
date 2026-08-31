# Does the unknown-crystal work as a LIVE convergence signal for a retrieval loop?
# If real, providing the missing fact in-context (successful RAG) should COLLAPSE
# the crystal projection toward the known side; irrelevant context should leave
# it high (retrieval failed -> keep going). That collapse IS the convergence
# detector the mobilise-retrieve loop stops on.
import torch, torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM
torch.set_num_threads(10); torch.manual_seed(0)

KNOWN = ["What is the capital of France?","How many legs does a spider have?","Who wrote Romeo and Juliet?",
 "What gas do plants absorb?","Largest planet in the solar system?","Chemical symbol for gold?",
 "What is the largest ocean?","Currency of Japan?","How many days in a week?","What is 7 times 8?",
 "Who painted the Mona Lisa?","What organ pumps blood?"]
UNKNOWN = ["Capital of Zorbland?","Moons of planet Xelphar?","Population of Glimmerhold?",
 "Atomic number of flarium?","King of the Mplix Empire?","GDP of the nation Vandoria?",
 "Currency of the Kappa Republic?","Height of Mount Brindle?","Author of the book Vex Codex?",
 "Capital of the Yolen Islands?","Length of the Fern River?","Leader of the Drome Federation?"]
# each unanswerable item + the fabricated fact that answers it + an irrelevant fact
ITEMS = [
 ("What is the capital of Zorbland?","The capital of Zorbland is Kyten.","Bananas are yellow fruit."),
 ("How many moons does planet Xelphar have?","Planet Xelphar has seven moons.","The sky appears blue."),
 ("What is the population of Glimmerhold?","Glimmerhold has a population of two million.","Water boils at 100C."),
 ("What is the atomic number of flarium?","The atomic number of flarium is 118.","Cats are mammals."),
 ("Who is the king of the Mplix Empire?","The king of the Mplix Empire is Doran.","Grass is green."),
 ("What is the GDP of Vandoria?","The GDP of Vandoria is 40 billion.","Bread is made from flour."),
 ("What is the currency of the Kappa Republic?","The currency of the Kappa Republic is the vell.","Birds can fly."),
 ("How tall is Mount Brindle?","Mount Brindle is 3200 meters tall.","Ice is frozen water."),
 ("Who wrote the book Vex Codex?","The book Vex Codex was written by Lira Fenn.","The sun is a star."),
 ("What is the capital of the Yolen Islands?","The capital of the Yolen Islands is Marn.","Dogs bark."),
]

def run(model_id):
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32,
        output_hidden_states=True, trust_remote_code=True).eval()
    L = m.config.num_hidden_layers // 2
    def enc(ps):   # LAST token: state right before answering (after reading any provided fact),
        V = []     # avoids mean-pool contamination from extra nonce tokens in the provided fact
        with torch.no_grad():
            for p in ps: V.append(m(**tok(p, return_tensors="pt")).hidden_states[L][0][-1])
        return torch.stack(V)
    K, U = enc(KNOWN), enc(UNKNOWN)
    base = enc([q for q, _, _ in ITEMS])
    answered = enc([f"{a} {q}" for q, a, _ in ITEMS])         # successful retrieval
    irrel = enc([f"{r} {q}" for q, _, r in ITEMS])            # failed retrieval
    del m
    allv = torch.cat([K, U]); mu = allv.mean(0); sd = allv.std(0) + 1e-5
    z = lambda X: (X - mu) / sd
    cr = F.normalize(z(U).mean(0) - z(K).mean(0), dim=0)
    c = (z(K).mean(0) + z(U).mean(0)) / 2
    proj = lambda X: ((z(X) - c) @ cr)
    pk, pu = proj(K).mean().item(), proj(U).mean().item()
    print(f"\n=== {model_id} (layer {L}) ===")
    print(f"  reference: known={pk:+.2f}  unknown={pu:+.2f}  (crystal axis)")
    pb, pa, pi = proj(base).mean().item(), proj(answered).mean().item(), proj(irrel).mean().item()
    # normalize to 0=known,1=unknown for interpretability
    norm = lambda p: (p - pk) / (pu - pk + 1e-9)
    print(f"  unanswerable alone         proj={pb:+.2f}  (uncertainty={norm(pb):.2f})")
    print(f"  + ANSWER in context        proj={pa:+.2f}  (uncertainty={norm(pa):.2f})  <- should COLLAPSE")
    print(f"  + irrelevant context       proj={pi:+.2f}  (uncertainty={norm(pi):.2f})  <- should stay high")
    drop = norm(pb) - norm(pa); leak = norm(pb) - norm(pi)
    print(f"  answer collapses uncertainty by {drop:.2f}; irrelevant by {leak:.2f}  "
          f"-> {'CONVERGENCE SIGNAL WORKS' if drop > 0.3 and drop > leak + 0.2 else 'weak/unreliable signal'}")

run("LiquidAI/LFM2.5-350M")
run("Qwen/Qwen2.5-1.5B-Instruct")
