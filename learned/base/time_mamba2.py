"""step 1 of the subtractive plan: Mamba-2 370M (Pile) on the CPU in plain torch via transformers; time forward and backward."""
import time, torch, sys
from transformers import AutoTokenizer, AutoModelForCausalLM
name = sys.argv[1] if len(sys.argv) > 1 else "AntonV/mamba2-370m-hf"
t0 = time.time(); tok = AutoTokenizer.from_pretrained(name); m = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.float32)
n = sum(p.numel() for p in m.parameters()); print(f"{name}: {n/1e6:.0f} M params, loaded in {time.time()-t0:.0f} s; threads {torch.get_num_threads()}", flush=True)
m.eval()
ids = tok("It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of", return_tensors="pt").input_ids
with torch.no_grad():
    t = time.time(); out = m.generate(ids, max_new_tokens=30, do_sample=False); dt = time.time() - t
print("generate:", repr(tok.decode(out[0, ids.shape[1]:])), f"({30/dt:.1f} tok/s)", flush=True)
x = torch.randint(0, 50000, (4, 512))
for label, train in (("forward", False), ("forward+backward", True)):
    m.train(train); ts = []
    for i in range(3):
        t = time.time()
        if train: loss = m(input_ids=x, labels=x).loss; loss.backward(); m.zero_grad(set_to_none=True)
        else:
            with torch.no_grad(): m(input_ids=x)
        ts.append(time.time() - t)
    print(f"{label}: batch 4 x 512 -> {sorted(ts)[1]:.2f} s = {4*512/sorted(ts)[1]:.0f} tok/s", flush=True)
