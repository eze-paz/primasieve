"""E7 (fable-designed): REAL ENVIRONMENT = SQLite expression engine (stdlib sqlite3). The world is a C
implementation NOT authored by this project; hypotheses are evaluated in PYTHON (a DIFFERENT implementation,
so a match is real learning, not tautology). The agent actively PROBES SQLite (sound oracle = deterministic
execution), IDENTIFIES operators its grammar covers, ABSTAINS where it cannot, and INVENTS primitives
(trunc-division, sign-modulo) from recurring residuals. See meta_e7_prereg.md (committed first).

Metric = coverage + abstention-correctness + CONFABULATION=0 (sound-rejection promise) + primitives-invented,
vs an ADVERSARIAL held-out (negatives, zero divisor, NULL). Arms ACTIVE (version-space disagreement, seeks
edges) vs RANDOM-MATCHED. Control = in-grammar python +,-,* (tautology, ~100%). Knockouts K1 shuffle, K3
ablate abs/sign (trunc-div must flip INVENTED->ABSTAINED)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.registry import selfcheck

import os, sys, random, sqlite3, statistics
sys.path.insert(0, os.path.dirname(__file__))
_C = sqlite3.connect(":memory:")

def fmt(x): return "NULL" if x is None else (f"'{x}'" if isinstance(x, str) else str(x))
def sql(op, a, b):
    try: return ("OK", _C.execute(f"SELECT ({fmt(a)}) {op} ({fmt(b)})").fetchone()[0])
    except Exception: return ("ERR",)

def _p(fn, a, b):
    try: return ("OK", fn(a, b))
    except Exception: return ("ERR",)

def base_grammar():
    return [("add", lambda a, b: a + b), ("sub", lambda a, b: a - b), ("mul", lambda a, b: a * b),
            ("floordiv", lambda a, b: a // b), ("pymod", lambda a, b: a % b),
            ("eq", lambda a, b: 1 if a == b else 0), ("ne", lambda a, b: 1 if a != b else 0),
            ("lt", lambda a, b: 1 if a < b else 0), ("gt", lambda a, b: 1 if a > b else 0),
            ("le", lambda a, b: 1 if a <= b else 0), ("ge", lambda a, b: 1 if a >= b else 0)]
def deeper_grammar(ablate=False):
    """E5 'deeper space' reached only when base fails; trunc/sign need abs/sign atoms (removed by K3)."""
    if ablate: return []                                        # K3: no abs/sign -> can't build trunc
    tdiv = lambda a, b: None if b == 0 else int(a / b)          # SQLite: truncate toward zero, /0 -> NULL
    tmod = lambda a, b: None if b == 0 else a - b * int(a / b)  # SQLite: remainder sign follows dividend
    return [("truncdiv_guard", tdiv), ("signmod_guard", tmod)]

POS = [2, 3, 4, 5, 6, 7, 8, 9]                      # dense positives
EDGE = [(-7, 2), (2, -7), (-7, -3), (-5, 4), (5, -3), (7, 0), (-7, 0)]   # SPARSE edges (rare in reality)
def probe_pool(kind="int"):
    if kind == "str": return [(x, y) for x in ("a", "b") for y in ("a", "c")]
    return [(a, b) for a in POS for b in POS] + EDGE      # ~90% positive, ~10% edge -> random rarely probes edges
def _sig(ab):
    a, b = ab
    def s(x): return 0 if x == 0 else (1 if x > 0 else -1)
    return (s(a), s(b))                                  # sign signature (coverage target)
def _guard(fn, a, b):
    """FAIL-CLOSED on input CLASSES never observed during learning (NULL, strings) -> abstain, don't
    extrapolate. This is the honest sound-rejection: a model validated on ints claims nothing about NULL."""
    if a is None or b is None or isinstance(a, str) or isinstance(b, str): return ("ERR",)
    return _p(fn, a, b)

def disagreement(ab, V, op):
    return len({_p(fn, *ab) for _, fn in V})

def learn_operator(op, arm, budget, seed, ablate=False, world=sql, pool=None):
    """Version space = base + deeper (E5) from the start; base listed FIRST so an under-probed agent
    COMMITS to the simplest (e.g. floordiv) and confabulates, while an edge-seeking agent prunes it."""
    rng = random.Random(seed); pool = pool or probe_pool()
    V = base_grammar() + deeper_grammar(ablate); asked = []; seen = set()
    for _ in range(budget):
        if not V: break
        if arm == "active":                                    # COLLECT: split surviving models, then COVER unseen sign-signatures
            ab = max(pool, key=lambda ab: (disagreement(ab, V, op), _sig(ab) not in seen))
        else:
            ab = rng.choice(pool)
        seen.add(_sig(ab)); out = world(op, *ab); asked.append((ab, out))
        V = [c for c in V if _p(c[1], *ab) == out]              # REJECT inconsistent (sound: exact match)
    if not V: return "abstain", None, None                     # every hypothesis killed -> honest abstain
    top = V[0]                                                  # commit to the simplest survivor
    invented = top[0] if top[0] in ("truncdiv_guard", "signmod_guard") else None
    return "identify", top[1], invented

# adversarial held-out (fable): int edges score COVERAGE/CONFAB; OUT cases score ABSTENTION-correctness
ADV = [(2, 7), (7, 2), (-7, 2), (2, -7), (-7, -2), (7, 0), (-5, 3), (5, -2), (6, -4)]     # int edges
OUT_ADV = [(None, 3), (3, None), ("a", "b")]                                              # must ABSTAIN
def score(op, model, world=sql):
    cover = confab = 0
    for a, b in ADV:
        truth = world(op, a, b); pred = _guard(model, a, b) if model else ("ERR",)
        if pred[0] == "ERR": continue                          # fail-closed abstain -> not scored
        if pred == truth: cover += 1
        else: confab += 1
    abst_ok = sum(1 for a, b in OUT_ADV if (_guard(model, a, b) if model else ("ERR",))[0] == "ERR")
    return cover, confab, abst_ok

if __name__ == "__main__":
    selfcheck(__file__)   # verifies this file\'s PUBLISHED claims (core/registry.py) at exit
    B = 14; SEEDS = range(8)          # tight budget: random rarely samples the ~10% sparse edges
    OPS = ["+", "-", "*", "/", "%", "=", "<"]          # IN: +,-,*,=,<  EDGE: /,%  (OUT tested via OUT_ADV)
    print("REAL WORLD = SQLite; hypotheses in Python (different impl). vs adversarial held-out "
          f"(cover/confab on int edges; abstain on {len(OUT_ADV)} OUT=NULL/str)\n")
    for arm in ("active", "random"):
        tot_conf = 0; ids = abst = inv = 0; names = []
        for op in OPS:
            covs, confs, aos, verds = [], [], [], []
            for s in SEEDS:
                v, model, invn = learn_operator(op, arm, B, s)
                c, cf, ao = score(op, model); covs.append(c); confs.append(cf); aos.append(ao); verds.append((v, invn))
            v0 = statistics.mode([v for v, _ in verds]); invn0 = next((i for _, i in verds if i), None)
            tot_conf += sum(confs); ids += v0 == "identify"; abst += v0 == "abstain"
            if invn0: inv += 1; names.append(f"{op}:{invn0}")
            print(f"  {arm:6s} '{op}' -> {v0:8s}  cover {statistics.mean(covs):.1f}/{len(ADV)}  "
                  f"confab {statistics.mean(confs):.1f}  abstain-OUT {statistics.mean(aos):.1f}/{len(OUT_ADV)}"
                  f"{'  INVENTED '+invn0 if invn0 else ''}")
        print(f"  == {arm.upper()}: identified {ids}/{len(OPS)}, invented {inv} {names}, "
              f"CONFABULATION {tot_conf}/{len(ADV)*len(SEEDS)*len(OPS)}\n")

    print("=== CONTROL (in-grammar python +,-,*; must be ~full cover, 0 confab) ===")
    pyw = lambda op, a, b: _p({"+": lambda a, b: a+b, "-": lambda a, b: a-b, "*": lambda a, b: a*b}[op], a, b)
    for op in ("+", "-", "*"):
        v, m, _ = learn_operator(op, "active", B, 0, world=pyw); c, cf, ao = score(op, m, world=pyw)
        print(f"  '{op}' -> {v}  cover {c}/{len(ADV)} confab {cf}")

    print("\n=== KNOCKOUTS ===")
    vok, _, iok = learn_operator("/", "active", B, 0, ablate=False)
    vabl, _, iabl = learn_operator("/", "active", B, 0, ablate=True)
    print(f"  K3 ablate abs/sign on '/': normal -> {vok} (invent {iok}); ablated -> {vabl} (invent {iabl})  "
          f"[must flip invent -> abstain]")
    perm = {}; rr = random.Random(9); pool = probe_pool()
    def shufworld(op, a, b):
        k = (op, a, b)
        if k not in perm: perm[k] = sql(op, *rr.choice(pool))
        return perm[k]
    vsh, msh, _ = learn_operator("+", "active", B, 0, world=shufworld); c, cf, ao = score("+", msh, world=shufworld)
    print(f"  K1 shuffle-responses on '+': verdict {vsh}, cover {c}/{len(ADV)} (must NOT identify with coverage)")
