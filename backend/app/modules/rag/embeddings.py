"""真实文本嵌入（bge）。

- HashingEmbedder：零依赖确定性向量（mock / 回退）。
- BGEHttpEmbedder：对接 OpenAI/TEI 兼容的 /embeddings 服务（bge-large-zh / bge-m3），
  非对称检索给查询加指令前缀；超时/重试；L2 归一化；可注入 httpx.Client（MockTransport 可测）。
- BGELocalEmbedder：本地加载 FlagEmbedding / sentence-transformers（生产 stub，需装包+模型）。
切换由 settings.embedder_backend 决定（mock | bge_http | bge_local），不可用自动回退 HashingEmbedder。
"""
from __future__ import annotations

import time
from typing import Optional, Protocol

import numpy as np

from app.core.config import settings
from app.modules.rag.text_utils import HashingEmbedder


class Embedder(Protocol):
    backend: str

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray: ...


def _l2norm(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(n == 0, 1, n)


class BGEHttpEmbedder:
    """OpenAI/TEI 兼容嵌入服务客户端。"""

    backend = "bge_http"

    def __init__(self, http_client=None) -> None:
        import httpx
        self._httpx = httpx
        self.base = settings.embed_base_url.rstrip("/")
        self.url = self.base + "/embeddings"
        self.client = http_client or httpx.Client(timeout=settings.embed_timeout_s)

    def _post(self, inputs: list[str]) -> np.ndarray:
        payload = {"model": settings.embed_model, "input": inputs}
        last_err = None
        for attempt in range(3):
            try:
                r = self.client.post(self.url, json=payload, timeout=settings.embed_timeout_s)
                r.raise_for_status()
                data = r.json()["data"]
                vecs = np.array([d["embedding"] for d in data], dtype=np.float64)
                return _l2norm(vecs)
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(0.2 * (2 ** attempt))
        raise RuntimeError(f"嵌入服务调用失败：{last_err!r}")

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, settings.embed_dim))
        if is_query and settings.embed_query_instruction:
            texts = [settings.embed_query_instruction + t for t in texts]
        return self._post(texts)

    def health(self) -> bool:
        try:
            self.embed(["ping"])
            return True
        except Exception:
            return False


class BGELocalEmbedder:  # pragma: no cover - 生产路径
    """本地 bge（FlagEmbedding / sentence-transformers）。"""

    backend = "bge_local"

    def __init__(self) -> None:
        from FlagEmbedding import FlagModel  # 需 pip install FlagEmbedding + 模型
        self.model = FlagModel(settings.embed_model,
                               query_instruction_for_retrieval=settings.embed_query_instruction,
                               use_fp16=True)

    def embed(self, texts, is_query=False):
        fn = self.model.encode_queries if is_query else self.model.encode
        return _l2norm(np.asarray(fn(texts), dtype=np.float64))


def get_embedder(http_client=None) -> Embedder:
    backend = settings.embedder_backend
    try:
        if backend == "bge_http":
            emb = BGEHttpEmbedder(http_client=http_client)
            if (not settings.embed_health_check) or emb.health():
                return emb
        elif backend == "bge_local":
            return BGELocalEmbedder()
    except Exception:
        pass
    return HashingEmbedder(dim=settings.embed_dim)


EMBEDDER: Optional[Embedder] = None  # 惰性初始化（见 retriever）
