Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_rnn.py --minutes 180 --lookup 0 --out r25_rnn_k0.pt --resume --threads 6 2>&1 | Out-File -Encoding utf8 r25_run_ax.txt
