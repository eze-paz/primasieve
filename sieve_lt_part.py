# ---------------- LT (sieve_lang_prereg.md LTJT): appended to sieve_harm_kernel.py (HARM_ARMS=HBlearn, HARM_CTX=4096, HARM_GEN=1) ----------------
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
lt = OLM("HBlearn").to(dev); lt.load_state_dict(torch.load(os.path.join(OUT, "harm_HBlearn_best.pt"), map_location=dev)); lt.eval(); R = {}
for W in (512, 4096, 16384): R[f"LT{W}"] = bits_at(lt, W); log(f"LT{W}: {np.nanmean(R[f'LT{W}']):.4f}")
np.savez_compressed(os.path.join(OUT, "lt_bits.npz"), **R); json.dump({k: float(np.nanmean(v)) for k, v in R.items()}, open(os.path.join(OUT, "lt.json"), "w")); log("lt done")
