"""P2/#1+#2 — does MORE EXPERIENCE fix strategy-transfer (the S2 refutation)? Mine winning
strategies from 109 SYNTHETIC bugs (from correct sources), warm-start the bandit on 26 REAL
held-out bugs (different distribution). If warm/cold < 1.0 now, data-starvation was the cause.
ZERO LLM. Held-back assertions gate every solve (anti-cheat). Leakage-safe: train=synthetic from
correct code, holdout=real seeded bugs; a-priori signature never sees the fix."""
import os, json, random
import reasoner_code as rc
from meta_reason import solve_ucb
from meta_transfer import signature, sig_dist, winning_forms
from meta_pool import build_pool

HELD_BACK = 0.25

def warm_prior(sig, casebase, k=5):
    near = sorted(casebase, key=lambda cs: sig_dist(sig, cs[0]))[:k]
    cnt = {}
    for _, forms in near:
        for f in set(forms): cnt[f] = cnt.get(f, 0) + 1
    if not cnt: return None
    m = max(cnt.values())
    return {f: 2.0 * c / m for f, c in cnt.items()}

if __name__ == "__main__":
    rng = random.Random(0)
    train, holdout = build_pool(rng)
    print(f"train(synthetic) {len(train)}  holdout(real) {len(holdout)}  held-back {int(HELD_BACK*100)}%\n")

    # TRAIN: mine winning strategy + a-priori signature from each solved synthetic bug
    casebase = []
    for b in train:
        ep = []
        ok, en, _ = solve_ucb(b["fn"], b["src"], b["tests"], ep, held_back=HELD_BACK)
        if ok:
            casebase.append((signature(b["fn"], b["src"], b["tests"]), winning_forms(ep)))
    print(f"casebase: {len(casebase)} solved-synthetic strategies mined\n")

    # HOLDOUT: cold vs warm (k-NN from the big synthetic casebase)
    print(f"{'real bug':26s} {'cold':>12s} {'warm':>12s}")
    ce = we = cs = ws = 0; wins = 0; losses = 0
    for b in holdout:
        sig = signature(b["fn"], b["src"], b["tests"])
        ep = []; cok, cen, _ = solve_ucb(b["fn"], b["src"], b["tests"], ep, held_back=HELD_BACK)
        wp = warm_prior(sig, casebase)
        ep2 = []; wok, wen, _ = solve_ucb(b["fn"], b["src"], b["tests"], ep2, warm=wp, held_back=HELD_BACK)
        cs += cok; ws += wok; ce += cen; we += wen
        if wen < cen: wins += 1
        elif wen > cen: losses += 1
        tag = "  <=" if wen < cen else ("  >" if wen > cen else "")
        print(f"{b['id']:26s} {('Y' if cok else 'n')}({cen:5d}) {('Y' if wok else 'n')}({wen:5d}){tag}", flush=True)

    print(f"\n=== S2 RE-TEST with 8x experience (holdout {len(holdout)} REAL bugs) ===")
    print(f"COLD : {cs}/{len(holdout)} solved, energy {ce}")
    print(f"WARM : {ws}/{len(holdout)} solved, energy {we}")
    print(f"energy warm/cold: {we/max(1,ce):.2f}x   per-bug: {wins} faster, {losses} slower")
    json.dump({"casebase": len(casebase), "cold_energy": ce, "warm_energy": we,
               "ratio": we/max(1,ce), "wins": wins, "losses": losses},
              open("meta_learn_result.json", "w"), indent=1)
