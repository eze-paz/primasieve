Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_rnn.py --hidden 384 --steps 8288 --lookup 0 --threads 6 --out r25_rnn_h384.pt 2>&1 | Out-File -Encoding utf8 r25_run_bb.txt
