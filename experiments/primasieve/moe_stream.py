"""MoE expert-streaming prototype with prefetch.
Shared/attention weights RESIDENT in RAM; sparse experts STREAMED from disk per token.
Compares:  (A) sequential blocking load   (B) parallel prefetch load   (C) B + LRU cache
Real disk I/O + real numpy compute. Synthetic MoE sized ~8B-total / ~0.5GB-active-per-token
(LFM2.5-8B-A1B-like) so the measured tok/s reflects real streaming, not toy sizes.
Routing locality is a knob (uniform = our granite finding; local = temporal reuse).
"""
import os, time, threading, queue, struct
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# --- config: sized so active-per-token ~0.5GB (int8), total experts ~4GB on disk ---
H=1024; I=2560; L=16; E=32; TOPK=4
DIR="C:/Users/aezequiel/Desktop/AI_Projects/sandpie/experiments/reasoning-library/_experts"
EXPERT_PARAMS=H*I*3                      # w1,w3 (H->I) + w2 (I->H) ~ 3*H*I
EXPERT_BYTES=EXPERT_PARAMS               # int8 = 1 byte/param
print(f"expert={EXPERT_BYTES/1e6:.1f}MB  active/token={TOPK*L*EXPERT_BYTES/1e6:.0f}MB  "
      f"total-experts={E*L*EXPERT_BYTES/1e9:.1f}GB", flush=True)

def gen_experts():
    os.makedirs(DIR, exist_ok=True)
    if os.path.exists(f"{DIR}/L15_E31.bin"): print("experts exist"); return
    print("generating expert files on disk...", flush=True)
    rng=np.random.default_rng(0)
    for l in range(L):
        for e in range(E):
            w=rng.integers(-8,8,size=EXPERT_PARAMS,dtype=np.int8)
            w.tofile(f"{DIR}/L{l}_E{e}.bin")
    print("done", flush=True)

def path(l,e): return f"{DIR}/L{l}_E{e}.bin"
def load_raw(l,e):
    with open(path(l,e),'rb') as f: return np.frombuffer(f.read(),dtype=np.int8)

# --- resident shared weights (attention etc.) small, in RAM ---
Wq=np.random.randn(H,H).astype(np.float32)*0.02
def attention(x):  # cheap resident compute (decode = 1 token)
    return np.tanh(x@Wq)

# --- router with tunable locality ---
class Router:
    def __init__(s, locality): s.loc=locality; s.prev=[None]*L; s.rng=np.random.default_rng(1)
    def pick(s, l):
        if s.prev[l] is not None and s.rng.random()<s.loc:
            # reuse most of previous token's experts (temporal locality)
            keep=s.prev[l][:max(1,TOPK-1)]
            new=[int(s.rng.integers(E))]
            sel=list(dict.fromkeys(list(keep)+new))[:TOPK]
            while len(sel)<TOPK:
                c=int(s.rng.integers(E));
                if c not in sel: sel.append(c)
        else:
            sel=list(s.rng.choice(E,TOPK,replace=False))
        s.prev[l]=sel; return sel

# --- LRU expert cache (bounded RAM) ---
class LRU:
    def __init__(s, budget_mb):
        s.cap=int(budget_mb*1e6/EXPERT_BYTES); s.d={}; s.order=[]; s.hits=0; s.miss=0; s.lock=threading.Lock()
    def get(s,key,loader):
        with s.lock:
            if key in s.d:
                s.hits+=1; s.order.remove(key); s.order.append(key); return s.d[key]
            s.miss+=1
        v=loader()
        with s.lock:
            s.d[key]=v; s.order.append(key)
            while len(s.order)>s.cap:
                k=s.order.pop(0); s.d.pop(k,None)
        return v

def expert_ffn(x, raw):
    # reconstruct 3 matrices from int8 buffer, SwiGLU-ish; compute in fp32 (transient)
    w=raw.astype(np.float32)
    w1=w[:H*I].reshape(H,I); w3=w[H*I:2*H*I].reshape(H,I); w2=w[2*H*I:].reshape(I,H)
    h=np.maximum(x@w1,0)*(x@w3)
    return h@w2

# --- decode loop under 3 strategies ---
def run(strategy, T=16, locality=0.0, cache_mb=512, io_threads=4):
    router=Router(locality); cache=LRU(cache_mb) if strategy=="cache" else None
    pool=ThreadPoolExecutor(max_workers=io_threads) if strategy in ("prefetch","cache") else None
    x=np.random.randn(H).astype(np.float32)
    bytes_read=[0]; rlock=threading.Lock()
    def load(l,e):
        if cache is not None:
            def ldr():
                with rlock: bytes_read[0]+=EXPERT_BYTES
                return load_raw(l,e)
            return cache.get((l,e), ldr)
        with rlock: bytes_read[0]+=EXPERT_BYTES
        return load_raw(l,e)
    t0=time.time()
    for t in range(T):
        for l in range(L):
            x=attention(x)
            sel=router.pick(l)
            if strategy=="sequential":
                raws=[load(l,e) for e in sel]                    # blocking, one by one
            else:
                raws=list(pool.map(lambda e: load(l,e), sel))     # parallel load (saturate NVMe QD)
            acc=np.zeros(H,np.float32)
            for raw in raws: acc+=expert_ffn(x,raw)
            x=x+acc/TOPK
            x=x/ (np.linalg.norm(x)+1e-6)*32
    dt=time.time()-t0
    gb=bytes_read[0]/1e9
    hr = (cache.hits/(cache.hits+cache.miss)) if cache else 0.0
    if pool: pool.shutdown()
    print(f"  {strategy:10} loc={locality:.1f}: {T} tok in {dt:.1f}s = {T/dt:.2f} tok/s | "
          f"disk {gb:.1f}GB @ {gb/dt:.2f} GB/s | cache-hit {hr*100:.0f}%", flush=True)
    return T/dt

if __name__=="__main__":
    gen_experts()
    print("\n=== UNIFORM routing (worst case, ~granite finding) ===")
    run("sequential", locality=0.0)
    run("prefetch",   locality=0.0)
    run("cache",      locality=0.0, cache_mb=512)
    print("\n=== LOCAL routing (temporal reuse, locality=0.7) ===")
    run("sequential", locality=0.7)
    run("prefetch",   locality=0.7)
    run("cache",      locality=0.7, cache_mb=512)
