"""R3c selection and test, directory-independent. Scores every kept checkpoint ckpt_<tag>_s*.pth on the validation set
(r3_val_v3.json), picks the best (ties -> fewer steps), then runs the registered tests ONCE on it:
r3_b6real_v3, r3_counter_v3, plain B6, mismatch. Run: python learned/base/r3c_select.py read3c"""
import os, sys, re, io, glob, json, contextlib
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
import eval_r3, b6_rwkv

tag = sys.argv[1] if len(sys.argv) > 1 else "read3c"
cks = sorted(glob.glob(f"ckpt_{tag}_s*.pth"), key=lambda p: int(re.search(r"_s(\d+)", p).group(1)))
lines = []; scores = []
for ck in cks:
    sys.argv = ["eval_r3.py", ck, "--set", "val_v3"]; buf = io.StringIO()
    with contextlib.redirect_stdout(buf): eval_r3.main()
    line = [l for l in buf.getvalue().splitlines() if l.startswith("R3")][0]; right = int(re.search(r": (\d+)/", line).group(1))
    scores.append((right, -int(re.search(r"_s(\d+)", ck).group(1)), ck)); lines.append("val " + line); print("val", line, flush=True)
best = max(scores)[2]; lines.append(f"selected {best}"); print("selected", best, flush=True)
for name in ("b6real_v3", "counter_v3"):
    sys.argv = ["eval_r3.py", best, "--set", name]; buf = io.StringIO()
    with contextlib.redirect_stdout(buf): eval_r3.main()
    lines += [l for l in buf.getvalue().splitlines() if l.startswith("R3")]
for extra in ([], ["--mismatch"]):
    sys.argv = ["b6_rwkv.py", best] + extra; b6_rwkv.CK = best; buf = io.StringIO()
    with contextlib.redirect_stdout(buf): b6_rwkv.main()
    lines += [l for l in buf.getvalue().splitlines() if l.startswith(("B6", "mismatch"))]
open(f"{tag}_select.out", "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
