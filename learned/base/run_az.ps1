Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_attn.py --resume --decay --minutes 45 --threads 6 --out r25_attn_az.pt 2>&1 | Out-File -Encoding utf8 r25_run_az_attn.txt
& py -3.12 r25_attn_eval.py --weights r25_attn_az.pt 2>&1 | Out-File -Encoding utf8 -Append r25_run_az_attn.txt
& py -3.12 r25_rnn.py --resume --decay --minutes 45 --lookup 0 --threads 6 --out r25_rnn_az.pt 2>&1 | Out-File -Encoding utf8 r25_run_az_rnn.txt
"ALLDONE" | Out-File -Encoding utf8 r25_run_az_done.txt
