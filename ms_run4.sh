cd /c/Users/aezequiel/Desktop/AI_Projects/primasieve
m() { timeout 295 py -3.12 -u -W ignore sieve_mstate.py "$@" 2>&1 | grep -a "MS\|Error\|Trace\|line "; }
for i in 1 2 3; do m assignall 32 1000; done; MS_ALL=1 m mix 32 1000
for i in 1 2 3; do m assignall 32 4000; done; MS_ALL=1 m mix 32 4000
for i in 1 2 3; do m assignall 8 1000; done; MS_ALL=1 m mix 8 1000
for i in 1 2 3 4 5; do m states 128 1000; done; m mix 128 1000
for i in 1 2 3 4; do m assignall 128 1000; done; MS_ALL=1 m mix 128 1000
