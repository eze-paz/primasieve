"""L2b_prereg.md: time one full training step (forward, loss, backward, clip, AdamW; batch 32 x 256) of the SSM model for
each scan implementation and width, against the L1 transformer. Run: python learned/bench_scan.py"""
import time, json, torch, torch.nn.functional as F
from train_lm import LM, CFG

torch.manual_seed(0)
x = torch.randint(0, 4097, (32, 256)); y = torch.randint(0, 4097, (32, 256))
rows = []
for name, cfg in [("attn (L1)", dict(arch="attn")), ("ssm log e1.5 (L2)", dict(arch="ssm", scan="log")),
                  ("ssm chunk e1.5", dict(arch="ssm", scan="chunk")), 
                  ("ssm chunk e1.0", dict(arch="ssm", scan="chunk", expand=1.0)),
                  ("ssm log e1.0", dict(arch="ssm", scan="log", expand=1.0))]:
    torch.manual_seed(0); m = LM(**dict(CFG, **cfg)); n = sum(p.numel() for p in m.parameters())
    opt = torch.optim.AdamW(m.parameters(), lr=1e-3)
    def step():
        loss = F.cross_entropy(m(x).flatten(0, 1), y.flatten()); opt.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0); opt.step()
    for _ in range(2): step()
    ts = []
    for _ in range(4): t = time.time(); step(); ts.append(time.time() - t)
    rows.append(dict(model=name, params=n, step_s=round(sorted(ts)[1], 3)))      # second-fastest of four
    print(f"{name:20s} {n / 1e6:.2f} M params  step {rows[-1]['step_s']:.2f} s   (all {[round(t, 2) for t in ts]})", flush=True)
json.dump(rows, open("bench_scan.json", "w"), indent=1)
