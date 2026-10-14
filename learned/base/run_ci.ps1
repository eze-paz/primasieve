Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_chapter.py --steps 6000 --groups-file r25_classes_wnx.json --hidden 256 --save r25_ci 2>&1 | Out-File -Encoding utf8 r25_run_ci.txt
