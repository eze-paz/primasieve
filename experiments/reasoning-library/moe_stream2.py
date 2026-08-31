"""MoE expert-streaming v2: SINGLE PACKED FILE + os.pread by offset (no per-expert open).
This is how real weight streaming works (safetensors = one mmap'd file). Compares
sequential-pread vs parallel-pread(prefetch) vs +LRU cache, uniform vs local routing.
"""
import os, time, threading, mmap
import numpy as np
from concurrent.futures import ThreadPoolExecutor

H=1024; I=2560; L=16; E=32; TOPK=4
EXPERT_BYTES=H*I*3
PACK="C:/Users/aezequiel/Desktop/AI_Projects/sandpie/experiments/reasoning-library/_experts.pack"
NEXP=L*E
def off(l,e): return (l*E+e)*EXPERT_BYTES

def gen_pack():
    if os.path.exists(PACK) and os.path.getsize(PACK)==NEXP*EXPERT_BYTES:
        print("pack exists"); return
    print(f"generating single packed file {NEXP*EXPERT_BYTES/1e9:.1f}GB ...", flush=True)
    rng=np.random.default_rng(0)
    with open(PACK,'wb',buffering=1024*1024) as f:
        for _ in range(NEXP):
            f.write(rng.integers(-8,8,size=EXPERT_BYTES,dtype=np.int8).tobytes())
    print("done", flush=True)

Wq=np.random.randn(H,H).astype(np.float32)*0.02
def attention(x): return np.tanh(x@Wq)

class Router:
    def __init__(s,loc): s.loc=loc; s.prev=[None]*L; s.rng=np.random.default_rng(1)
    def pick(s,l):
        if s.prev[l] is not None and s.rng.random()<s.loc:
            sel=list(s.prev[l][:TOPK-1]);
            while len(sel)<TOPK:
                c=int(s.rng.integers(E));
                if c not in sel: sel.append(c)
        else:
            sel=list(s.rng.choice(E,TOPK,replace=False))
        s.prev[l]=sel; return sel

class LRU:
    def __init__(s,mb): s.cap=int(mb*1e6/EXPERT_BYTES); s.d={}; s.o=[]; s.hits=0; s.miss=0; s.lk=threading.Lock()
    def get(s,k,ldr):
        with s.lk:
            if k in s.d: s.hits+=1; s.o.remove(k); s.o.append(k); return s.d[k]
            s.miss+=1
        v=ldr()
        with s.lk:
            s.d[k]=v; s.o.append(k)
            while len(s.o)>s.cap: s.d.pop(s.o.pop(0),None)
        return v

def ffn(x,raw):
    w=raw.astype(np.float32)
    w1=w[:H*I].reshape(H,I); w3=w[H*I:2*H*I].reshape(H,I); w2=w[2*H*I:].reshape(I,H)
    return (np.maximum(x@w1,0)*(x@w3))@w2

def run(strategy, mm, T=16, locality=0.0, cache_mb=768, io_threads=6):
    router=Router(locality); cache=LRU(cache_mb) if strategy=="cache" else None
    pool=ThreadPoolExecutor(max_workers=io_threads) if strategy in ("prefetch","cache") else None
    x=np.random.randn(H).astype(np.float32); br=[0]; lk=threading.Lock()
    def pread(l,e):
        with lk: br[0]+=EXPERT_BYTES
        o=off(l,e)
        return np.frombuffer(mm[o:o+EXPERT_BYTES],dtype=np.int8)  # mmap slice = page-fault disk read
    def load(l,e):
        if cache is not None: return cache.get((l,e), lambda: pread(l,e))
        return pread(l,e)
    t0=time.time()
    for t in range(T):
        for l in range(L):
            x=attention(x); sel=router.pick(l)
            raws=[load(l,e) for e in sel] if strategy=="sequential" else list(pool.map(lambda e: load(l,e), sel))
            acc=np.zeros(H,np.float32)
            for raw in raws: acc+=ffn(x,raw)
            x=x+acc/TOPK; x=x/(np.linalg.norm(x)+1e-6)*32
    dt=time.time()-t0; gb=br[0]/1e9
    hr=(cache.hits/(cache.hits+cache.miss)) if cache else 0.0
    if pool: pool.shutdown()
    print(f"  {strategy:10} loc={locality:.1f}: {T/dt:.2f} tok/s | disk {gb:.1f}GB @ {gb/dt:.2f} GB/s | "
          f"cache-hit {hr*100:.0f}% | {dt:.1f}s", flush=True)

if __name__=="__main__":
    gen_pack()
    f=open(PACK,'rb'); mm=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
    print("\n=== single-file mmap, UNIFORM routing ===")
    run("sequential",mm,locality=0.0); run("prefetch",mm,locality=0.0); run("cache",mm,locality=0.0)
    print("=== single-file mmap, LOCAL routing (0.7) ===")
    run("sequential",mm,locality=0.7); run("prefetch",mm,locality=0.7); run("cache",mm,locality=0.7)
    mm.close(); f.close()
    print("\n(compare to v1 small-files: 0.33-0.38 tok/s @ 0.16-0.19 GB/s)")
