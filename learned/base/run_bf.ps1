Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_rnn.py --groups --groups-file r25_classes_wn.json --lookup 0 --steps 2000 --eval-paras 1000 --fast --threads 3 --out r25_bf_wn.pt 2>&1 | Out-File -Encoding utf8 r25_run_bf_wn.txt
& py -3.12 r25_rnn.py --groups --groups-file r25_classes_wnx.json --lookup 0 --steps 2000 --eval-paras 1000 --fast --threads 3 --out r25_bf_wnx.pt 2>&1 | Out-File -Encoding utf8 r25_run_bf_wnx.txt
"ALLDONE" | Out-File -Encoding utf8 r25_run_bf_done.txt
