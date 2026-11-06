import subprocess, os, glob, time
def sh(c, t=None):
    print("$", c, flush=True); t0 = time.time()
    try: r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t); print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
    except subprocess.TimeoutExpired: print("TIMEOUT", flush=True)
    print(f"[{time.time() - t0:.0f} s]", flush=True)
sh("git clone --depth 1 https://github.com/hxim/paq8px.git /tmp/paq8px && cd /tmp/paq8px && git log -1 --format='%H %cd'")
sh("mkdir -p /tmp/paq8px/b && cd /tmp/paq8px/b && cmake .. -DCMAKE_BUILD_TYPE=Release > /dev/null && make -j4 2>&1 | tail -3; ls /tmp/paq8px/b")
os.makedirs("/kaggle/working/out", exist_ok=True)
for f in sorted(glob.glob("/kaggle/input/**/*.bin", recursive=True), key=os.path.getsize):
    nm = os.path.basename(f); sh(f"cp {f} /tmp/{nm} && cd /tmp && /tmp/paq8px/b/paq8px -8 {nm} /kaggle/working/out/{nm}.paq8px > /dev/null; ls -l /kaggle/working/out/{nm}.paq8px", t=295)
