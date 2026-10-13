Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_chapter.py --steps 6000 --reset 2>&1 | Out-File -Encoding utf8 r25_run_bk_a.txt
& py -3.12 r25_chapter.py --steps 6000 2>&1 | Out-File -Encoding utf8 r25_run_bk_b.txt
"ALLDONE" | Out-File -Encoding utf8 r25_run_bk_done.txt
