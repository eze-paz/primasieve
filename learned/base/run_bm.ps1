Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_reservoir.py --n 1024 --tokens 4000000 2>&1 | Out-File -Encoding utf8 r25_run_bm.txt
