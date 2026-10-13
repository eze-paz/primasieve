Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_chapter.py --steps 12000 --groups-file r25_classes_wnx.json --save r25_bu 2>&1 | Out-File -Encoding utf8 r25_run_bu_train.txt
& py -3.12 r25_cm.py B=r25_bu_probs.npz Y=r25_bookcopy_0.99_probs.npz Z=r25_bookcopy_probs.npz -drop=W 2>&1 | Out-File -Encoding utf8 r25_run_bu.txt
