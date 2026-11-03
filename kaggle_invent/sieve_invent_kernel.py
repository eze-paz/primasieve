"""Kaggle CPU kernel for invent_prereg.md lever 2: assemble the engine from two datasets (primasieve-lx-tokens: token
arrays; primasieve-sieve-code: code, trees, states), then chain checkpointed `sieve_invent.py search` runs for ~10.5 h
under SZ_FRESH=10, SZ_SCALE=4, 4 processes; finally score base / hand / search on "eval" (the 50,114 positions) and
"fresh". Everything that matters is copied to /kaggle/working (state json, logs, per-position bits)."""
import os, sys, glob, shutil, subprocess, time, json
T0 = time.time(); HOURS = float(os.environ.get("INVENT_HOURS", "10.5")); TAG = os.environ.get("INVENT_TAG", "a"); SEED = os.environ.get("INVENT_SEED", "0")
W = "/kaggle/working"; ENG = os.path.join(W, "eng"); LX = os.path.join(ENG, "learned", "lx"); os.makedirs(LX, exist_ok=True)
def find(name):
    hits = glob.glob(f"/kaggle/input/**/{name}", recursive=True); assert hits, f"missing {name}"; return hits[0]
code = os.path.dirname(find("sieve_invent.py"))
for f in glob.glob(os.path.join(code, "*.py")) + glob.glob(os.path.join(code, "*.json")): shutil.copy(f, ENG)
shutil.copytree(os.path.join(code, "core"), os.path.join(ENG, "core"), dirs_exist_ok=True)
for nm in ("lx_tokens.npz", "lx_library.npz", "lx_docs.npz", "lx_vocab.json", "sieve_forms_labels.npy", "lx_library_books.npz"): os.symlink(find(nm), os.path.join(LX, nm))
os.makedirs(os.path.join(LX, "sieve_tree"), exist_ok=True)
for f in glob.glob(os.path.join(code, "sieve_tree", "*")): shutil.copy(f, os.path.join(LX, "sieve_tree"))
os.makedirs(os.path.join(ENG, "kaggle_fair_control"), exist_ok=True)
env = dict(os.environ, SZ_EXACT="1", SZ_FRESH="10", SZ_SCALE=os.environ.get("INVENT_SCALE", "4"), SZ_NPROC="4", SZ_SEED=SEED, PYTHONUNBUFFERED="1")
LOG = open(os.path.join(W, f"sieve_invent_{TAG}_run.txt"), "a")
def run(args, budget):
    cmd = [sys.executable, "-W", "ignore", "sieve_invent.py"] + args; t = time.time()
    p = subprocess.run(cmd, cwd=ENG, env=env, capture_output=True, text=True, timeout=budget)
    out = "\n".join(l for l in (p.stdout + p.stderr).splitlines() if not l.startswith(("weight terms", "trust terms")))
    print(out, flush=True); LOG.write(out + "\n"); LOG.flush(); return p.returncode, time.time() - t
print(f"engine assembled ({time.time() - T0:.0f} s); cpu {os.cpu_count()}", flush=True)
rc, dt = run(["smoke"], 1800); print(f"smoke rc {rc} in {dt:.0f} s", flush=True)
n = 0
while time.time() - T0 < HOURS * 3600 - 2400:
    rc, dt = run(["search", TAG], 3600); n += 1
    shutil.copy(os.path.join(ENG, f"sieve_invent_{TAG}.json"), W)
    print(f"--- run {n} rc {rc} {dt:.0f} s; elapsed {(time.time() - T0) / 3600:.2f} h", flush=True)
    if rc != 0 and n > 3: break
for st in ("sieve_onto_base.json", "sieve_onto_all.json", f"sieve_invent_{TAG}.json"):
    for cx in ("eval", "fresh"):
        if time.time() - T0 > HOURS * 3600 + 3000: break
        run(["eval", st, cx], 2400)
for f in glob.glob(os.path.join(ENG, "kaggle_fair_control", "bits_*.npz")): shutil.copy(f, W)
print(f"done: {n} search runs ({(time.time() - T0) / 3600:.2f} h)", flush=True)
