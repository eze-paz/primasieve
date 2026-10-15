#!/bin/bash
# R25-dx: model answers for practice E and F appended (after 2,910), main system with E+F appended, trust on 710 + val_fresh11 + E + F; val_fresh12 and val_fresh10 reported.
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve; B=learned/base
until [ -s $B/val_practice_f.json ] && [ -s $B/val_practice_e.json ]; do sleep 30; done; sleep 10
py -3.12 -c "
import json; a=json.load(open('$B/val_practice_e.json',encoding='utf-8')); b=json.load(open('$B/val_practice_f.json',encoding='utf-8'))
json.dump({'note':'R25-dx: E + F','stories':a['stories']+b['stories']},open('$B/val_practice_ef.json','w',encoding='utf-8'))"
cp $B/b6_rwkv_val_ckpt_read1b.json $B/b6_rwkv_val2910_backup_ckpt_read1b.json
py -3.12 $B/b6_rwkv.py $B/ckpt_read1b.pth --stories $B/val_practice_ef.json > $B/r25_run_dx_model.txt 2>&1
cp $B/b6_rwkv_val_ckpt_read1b.json $B/b6_rwkv_valef_ckpt_read1b.json
py -3.12 -c "
import json
a=json.load(open('$B/b6_rwkv_val2910_backup_ckpt_read1b.json',encoding='utf-8')); b=json.load(open('$B/b6_rwkv_valef_ckpt_read1b.json',encoding='utf-8'))
a['items']=a['items']+b['items']; a['right']=sum(x['hit'] for x in a['items']); a['n']=len(a['items'])
json.dump(a,open('$B/b6_rwkv_val_ckpt_read1b.json','w',encoding='utf-8')); print('model items', len(a['items']), 'E+F right', b['right'], 'of', b['n'])" >> $B/r25_run_dx_model.txt
F="--learned-q --routes2 --shape-keys --self-shapes --pron-ref --vs-model --disagree --val-more --val-fresh2 --val-practice --val-fresh3 --val-fresh4 --val-fresh5 --val-fresh6 --val-fresh7 --val-fresh8 --val-fresh9 --val-fresh10 --val-fresh12 --val-fresh11 --val-practice-ef --reinterp --no-loose --dict --soft --role --role-json --do --time-args --state --did-verb --old-args --diag"
(R25_VEC=r25_vectors_all.npz py -3.12 $B/r24_agree.py $F 2>&1 | grep -v USDT | grep -E "^VAL|^B6 once|^R24|^R25|Traceback|^[A-Za-z]+Error") > $B/r24_diag_dx.txt
cd $B; grep -c "^VAL" r24_diag_dx.txt
echo "== val_fresh12"; R25_TRUSTX=2710:3310 R25_NAMEONLY=1 R25_DIAG=r24_diag_dx.txt R25_SET=val_fresh12.json R25_OFF=2510 py -3.12 r25_combo.py 2>&1 | grep -E "R25-d[pu]|Error|Traceback"
echo "== val_fresh10"; R25_TRUSTX=2710:3310 R25_NAMEONLY=1 R25_DIAG=r24_diag_dx.txt R25_SET=val_fresh10.json R25_OFF=2310 py -3.12 r25_combo.py 2>&1 | grep -E "R25-d[pu]|Error|Traceback"
