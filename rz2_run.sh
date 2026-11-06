#!/bin/bash
# RZ2 pipeline: every python run stops itself after ~4 minutes and resumes on the next call
cd "$(dirname "$0")"
run() { local f=$1; shift; for i in $(seq 1 12); do [ -f "mtest/$f" ] && return 0; env "$@" py -3.12 -I sieve_mtz.py $CMD $C 2>&1 | tail -2; done; }
for C in books wiki; do
  CMD=fit run ${C}_rz_phi_k256.npz RZ_K=256
  CMD=infer run ${C}_rz_k64w256n8.npz RZ_K=64 RZ_WIN=256 RZ_NS=8
  CMD=infer run ${C}_rz_k64w1024n8.npz RZ_K=64 RZ_WIN=1024 RZ_NS=8
  CMD=infer run ${C}_rz_k256w1024n8.npz RZ_K=256 RZ_WIN=1024 RZ_NS=8
done
echo RZ2 pipeline finished
