#!/bin/bash
for W in "r26_t13_dyn_probs.npz:r26_t13_ingroup_probs.npz" "r26_t13c_bq_dyn_probs.npz:r26_t13c_ingroup_probs.npz"; do
  IN=${W%%:*}; OUT=${W##*:}
  echo "== main $OUT $(date +%T)"; timeout 1700 py -3.12 r26_ingroup2.py $IN $OUT 2>&1 | tail -1
  for R in 1 2; do
    a=$((R*1000)); b=$((R*1000+1000)); echo "== range$R $OUT $(date +%T)"
    R26_RANGE=$a:$b R26_OUTDIR=r26_range$R timeout 1700 py -3.12 r26_ingroup2.py r26_range$R/$IN r26_range$R/$OUT 2>&1 | tail -1
  done
done
echo "== done"
