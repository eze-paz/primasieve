"""Frozen encoders for the JIT-router bake-off.

The whole premise: the encoder is trained/downloaded ONCE and frozen. All
per-task cost lives in the head (heads.py). We compare heads on a shared,
frozen feature space so cost numbers are apples-to-apples.

Two backends:
  HashingEncoder  - pure-numpy char+word n-gram hashed TF-IDF. Offline, zero
                    deps, deterministic. This is the honest CPU floor.
  HFEncoder       - a real transformer sentence encoder via `transformers`,
                    used only if a model is available/cached. Optional.
"""
from __future__ import annotations
import re
import numpy as np

_WORD = re.compile(r"[a-z0-9']+")


def _tokens(text: str):
    return _WORD.findall(text.lower())


class HashingEncoder:
    """Hashed n-gram TF-IDF-ish features, L2-normalized. Offline + frozen.

    'Frozen' here means the hashing function and dim are fixed; there is no
    fitting. IDF is a fixed 1/(1+log(hash_bucket_load)) approximation baked in
    via sublinear TF, so the encoder truly has zero per-corpus training.
    """

    def __init__(self, dim: int = 4096, word_ngrams=(1, 2), char_ngrams=(3, 4), seed: int = 0):
        self.dim = dim
        self.word_ngrams = word_ngrams
        self.char_ngrams = char_ngrams
        self.seed = seed

    def _hash(self, s: str) -> int:
        # deterministic FNV-1a, salted by seed
        h = 0x811C9DC5 ^ self.seed
        for ch in s:
            h ^= ord(ch)
            h = (h * 0x01000193) & 0xFFFFFFFF
        return h % self.dim

    def _feat_one(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = _tokens(text)
        # word n-grams
        lo, hi = self.word_ngrams
        for n in range(lo, hi + 1):
            for i in range(len(toks) - n + 1):
                g = " ".join(toks[i:i + n])
                v[self._hash("w%d:%s" % (n, g))] += 1.0
        # char n-grams over the raw (spaced) text
        s = " ".join(toks)
        lo, hi = self.char_ngrams
        for n in range(lo, hi + 1):
            for i in range(len(s) - n + 1):
                v[self._hash("c%d:%s" % (n, s[i:i + n]))] += 1.0
        # sublinear TF + L2 norm
        np.log1p(v, out=v)
        nrm = np.linalg.norm(v)
        if nrm > 0:
            v /= nrm
        return v

    def encode(self, texts) -> np.ndarray:
        return np.stack([self._feat_one(t) for t in texts]).astype(np.float32)

    @property
    def name(self):
        return "hashing-%d" % self.dim


class HFEncoder:
    """Optional real transformer encoder (mean-pooled, L2-normalized).

    Only used if the model loads (cached or downloadable). Kept lazy so the
    offline path never pays the import/download cost.
    """

    def __init__(self, model_id: str = "sentence-transformers/all-MiniLM-L6-v2"):
        import torch
        from transformers import AutoTokenizer, AutoModel
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id).eval()
        self.model_id = model_id

    def encode(self, texts) -> np.ndarray:
        torch = self.torch
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), 32):
                batch = list(texts[i:i + 32])
                enc = self.tok(batch, padding=True, truncation=True,
                               max_length=128, return_tensors="pt")
                h = self.model(**enc).last_hidden_state  # (B,T,H)
                mask = enc["attention_mask"].unsqueeze(-1).float()
                emb = (h * mask).sum(1) / mask.sum(1).clamp(min=1e-6)
                emb = torch.nn.functional.normalize(emb, dim=-1)
                out.append(emb.cpu().numpy())
        return np.concatenate(out).astype(np.float32)

    @property
    def name(self):
        return "hf:" + self.model_id.split("/")[-1]


def get_encoder(kind: str = "hashing", **kw):
    if kind == "hashing":
        return HashingEncoder(**kw)
    if kind == "hf":
        return HFEncoder(**kw)
    raise ValueError(kind)
