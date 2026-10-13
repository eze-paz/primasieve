Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_rnn.py --lookup 0 --steps 2000 --eval-paras 1000 --fast --threads 6 --out r25_be_a.pt 2>&1 | Out-File -Encoding utf8 r25_run_be_a.txt
& py -3.12 r25_rnn.py --groups --lookup 0 --steps 2000 --eval-paras 1000 --fast --threads 6 --out r25_be_b.pt 2>&1 | Out-File -Encoding utf8 r25_run_be_b.txt
& py -3.12 r25_rnn.py --groups --lookup 0 --steps 6000 --eval-paras 1000 --fast --threads 6 --out r25_be_c.pt 2>&1 | Out-File -Encoding utf8 r25_run_be_c.txt
"ALLDONE" | Out-File -Encoding utf8 r25_run_be_done.txt
