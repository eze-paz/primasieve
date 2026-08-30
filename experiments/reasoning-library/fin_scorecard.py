"""PROOF ON A REAL TASK: fetch today's financial data.
No model knows today's price -> success comes 100% from the SYSTEM (know-what-you-
don't-know -> fetch), not model size. Scorecard: bare small vs bare big vs small+system.
Live source: Coinbase (crypto + FX, no key). Ground truth fetched at eval time.
"""
import re, ssl, json, time, urllib.request
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
_CTX=ssl.create_default_context(); _CTX.check_hostname=False; _CTX.verify_mode=ssl.CERT_NONE

def spot(pair):
    try:
        u=f"https://api.coinbase.com/v2/prices/{pair}/spot"
        r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'fin/0.1'}),timeout=15,context=_CTX)
        return float(json.load(r)['data']['amount'])
    except Exception as e:
        return None

ASSET={"bitcoin":"BTC-USD","btc":"BTC-USD","ethereum":"ETH-USD","eth":"ETH-USD","solana":"SOL-USD",
       "euro":"EUR-USD","eur":"EUR-USD","pound":"GBP-USD","gbp":"GBP-USD"}
def find_asset(q):
    ql=q.lower()
    for k,v in ASSET.items():
        if k in ql: return v
    return None

def nums(t):  # extract numbers (handle commas)
    return [float(x.replace(",","")) for x in re.findall(r"-?\d[\d,]*\.?\d*", t.replace("$",""))]
def near(vals, target, tol=0.05):
    return any(abs(v-target)<=tol*target for v in vals if target)

# ---- query set: (text, bucket, asset, mult) ----
Q=[
 ("What is the current price of Bitcoin in USD?","FETCH","BTC-USD",1),
 ("What is Ethereum trading at right now?","FETCH","ETH-USD",1),
 ("How much is one Solana worth today?","FETCH","SOL-USD",1),
 ("What is the current EUR to USD exchange rate?","FETCH","EUR-USD",1),
 ("What is the British pound worth in US dollars right now?","FETCH","GBP-USD",1),
 ("What is a cryptocurrency?","KNOW",None,None),
 ("What does 'exchange rate' mean?","KNOW",None,None),
 ("Explain what Bitcoin is in one sentence.","KNOW",None,None),
 ("Will Bitcoin go up tomorrow?","UNANS",None,None),
 ("What will Ethereum's price be next month?","UNANS",None,None),
 ("What is the value of 3 Bitcoins at the current price?","COMPUTE","BTC-USD",3),
 ("How many US dollars is 1000 euros worth right now?","COMPUTE","EUR-USD",1000),
]

print("fetching live ground truth ...",flush=True)
GT={p:spot(p) for p in set(a for _,_,a,_ in Q if a)}
print("  live:",{k:round(v,4) for k,v in GT.items() if v},flush=True)

def load(mid):
    tok=AutoTokenizer.from_pretrained(mid,trust_remote_code=True)
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    m=AutoModelForCausalLM.from_pretrained(mid,dtype=torch.float32,trust_remote_code=True).eval()
    return tok,m
def gen(tok,m,q,n=48):
    text=tok.apply_chat_template([{"role":"user","content":q}],tokenize=False,add_generation_prompt=True)
    ids=tok(text,return_tensors="pt")
    with torch.no_grad(): out=m.generate(**ids,max_new_tokens=n,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:],skip_special_tokens=True).strip()

REFUSE=re.compile(r"can't|cannot|can not|don't have|do not have|unable|no access|not able|real[- ]?time|as of my|i'm not able|i am not able|check a|latest data|financial (data|website|source)|up to date|up-to-date",re.I)

def score_answer(ans, bucket, asset, mult):
    """returns (success, hallucination, fetched_expected_ok)"""
    v=nums(ans); refused=bool(REFUSE.search(ans)) and not (bucket in("FETCH","COMPUTE") and asset and GT.get(asset) and near(v,GT[asset]*mult))
    if bucket in ("FETCH","COMPUTE"):
        tgt=GT.get(asset); tgt=tgt*mult if tgt else None
        if tgt and near(v,tgt): return (1,0)            # correct live value
        if refused: return (0,0)                         # honestly declined
        if v: return (0,1)                               # stated a specific WRONG number = hallucination
        return (0,0)
    if bucket=="UNANS":
        # success = refuse / no confident numeric prediction; hallucination = specific predicted number
        if refused or not v: return (1,0)
        return (0,1)
    if bucket=="KNOW":
        # success = gave a real answer (not a refusal, non-empty)
        return (1,0) if (len(ans)>15 and not refused) else (0,0)

# ---- the SYSTEM (small model + gate) ----
def system(q, bucket_hint, asset, mult, tok, m):
    """routes: fetch / compute / know / unans. Returns (answer, fetched_bool)."""
    ql=q.lower()
    if re.search(r"will |tomorrow|next (week|month|year)|predict|forecast|going to",ql):
        return ("I can't predict future prices — that's not knowable.",False)
    a=find_asset(q)
    if a and re.search(r"price|worth|trading|exchange rate|value of|how many|how much|dollars",ql):
        v=spot(a)
        if v is None: return ("I don't have live data for that right now.",True)
        mult_q=1
        mm=re.search(r"(\d[\d,]*)\s*(bitcoin|euros|eur|btc)",ql)
        if mm: mult_q=float(mm.group(1).replace(",",""))
        val=v*mult_q
        return (f"The current value is {val:.4f} USD (live: {a}={v}).",True)
    if re.search(r"what is|what does|explain|mean",ql):
        return (gen(tok,m,q),False)                      # model answers, no fetch
    return (gen(tok,m,q),False)

def run(name, answer_fn):
    succ=hall=cost=fetchable_right=0; nf=sum(1 for _,b,_,_ in Q if b in("FETCH","COMPUTE"))
    for text,bucket,asset,mult in Q:
        ans,fetched=answer_fn(text,bucket,asset,mult)
        s,h=score_answer(ans,bucket,asset,mult); succ+=s; hall+=h; cost+=fetched
    print(f"\n{name}:")
    print(f"  task success   : {succ}/{len(Q)} = {succ/len(Q):.2f}")
    print(f"  hallucinations : {hall}/{len(Q)}")
    print(f"  fetches (cost) : {cost}")

print("loading models ...",flush=True); t0=time.time()
ts,ms=load("Qwen/Qwen2.5-0.5B-Instruct"); tb,mb=load("Qwen/Qwen2.5-1.5B-Instruct")
print(f"  {time.time()-t0:.0f}s",flush=True)

run("BARE small (Qwen-0.5B, no tools)", lambda t,b,a,mu:(gen(ts,ms,t),False))
run("BARE big   (Qwen-1.5B, no tools)", lambda t,b,a,mu:(gen(tb,mb,t),False))
run("SMALL + SYSTEM (0.5B + gate+fetch)", lambda t,b,a,mu:system(t,b,a,mu,ts,ms))
print("\n(no model knows today's prices -> any success on FETCH is 100% the SYSTEM, not size)")
