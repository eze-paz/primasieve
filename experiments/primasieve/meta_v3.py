"""v3 (fable-designed): THIRD REAL ENVIRONMENT, a NEW PROBLEM CLASS = INVERSE-MAP INFERENCE over json/_json
(the C encoder, a genuinely separate implementer). NOT perception (a serializer round-trip is still tokenized;
see perception_p1_prereg.md for real perception). The convention is JSON string-escaping under ensure_ascii;
the sparse edge + invention target is ASTRAL codepoints -> UTF-16 SURROGATE-PAIR escaping. The agent probes
json.dumps as a black box (sound oracle = deterministic), learns the forward renderer in PURE-PYTHON primitives
(json/repr/ascii STRUCK from the atom list), REJECTS inconsistent hypotheses, COMMITS the simplest survivor
(Occam = confab surface), INVENTS the surrogate rule from residuals, and ABSTAINS on non-injective classes where
the inverse is provably ambiguous. See meta_v3_prereg.md (committed first). n=2 -> n=3 implementers, n=2 classes."""
import os, sys, random, statistics, json
sys.path.insert(0, os.path.dirname(__file__))

# --- independence guard: the C _json encoder must be the backend, else it is not a separate binary ---
C_ENCODER = json.encoder.c_make_encoder is not None

def world_esc(cp):
    """REAL WORLD = _json. Return the escaped body json.dumps produces for the 1-char string chr(cp)
    (outer quotes stripped). Black box; the agent never calls json."""
    try: return ("OK", json.dumps(chr(cp))[1:-1])
    except Exception: return ("ERR",)

def _p(fn, cp):
    try: return ("OK", fn(cp))
    except Exception: return ("ERR",)

# generic escape scaffolding shared by all hypotheses (control-char + quote/backslash rules are in-grammar)
_SIMPLE = {0x22: '\\"', 0x5c: '\\\\', 0x08: '\\b', 0x09: '\\t', 0x0a: '\\n', 0x0c: '\\f', 0x0d: '\\r'}
def _lowesc(cp):                         # control chars C0 and the mandatory escapes (generic, not the invention)
    if cp in _SIMPLE: return _SIMPLE[cp]
    if cp < 0x20: return "\\u%04x" % cp
    return None

def base_grammar():
    """Naive candidates FIRST. esc_bmp is correct across ASCII + the whole BMP; it is WRONG on astral (emits one
    \\u of the raw codepoint instead of a surrogate pair). repr/ascii/json are NOT here (struck)."""
    def esc_raw(cp):                     # rawest: printable stays, everything else raw chr (wrong beyond ASCII)
        e = _lowesc(cp)
        return e if e is not None else chr(cp)
    def esc_bmp(cp):                     # ASCII raw, else \uXXXX from the codepoint (correct through U+FFFF only)
        e = _lowesc(cp)
        if e is not None: return e
        if cp < 0x80: return chr(cp)
        return "\\u%04x" % cp
    return [("esc_raw", esc_raw), ("esc_bmp", esc_bmp)]

def deeper_grammar(ablate=False):
    """Deeper space: the SURROGATE-PAIR rule for astral codepoints, reachable ONLY via the generic bit primitives
    >> and & . K3 removes them -> astral rule unreachable -> must flip INVENTED->ABSTAINED on astral."""
    if ablate: return []
    def esc_surrogate(cp):
        e = _lowesc(cp)
        if e is not None: return e
        if cp < 0x80: return chr(cp)
        if cp <= 0xFFFF: return "\\u%04x" % cp
        v = cp - 0x10000                 # UTF-16 surrogate pair (generic bit arithmetic)
        return "\\u%04x\\u%04x" % (0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF))
    return [("surrogate_guard", esc_surrogate)]

# --- probe pool: dense ASCII + fixed BMP sample + SPARSE astral; p pre-computed = astral/pool ---
ASCII = list(range(0x20, 0x7F))                                   # 95 printable
CTRL = [0x00, 0x07, 0x08, 0x09, 0x0a, 0x0c, 0x0d, 0x1b, 0x22, 0x5c]  # control + quote + backslash edges
BMP = [0x80, 0xa9, 0xe9, 0x100, 0x3b1, 0x41f, 0x5d0, 0x2013, 0x20ac, 0x4e2d, 0x7fff, 0xffff]  # non-ASCII BMP
ASTRAL = [0x10000, 0x1d538, 0x1f600, 0x1f680]                     # sparse: 𝔸 😀 🚀 + first astral
POOL = ASCII + CTRL + BMP + ASTRAL
P_DISC = len(ASTRAL) / len(POOL)

