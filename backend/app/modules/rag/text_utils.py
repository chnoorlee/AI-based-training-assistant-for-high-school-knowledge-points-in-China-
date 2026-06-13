"""检索基础工具：中文分词、确定性哈希嵌入（占位/回退）、归一化。

抽到独立模块，供 embeddings / retriever / reranker 共用，避免循环依赖。
"""
from __future__ import annotations

import hashlib
import re

import numpy as np

_CJK = re.compile(r"[一-鿿]")
_WORD = re.compile(r"[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    """中文 bigram + 英文/数字词；可用 jieba 时自动启用更优分词。"""
    text = text or ""
    try:
        import jieba
        toks = [t.strip() for t in jieba.cut(text) if t.strip()]
        if toks:
            return [t.lower() for t in toks]
    except Exception:
        pass
    toks: list[str] = [w.lower() for w in _WORD.findall(text)]
    cjk = _CJK.findall(text)
    toks += ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)] or cjk
    return toks


def _stable_hash(token: str, dim: int) -> tuple[int, int]:
    h = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:8], "big")
    return h % dim, (1 if (h >> 63) & 1 else -1)


class HashingEmbedder:
    """确定性特征哈希向量（占位/fallback）。生产替换：bge-m3 / bge-large-zh。"""

    backend = "mock"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), self.dim))
        for r, t in enumerate(texts):
            for tok in tokenize(t):
                idx, sign = _stable_hash(tok, self.dim)
                out[r, idx] += sign
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


def minmax(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)
