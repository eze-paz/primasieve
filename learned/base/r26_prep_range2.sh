#!/bin/bash
# R26 T39 data preparation: components on held-out paragraphs 2,000-2,999 into r26_range2/
export R26_RANGE=2000:3000 R26_OUTDIR=r26_range2
O=r26_range2
t() { echo "== $1 $(date +%T)"; }
t kn2;   timeout 1700 py -3.12 r25_kn2.py --order 5 --mkn --cross --all-text 2>&1 | tail -1
t static; timeout 1700 py -3.12 r25_dyneval.py r25_ch.pt 0 2>&1 | tail -1
t D;     timeout 1700 py -3.12 r25_dyneval.py r25_ch.pt 0.3:0.001:1 --decay --out r26_t02_dyn_probs.npz 2>&1 | tail -1
t W2;    timeout 1700 py -3.12 r25_dyneval.py r25_bg.pt 0.3:0.001:1 --decay --out r26_t13_dyn_probs.npz 2>&1 | tail -1
t W3;    timeout 1700 py -3.12 r25_dyneval.py r25_bq.pt 0.3:0.001:1 --decay --out r26_t13c_bq_dyn_probs.npz 2>&1 | tail -1
t copies; for a in "0.99" "0.999"; do py -3.12 r25_bookcopy.py $a 2>&1 | tail -1; done
for a in "0.9999 1" "0.999 1" "0.9999 2" "0.9999 3"; do py -3.12 r25_bicopy.py $a 2>&1 | tail -1; done
py -3.12 r26_grpcopy.py 0.999 1 2>&1 | tail -1; py -3.12 r26_wnxcopy.py 0.9999 1 2>&1 | tail -1
t B;     timeout 1700 py -3.12 r26_ingroup2.py $O/r26_t02_dyn_probs.npz $O/r26_t02_ingroup2_probs.npz 2>&1 | tail -1
t I;     timeout 1700 py -3.12 r25_ingroup.py $O/r25_dyn_probs.npz 2>&1 | tail -1
t done; ls $O
