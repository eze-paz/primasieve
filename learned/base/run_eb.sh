#!/bin/bash
# R25-eb: clean score on val_fresh13 (waits for the file).
cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve; B=learned/base
until [ -s $B/val_fresh13.json ]; do sleep 30; done; sleep 15
cp $B/b6_rwkv_val_ckpt_read1b.json $B/b6_rwkv_val3310_backup_ckpt_read1b.json
py -3.12 $B/b6_rwkv.py $B/ckpt_read1b.pth --stories $B/val_fresh13.json > $B/r25_run_eb_model.txt 2>&1
cp $B/b6_rwkv_val_ckpt_read1b.json $B/b6_rwkv_valfresh13_ckpt_read1b.json
py -3.12 -c "
import json
a=json.load(open('$B/b6_rwkv_val3310_backup_ckpt_read1b.json',encoding='utf-8')); b=json.load(open('$B/b6_rwkv_valfresh13_ckpt_read1b.json',encoding='utf-8'))
a['items']=a['items']+b['items']; a['right']=sum(x['hit'] for x in a['items']); a['n']=len(a['items'])
json.dump(a,open('$B/b6_rwkv_val_ckpt_read1b.json','w',encoding='utf-8')); print('model items', len(a['items']), 'fresh13 right', b['right'], 'of', b['n'])" >> $B/r25_run_eb_model.txt
F="--learned-q --routes2 --shape-keys --self-shapes --pron-ref --vs-model --disagree --val-more --val-fresh2 --val-practice --val-fresh3 --val-fresh4 --val-fresh5 --val-fresh6 --val-fresh7 --val-fresh8 --val-fresh9 --val-fresh10 --val-fresh12 --val-fresh11 --val-practice-ef --val-fresh13 --reinterp --no-loose --dict --soft --role --role-json --do --time-args --state --did-verb --old-args --story-span2 --diag"
(R25_VEC=r25_vectors_all.npz py -3.12 $B/r24_agree.py $F 2>&1 | grep -v USDT | grep -E "^VAL|^B6 once|^R24|^R25|Traceback|^[A-Za-z]+Error") > $B/r24_diag_eb.txt
cd $B; grep -c "^VAL" r24_diag_eb.txt; tail -1 r25_run_eb_model.txt
echo "== val_fresh13 (scored once)"; R25_TRUSTX=2710:3310 R25_NAMEONLY=1 R25_DIAG=r24_diag_eb.txt R25_SET=val_fresh13.json R25_OFF=3310 py -3.12 r25_combo.py 2>&1 | grep -E "R25-d[pu]|Error|Traceback"
