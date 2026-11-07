#!/bin/bash
# PS pipeline: each python run stops itself before ~4.5 minutes and resumes on the next call
cd "$(dirname "$0")"
for C in books wiki; do
  [ -f mtest/${C}_ps_prep.npz ] || py -3.12 -I sieve_mts.py prep $C
  [ -f mtest/${C}_base_content.npz ] || MT_EVAL=content MT_BASEONLY=1 py -3.12 -I sieve_mtest.py eval $C
  for K in 256 1024 4096 16384; do
    for i in $(seq 1 30); do py -3.12 -I sieve_mts.py fit $C $K | tail -1 | tee /dev/stderr | grep -q "done" && break; done
    [ -f mtest/${C}_ps_S$K.npz ] || py -3.12 -I sieve_mts.py score $C $K
  done
  py -3.12 -I sieve_mts.py curve $C
done
echo PS pipeline finished
