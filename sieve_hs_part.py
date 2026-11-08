# ---------------- HGH (sieve_lang_prereg.md): appended to sieve_harm_kernel.py by the push (HARM_ARMS empty) ----------------
# 1) training-position oscillator states for HG/HH  2) LC: long-context dev bits, NET 512 vs HBlearn 512/4096/16384
CTX = 512                                                                                         # NET position table
def find(name): return glob.glob("/kaggle/input/**/" + name, recursive=True)[0]
hb = OLM("HBlearn").to(dev); hb.load_state_dict(torch.load(os.environ.get("HS_HB") or find("harm_HBlearn_best.pt"), map_location=dev)); hb.eval()
W0, KEEP, BW = 128, 64, 512
if TINY: tr = tr[:20000]; BW = 32
n = len(tr); Hs = np.zeros((n, SLOW_DIMS), np.float16); starts = list(range(0, n, KEEP))
for i in range(0, len(starts), BW):
    ss = starts[i:i + BW]; idx = torch.stack([torch.as_tensor(np.pad(tr[max(0, s - KEEP):s + KEEP], (0, max(0, s + KEEP - n) + (KEEP - s if s < KEEP else 0)))) for s in ss]).to(dev)
    f = hstate(hb, idx).float().cpu().numpy()
    for r, s in enumerate(ss):
        o = KEEP if s >= KEEP else 0; m = min(KEEP, n - s); Hs[s:s + m] = f[r, o:o + m]
    if i % (BW * 100) == 0: log(f"states {s:,}/{n:,}")
mu = Hs[::97].astype(np.float32).mean(0); np.save(os.path.join(OUT, "hs_states.npy"), Hs); np.savez(os.path.join(OUT, "hs_proj.npz"), proj=PROJ.numpy(), mu=mu); log("states saved"); del Hs
@torch.no_grad()
def bits_at(model, W):
    out = np.full(len(ho), np.nan, np.float32); stride = W // 2; starts = list(range(0, len(ho) - 1, stride)); B = max(1, 4096 // W)
    if TINY: starts = starts[:6]
    for i in range(0, len(starts), B):
        ss = starts[i:i + B]; idx = torch.stack([torch.as_tensor(np.pad(ho[s:s + W + 1], (0, max(0, s + W + 1 - len(ho))))) for s in ss]).to(dev)
        with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"): lp = F.log_softmax(model(idx[:, :-1]).float(), -1)
        b = (-torch.gather(lp, 2, idx[:, 1:, None])[:, :, 0] / math.log(2)).cpu().numpy()
        for r, s in enumerate(ss):
            lo = 0 if s == 0 else stride; hi = min(W, len(ho) - 1 - s)
            if hi > lo: out[s + 1 + lo:s + 1 + hi] = b[r, lo:hi]
    return out[dvm]
net = TLM("NET").to(dev); net.load_state_dict(torch.load(os.environ.get("HS_NET") or find("ceil_best.pt"), map_location=dev)); net.eval()
R = {"NET512": bits_at(net, 512)}; del net
for W in (512, 4096, 16384): R[f"HB{W}"] = bits_at(hb, W); log(f"HB{W}: {np.nanmean(R[f'HB{W}']):.4f}")
ok = np.all([np.isfinite(v) for v in R.values()], 0); g = np.random.default_rng(0); nb = ok.sum() // 1000
blk = lambda v: v[ok][:nb * 1000].reshape(nb, 1000).mean(1)
res = {k: float(np.mean(v[ok])) for k, v in R.items()}; res["n_words"] = int(ok.sum())
for a_, b_ in (("HB512", "HB4096"), ("NET512", "HB4096"), ("HB4096", "HB16384"), ("NET512", "HB512")):
    d = blk(R[a_]) - blk(R[b_]); bs = [d[g.integers(0, nb, nb)].mean() for _ in range(2000)]
    res[f"{a_} minus {b_}"] = [round(float(d.mean()), 4), round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]
log(json.dumps(res)); json.dump(res, open(os.path.join(OUT, "lc.json"), "w"), indent=1); np.savez_compressed(os.path.join(OUT, "lc_bits.npz"), **R); log("all done")