def _sig(cp):                            # coverage signature: which regime the codepoint is in
    return (cp in _SIMPLE, cp < 0x20, cp < 0x80, cp <= 0xFFFF)
def _guard(fn, cp):
    """FAIL-CLOSED on input CLASSES never observed (here: surrogates themselves, negatives) -> abstain."""
    if fn is None or cp < 0 or 0xD800 <= cp <= 0xDFFF or cp > 0x10FFFF: return ("ERR",)
    return _p(fn, cp)
def disagreement(cp, V): return len({_p(fn, cp) for _, fn in V})

def learn(arm, budget, seed, ablate=False, wrld=world_esc):
    rng = random.Random(seed)
    V = base_grammar() + deeper_grammar(ablate); seen = set()
    for _ in range(budget):
        if not V: break
        if arm == "active":
            cp = max(POOL, key=lambda cp: (disagreement(cp, V), _sig(cp) not in seen))
        else:
            cp = rng.choice(POOL)
        seen.add(_sig(cp)); out = wrld(cp)
        V = [c for c in V if _p(c[1], cp) == out]
    if not V: return "abstain", None, None
    top = V[0]
    invented = top[0] if top[0] == "surrogate_guard" else None
    return "identify", top[1], invented

# --- adversarial held-out: ASCII/control/BMP (coverage) + astral (confab); OUT = classes never observed ---
ADV = [0x41, 0x7e, 0x20, 0x09, 0x0a, 0x22, 0x5c, 0xa9, 0x3b1, 0x20ac, 0xffff,   # coverage
       0x10000, 0x1f600, 0x1f680, 0x1d538]                                       # astral -> confab test
OUT_ADV = [-1, 0xD834, 0x110000]                                                 # lone surrogate / out-of-range
def score(model, wrld=world_esc):
    cover = confab = 0
    for cp in ADV:
        truth = wrld(cp); pred = _guard(model, cp) if model else ("ERR",)
        if pred[0] == "ERR": continue
        if pred == truth: cover += 1
        else: confab += 1
    abst_ok = sum(1 for cp in OUT_ADV if (_guard(model, cp) if model else ("ERR",))[0] == "ERR")
    return cover, confab, abst_ok

# --- OP-B: injectivity abstention. Given an observation, invert-or-abstain (sound: >=2 latents re-render same) ---
def dumps(x): return json.dumps(x, ensure_ascii=True, sort_keys=True)   # renderer (oracle only)
INJ_CASES = [                                    # (observation, latents that render to it, must_abstain)
    (dumps({1: 0}),      [{1: 0}, {"1": 0}],      True),      # int key vs str key coerce+sort collide
    (dumps([1, 2]),      [[1, 2], (1, 2)],        True),      # list vs tuple
    (dumps("hello"),     ["hello"],               False),     # unique string
    (dumps(42),          [42],                    False),     # unique int
    (dumps({"a": 1}),    [{"a": 1}],              False),     # unique dict
]
def invert_or_abstain(obs):
    """SOUND inversion: abstain iff >=2 DISTINCT latents re-render to the same observation (ambiguous)."""
    cands = [{1: 0}, {"1": 0}, [1, 2], (1, 2), "hello", 42, {"a": 1}]   # small hypothesis latent set
    hits = [c for c in cands if dumps(c) == obs]
    reps = {repr(c) for c in hits}
    return ("abstain",) if len(reps) >= 2 else (("invert", hits[0]) if hits else ("abstain",))

