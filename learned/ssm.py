"""L2_prereg.md: a state-space (gated linear RNN) block that replaces attention in train_lm.LM. The recurrence is
    h_t = (1 - z_t) * h_{t-1} + z_t * g(c_t),   z_t = sigmoid(k_t),  g(.) > 0
(minGRU form); a short depthwise causal convolution in front gives the recurrence local context (as in Mamba).
Per-token inference state: the conv window (3 tokens) and h (e floats per layer) -- no cache that grows with length.

The recurrence can be computed four ways, all giving the same h (checked by `python ssm.py`); they differ only in speed
on the CPU (L2b_prereg.md, bench_scan.py):
  log    -- log-space parallel scan (cumsum + logcumsumexp), the L2 version; memory-bound, slow backward
  chunk  -- linear space in chunks of 16: a 16-step loop inside the chunks, then a 16-step carry across chunks
  loop   -- a plain Python loop over the T positions on (B, e) tensors
  jit    -- the same loop compiled by torch.jit.script"""
import torch, torch.nn as nn, torch.nn.functional as F


def g(x):                                   # continuous, strictly positive candidate (minGRU paper): x+0.5 for x>=0, sigmoid(x) below
    return torch.where(x >= 0, x + 0.5, torch.sigmoid(x))


def log_g(x):
    return torch.where(x >= 0, torch.log(F.relu(x) + 0.5), -F.softplus(-x))


# ---- the four scans: all take the gate pre-activation k and the candidate c, (B, T, D), and return h, (B, T, D)

def scan_log(k, c):
    log_a = F.logsigmoid(-k); log_b = F.logsigmoid(k) + log_g(c)
    a_star = torch.cumsum(log_a, 1)
    return torch.exp(a_star + torch.logcumsumexp(log_b - a_star, 1))


def scan_chunk(k, c, C=16):
    z = torch.sigmoid(k); a = 1 - z; b = z * g(c)
    B, T, D = a.shape; n = T // C
    a = a.view(B, n, C, D); b = b.view(B, n, C, D)
    # unbind once rather than slicing per step: each slice's backward would fill and add a full-size zero tensor
    at = a.unbind(2); bt = b.unbind(2)
    h = bt[0]; loc = [h]
    for t in range(1, C):                                 # inside every chunk at once, from h = 0
        h = at[t] * h + bt[t]; loc.append(h)
    loc = torch.stack(loc, 2)                              # (B, n, C, D)
    A = torch.cumprod(a, 2)                                # products of the forget gates inside the chunk (underflow -> 0 is harmless)
    loc_last = loc[:, :, -1].unbind(1); A_last = A[:, :, -1].unbind(1)
    carry = torch.zeros(B, D, dtype=a.dtype); carries = [carry]
    for j in range(n - 1):                                 # carry the state across chunks
        carry = loc_last[j] + A_last[j] * carry; carries.append(carry)
    carries = torch.stack(carries, 1)                      # (B, n, D): state entering each chunk
    return (loc + A * carries[:, :, None]).view(B, T, D)


def scan_loop(k, c):
    z = torch.sigmoid(k); a = 1 - z; b = z * g(c)
    h = torch.zeros(a.shape[0], a.shape[2], dtype=a.dtype); out = []
    for t in range(a.shape[1]):
        h = a[:, t] * h + b[:, t]; out.append(h)
    return torch.stack(out, 1)


@torch.jit.script
def _loop_jit(a, b):
    h = torch.zeros(a.shape[0], a.shape[2], dtype=a.dtype); out = []
    for t in range(a.shape[1]):
        h = a[:, t] * h + b[:, t]; out.append(h)
    return torch.stack(out, 1)


def scan_jit(k, c):
    z = torch.sigmoid(k)
    return _loop_jit(1 - z, z * g(c))


SCANS = dict(log=scan_log, chunk=scan_chunk, loop=scan_loop, jit=scan_jit)


class SSMBlock(nn.Module):
    def __init__(s, d, expand=1.5, kernel=4, scan="log"):
        super().__init__(); e = int(d * expand); s.e = e; s.k = kernel; s.scan = SCANS[scan]
        s.ln1 = nn.LayerNorm(d); s.inp = nn.Linear(d, 2 * e, bias=False)              # gate pre-activation k and candidate c
        s.conv = nn.Conv1d(2 * e, 2 * e, kernel, groups=2 * e, bias=True)            # depthwise, causal by left padding
        s.outp = nn.Linear(e, d, bias=False)
        s.ln2 = nn.LayerNorm(d); s.fc = nn.Linear(d, 4 * d, bias=False); s.out = nn.Linear(4 * d, d, bias=False)

    def forward(s, x):
        u = s.inp(s.ln1(x))                                                          # (B, T, 2e)
        u = s.conv(F.pad(u.transpose(1, 2), (s.k - 1, 0))).transpose(1, 2)           # causal depthwise conv
        k, c = u.split(s.e, -1)
        x = x + s.outp(s.scan(k, c))
        return x + s.out(F.gelu(s.fc(s.ln2(x))))


if __name__ == "__main__":                 # check every scan against the sequential recurrence, values and gradients
    torch.manual_seed(0); B, T, D = 2, 64, 8
    k0 = torch.randn(B, T, D) * 3; c0 = torch.randn(B, T, D) * 3
    def ref(k, c):
        z = torch.sigmoid(k); hs = torch.zeros(B, D); out = []
        for t in range(T): hs = (1 - z[:, t]) * hs + z[:, t] * g(c[:, t]); out.append(hs)
        return torch.stack(out, 1)
    kr = k0.clone().requires_grad_(); cr = c0.clone().requires_grad_(); r = ref(kr, cr); r.sum().backward()
    for name, fn in SCANS.items():
        kk = k0.clone().requires_grad_(); cc = c0.clone().requires_grad_(); h = fn(kk, cc); h.sum().backward()
        print(f"{name:6s} max abs error vs recurrence: value {(h - r).abs().max().item():.2e}  "
              f"grad k {(kk.grad - kr.grad).abs().max().item():.2e}  grad c {(cc.grad - cr.grad).abs().max().item():.2e}")
