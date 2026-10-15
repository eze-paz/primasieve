#!/bin/bash
# R25-dv: model answers for val_fresh11 appended (after the 2,710), main system with val_fresh11 appended, trust on 710 + val_fresh11, val_fresh12 scored once.
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve; B=learned/base
cp $B/b6_rwkv_val_ckpt_read1b.json $B/b6_rwkv_val2710_backup_ckpt_read1b.json
py -3.12 $B/b6_rwkv.py $B/ckpt_read1b.pth --stories $B/val_fresh11.json > $B/r25_run_dv_model.txt 2>&1
cp $B/b6_rwkv_val_ckpt_read1b.json $B/b6_rwkv_valfresh11_ckpt_read1b.json
py -3.12 -c "
import json
a=json.load(open('$B/b6_rwkv_val2710_backup_ckpt_read1b.json',encoding='utf-8')); b=json.load(open('$B/b6_rwkv_valfresh11_ckpt_read1b.json',encoding='utf-8'))
a['items']=a['items']+b['items']; a['right']=sum(x['hit'] for x in a['items']); a['n']=len(a['items'])
json.dump(a,open('$B/b6_rwkv_val_ckpt_read1b.json','w',encoding='utf-8')); print('model items', len(a['items']), 'fresh11 right', b['right'], 'of', b['n'])" >> $B/r25_run_dv_model.txt
F="--learned-q --routes2 --shape-keys --self-shapes --pron-ref --vs-model --disagree --val-more --val-fresh2 --val-practice --val-fresh3 --val-fresh4 --val-fresh5 --val-fresh6 --val-fresh7 --val-fresh8 --val-fresh9 --val-fresh10 --val-fresh12 --val-fresh11 --reinterp --no-loose --dict --soft --role --role-json --do --time-args --state --did-verb --old-args --diag"
(R25_VEC=r25_vectors_all.npz py -3.12 $B/r24_agree.py $F 2>&1 | grep -v USDT | grep -E "^VAL|^B6 once|^R24|^R25|Traceback|^[A-Za-z]+Error") > $B/r24_diag_dv.txt
cd $B; grep -c "^VAL" r24_diag_dv.txt
R25_TRUSTX=2710:2910 R25_NAMEONLY=1 R25_DIAG=r24_diag_dv.txt R25_SET=val_fresh12.json R25_OFF=2510 py -3.12 r25_combo.py 2>&1 | grep -E "R25-d[pu]|Error|Traceback"
