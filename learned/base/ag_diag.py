import os, sys, json, random, collections, torch
sys.argv=[sys.argv[0]]
import ag1_translator as A
data=[s for s in json.load(open('stories_train_v2.json', encoding='utf-8')) if s.get('events')]
random.Random(0).shuffle(data); train_s=data[:2240]
F=A.Feats([tk for st in train_s for tk,_ in A.gold_examples(st)])
vm=A.Tagger(F,2,False); am=A.Tagger(F,len(A.ATAGS),True); sd=torch.load('ag1_translator.pt'); vm.load_state_dict(sd['vm']); am.load_state_dict(sd['am']); vm.eval(); am.eval()
T=A.Translator(F,vm,am)
stories=json.load(open('val_all13.json', encoding='utf-8'))['stories'][310:510]
nsent=nev=0; verbs=collections.Counter(); known=0; ex=[]
for s in stories:
    for sent in [x.strip() for x in A.SENT.split(s['text']) if x.strip()]:
        nsent+=1; ev=T.read(sent); nev+=len(ev)
        for e in ev:
            verbs[e['verb']]+=1
            if len(ex)<12: ex.append((sent[:110], e))
print('untouched stories 200: sentences', nsent, 'events extracted', nev, 'per sentence', round(nev/nsent,2))
print('verbs fired', len(verbs), verbs.most_common(25))
print('share of fired verbs in the 32 synthetic lemmas', round(sum(c for v,c in verbs.items() if v in {'take','come','carry','be','run','wait','belong','leave','find','put','drop','steal','follow','row','chase','walk','set','go','give','return','have','borrow','make','reach','arrive','ride','knock','flatten','smash','eat','break','trample'})/max(1,nev),2))
for x in ex: print(x)
