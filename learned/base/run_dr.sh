#!/bin/bash
# R25-dr: main system + reader on val_fresh12 (scored once). Waits for the set, then: model answers for the new questions
# appended to the 2,510 existing ones (backup kept), main system's adopted configuration with the new set, combination.
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
B=learned/base
until [ -s $B/val_fresh12.json ]; do sleep 30; done; sleep 10
cp $B/b6_rwkv_val_ckpt_read1b.json $B/b6_rwkv_val2510_backup_ckpt_read1b.json
py -3.12 $B/b6_rwkv.py $B/ckpt_read1b.pth --stories $B/val_fresh12.json > $B/r25_run_dr_model.txt 2>&1
cp $B/b6_rwkv_val_ckpt_read1b.json $B/b6_rwkv_valfresh12_ckpt_read1b.json
py -3.12 -c "
import json
a=json.load(open('$B/b6_rwkv_val2510_backup_ckpt_read1b.json',encoding='utf-8')); b=json.load(open('$B/b6_rwkv_valfresh12_ckpt_read1b.json',encoding='utf-8'))
a['items']=a['items']+b['items']; a['right']=sum(x['hit'] for x in a['items']); a['n']=len(a['items'])
json.dump(a,open('$B/b6_rwkv_val_ckpt_read1b.json','w',encoding='utf-8')); print('model items', len(a['items']), 'fresh12 right', b['right'], 'of', b['n'])" >> $B/r25_run_dr_model.txt
F="--learned-q --routes2 --shape-keys --self-shapes --pron-ref --vs-model --disagree --val-more --val-fresh2 --val-practice --val-fresh3 --val-fresh4 --val-fresh5 --val-fresh6 --val-fresh7 --val-fresh8 --val-fresh9 --val-fresh10 --val-fresh12 --reinterp --no-loose --dict --soft --role --role-json --do --time-args --state --did-verb --old-args --diag"
(R25_VEC=r25_vectors_all.npz py -3.12 $B/r24_agree.py $F 2>&1 | grep -v USDT | grep -E "^VAL|^B6 once|^R24|^R25|Traceback|^[A-Za-z]+Error") > $B/r24_diag_dr.txt
cd $B; R25_NAMEONLY=1 R25_DIAG=r24_diag_dr.txt R25_SET=val_fresh12.json R25_OFF=2510 py -3.12 r25_combo.py > r25_run_dr.txt 2>&1
grep -E "model items|R25-dp|Error|Traceback" r25_run_dr_model.txt r25_run_dr.txt
