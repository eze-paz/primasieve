import re
with open('sandpie.css','r',encoding='utf-8') as f:
    css=f.read()
print('Total lines:', css.count(chr(10)))
print('Any 1pxpx:', '1pxpx' in css)
idx=css.find('THEME: CLEAR')
if idx!=-1:
    block=css[idx:]
    lines=block.splitlines()
    for ln in lines[:80]:
        print(ln)
    print('...')
else:
    print('No clear block!')
