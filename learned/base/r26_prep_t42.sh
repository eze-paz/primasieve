#!/bin/bash
for N in "r25_bu.pt:w4" "r25_cg.pt:w5"; do
  CK=${N%%:*}; T=${N##*:}
  for R in 0 1 2; do
    if [ $R = 0 ]; then E=""; D="."; else a=$((R*1000)); b=$((R*1000+1000)); E="R26_RANGE=$a:$b R26_OUTDIR=r26_range$R"; D=r26_range$R; fi
    echo "== $T range$R $(date +%T)"
    [ -f $D/r26_${T}_dyn_probs.npz ] || env $E timeout 1700 py -3.12 r25_dyneval.py $CK 0.3:0.001:1 --decay --out r26_${T}_dyn_probs.npz 2>&1 | tail -1
    [ -f $D/r26_${T}_ingroup_probs.npz ] || env $E timeout 1700 py -3.12 r26_ingroup2.py $D/r26_${T}_dyn_probs.npz $D/r26_${T}_ingroup_probs.npz 2>&1 | tail -1
  done
done
echo "== done"
