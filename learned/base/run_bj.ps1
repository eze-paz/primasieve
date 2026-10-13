Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_rnn.py --groups --oov-groups --lookup 0 --steps 6000 --eval-paras 1000 --fast --threads 6 --out r25_bj.pt 2>&1 | Out-File -Encoding utf8 r25_run_bj.txt
