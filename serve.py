# Thin launcher — the actual proxy lives inline in sandpie.html as
# <script id="serve-py-source">. This file just extracts that block and
# execs it, so there's only ever ONE source of truth. Do not add proxy
# logic here; edit the inline copy in sandpie.html instead.
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, 'sandpie.html')
if not os.path.isfile(HTML):
    sys.exit(f'sandpie.html not found next to serve.py (looked in {HERE})')

src = open(HTML, encoding='utf-8').read()
m = re.search(r'<script id="serve-py-source"[^>]*>(.*?)</script>', src, re.S)
if not m:
    sys.exit('could not find <script id="serve-py-source"> in sandpie.html')

# __file__ override so os.path.dirname(__file__) inside the embedded code
# resolves to this directory (needed for SHELL_CWD / os.chdir at the bottom).
exec(compile(m.group(1), os.path.join(HERE, 'sandpie.html#serve-py-source'), 'exec'),
     {'__name__': '__main__', '__file__': __file__})
