"""L2_prereg.md: a state-space (gated linear RNN) block that replaces attention in train_lm.LM. The recurrence is
    h_t = (1 - z_t) * h_{t-1} + z_t * g(c_t),   z_t = sigmoid(k_t),  g(.) > 0
(minGRU form) computed for the whole sequence at once by a log-space parallel scan, so training is O(T) with no Python
loop over time; a short depthwise causal convolution in front gives the recurrence local context (as in Mamba).
Per-token inference state: the conv window (3 tokens) and h (e floats per layer) -- no cache that grows with length."""
import torch, torch.nn as nn, torch.nn.functional as F


def g(x):                                   # continuous, strictly positive candidate (minGRU paper): x+0.5 for x>=0, sigmoid(x) below
    return torch.where(x >= 0, x + 0.5, torch.sigmoid(x))


def log_g(x):
    return torch.where(x >= 0, torch.log(F.relu(x) + 0.5), -F.softplus(-x))


def scan(log_a, log_b):
    """h_t = sum_{s<=t} (prod_{r=s+1..t} a_r) b_s with h_0 = 0, in log space: a_star_t = cumsum(log a);
    h_t = exp(a_star_t) * sum_{s<=t} exp(log b_s - a_star_s). Stable through logcumsumexp."""
    a_star = torch.cumsum(log_a, 1)
    return torch.exp(a_star + torch.logcumsumexp(log_b - a_star, 1))


class SSMBlock(nn.Module):
    def __init__(s, d, expand=1.5, kernel=4):
        super().__init__(); e = int(d * expand); s.e = e; s.k = kernel
        s.ln1 = nn.LayerNorm(d); s.inp = nn.Linear(d, 2 * e, bias=False)              # gate pre-activation k and candidate c
        s.conv = nn.Conv1d(2 * e, 2 * e, kernel, groups=2 * e, bias=True)            # depthwise, causal by left padding
        s.outp = nn.Linear(e, d, bias=False)
        s.ln2 = nn.LayerNorm(d); s.fc = nn.Linear(d, 4 * d, bias=False); s.out = nn.Linear(4 * d, d, bias=False)

    def forward(s, x):
        u = s.inp(s.ln1(x))                                                          # (B, T, 2e)
        u = s.conv(F.pad(u.transpose(1, 2), (s.k - 1, 0))).transpose(1, 2)           # causal depthwise conv
        k, c = u.split(s.e, -1)
        log_a = F.logsigmoid(-k)                                                     # log(1 - z)
        log_b = F.logsigmoid(k) + log_g(c)                                           # log(z * g(c))
        h = scan(log_a, log_b)
        x = x + s.outp(h)
        return x + s.out(F.gelu(s.fc(s.ln2(x))))


if __name__ == "__main__":                 # check the scan against the sequential recurrence
    torch.manual_seed(0); B, T, D = 2, 50, 8
    k = torch.randn(B, T, D); c = torch.randn(B, T, D)
    h = scan(F.logsigmoid(-k), F.logsigmoid(k) + log_g(c))
    z = torch.sigmoid(k); hs = torch.zeros(B, D); ref = []
    for t in range(T):
        hs = (1 - z[:, t]) * hs + z[:, t] * g(c[:, t]); ref.append(hs)
    ref = torch.stack(ref, 1)
    print("max abs error scan vs recurrence:", (h - ref).abs().max().item())
