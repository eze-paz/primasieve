Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_chapter.py --steps 6000 --groups-file r25_classes_wnx.json --save r25_bq 2>&1 | Out-File -Encoding utf8 r25_run_bq_train.txt
& py -3.12 r25_cm.py B=r25_bq_probs.npz 2>&1 | Out-File -Encoding utf8 r25_run_bq.txt
