import re

with open('sandpie.css','r',encoding='utf-8') as f:
    css=f.read()

# Fix doubled px: 1pxpx -> 1px
css=re.sub(r'(?<!([0-9]))1pxpx',r'1px',css)

# Also catch 1pxpx (shouldn't have 
# Actually just replace every '1pxpx' with '1px'
css=css.replace('1pxpx','1px')

with open('sandpie.css','w',encoding='utf-8') as f:
    f.write(css)
print('Done')
