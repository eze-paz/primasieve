"""Render/verify-in-the-loop refinement: small model + local verifier beats its own one-shot.
generate -> verify (parse the real HTML) -> critique -> revise -> repeat, keep best.
"""
import re, sys, os, time, torch
from html.parser import HTMLParser
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

torch.set_num_threads(10)
MODEL = "LiquidAI/LFM2.5-350M"
ADAPTER = "lora_probe"
SYS = ("You are an expert front-end engineer. Output ONE complete, self-contained HTML5 "
       "document: <!DOCTYPE html> ... </html>, all CSS inline in a <style> tag in the <head>, "
       "a full <body>. Output only HTML, no markdown fences.")

tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None: tok.pad_token = tok.eos_token
base = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, trust_remote_code=True).eval()
mdl = PeftModel.from_pretrained(base, ADAPTER).eval()

# ---------------- local verifier ----------------
class Bal(HTMLParser):
    def __init__(s): super().__init__(); s.stack=[]; s.max_depth=0; s.unclosed=0
    def handle_starttag(s,t,a):
        if t not in ("meta","link","img","br","hr","input","source"): s.stack.append(t)
        s.max_depth=max(s.max_depth,len(s.stack))
    def handle_endtag(s,t):
        if t in s.stack:
            while s.stack and s.stack.pop()!=t: pass
        else: s.unclosed+=1

def verify(html, req=None):
    req = req or {}
    checks, crit = {}, []
    s = html.strip()
    low = s.lower()
    def C(name, ok, msg):
        checks[name]=ok
        if not ok: crit.append(msg)
    C("doctype", low.startswith("<!doctype html"), "must start with <!DOCTYPE html>")
    C("no_leading_junk", low.startswith("<!doctype") or low.startswith("<html"),
      "remove any text before <!DOCTYPE html>")
    C("closes_html", "</html>" in low, "document must end with </html>")
    C("one_body", low.count("<body")==1 and low.count("</body>")==1, "need exactly one <body>...</body>")
    C("no_fence", "```" not in s, "remove markdown code fences")
    # style must not contain HTML tags (the classic bug)
    styles = re.findall(r"<style[^>]*>(.*?)</style>", s, re.S|re.I)
    style_clean = all(not re.search(r"<[a-zA-Z/][a-zA-Z0-9]*", blk) for blk in styles)
    C("style_no_markup", style_clean and len(styles)>=1, "put NO HTML tags inside <style>; move content into <body>")
    # body non-empty with real content
    m = re.search(r"<body[^>]*>(.*?)</body>", s, re.S|re.I)
    body = m.group(1) if m else ""
    body_text = re.sub(r"<[^>]+>","",body)
    C("body_nonempty", len(body_text.strip())>=40 and body.count("<")>=6,
      "the <body> must contain the full visible page, not be empty")
    # no garbage run
    C("no_garbage", re.search(r"(.)\1{29,}", re.sub(r"\s","",s)) is None,
      "remove repeated filler characters")
    # tag balance
    b=Bal();
    try: b.feed(s)
    except Exception: pass
    C("balanced", b.unclosed==0 and len(b.stack)<=1, "close all open tags properly")
    # css present
    C("has_css", sum(len(x) for x in styles)>=120, "include real CSS styling in <style>")
    C("interactive", ("<a " in low or "<button" in low), "include links or buttons")
    # per-prompt requirements
    if "min_prices" in req:
        n=len(re.findall(r"\$\s?\d", s)); C("prices", n>=req["min_prices"],
          f"show a numeric price for each tier (found {n}, need {req['min_prices']})")
    if "keywords" in req:
        miss=[k for k in req["keywords"] if k.lower() not in low]
        C("keywords", not miss, f"include these sections/labels: {', '.join(miss)}")
    if "min_cards" in req:
        n=low.count('class="card')+low.count('class="tier')+low.count('class="feature')
        n=max(n, low.count("<section"))
        C("cards", n>=req["min_cards"], f"include at least {req['min_cards']} content blocks/cards")
    score = sum(checks.values())/len(checks)
    return score, checks, crit

@torch.no_grad()
def gen(messages, n=900):
    txt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids = tok(txt, return_tensors="pt")
    out = mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).strip()

def refine_loop(task, req, iters=3, outdir="loop_out"):
    os.makedirs(outdir, exist_ok=True)
    msgs = [{"role":"system","content":SYS},{"role":"user","content":task}]
    best=(-1,None,None); hist=[]
    for it in range(iters):
        t0=time.time()
        html = gen(msgs)
        score, checks, crit = verify(html, req)
        dt=time.time()-t0
        open(f"{outdir}/iter{it}.html","w",encoding="utf-8").write(html)
        fails=[k for k,v in checks.items() if not v]
        print(f"[iter {it}] score {score:.2f} ({sum(checks.values())}/{len(checks)}) "
              f"{dt:.0f}s  fails={fails}", flush=True)
        hist.append(score)
        if score>best[0]: best=(score,html,it)
        if score>=1.0:
            print("  perfect - stop"); break
        # feed critique back
        fixmsg = ("Your HTML has these problems:\n- " + "\n- ".join(crit) +
                  "\nReturn the FULL corrected HTML document, fixing every problem. Output only HTML.")
        msgs = [{"role":"system","content":SYS},{"role":"user","content":task},
                {"role":"assistant","content":html},{"role":"user","content":fixmsg}]
    open(f"{outdir}/best.html","w",encoding="utf-8").write(best[1])
    print(f"BEST score {best[0]:.2f} at iter {best[2]}; trajectory {hist} -> {outdir}/best.html")
    return best, hist

if __name__ == "__main__":
    TASK = ("Create a pricing page for 'Northwind' with three tiers (Free, Pro, Enterprise) as "
            "side-by-side cards, each showing a price and a button, with the middle Pro tier highlighted.")
    REQ = {"min_prices":3, "keywords":["Free","Pro","Enterprise"], "min_cards":3}
    refine_loop(TASK, REQ, iters=3)
