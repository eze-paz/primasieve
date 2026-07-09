import re
with open('sandpie.css','r',encoding='utf-8') as f:
    css=f.read()
es=css.find('[data-theme="electric"]')
search=es+1
ee=-1
while True:
    p=css.find('[data-theme=',search)
    if p==-1:
        ee=len(css);break
    if not css[p:p+30].startswith('[data-theme="electric"]'):
        ee=p;break
    search=p+1
blk=css[es:ee]
blk=blk.replace('data-theme="electric"','data-theme="clear"')
blk=re.sub(r'\[data-theme="clear"\]\s*\{\s*--sp-accent-2:[^}]+\}\s*','',blk)
ls=blk.splitlines(keepends=True)
blk=''.join(L for L in ls if 'clip-path:' not in L.lower() and '.user::before' not in L)
blk=re.sub(r'(border(?:-[a-z]+)?\s*:\s*)([2-9])(px\b[^;\n]*;)',lambda m:m.group(1)+'1px'+m.group(3),blk)
blk=re.sub(r'(border-(?:left|right|top|bottom)\s*:\s*)([2-9])(px\b[^;\n]*;)',lambda m:m.group(1)+'1px'+m.group(3),blk)
blk=re.sub(r'\[data-theme="clear"\] body::after\s*\{(?:[^{}]|\{[^{}]*\})*\}\s*','',blk)
blk=blk.replace('  background: var(--sp-text);\r\n  color: var(--sp-bg);','  background: #000000;\r\n  color: #FFFFFF;',1)
blk=blk.replace('  background: var(--sp-text);\n  color: var(--sp-bg);','  background: #000000;\n  color: #FFFFFF;',1)
blk=blk.replace('[data-theme="clear"] .user {\r\n','[data-theme="clear"] .user {\r\n  --sp-user-spot: #000000;\r\n',1)
blk=blk.replace('[data-theme="clear"] .user {\n','[data-theme="clear"] .user {\n  --sp-user-spot: #000000;\n',1)
blk=re.sub(r'\[data-theme="clear"\][^\{]+\{\s*\}\r?\n','',blk)
vb='[data-theme="clear"] {\r\n  --sp-bg: #FFFFFF;\r\n  --sp-surface: #FFFFFF;\r\n  --sp-border: #000000;\r\n  --sp-border-bright: #000000;\r\n  --sp-panel: #FFFFFF;\r\n  --sp-accent: #000000;\r\n  --sp-accent-dim: rgba(0,0,0,0.12);\r\n  --sp-text: #000000;\r\n  --sp-text-dim: #000000;\r\n  --sp-success: #1f883d;\r\n  --sp-danger: #cf222e;\r\n  --sp-warn: #9a6700;\r\n  --sp-accent-2: #333333;\r\n}\r\n'
blk=vb+blk
header='/* ------------------------------------------------------------------------------\r\n   THEME: CLEAR\r\n   ------------------------------------------------------------------------------ */\r\n\r\n'
clear=header+blk
cb='/* ------------------------------------------------------------------------------\r\n   THEME: CLEAR\r\n'
i=css.find(cb)
if i!=-1:
    np=css.find('\r\n[data-theme=',i+100)
    if np==-1: np=len(css)
    css=css[:i]+css[np:]
css=css.rstrip('\r\n')+'\r\n\r\n'+clear
with open('sandpie.css','w',encoding='utf-8') as f:
    f.write(css)
print('Done')
