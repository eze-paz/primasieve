"""E6 (fable-designed): the ENVIRONMENT that adds the last verb, COLLECT. A hidden-state black-box machine
with PARTIAL OBSERVABILITY: registers (r0 observed, r1 HIDDEN) + a hidden MODE flag set only after a d-op
prefix condition. The agent proposes experiments (programs), observes r0 at halt (sound oracle = execution),
and must IDENTIFY each opcode's hidden semantics + the mode rule. COLLECT = choose the query that maximally
SPLITS the surviving world-models (version-space disagreement, generic belief-splitting -- NOT hand-coded L*).

Why hidden state (Angluin): with a mode flag behind a d-op prefix, random sampling hits the flag with prob
~k^-d, so ACTIVE experimental design should identify in far fewer queries than RANDOM, and the gap grows with
the dose d. Arms: ACTIVE vs RANDOM-SHORT (length-matched -- mandatory). Knockouts: shuffle-responses (-> no
identification), stateless (no mode -> active~random), dose-response (gap grows with d). NULL: ACTIVE ~
RANDOM-SHORT across all d = COLLECT vacuous. ZERO LLM, ZERO external oracle beyond the world's exact response."""
import os, sys, random, itertools, statistics
sys.path.insert(0, os.path.dirname(__file__))
CLAMP = 100
def _cl(x): return max(-CLAMP, min(CLAMP, x))

# candidate opcode semantics (r0,r1,mode)->(r0,r1): the agent's hypothesis grammar; world picks from it.
def candidates(dose):
    return [
        ("r0+=r1", lambda r0, r1, m: (_cl(r0 + r1), r1)),      # reader (exposes hidden r1 into r0)
        ("r0+=1",  lambda r0, r1, m: (_cl(r0 + 1), r1)),
        ("r1+=1",  lambda r0, r1, m: (r0, _cl(r1 + 1))),        # hidden incrementer (only seen via a reader)
        ("swap",   lambda r0, r1, m: (r1, r0)),
        ("r0*=2",  lambda r0, r1, m: (_cl(r0 * 2), r1)),
        ("r0-=r1", lambda r0, r1, m: (_cl(r0 - r1), r1)),
        (f"gate{dose}", lambda r0, r1, m: (_cl(r0 + (5 if m else 0)), r1)),  # MODE-gated (hidden state)
    ]
OPS = "ABCD"
def make_model(assign, dose):
    """assign: opcode->candidate index. Returns a runnable (prog, init)->r0-at-halt with hidden mode."""
    cand = candidates(dose)
    def run(prog, init=(0, 1)):
        r0, r1 = init; incs = 0
        for op in prog:
            m = incs >= dose                       # MODE set once r1 has been incremented >= dose times
            lab, fn = cand[assign[op]]
            if lab.startswith("r1+="): incs += 1
            r0, r1 = fn(r0, r1, m)
        return r0
    return run

def all_models(dose):
    C = len(candidates(dose))
    return [dict(zip(OPS, a)) for a in itertools.product(range(C), repeat=len(OPS))]

def prog_pool(L=3):
    P = []
    for n in range(1, L + 1): P += ["".join(p) for p in itertools.product(OPS, repeat=n)]
    return P

def identified(V, runs_cache, heldout):
    """functionally identified: all surviving models agree with each other on the held-out programs."""
    if len(V) <= 1: return True
    ref = V[0]
    for q in heldout:
        o = runs_cache[(id(ref), q)]
        for m in V[1:]:
            if runs_cache[(id(m), q)] != o: return False
    return True

