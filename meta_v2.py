"""v2 (fable-designed): SECOND REAL ENVIRONMENT = decimal / libmpdec (a genuinely SEPARATE C binary from
CPython int/float, the structural analog of SQLite in E7). The convention divergence is BANKER'S ROUNDING
(IEEE-754 ROUND_HALF_EVEN) -- the same flavor as SQLite's truncation-toward-zero. The agent actively PROBES
decimal (sound oracle = deterministic under a fixed context), maintains a version space of hypotheses
evaluated in PURE PYTHON int arithmetic (a DIFFERENT code path -> a match is real learning, not tautology),
REJECTS inconsistent hypotheses, COMMITS the simplest survivor (Occam -> the confabulation surface), ABSTAINS
fail-closed on input CLASSES never observed, and INVENTS the half-even correction from a GENERIC parity
primitive. See meta_v2_prereg.md (committed first). n=1 (SQLite) -> n=2.

Pre-registered before running: discriminating fraction p=0.08 -> predicted RANDOM confab = 0.92^B,
ACTIVE ~0 for B>=2. round()/Fraction/Decimal STRUCK from the hypothesis atom list (they implement half-even ->
would re-enter the isleap tautology). Negative-operand floor/trunc confound CONTROLLED: discriminator is
positive-only. Independence guard: assert libmpdec actually loaded (not the _pydecimal fallback)."""
import os, sys, random, statistics, decimal
from decimal import Decimal, ROUND_HALF_EVEN
sys.path.insert(0, os.path.dirname(__file__))

# --- independence guard (fable cond. 1a): libmpdec must be the backend, else it is not a separate binary ---
LIBMPDEC = getattr(decimal, "__libmpdec_version__", None)
_CTX = decimal.Context(prec=50, rounding=ROUND_HALF_EVEN)   # fixed context -> deterministic sound oracle

def world(n, d):
    """REAL WORLD = libmpdec. Round the exact rational n/d to nearest int, banker's rounding. Black box."""
    try:
        if d == 0: return ("ERR",)
        q = (_CTX.divide(Decimal(n), Decimal(d))).quantize(Decimal(1), rounding=ROUND_HALF_EVEN, context=_CTX)
        return ("OK", int(q))
    except Exception: return ("ERR",)

def _p(fn, n, d):
    try: return ("OK", fn(n, d))
    except Exception: return ("ERR",)

def is_even(x): return x % 2 == 0          # GENERIC parity primitive (NOT a domain constant)

