# Verifies each factual claim in the run_walios tool description.
# Prints one CLAIM:<name>:<PASS|FAIL>:<detail> line per claim, then a summary.
# Run in the REAL walios (terminal or tool), not the poc page: it needs the
# full bin set the backend manifest mounts.
OUT=/tmp/claims.out; : > $OUT
ok()   { echo "PASS:$1:$2" >> $OUT; }
bad()  { echo "FAIL:$1:$2" >> $OUT; }
have() { command -v "$1" >/dev/null 2>&1; }
cd /tmp 2>/dev/null || true

# --- identity / filesystem ---
[ "$HOME" = /root ] && ok home "$HOME" || bad home "$HOME"
cd /root 2>/dev/null && [ "$PWD" = /root ] && ok cwd-root "$PWD" || bad cwd-root "$PWD"
[ -d /files ] && ok files-dir exists || bad files-dir missing
cd /tmp

# --- node (NEW: not in the current description) ---
have node && ok node-present "$(node -v 2>&1 | head -1)" || bad node-present 127
echo 'const x=1' > /tmp/ok.js
node --check /tmp/ok.js >/dev/null 2>&1 && ok node-check-good "exit 0, silent" || bad node-check-good "nonzero"
printf 'function ( {\n' > /tmp/bad.js
node --check /tmp/bad.js >/dev/null 2>&1 && bad node-check-bad "accepted bad source" || ok node-check-bad "rejected"

# --- claimed absent ---
have jq  && bad no-jq  "jq EXISTS now"  || ok no-jq  absent
have zip && bad no-zip "zip EXISTS now" || ok no-zip absent
have unzip && ok unzip present || bad unzip missing

# --- tar compression flags ---
mkdir -p /tmp/td && echo payload > /tmp/td/f
for f in z j J; do
  tar c${f}f /tmp/t.$f -C /tmp td 2>/dev/null && tar x${f}f /tmp/t.$f -C /tmp/x$f 2>/dev/null
  mkdir -p /tmp/x$f; rm -rf /tmp/x$f; mkdir -p /tmp/x$f
  if tar c${f}f /tmp/t.$f -C /tmp td 2>/dev/null && tar x${f}f /tmp/t.$f -C /tmp/x$f 2>/dev/null && [ -f /tmp/x$f/td/f ]; then
    ok "tar-$f" "round trip"; else bad "tar-$f" "failed"; fi
done

# --- the rest of the claimed program set ---
for p in curl git python3 qjs qjsc soffice ssh make clang nm strip ar ranlib wasm-ld cc; do
  have $p && ok "prog-$p" present || bad "prog-$p" "missing (127)"
done
# present but NOT listed in the description
for p in node lua rustc objdump tlswrap; do
  have $p && ok "unlisted-$p" present || bad "unlisted-$p" absent
done

# --- versions the description asserts ---
git --version 2>&1 | grep -q '2\.45' && ok git-2.45 "$(git --version 2>&1)" || bad git-2.45 "$(git --version 2>&1 | head -1)"

# --- qjsc as a node --check equivalent ---
printf 'function ( {\n' > /tmp/q.js
( cd /tmp && qjsc /tmp/q.js >/tmp/qerr 2>&1 )
if [ $? -ne 0 ] && grep -qi syntaxerror /tmp/qerr; then ok qjsc-syntaxerr "$(head -c 60 /tmp/qerr)"; else bad qjsc-syntaxerr "$(head -c 60 /tmp/qerr)"; fi

# --- qjs std/os are MODULES not globals ---
qjs -e 'std.exit(0)' >/dev/null 2>&1 && bad qjs-std-global "std IS a global" || ok qjs-std-global "not a global, as claimed"
qjs --std -e 'std.exit(0)' >/dev/null 2>&1 && ok qjs-std-flag "--std works" || bad qjs-std-flag "--std failed"

# --- apk ---
apk list >/dev/null 2>&1 && ok apk-list works || bad apk-list failed
for p in bc cpio m4 patch; do
  apk list 2>/dev/null | grep -q "^$p\b" && ok "apk-$p" listed || bad "apk-$p" "not in index"
done

echo "=== FAILURES ==="
grep "^FAIL:" $OUT || echo "(none)"
echo "=== PASSED ==="
grep "^PASS:" $OUT | cut -d: -f2 | tr "
" " "
echo
echo "TOTAL: $(grep -c "^PASS:" $OUT) pass, $(grep -c "^FAIL:" $OUT) fail"
echo "CLAIMS-DONE"