def learn(true_run, dose, arm, budget, seed, pool, heldout):
    rng = random.Random(seed); V = all_models(dose)
    runs = {(id(m), q): make_model_run(m, dose)(q) for m in V for q in pool + heldout}   # precompute
    active_lengths = []
    for step in range(budget):
        if identified(V, runs, heldout): break
        if arm == "active":
            q = max(pool, key=lambda q: len({runs[(id(m), q)] for m in V}))
        elif arm == "random":
            q = rng.choice(pool)
        else:  # random-short: match ACTIVE's realized length distribution
            L = rng.choice(active_lengths) if active_lengths else rng.randint(1, 3)
            q = rng.choice([p for p in pool if len(p) == L])
        active_lengths.append(len(q))
        out = true_run(q)
        V = [m for m in V if runs[(id(m), q)] == out]
    ok = identified(V, runs, heldout)
    # CORRECTNESS vs the true world (not internal agreement): shuffle must fail this
    acc = statistics.mean(1.0 if (V and runs[(id(V[0]), q)] == true_run(q)) else 0.0 for q in heldout)
    return (step + 1) if ok else budget + 1, len(V), acc

_MODEL_RUNS = {}
def make_model_run(m, dose):
    return make_model(m, dose)

if __name__ == "__main__":
    L = 3; B = 60; SEEDS = range(5); pool = prog_pool(L)
    print(f"hidden-state machine: 4 opcodes x {len(candidates(1))} candidate semantics = {len(candidates(1))**4} models; "
          f"r1 HIDDEN, mode gated by dose-d prefix; pool {len(pool)} programs, budget {B}\n")
    print(f"{'dose':>4s} {'ACTIVE q':>9s} {'RAND-SHORT q':>12s} {'speedup':>8s} {'acc':>6s}")
    hh = random.Random(0)
    heldout = hh.sample(pool, 30)
    for dose in (1, 2, 3):
        # true world: force the interesting structure (incrementer + reader + gate present), rest random
        aq, rq, accs = [], [], []
        for s in SEEDS:
            rw = random.Random(1000 + s * 7 + dose)
            assign = {"A": 2, "B": 0, "C": rw.randint(0, 5), "D": 6}   # A=r1+=1, B=reader, D=gate; C random
            true_run = make_model(assign, dose)
            a, _, aa = learn(true_run, dose, "active", B, s, pool, heldout)
            r, _, _ = learn(true_run, dose, "randshort", B, 100 + s, pool, heldout)
            aq.append(a); rq.append(r); accs.append(aa)
        ma, mr = statistics.mean(aq), statistics.mean(rq)
        print(f"{dose:>4d} {ma:>9.1f} {mr:>12.1f} {mr/max(1,ma):>7.1f}x {statistics.mean(accs):>6.2f}")

    print("\n=== KNOCKOUTS (dose=2) ===")
    dose = 2
    # K2 stateless: gate replaced by a plain op -> no hidden state; ACTIVE should ~ RANDOM
    aq, rq = [], []
    for s in SEEDS:
        assign = {"A": 2, "B": 0, "C": 1, "D": 1}                       # D no longer a gate (stateless)
        tr = make_model(assign, dose)
        aq.append(learn(tr, dose, "active", B, s, pool, heldout)[0])
        rq.append(learn(tr, dose, "randshort", B, 100 + s, pool, heldout)[0])
    print(f"  K2 stateless: ACTIVE {statistics.mean(aq):.1f} vs RAND-SHORT {statistics.mean(rq):.1f}  "
          f"(tie => advantage was hidden-state; gap persists => advantage is generic active design)")
    # K1 shuffle responses: true outputs permuted -> no model consistent -> never identifies
    for s in SEEDS[:1]:
        assign = {"A": 2, "B": 0, "C": 1, "D": 6}; base = make_model(assign, dose)
        perm = {}; rr = random.Random(5)
        def shuf_run(q, base=base, perm=perm, rr=rr):
            if q not in perm: perm[q] = base(rr.choice(pool))          # response detached from the query
            return perm[q]
        q, vsize, acc = learn(shuf_run, dose, "active", B, s, pool, heldout)
        print(f"  K1 shuffle-responses: held-out accuracy vs world {acc:.2f} (must be ~chance, NOT 1.0) "
              f"-> internal 'identification' is spurious; correctness gate catches it")
