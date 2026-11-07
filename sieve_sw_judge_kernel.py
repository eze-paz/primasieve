"""SW judge: Pythia-410m-deduped bits per BPE token of each continuation given its prompt."""
import glob, json, math, torch
from transformers import AutoTokenizer, GPTNeoXForCausalLM
f = glob.glob("/kaggle/input/**/sw_gen.json", recursive=True)[0]; G = json.load(open(f)); N = "EleutherAI/pythia-410m-deduped"
tk = AutoTokenizer.from_pretrained(N); m = GPTNeoXForCausalLM.from_pretrained(N, torch_dtype=torch.float32).cuda().eval(); out = []
with torch.no_grad():
    for g in G:
        p = tk(g["prompt"])["input_ids"]; c = tk(" " + g["text"])["input_ids"]; x = torch.tensor([p + c]).cuda()
        lp = torch.log_softmax(m(x).logits[0, :-1].float(), -1); t = x[0, 1:]; l = lp.gather(1, t[:, None])[:, 0][len(p) - 1:]
        out.append(dict(pid=g["pid"], B=g["B"], bits_per_token=float(-l.mean() / math.log(2)), ntok=len(c)))
json.dump(out, open("/kaggle/working/sw_pythia.json", "w")); print("done", len(out))
