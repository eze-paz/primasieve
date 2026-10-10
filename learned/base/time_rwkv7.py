"""Larger-base feasibility: load an RWKV-7 checkpoint in plain torch, check generation, time forward and forward+backward
with the top K blocks trainable at batch 4 x 256 tokens, and report peak memory.
Run: python learned/base/time_rwkv7.py rwkv7/RWKV-x070-World-1.5B-v3-20250127-ctx4096.pth [--layers 6]"""
import os, sys, time, torch, torch.nn.functional as F
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
from rwkv7 import RWKV7, tokenizer

ck = sys.argv[1]; K = int(sys.argv[sys.argv.index("--layers") + 1]) if "--layers" in sys.argv else 6
t0 = time.time(); m = RWKV7.load(ck); tok = tokenizer(); n = sum(p.numel() for p in m.parameters())
print(f"{os.path.basename(ck)}: {n/1e6:.0f} M params, {m.n_layer} layers x {m.n_embd}, loaded {time.time()-t0:.0f} s", flush=True)
m.eval(); ids = torch.tensor([tok.encode("Story: Mira had a small red boat. Her brother Tomas borrowed it without asking.\n\nQuestion: Who borrowed the boat?\nAnswer:")])
t = time.time(); out = m.greedy(ids, 8, tok=tok); print("greedy:", repr(tok.decode(out)), f"{time.time()-t:.1f} s", flush=True)
x = torch.randint(0, 65536, (4, 256))
with torch.no_grad():
    t = time.time(); m(x); print(f"forward 4x256: {time.time()-t:.1f} s = {1024/(time.time()-t):.0f} tok/s", flush=True)
for p in m.parameters(): p.requires_grad_(False)
params = [p for b in m.blocks[-K:] for p in b.parameters()] + list(m.ln_out.parameters()) + list(m.head.parameters())
for p in params: p.requires_grad_(True)
m.train(); opt = torch.optim.AdamW(params, lr=1e-5)
for i in range(2):
    t = time.time(); loss = F.cross_entropy(m(x).flatten(0, 1), x.flatten()); loss.backward(); opt.step(); opt.zero_grad(set_to_none=True)
    print(f"forward+backward+step (top {K} of {m.n_layer} blocks, {sum(p.numel() for p in params)/1e6:.0f} M trainable) 4x256: {time.time()-t:.1f} s = {1024/(time.time()-t):.0f} tok/s", flush=True)
import psutil; print(f"process RSS {psutil.Process().memory_info().rss/1e9:.1f} GB")
