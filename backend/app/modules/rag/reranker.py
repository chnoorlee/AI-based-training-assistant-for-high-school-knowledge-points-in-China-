"""重排序：对召回候选交叉打分，提升 Top-K 精度（PRD 2.1）。

- HeuristicReranker：启发式交叉特征（mock / 回退）。
- BGEHttpReranker：对接 bge-reranker-large 的 /rerank 服务（TEI 兼容），可注入 httpx.Client。
切换由 settings.reranker_backend 决定（mock | bge_http），不可用自动回退启发式。
"""
from __future__ import annotations

from app.core.config import settings
from app.modules.rag.retriever import Chunk
from app.modules.rag.text_utils import tokenize


class HeuristicReranker:
    backend = "mock"

    def score(self, query: str, chunk: Chunk) -> float:
        q = set(tokenize(query))
        d = set(tokenize(chunk.text))
        if not q or not d:
            return 0.0
        jaccard = len(q & d) / len(q | d)
        overlap = len(q & d) / len(q)
        type_bonus = 0.05 if chunk.kind == "problem" else 0.0
        return 0.6 * overlap + 0.35 * jaccard + type_bonus

    def rerank(self, query: str, candidates: list[tuple[Chunk, float]],
               top_k: int = 10) -> list[tuple[Chunk, float]]:
        scored = [(c, 0.5 * self.score(query, c) + 0.5 * recall) for c, recall in candidates]
        scored.sort(key=lambda t: -t[1])
        return scored[:top_k]


class BGEHttpReranker:
    backend = "bge_http"

    def __init__(self, http_client=None) -> None:
        import httpx
        self.client = http_client or httpx.Client(timeout=20.0)
        self.url = settings.rerank_base_url.rstrip("/") + "/rerank"
        self._fallback = HeuristicReranker()

    def rerank(self, query, candidates, top_k=10):
        if not candidates:
            return []
        try:
            docs = [c.text for c, _ in candidates]
            r = self.client.post(self.url, json={"query": query, "texts": docs,
                                                 "documents": docs}, timeout=20.0)
            r.raise_for_status()
            data = r.json()
            results = data if isinstance(data, list) else data.get("results", [])
            scored = []
            for item in results:
                idx = item.get("index")
                s = item.get("relevance_score", item.get("score", 0.0))
                if idx is not None and 0 <= idx < len(candidates):
                    scored.append((candidates[idx][0], float(s)))
            if scored:
                scored.sort(key=lambda t: -t[1])
                return scored[:top_k]
        except Exception:
            pass
        return self._fallback.rerank(query, candidates, top_k)  # 降级


def get_reranker():
    if settings.reranker_backend == "bge_http":
        try:
            return BGEHttpReranker()
        except Exception:
            pass
    return HeuristicReranker()


RERANKER = get_reranker()
