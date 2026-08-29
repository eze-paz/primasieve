"""Reasoning-crystal library with a two-tier registry — the PoC of the whole
architecture. Ties together every result from this session:

  TIER 1 (inside): labeled OPERATOR crystals. Each is a tiny net trained to GROK
    one reasoning operation, VERIFIED by exact-match on held-out operands (grok =
    generalizes, not memorizes). The label registry = the skill index.
    -> skill-void = query needs an operator NOT in the registry.
  TIER 2 (outside): a FACT store (retrieval). -> fact-void = entity not in store.

  CONTROLLER: parse query (op, x, y) -> check operator exists (else skill-void) ->
    retrieve operand facts (else fact-void) -> run the operator crystal -> answer.
    On either void it REFUSES HONESTLY instead of confidently lying.

  Demonstrated: (1) crystals grok, (2) correct answers on in-library+known-fact
  queries, (3) honest refusal on both void types where a naive model lies,
  (4) LEARNING MODE: ingest a fact (no weight update) and crystallize a NEW
  operator (targeted seed block) -> previously-void queries become answerable.
"""
import random
import torch, torch.nn as nn, torch.nn.functional as F

torch.set_num_threads(1); torch.manual_seed(0)
A = 12                      # value range operators work over (0..A-1)

# ---------------- TIER 1: operator crystals ----------------
class Crystal(nn.Module):
    def __init__(self, n_out, d=32):
        super().__init__()
        self.ea = nn.Embedding(A, d); self.eb = nn.Embedding(A, d)
        self.net = nn.Sequential(nn.Linear(2*d, 64), nn.GELU(), nn.Linear(64, 64), nn.GELU(), nn.Linear(64, n_out))
    def forward(self, a, b):
        return self.net(torch.cat([self.ea(a), self.eb(b)], -1))

# operator semantics (ground truth) + output arity
OPS = {
    "greater": (lambda a, b: int(a > b), 2),
    "same":    (lambda a, b: int(a == b), 2),
    "summod":  (lambda a, b: (a + b) % A, A),
}

def crystallize(fn, n_out, seed=0, steps=6000, wd=0.5):
    """Train a crystal on 60% of (a,b) pairs; VERIFY grok on the held-out 40%.
    Heavy weight decay (wd) is the grokking lever: it pushes memorization ->
    generalization (Nanda 2023). Low wd stalls in the memorization phase."""
    rng = random.Random(seed)
    allp = [(a, b) for a in range(A) for b in range(A)]
    rng.shuffle(allp); ntr = int(0.6 * len(allp))
    tr, te = allp[:ntr], allp[ntr:]
    torch.manual_seed(seed)
    m = Crystal(n_out)
    opt = torch.optim.AdamW(m.parameters(), lr=3e-3, weight_decay=wd)
    ta = torch.tensor([p[0] for p in tr]); tb = torch.tensor([p[1] for p in tr])
    ty = torch.tensor([fn(*p) for p in tr])
    for _ in range(steps):
        i = torch.randint(0, len(tr), (128,))
        loss = F.cross_entropy(m(ta[i], tb[i]), ty[i]); opt.zero_grad(); loss.backward(); opt.step()
    with torch.no_grad():
        xa = torch.tensor([p[0] for p in te]); xb = torch.tensor([p[1] for p in te])
        xy = torch.tensor([fn(*p) for p in te])
        grok = (m(xa, xb).argmax(-1) == xy).float().mean().item()
    return m, grok

# ---------------- system ----------------
class ReasoningSystem:
    def __init__(self):
        self.registry = {}          # tier 1: operator crystals (labeled)
        self.facts = {}             # tier 2: fact store (entity -> value)
    def add_operator(self, name, crystal, n_out):
        self.registry[name] = (crystal, n_out)
    def add_fact(self, entity, value):
        self.facts[entity] = value
    def answer(self, op, x, y):
        # skill-void?
        if op not in self.registry:
            return ("refuse", f"skill-void: no crystal for '{op}'")
        # fact-void?
        miss = [e for e in (x, y) if e not in self.facts]
        if miss:
            return ("refuse", f"fact-void: unknown entity {miss}")
        crystal, _ = self.registry[op]
        va, vb = self.facts[x], self.facts[y]
        with torch.no_grad():
            pred = crystal(torch.tensor([va]), torch.tensor([vb])).argmax(-1).item()
        return ("answer", pred)