if __name__ == "__main__":
    print(f"REAL WORLD = json/_json (C encoder={C_ENCODER}); hypotheses in pure-Python primitives (json struck)")
    if not C_ENCODER:
        print("  !! INDEPENDENCE GUARD FAILED: pure-Python json fallback loaded -> INVALID"); sys.exit(1)
    print(f"  pool={len(POOL)} astral(discriminating)={len(ASTRAL)} -> p={P_DISC:.3f}  ASTRAL={[hex(c) for c in ASTRAL]}\n")

    SEEDS = range(200)
    print("=== BUDGET CURVE (mean confab / held-out) + MEASURED commit mechanism [200 seeds] ===")
    print(f"  {'B':>3} {'ACT cf':>7} {'RND cf':>7} | {'P(commit esc_bmp)':>17} {'(1-p)^B':>8} | RND V0-distribution")
    def commit_label(arm, B, seed):
        rng = random.Random(seed); V = base_grammar() + deeper_grammar(); seen = set()
        for _ in range(B):
            if not V: break
            cp = rng.choice(POOL) if arm == "random" else max(POOL, key=lambda cp: (disagreement(cp, V), _sig(cp) not in seen))
            seen.add(_sig(cp)); out = world_esc(cp); V = [c for c in V if _p(c[1], cp) == out]
        return V[0][0] if V else "ABSTAIN"
    import collections
    for B in (2, 3, 5, 8, 12, 20, 40):
        rates = {a: statistics.mean([score(learn(a, B, s)[1])[1] for s in SEEDS]) for a in ("active", "random")}
        v0 = collections.Counter(commit_label("random", B, s) for s in SEEDS)
        print(f"  {B:>3} {rates['active']:>7.2f} {rates['random']:>7.2f} | {v0['esc_bmp']/len(list(SEEDS)):>17.2f} "
              f"{(1-P_DISC)**B:>8.2f} | {dict(v0)}")

    B = 8
    print(f"\n=== HEADLINE @ B={B} ({len(list(SEEDS))} seeds) ===")
    for arm in ("active", "random"):
        covs, confs, aos, verds, invs = [], [], [], [], []
        for s in SEEDS:
            v, m, inv = learn(arm, B, s); c, cf, ao = score(m)
            covs.append(c); confs.append(cf); aos.append(ao); verds.append(v); invs.append(inv)
        v0 = statistics.mode(verds); inv0 = next((i for i in invs if i), None)
        print(f"  {arm:6s} -> {v0:8s}  cover {statistics.mean(covs):.1f}/{len(ADV)}  confab {statistics.mean(confs):.2f}  "
              f"abstain-OUT {statistics.mean(aos):.1f}/{len(OUT_ADV)}  CONFAB-total {sum(confs)}/{len(ADV)*len(list(SEEDS))}"
              f"{'  INVENTED '+inv0 if inv0 else ''}")

    print("\n=== CONTROL (ASCII-only held-out; naive == world -> full cover, 0 confab) ===")
    _, m, _ = learn("active", B, 0)
    asc = [cp for cp in ADV if cp < 0x80]
    print(f"  active model covers {sum(1 for cp in asc if _guard(m, cp) == world_esc(cp))}/{len(asc)} ASCII points")

    print("\n=== KNOCKOUTS ===")
    vok, mok, iok = learn("active", B, 0, ablate=False)
    vab, mab, iab = learn("active", B, 0, ablate=True)
    astral0 = ASTRAL[2]
    print(f"  K3 ablate >>/&: normal -> {vok} invent {iok} (astral correct={_guard(mok, astral0)==world_esc(astral0)}); "
          f"ablated -> {vab} invent {iab} (astral pred={_guard(mab, astral0)}, must be ERR/abstain or wrong-not-invented)")
    perm = {}; rr = random.Random(9)
    def shufworld(cp):
        if cp not in perm: perm[cp] = world_esc(rr.choice(POOL))
        return perm[cp]
    vsh, msh, _ = learn("active", B, 0, wrld=shufworld); c, cf, _ = score(msh, wrld=shufworld)
    print(f"  K1 shuffle: verdict {vsh}, cover {c}/{len(ADV)} (must NOT identify with coverage)")

    print("\n=== OP-B: INJECTIVITY ABSTENTION (must abstain iff >=2 latents re-render identically) ===")
    ok = 0
    for obs, latents, must_abstain in INJ_CASES:
        got = invert_or_abstain(obs); did_abstain = got[0] == "abstain"
        good = did_abstain == must_abstain; ok += good
        print(f"  {obs!r:22s} -> {got[0]:7s}  expect {'abstain' if must_abstain else 'invert':7s}  {'OK' if good else 'FAIL'}")
    print(f"  abstention-correctness {ok}/{len(INJ_CASES)}")
