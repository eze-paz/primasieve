Set-Location "C:\Users\aezequiel\Desktop\AI_Projects\primasieve\learned\base"
& py -3.12 r25_chapter.py --steps 12000 --groups-file r25_classes_wnx.json --init r25_bu.pt --save r25_cg 2>&1 | Out-File -Encoding utf8 r25_run_cg_train.txt
$env:R25_KN = "r25_kn2_o5mxa.npz"
& py -3.12 r25_cm.py B=r25_cg_probs.npz Y=r25_bookcopy_0.99_probs.npz Z=r25_bookcopy_probs.npz Q=r25_discover2a_probs.npz -drop=W -drop=G 2>&1 | Out-File -Encoding utf8 r25_run_cg.txt