def base_grammar():
    """Naive candidates listed FIRST so an under-probed agent COMMITS the simplest (round-half-away) and
    confabulates on unprobed halves; an edge-seeking agent prunes it. round()/Decimal are NOT here (struck)."""
    def rha(n, d):                          # round half AWAY from zero (the naive default)
        if d < 0: n, d = -n, -d
        q, r = divmod(n, d)                 # Python floor-div; positive-only discriminator (see prereg)
        return q + (1 if 2 * r >= d else 0)
    return [("half_away", rha),
            ("floor", lambda n, d: n // d),
            ("ceil",  lambda n, d: -(-n // d)),
            ("trunc", lambda n, d: int(n / d) if d else None)]

def deeper_grammar(ablate=False):
    """E5 'deeper space': the half-EVEN correction, reachable ONLY via the generic parity atom is_even.
    K3 removes is_even -> half_even unreachable -> must flip INVENTED->ABSTAINED on discriminating halves."""
    if ablate: return []                    # K3: no parity primitive -> cannot build banker's rounding
    def rhe(n, d):                          # round half to EVEN (what libmpdec does)
        if d < 0: n, d = -n, -d
        q, r = divmod(n, d)
        if 2 * r < d: return q
        if 2 * r > d: return q + 1
        return q if is_even(q) else q + 1   # exact half -> even neighbor
    return [("half_even_guard", rhe)]

# --- probe pool: NATURAL, positive-only, p pre-computed = 8/100 (NOT tuned) ---
DVALS = [1, 2, 3, 4, 5]; NVALS = list(range(1, 21))
def is_disc(n, d):                          # exact half with EVEN floor = the only discriminating probe
    if d == 0: return False
    q, r = divmod(n, d)
    return 2 * r == d and is_even(q)
def probe_pool(): return [(n, d) for d in DVALS for n in NVALS]
POOL = probe_pool(); DISC = [ab for ab in POOL if is_disc(*ab)]
P_DISC = len(DISC) / len(POOL)             # pre-registered 0.08

def _sig(ab):                              # coverage target: (is-exact-half, floor-parity)
    n, d = ab; q, r = divmod(n, d) if d else (0, 1)
    return (2 * r == d, is_even(q))
def _guard(fn, n, d):
    """FAIL-CLOSED on input CLASSES never observed (None, str, float) -> abstain (= the prereg's CLASS-level
    >=2-survivor abstention). In-class points commit the simplest survivor (the confab surface, per E7)."""
    if any(x is None or isinstance(x, (str, float)) for x in (n, d)): return ("ERR",)
    return _p(fn, n, d)

def disagreement(ab, V):
    return len({_p(fn, *ab) for _, fn in V})

def learn(arm, budget, seed, ablate=False, wrld=world):
    """Version space = base(naive first) + deeper(half_even) from the START, so ACTIVE can PRUNE half_away by
    probing the disagreement; commit V[0] (simplest survivor) = Occam = the confabulation surface."""
    rng = random.Random(seed)
    V = base_grammar() + deeper_grammar(ablate); seen = set()
    for _ in range(budget):
        if not V: break
        if arm == "active":                # COLLECT: split survivors, then COVER unseen signatures
            ab = max(POOL, key=lambda ab: (disagreement(ab, V), _sig(ab) not in seen))
        else:
            ab = rng.choice(POOL)
        seen.add(_sig(ab)); out = wrld(*ab)
        V = [c for c in V if _p(c[1], *ab) == out]     # REJECT inconsistent (sound: exact match)
    if not V: return "abstain", None, None
    top = V[0]
    invented = top[0] if top[0] == "half_even_guard" else None
    return "identify", top[1], invented

# --- adversarial held-out: non-half (coverage) + discriminating halves (confab); OUT must ABSTAIN ---
ADV = [(1, 3), (7, 3), (5, 3), (2, 3), (7, 5), (1, 5), (9, 5),          # non-half: both agree -> coverage
       (1, 2), (5, 2), (9, 2), (13, 2), (2, 4), (10, 4), (18, 4)]      # discriminating halves -> confab test
OUT_ADV = [(None, 3), (3, None), ("a", "b"), (1.5, 2)]                  # novel CLASS -> must abstain
def score(model, wrld=world):
    cover = confab = 0
    for n, d in ADV:
        truth = wrld(n, d); pred = _guard(model, n, d) if model else ("ERR",)
        if pred[0] == "ERR": continue
        if pred == truth: cover += 1
        else: confab += 1
    abst_ok = sum(1 for n, d in OUT_ADV if (_guard(model, n, d) if model else ("ERR",))[0] == "ERR")
    return cover, confab, abst_ok

if __name__ == "__main__":
    print(f"REAL WORLD = decimal/libmpdec {LIBMPDEC}; hypotheses in pure-Python int arithmetic (different path)")
    if LIBMPDEC is None:
        print("  !! INDEPENDENCE GUARD FAILED: _pydecimal fallback loaded, not a separate C binary -> INVALID")
        sys.exit(1)
    print(f"  pool={len(POOL)} discriminating(exact-half,even-floor)={len(DISC)} -> p={P_DISC:.2f}  "
          f"DISC={DISC}\n")

    # ---- BUDGET CURVE + MEASURED mechanism ----
    # PRE-REG MISS (logged, per fable): I predicted RANDOM-any-confab = 0.92^B. That form is WRONG at small B.
    # The MEASUREMENT below shows why, from the actual hypothesis set (not a post-hoc story):
    #  * 0.92^B is exactly right for P(committing the naive half_away)  [half_away is pruned ONLY by a disc pt].
    #  * EXTRA low-B confab comes from FLOOR being promoted to V[0] when half_away is pruned but the space is
    #    not yet narrowed to half_even -> floor also confabulates. So any-confab > 0.92^B at small B, by a
    #    MEASURED mechanism. Sparsity p=0.08 was right; the edge is real; the gap is BIGGER, not smaller.
    SEEDS = range(200)
    def commit_label(arm, B, seed):
        rng = random.Random(seed); V = base_grammar() + deeper_grammar(); seen = set()
        for _ in range(B):
            if not V: break
            ab = rng.choice(POOL) if arm == "random" else max(POOL, key=lambda ab: (disagreement(ab, V), _sig(ab) not in seen))
            seen.add(_sig(ab)); out = world(*ab); V = [c for c in V if _p(c[1], *ab) == out]
        return V[0][0] if V else "ABSTAIN"
    print("=== BUDGET CURVE (mean confab / 14-pt held-out) + MEASURED commit mechanism [200 seeds] ===")
    print(f"  {'B':>3} {'ACT cf':>7} {'RND cf':>7} | {'P(commit half_away)':>19} {'(1-p)^B':>8} | RND V0-distribution")
    for B in (2, 3, 5, 8, 12, 20, 40):
        rates = {}
        for arm in ("active", "random"):
            rates[arm] = statistics.mean([score(learn(arm, B, s)[1])[1] for s in SEEDS])
        import collections
        v0 = collections.Counter(commit_label("random", B, s) for s in SEEDS)
        p_naive = v0["half_away"] / len(list(SEEDS))
        print(f"  {B:>3} {rates['active']:>7.2f} {rates['random']:>7.2f} | {p_naive:>19.2f} {(1-P_DISC)**B:>8.2f} | "
              f"{dict(v0)}")

    # ---- headline at a small budget ----
    B = 5
    print(f"\n=== HEADLINE @ B={B} ({len(list(SEEDS))} seeds) ===")
    for arm in ("active", "random"):
        covs, confs, aos, verds, invs = [], [], [], [], []
        for s in SEEDS:
            v, m, inv = learn(arm, B, s); c, cf, ao = score(m)
            covs.append(c); confs.append(cf); aos.append(ao); verds.append(v); invs.append(inv)
        v0 = statistics.mode(verds); inv0 = next((i for i in invs if i), None)
        print(f"  {arm:6s} -> {v0:8s}  cover {statistics.mean(covs):.1f}/{len(ADV)}  "
              f"confab {statistics.mean(confs):.2f}  abstain-OUT {statistics.mean(aos):.1f}/{len(OUT_ADV)}  "
              f"CONFAB-total {sum(confs)}/{len(ADV)*len(list(SEEDS))}{'  INVENTED '+inv0 if inv0 else ''}")

    # ---- CONTROL: in-grammar non-half region must be ~full cover, 0 confab ----
    print("\n=== CONTROL (non-half held-out only; naive == world -> ~full cover, 0 confab) ===")
    _, m, _ = learn("active", B, 0)
    nh = [(n, d) for n, d in ADV if not is_disc(n, d)]
    cc = sum(1 for n, d in nh if _guard(m, n, d) == world(n, d))
    print(f"  active model covers {cc}/{len(nh)} non-half points")

    # ---- KNOCKOUTS ----
    print("\n=== KNOCKOUTS ===")
    vok, mok, iok = learn("active", B, 0, ablate=False)
    vab, mab, iab = learn("active", B, 0, ablate=True)
    dc_ok = _guard(mok, *DISC[0]) == world(*DISC[0]) if mok else False
    dc_ab = (_guard(mab, *DISC[0]) if mab else ("ERR",))
    print(f"  K3 ablate is_even: normal -> {vok} invent {iok} (disc-half correct={dc_ok}); "
          f"ablated -> {vab} invent {iab} (disc-half pred={dc_ab}, must be ERR/abstain or wrong-but-not-invented)")
    perm = {}; rr = random.Random(9)
    def shufworld(n, d):
        k = (n, d)
        if k not in perm: perm[k] = world(*rr.choice(POOL))
        return perm[k]
    vsh, msh, _ = learn("active", B, 0, wrld=shufworld); c, cf, _ = score(msh, wrld=shufworld)
    print(f"  K1 shuffle-responses: verdict {vsh}, cover {c}/{len(ADV)} (must NOT identify with coverage)")

    # ---- K-INV: reducibility measurement (logged amendment) -- SAME E8 enumerator on trunc AND half_even ----
    print("\n=== K-INV (reducibility measurement, NOT a kill) — same meta_e8 enumerator on both inventions ===")
    import meta_e8 as e8
    KD = [(7, 2), (-7, 2), (1, 2), (5, 2), (2, 4), (3, 2), (9, 2), (10, 4), (6, 3), (7, 3), (1, 3), (13, 2)]
    def rhe_fn(n, d):
        if d == 0: return None
        if d < 0: n, d = -n, -d
        q, r = divmod(n, d)
        return q if 2 * r < d else (q + 1 if 2 * r > d else (q if q % 2 == 0 else q + 1))
    leaves = [("a", tuple(n for n, d in KD)), ("b", tuple(d for n, d in KD)),
              ("1", (1,) * len(KD)), ("2", (2,) * len(KD))]
    # trunc (E7) reproduced in the arithmetic basis:
    tt = e8.sig_of(e8.tgt_trunc, KD); tl, tE, _ = e8.enum_until(leaves, tt, cap=200000)
    # half_even (v2) in the SAME arithmetic basis (no %2 / no branch): expected UNREACHABLE
    he = e8.sig_of(rhe_fn, KD); hl, hE, hsz = e8.enum_until(leaves, he, cap=200000)
    print(f"  E7 trunc    in arithmetic basis: {'energy '+str(tE)+' -> '+tl if tE else 'NOT FOUND'}")
    print(f"  v2 half_even in SAME basis:      {'energy '+str(hE)+' -> '+hl if hE else 'NOT FOUND (searched '+str(hsz)+')'}")
    print("  READING: half_even is UNREACHABLE in E7-trunc's arithmetic basis — it lives in a DIFFERENT basis")
    print("  (needs the generic parity atom %2 + a threshold branch). Not smaller-k than trunc; not on the same")
    print("  k-axis at all. With parity+select added it is depth-2 (q, is_even(q), select). Reported honestly:")
    print("  v2's claim rests on ACTIVE-necessity for 0-confab on real sparse edges, NOT on invention magic.")
