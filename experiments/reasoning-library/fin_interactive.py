"""Interactive: type any financial question, see side-by-side what a BARE small
model says vs what the SYSTEM does (recognize -> fetch live / compute / refuse).

Run interactively:   python fin_interactive.py
One-shot test:       python fin_interactive.py "what is the price of bitcoin?"
Live data: Coinbase (crypto + FX, no key). Small model: Qwen-0.5B.
"""
import re, ssl, sys, json, urllib.request
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(10)
_CTX=ssl.create_default_context(); _CTX.check_hostname=False; _CTX.verify_mode=ssl.CERT_NONE

def spot(pair):
    try:
        u=f"https://api.coinbase.com/v2/prices/{pair}/spot"
        r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'fin/0.1'}),timeout=15,context=_CTX)
        return float(json.load(r)['data']['amount'])
    except Exception:
        return None

# name -> Coinbase pair (crypto priced in USD; fiat X-USD gives USD per 1 X)
ASSET={"bitcoin":"BTC-USD","btc":"BTC-USD","ethereum":"ETH-USD","eth":"ETH-USD","ether":"ETH-USD",
 "solana":"SOL-USD","sol":"SOL-USD","dogecoin":"DOGE-USD","doge":"DOGE-USD","cardano":"ADA-USD","ada":"ADA-USD",
 "xrp":"XRP-USD","ripple":"XRP-USD","litecoin":"LTC-USD","ltc":"LTC-USD","euro":"EUR-USD","eur":"EUR-USD",
 "pound":"GBP-USD","sterling":"GBP-USD","gbp":"GBP-USD","yen":"JPY-USD","jpy":"JPY-USD","franc":"CHF-USD","cad":"CAD-USD"}
def find_asset(q):
    ql=q.lower()
    for k in sorted(ASSET,key=len,reverse=True):
        if re.search(rf"\b{re.escape(k)}\b",ql): return ASSET[k]
    return None

print("loading Qwen-0.5B (first run downloads ~1GB) ...",flush=True)
tok=AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
if tok.pad_token is None: tok.pad_token=tok.eos_token
mdl=AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct",dtype=torch.float32).eval()
print("ready.\n",flush=True)

def gen(q,n=60):
    text=tok.apply_chat_template([{"role":"user","content":q}],tokenize=False,add_generation_prompt=True)
    ids=tok(text,return_tensors="pt")
    with torch.no_grad(): out=mdl.generate(**ids,max_new_tokens=n,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:],skip_special_tokens=True).strip()

def system(q):
    ql=q.lower()
    if re.search(r"\bwill\b|tomorrow|next (week|month|year)|predict|forecast|going to|future",ql):
        return ("REFUSE","I can't predict future prices — that isn't knowable. I won't guess.")
    a=find_asset(q)
    wants_price=re.search(r"price|worth|trading|exchange rate|value|how much|how many|cost|rate|\$",ql)
    if a and wants_price:
        v=spot(a)
        if v is None: return ("FETCH-FAILED","I tried to fetch live data but couldn't reach the source right now.")
        mm=re.search(r"(\d[\d,]*\.?\d*)\s*(bitcoin|btc|ethereum|eth|euros?|eur|pounds?|gbp|solana|sol|dollars?)",ql)
        if mm:  # fetch + compute
            qty=float(mm.group(1).replace(",","")); val=v*qty
            return ("FETCH+COMPUTE",f"{qty:g} x {a.split('-')[0]} @ live {v:g} USD = {val:,.2f} USD  (source: Coinbase)")
        return ("FETCH",f"Live {a.split('-')[0]} = {v:,.4f} USD  (source: Coinbase, fetched just now)")
    if re.search(r"what is|what does|explain|define|mean|who|how do",ql):
        return ("ANSWER (no fetch)",gen(q))
    return ("ANSWER (no fetch)",gen(q))

def show(q):
    print("="*70)
    print(f"Q: {q}")
    print("-"*70)
    print(f"BARE 0.5B : {gen(q)}")
    route,ans=system(q)
    print(f"SYSTEM    : [{route}] {ans}")
    print("="*70+"\n",flush=True)

if __name__=="__main__":
    if len(sys.argv)>1:
        show(" ".join(sys.argv[1:]))
    else:
        print("Ask a financial question (or 'quit'). Try:")
        print("  what is the price of bitcoin?")
        print("  how much is 3 ethereum worth right now?")
        print("  will bitcoin go up tomorrow?")
        print("  what is a cryptocurrency?\n")
        while True:
            try: q=input("ask> ").strip()
            except (EOFError,KeyboardInterrupt): break
            if q.lower() in ("quit","exit","q",""): break
            show(q)
