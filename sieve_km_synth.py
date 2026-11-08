# ---------------- KM synthetic recall (sieve_lang_prereg.md KM): appended to sieve_harm_kernel.py, runs after its arm loop ----------------
# Multi-query associative recall: n (key, value) pairs at the start of a 256-token sequence (keys 1..255, values 256..511, filler 0),
# then each key queried once at a random later position; the model must output the key's value at the query position.
# Arms built from the kernel's own classes at d 128, 2 layers, vocab 512, no dropout. Writes km_synth.json.
VT = 512; DROP = 0.0; CTX = 256; D = 128; NL = 2; FF = 512
SY_STEPS = 60 if TINY else int(os.environ.get("KM_STEPS", 4000)); SY_NS = (4, 8, 16, 32, 64)
def mqar(rng, Bn, T, n, far=0):
    x = np.zeros((Bn, T), np.int64); y = np.full((Bn, T), -100, np.int64)
    for b in range(Bn):
        ks = rng.choice(255, n, replace=False) + 1; vs = rng.integers(256, 512, n); x[b, 0:2 * n:2] = ks; x[b, 1:2 * n:2] = vs
        lo = max(2 * n, T - far) if far else 2 * n; qp = rng.choice(np.arange(lo, T), n, replace=False); o = rng.permutation(n)
        x[b, qp] = ks[o]; y[b, qp] = vs[o]
    return torch.as_tensor(x).to(dev), torch.as_tensor(y).to(dev)
@torch.no_grad()
def acc(model, rng, T, n, far=0, reps=8):
    model.eval(); c = t = 0; bn = 64 if T <= 256 else 8
    for _ in range(reps * 64 // bn):
        x, y = mqar(rng, bn, T, n, far); m = y >= 0
        with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"): p = model(x).argmax(-1)
        c += int((p[m] == y[m]).sum()); t += int(m.sum())
    model.train(); return c / t
SY = {}
for arm in ("NET2s0", "HBlearn", "HM", "HMonly", "HMsel"):
    torch.manual_seed(0); t0 = time.time(); model = build(arm).to(dev); NP = sum(p.numel() for p in model.parameters())
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, betas=(0.9, 0.95), weight_decay=0.1); rng = np.random.default_rng(1)
    scaler = torch.cuda.amp.GradScaler(enabled=dev.type == "cuda")
    for k in range(SY_STEPS):
        for g in opt.param_groups: g["lr"] = 1e-3 * min(1.0, (k + 1) / 200) * 0.5 * (1 + math.cos(math.pi * k / SY_STEPS))
        x, y = mqar(rng, 64, 256, int(rng.choice(SY_NS)))
        with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"): loss = F.cross_entropy(model(x).reshape(-1, VT).float(), y.reshape(-1))
        opt.zero_grad(set_to_none=True); scaler.scale(loss).backward(); scaler.unscale_(opt); nn.utils.clip_grad_norm_(model.parameters(), 1.0); scaler.step(opt); scaler.update()
        if k % 1000 == 0: log(f"synth {arm}: step {k} loss {loss.item():.3f}")
    er = np.random.default_rng(2); r = {f"n{n}": acc(model, er, 256, n) for n in SY_NS}
    if isinstance(model, OLM): r["far1024_n16"] = acc(model, er, 1024, 16, far=256)                       # queries >= 736 tokens after the pairs
    r["params"] = NP; r["seconds"] = time.time() - t0; SY[arm] = r; log(f"synth {arm}: {json.dumps(r)}")
    del model, opt
    if dev.type == "cuda": torch.cuda.empty_cache()
json.dump(SY, open(os.path.join(OUT, "km_synth.json"), "w"), indent=1); log("synth done")
