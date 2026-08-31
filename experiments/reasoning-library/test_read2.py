"""Cleaner NVMe read-bandwidth test: buffered + multi-threaded, on COLD data
(middle of the 65GB WSL vhdx, >> RAM so uncached). Read-only, no modification.
"""
import time, threading
VHDX="C:/Users/aezequiel/AppData/Local/wsl/{15d48759-7041-4720-b977-56f7bc9b0a86}/ext4.vhdx"
GB=1024**3

def read_range(off, nbytes, chunk=64*1024*1024):
    got=0
    with open(VHDX,'rb') as f:      # default buffering -> OS read-ahead
        f.seek(off)
        while got<nbytes:
            b=f.read(min(chunk, nbytes-got))
            if not b: break
            got+=len(b)
    return got

# single-threaded, 10 GB from offset 25 GB (cold region)
t0=time.time(); n=read_range(25*GB, 10*GB); dt=time.time()-t0
print(f"1-thread buffered: {n/GB:.1f} GB in {dt:.1f}s = {n/1e6/dt:.0f} MB/s ({n/1e9/dt:.2f} GB/s)", flush=True)

# 4 threads, each 4 GB from spread-out cold offsets (probe queue-depth scaling)
res=[0]*4; offs=[8,18,30,42]
def worker(i): res[i]=read_range(offs[i]*GB, 4*GB)
t0=time.time()
ths=[threading.Thread(target=worker,args=(i,)) for i in range(4)]
for t in ths: t.start()
for t in ths: t.join()
dt=time.time()-t0; tot=sum(res)
print(f"4-thread buffered: {tot/GB:.1f} GB in {dt:.1f}s = {tot/1e6/dt:.0f} MB/s ({tot/1e9/dt:.2f} GB/s)", flush=True)
