#!/bin/bash
# R25-dx: model answers for practice E and F appended (after 2,910), main system with E+F appended, trust on 710 + val_fresh11 + E + F; val_fresh12 and val_fresh10 reported.
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve; B=learned/base
F="--learned-q --routes2 --shape-keys --self-shapes --pron-ref --vs-model --disagree --val-more --val-fresh2 --val-practice --val-fresh3 --val-fresh4 --val-fresh5 --val-fresh6 --val-fresh7 --val-fresh8 --val-fresh9 --val-fresh10 --val-fresh12 --val-fresh11 --val-practice-ef --reinterp --no-loose --dict --soft --role --role-json --do --time-args --state --did-verb --old-args --story-span --diag"
(R25_VEC=r25_vectors_all.npz py -3.12 $B/r24_agree.py $F 2>&1 | grep -v USDT | grep -E "^VAL|^B6 once|^R24|^R25|Traceback|^[A-Za-z]+Error") > $B/r24_diag_dy.txt
cd $B; grep -c "^VAL" r24_diag_dy.txt
echo "== val_fresh12"; R25_TRUSTX=2710:3310 R25_NAMEONLY=1 R25_DIAG=r24_diag_dy.txt R25_SET=val_fresh12.json R25_OFF=2510 py -3.12 r25_combo.py 2>&1 | grep -E "R25-d[pu]|Error|Traceback"
echo "== val_fresh10"; R25_TRUSTX=2710:3310 R25_NAMEONLY=1 R25_DIAG=r24_diag_dy.txt R25_SET=val_fresh10.json R25_OFF=2310 py -3.12 r25_combo.py 2>&1 | grep -E "R25-d[pu]|Error|Traceback"
