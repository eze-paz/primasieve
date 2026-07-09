import re
with open('sandpie.css','r',encoding='utf-8') as f:
    css=f.read()

idx=css.find('THEME: CLEAR')
end=css.find('THEME:', idx+20)
if end==-1: end=len(css)
block=css[idx:end]
print('CLEAR block lines:', block.count(chr(10)))
print('Any clip-path in Clear:', 'clip-path' in block.lower())
# Also check for any borders > 1px
matches=re.findall(r'\bborder[^:]*:\s*\d+px', block)
big=[m for m in matches if int(re.search(r'(\d+)px',m).group(1))>1]
print('Big borders:', big[:10] if big else 'None')
# Check for empty rulesets
empty=re.findall(r'\[data-theme="clear"\][^\{]*\{\s*\}', block)
print('Empty rules:', len(empty))
