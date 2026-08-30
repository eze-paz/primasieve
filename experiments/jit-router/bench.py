"""Regime-A bake-off: JIT per-task heads on a shared frozen encoder.

Reports, per (task, head): test accuracy, per-task fit time (ms), predict time.
Also reports the encoder's amortized cost (ms/example) and a ROUTER eval where
the 'task' is: which of the N tasks does this text belong to.

Run:
    py -3.12 bench.py                 # hashing encoder, offline
    py -3.12 bench.py --encoder hf    # real MiniLM if available
    py -3.12 bench.py --pool 8        # 8 labeled examples/class (JIT regime)
"""
from __future__ import annotations
import argparse
import time
import numpy as np

from encoders import get_encoder
from heads import REGISTRY
from tasks import build_suite


def _median_ms(fn, repeats):
    ts = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        out = fn()
        ts.append((time.perf_counter() - t0) * 1e3)
    return float(np.median(ts)), out


def run(encoder_kind, pool_k, test_k, seed, repeats):
    enc = get_encoder(encoder_kind)
    tasks = build_suite(n_per_class=pool_k + test_k + 20, seed=seed)

    # ---- frozen-encoder amortized cost (measured once) ----
    warm = ["measure the encoder throughput please now"] * 64
    enc.encode(warm[:1])  # warm any lazy init
    t0 = time.perf_counter()
    _ = enc.encode(warm)
    enc_ms_per = (time.perf_counter() - t0) * 1e3 / len(warm)

    print("\n=== JIT-router Regime-A bake-off ===")
    print("encoder = %s | %.3f ms/example (frozen, amortized)" % (enc.name, enc_ms_per))
    print("pool = %d labeled/class | test = %d/class | fit timed x%d (median)\n"
          % (pool_k, test_k, repeats))

    hdr = "%-11s | " % "task" + " | ".join("%-22s" % h for h in REGISTRY)
    print(hdr)
    print("-" * len(hdr))

    agg = {h: [] for h in REGISTRY}
    for t in tasks:
        Xtr_t, ytr, Xte_t, yte = t.split(seed + 100, pool_k, test_k)
        Xtr = enc.encode(Xtr_t)
        Xte = enc.encode(Xte_t)
        cells = []
        for hname, make in REGISTRY.items():
            head = make()
            fit_ms, st = _median_ms(lambda: head.fit(Xtr, ytr, t.n_classes), repeats)
            pred = head.predict(st, Xte)
            acc = float((pred == yte).mean())
            agg[hname].append(acc)
            cells.append("%.2f  %6.3fms" % (acc, fit_ms))
        print("%-11s | " % t.name + " | ".join("%-22s" % c for c in cells))

    print("-" * len(hdr))
    print("%-11s | " % "mean-acc" +
          " | ".join("%-22s" % ("%.3f" % np.mean(agg[h])) for h in REGISTRY))

    # ---- ROUTER: classify which task a text belongs to ----
    router_texts, router_labels = [], []
    for ti, t in enumerate(tasks):
        idx = np.arange(len(t.texts))
        np.random.default_rng(seed + ti).shuffle(idx)
        take = idx[:pool_k + test_k]
        router_texts += list(t.texts[take])
        router_labels += [ti] * len(take)
    router_texts = np.array(router_texts, dtype=object)
    router_labels = np.array(router_labels)
    rng = np.random.default_rng(seed + 999)
    perm = rng.permutation(len(router_texts))
    ntr = len(tasks) * pool_k
    tri, tei = perm[:ntr], perm[ntr:]
    RXtr = enc.encode(router_texts[tri]); Rytr = router_labels[tri]
    RXte = enc.encode(router_texts[tei]); Ryte = router_labels[tei]
    print("\n--- ROUTER (label = task id, %d classes) ---" % len(tasks))
    for hname, make in REGISTRY.items():
        head = make()
        fit_ms, st = _median_ms(lambda: head.fit(RXtr, Rytr, len(tasks)), repeats)
        acc = float((head.predict(st, RXte) == Ryte).mean())
        print("  %-10s acc=%.3f  fit=%.3fms" % (hname, acc, fit_ms))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--encoder", default="hashing", choices=["hashing", "hf"])
    ap.add_argument("--pool", type=int, default=16, help="labeled examples per class")
    ap.add_argument("--test", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=25)
    a = ap.parse_args()
    run(a.encoder, a.pool, a.test, a.seed, a.repeats)
