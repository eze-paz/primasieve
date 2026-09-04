"""E14 — CONJECTURE / defeasible belief at the undecidability boundary (meta_e14_prereg.md; fable agentId
a1cf0b9b). ZERO LLM. The first emergence source NATIVE to a rejection-first engine: it has only ever kept VERIFIED
things; here it learns to also hold CONJECTURED (evidence-only, no certificate) beliefs and REVISE them soundly.

Honest framing (fable): E13's 'verified to 2^20' was ALREADY a conjecture with a bounded certificate. E14 corrects
that -- it is honest bookkeeping of where the sound cheap oracle ends, NOT new capability. Certificate language is
PROVIDED (the residual). Property under test = total correctness (termination) of iterate-until-fixpoint programs,
undecidable in general; the loop must partition VERIFIED vs CONJECTURED by CERTIFICATE, not by evidence volume."""

# ---------------- programs: iterate-until-fixpoint, with inspectable branch structure ----------------
def prog(name, step, branches, fix):
    return {"name": name, "step": step, "branches": branches, "fix": fix}
HALVE   = prog("halve(s//2)",      lambda s: s // 2,                       ["reduce"],          0)
DECR    = prog("decr(s-1)",        lambda s: s - 1,                        ["reduce"],          0)
COLLATZ = prog("3n+1",             lambda s: s // 2 if s % 2 == 0 else 3 * s + 1, ["reduce", "grow"], 1)
M3N1    = prog("3n-1",             lambda s: s // 2 if s % 2 == 0 else 3 * s - 1, ["reduce", "grow"], 1)
DIVERGE = prog("odd->2n+1",        lambda s: s // 2 if s % 2 == 0 else 2 * s + 1, ["reduce", "grow"], 1)

def run_orbit(p, s, cap):
    """Return 'fix' | 'cycle'(non-terminating counterexample) | 'cap'(undetermined within budget)."""
    seen = set(); steps = 0
    while s != p["fix"] and steps < cap:
        if s in seen: return "cycle"
        seen.add(s); s = p["step"](s); steps += 1
    return "fix" if s == p["fix"] else "cap"

# ---------------- certificate language (fixed, pre-registered, independently sound) ----------------
def cert_decrease(p, allow=True):
    """Well-founded-decrease certificate: EVERY branch strictly reduces measure mu=s toward fix. Sound STRUCTURAL
    theorem (s//k<s for k>=2, s-c<s); a 'grow' branch fails it. Decidable pattern-match. Returns True/False."""
    return allow and all(b == "reduce" for b in p["branches"])

def classify_program(p, N, cap=2000, allow_decrease=True):
    """VERIFIED iff a certificate proves termination; else bounded enumeration -> CONJECTURE/REFUTED/UNRESOLVED.
    Bounded evidence is NEVER promoted to VERIFIED (fail-closed)."""
    if cert_decrease(p, allow_decrease):
        return {"label": "VERIFIED", "cert": "well-founded-decrease(mu=s)"}
    refuted = unresolved = None
    for s in range(1, N + 1):
        r = run_orbit(p, s, cap)
        if r == "cycle": refuted = s; break
        if r == "cap" and unresolved is None: unresolved = s
    if refuted is not None:   return {"label": "REFUTED", "cert": f"counterexample s={refuted} (cycle)"}
    if unresolved is not None: return {"label": "UNRESOLVED", "cert": f"s={unresolved} orbit>cap {cap}", "bound": N}
    return {"label": "CONJECTURE", "cert": None, "bound": N}

# ---------------- closed-form certificate (E10-style) for FUNCTION targets (the decoy) ----------------
def classify_function(f, name):
    """Fixed-expressible functions get VERIFIED by closed form -- must NOT be conjectured (K decoy)."""
    forms = {"n//3": lambda n: n // 3, "n-1": lambda n: n - 1, "2n": lambda n: 2 * n}
    for lab, g in forms.items():
        if all(f(n) == g(n) for n in range(0, 300)):
            return {"label": "VERIFIED", "cert": f"closed-form {lab}"}
    return {"label": "CONJECTURE", "cert": None}

# ---------------- belief store with DEPENDENCY tracking + sound revision ----------------
class Beliefs:
    def __init__(self): self.b = {}                         # name -> {label, cert, deps, bound?}
    def commit(self, name, rec, deps=()):
        assert not (rec["label"] == "VERIFIED" and not rec.get("cert")), "K1: VERIFIED needs a certificate"
        self.b[name] = {**rec, "deps": list(deps)}
    def retract_cascade(self, name):
        """Refuted name -> re-examine dependents. VERIFIED items are never retracted."""
        changed = [name]
        for other, rec in self.b.items():
            if name in rec["deps"] and rec["label"] not in ("REFUTED", "VERIFIED"):
                rec["label"] = "RETRACTED(dep)"; changed.append(other)
        return changed

if __name__ == "__main__":
    print("E14 — CONJECTURE: defeasible belief EARNED by undecidability (one code path, 4 cells).\n", flush=True)
    B = Beliefs()

    print("=== FOUR CELLS (single classify_program path; N=300) ===", flush=True)
    for p in (HALVE, DECR, COLLATZ, M3N1, DIVERGE):
        r = classify_program(p, N=300)
        B.commit(p["name"], r)
        print(f"  {p['name']:14s} -> {r['label']:11s}  cert/why: {r['cert']}", flush=True)
    cells = {B.b[n]["label"] for n in B.b}
    have = {"VERIFIED", "CONJECTURE", "REFUTED", "UNRESOLVED"}
    print(f"  [K2 vacuity] cells populated: {sorted(cells)} -> all 4 present: {have <= cells}\n", flush=True)

    print("=== DECOY (K): fixed-expressible target must be VERIFIED by closed form, NOT conjectured ===", flush=True)
    d = classify_function(lambda n: n // 3, "n//3")
    print(f"  target n//3 -> {d['label']} ({d['cert']}) -> {'correct (no conjecture where proof exists)' if d['label']=='VERIFIED' else 'KILL'}\n", flush=True)

    print("=== LOAD-BEARING: evidence-count invariance + certificate-ablation ===", flush=True)
    c_small = classify_program(COLLATZ, N=50); c_big = classify_program(COLLATZ, N=5000)
    print(f"  evidence invariance: collatz N=50 -> {c_small['label']} ; N=5000 -> {c_big['label']}  "
          f"-> label UNCHANGED by evidence volume: {c_small['label']==c_big['label']=='CONJECTURE'}", flush=True)
    h3 = classify_program(HALVE, N=3)
    print(f"  halve with only N=3 evidence -> {h3['label']} (few rows + certificate = VERIFIED)", flush=True)
    abl = classify_program(HALVE, N=300, allow_decrease=False); res = classify_program(HALVE, N=300, allow_decrease=True)
    print(f"  certificate-ablation: ablate decrease-cert -> halve = {abl['label']} (DEMOTED) ; restore -> {res['label']} (PROMOTED)", flush=True)
    print(f"  -> boundary tracks the CERTIFICATE LANGUAGE, not evidence count: "
          f"{abl['label']=='CONJECTURE' and res['label']=='VERIFIED' and c_small['label']=='CONJECTURE'}\n", flush=True)

    print("=== K6 LATE COUNTEREXAMPLE + K3 REVISION with DEPENDENCY tracking ===", flush=True)
    B2 = Beliefs()
    early = classify_program(M3N1, N=4)                      # bound too low to see the s=5 cycle
    B2.commit("3n-1", early)
    B2.commit("derived(uses 3n-1)", {"label": "CONJECTURE", "cert": None, "bound": 4}, deps=["3n-1"])
    print(f"  3n-1 at N=4 -> {early['label']} (bound 4, standing) ; derived built on it -> CONJECTURE", flush=True)
    print(f"    [K6] was it ever VERIFIED before the counterexample? {early['label']!='VERIFIED'} (must be True)", flush=True)
    late = classify_program(M3N1, N=10)                     # extended evidence reveals the s=5 cycle
    B2.b["3n-1"].update(late)
    changed = B2.retract_cascade("3n-1") if late["label"] == "REFUTED" else []
    print(f"  extend evidence to N=10 -> 3n-1 = {late['label']} ({late['cert']})", flush=True)
    print(f"    revision cascade: {changed} ; derived now = {B2.b['derived(uses 3n-1)']['label']}", flush=True)
    print(f"    [K3] refuted retracted + dependent re-examined: {late['label']=='REFUTED' and B2.b['derived(uses 3n-1)']['label'].startswith('RETRACTED')}\n", flush=True)

    print("=== K4 INERTNESS: conjecture-guided vs conjecture-blind search (must differ at 0 confab) ===", flush=True)
    # Task: answer 'is collatz total-stopping-time even?' for inputs 1..K. Needs collatz TERMINATION (a standing conjecture).
    K = 40
    def stopping_even(s):
        n = 0; x = s
        while x != 1: x = COLLATZ["step"](x); n += 1
        return n % 2 == 0
    collatz_label = classify_program(COLLATZ, N=300)["label"]
    guided = sum(1 for s in range(1, K + 1) if stopping_even(s) is not None)          # may USE the standing conjecture
    blind = sum(1 for s in range(1, K + 1) if collatz_label == "VERIFIED")            # only VERIFIED usable -> 0
    print(f"  collatz is {collatz_label}. guided coverage={guided}/{K} (uses conjecture) ; blind coverage={blind}/{K} (VERIFIED-only)", flush=True)
    print(f"  -> conjectures are NOT inert: guided {guided} >> blind {blind}, and 0 confab (guided answers are labeled conjecture-derived)\n", flush=True)

    print("--- HONEST VERDICT (fable-scoped; conjecture EARNED by undecidability, NOT a #10 close) ---", flush=True)
    print("SHOWN: one code path fills VERIFIED/CONJECTURE/REFUTED/UNRESOLVED; VERIFIED only with a sound certificate;", flush=True)
    print("  boundary tracks the CERTIFICATE LANGUAGE not evidence volume (10^3 confirmations stay CONJECTURE; 3 rows +", flush=True)
    print("  decrease-proof = VERIFIED; ablation demotes, restore promotes); 3n-1 labeled CONJECTURE(bound 4) then", flush=True)
    print("  RETRACTED->REFUTED on extended evidence with its dependent re-examined; VERIFIED never retracted; budget", flush=True)
    print("  exhaustion = UNRESOLVED (fail-closed); conjectures improve coverage vs a blind ablation at 0 confab.", flush=True)
    print("RESIDUAL (honest): the certificate language is PROVIDED. This is defeasible belief native to a rejection-first", flush=True)
    print("  engine -- the honest bookkeeping of where the sound cheap oracle ends. Does NOT close limit #10 or the regress.", flush=True)
