Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_rnn.py --minutes 75 --lookup 4 --out r25_rnn_k4.pt --threads 6 > r25_run_aw_a.txt 2> r25_run_aw_a_err.txt
& py -3.12 r25_rnn.py --minutes 75 --lookup 0 --out r25_rnn_k0.pt --threads 6 > r25_run_aw_b.txt 2> r25_run_aw_b_err.txt
"ALLDONE" | Out-File r25_run_aw_done.txt