# naive baseline: always answers (no void checks) using a default op -> lies in the void
class NaiveModel:
    def __init__(self, sys): self.sys = sys
    def answer(self, op, x, y):
        # pretends: unknown op -> guess 'greater'; unknown entity -> value 0
        crystal, _ = self.sys.registry.get(op, next(iter(self.sys.registry.values())))
        va = self.sys.facts.get(x, 0); vb = self.sys.facts.get(y, 0)
        with torch.no_grad():
            return crystal(torch.tensor([va]), torch.tensor([vb])).argmax(-1).item()

# ---------------- build ----------------
print("="*68); print("TIER 1: crystallizing reasoning operators (grok = held-out exact)"); print("="*68)
sys = ReasoningSystem()
for name, (fn, n_out) in OPS.items():
    c, grok = crystallize(fn, n_out)
    sys.add_operator(name, c, n_out)
    print(f"  operator '{name:8}' grok (held-out unseen operands): {grok:.3f}")

# tier 2: fact store — 30 known entities
rng = random.Random(1)
KNOWN = list(range(30))
for e in KNOWN: sys.add_fact(e, rng.randrange(A))
print(f"\nTIER 2: fact store loaded with {len(sys.facts)} entities")

# ---------------- evaluate ----------------
def truth(op, x, y): return OPS[op][0](sys.facts.get(x, -1), sys.facts.get(y, -1))
naive = NaiveModel(sys)

qs_valid, qs_skill, qs_fact = [], [], []
for _ in range(300):
    x, y = rng.sample(KNOWN, 2)
    qs_valid.append((rng.choice(list(OPS)), x, y))          # answerable + checkable
    qs_skill.append(("product", x, y))                       # op NOT crystallized
    u = rng.randrange(30, 45)                                # entity NOT in store
    qs_fact.append((rng.choice(list(OPS)), u, rng.choice(KNOWN)))

def score(qs, kind):
    ans = refuse = correct = lies = 0
    for op, x, y in qs:
        tag, out = sys.answer(op, x, y)
        if tag == "answer":
            ans += 1
            if out == truth(op, x, y): correct += 1
        else:
            refuse += 1
        # naive baseline: always answers -> count confident lies on void
        nout = naive.answer(op, x, y)
        if kind != "valid":
            if nout != (truth(op, x, y) if kind == "fact" and op in OPS else -999):
                lies += 1
    return ans, refuse, correct, lies

print("\n"+"="*68); print("EVALUATION: two-tier system vs naive always-answer model"); print("="*68)
a, r, c, _ = score(qs_valid, "valid")
print(f"  VALID queries (op in library, facts known):")
print(f"    answered {a}/{len(qs_valid)}, correct {c}/{a} ({100*c/max(a,1):.0f}%)  <- crystals compute it")
a, r, c, lies = score(qs_skill, "skill")
print(f"  SKILL-VOID queries (operator 'product' not crystallized):")
print(f"    system: refused {r}/{len(qs_skill)} honestly  |  naive model: {lies} confident lies")
a, r, c, lies = score(qs_fact, "fact")
print(f"  FACT-VOID queries (entity not in store):")
print(f"    system: refused {r}/{len(qs_fact)} honestly  |  naive model: {lies} confident answers on unknown facts")

# ---------------- LEARNING MODE ----------------
print("\n"+"="*68); print("LEARNING MODE (grow without weight updates / with targeted crystals)"); print("="*68)
# (a) fact-void -> ingest a fact (NO weight update)
q = ("greater", 99, 5)
print(f"  query {q}: {sys.answer(*q)}")
sys.add_fact(99, 7)                                          # teacher provides the fact
print(f"  -> ingested fact(99)=7 into store (no weight update)")
print(f"  query {q} again: {sys.answer(*q)}  (truth={OPS['greater'][0](7, sys.facts[5])})")
# (b) skill-void -> crystallize a NEW operator on the fly (seed block)
q = ("product", 3, 6)
print(f"\n  query {q}: {sys.answer(*q)}")
prod_fn = lambda a, b: (a * b) % A
newc, grok = crystallize(prod_fn, A, seed=1)
sys.add_operator("product", newc, A)
print(f"  -> crystallized NEW operator 'product' (grok={grok:.3f}), added to registry")
tag, out = sys.answer(*q)
print(f"  query {q} again: ({tag}, {out})  (truth={prod_fn(sys.facts[3], sys.facts[6])})")
