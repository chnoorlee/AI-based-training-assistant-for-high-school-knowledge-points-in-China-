"""向量库抽象。

- InMemoryVectorStore：NumPy 真实余弦检索 + 标量过滤（如按学科）。零依赖、可跑、检索质量真实，
  仅"存储/规模"层与生产不同——是默认实现，也是 Milvus 的契约对照实现。
- MilvusVectorStore：生产实现（pymilvus，HNSW/IVF + COSINE，支持标量过滤分区）。
切换由 settings.vector_store 决定（memory | milvus），不可用自动回退内存。
"""
from __future__ import annotations

from typing import Optional, Protocol

import numpy as np

from app.core.config import settings


class VectorStore(Protocol):
    backend: str

    def upsert(self, ids: list[str], vectors: np.ndarray, metas: list[dict]) -> None: ...
    def search(self, qvec: np.ndarray, top_k: int,
               where: Optional[dict] = None) -> list[tuple[str, float, dict]]: ...
    def count(self) -> int: ...


def _match(meta: dict, where: Optional[dict]) -> bool:
    if not where:
        return True
    for k, v in where.items():
        mv = meta.get(k)
        if isinstance(v, (list, tuple, set)):
            if mv not in v:
                return False
        elif mv != v:
            return False
    return True


class InMemoryVectorStore:
    backend = "memory"

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.vecs: Optional[np.ndarray] = None
        self.metas: list[dict] = []

    def upsert(self, ids, vectors, metas):
        vectors = np.asarray(vectors, dtype=np.float64)
        self.ids = list(ids)
        self.vecs = vectors
        self.metas = list(metas)

    def search(self, qvec, top_k, where=None):
        if self.vecs is None or len(self.ids) == 0:
            return []
        q = np.asarray(qvec, dtype=np.float64).reshape(-1)
        sims = self.vecs @ q  # 向量已 L2 归一化 → 点积即余弦
        order = np.argsort(-sims)
        out: list[tuple[str, float, dict]] = []
        for i in order:
            if _match(self.metas[i], where):
                out.append((self.ids[i], float(sims[i]), self.metas[i]))
            if len(out) >= top_k:
                break
        return out

    def count(self) -> int:
        return len(self.ids)


class MilvusVectorStore:  # pragma: no cover - 生产路径
    """pymilvus 实现：建集合(dim, COSINE, HNSW)、插入、按学科标量过滤检索。"""

    backend = "milvus"

    def __init__(self) -> None:
        from pymilvus import MilvusClient
        self.client = MilvusClient(uri=settings.milvus_uri)
        self.coll = settings.milvus_collection

    def upsert(self, ids, vectors, metas):
        from pymilvus import DataType
        vectors = np.asarray(vectors)
        dim = vectors.shape[1]
        if not self.client.has_collection(self.coll):
            schema = self.client.create_schema(auto_id=False)
            schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=64)
            schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
            schema.add_field("subject", DataType.VARCHAR, max_length=32)
            schema.add_field("ref_id", DataType.VARCHAR, max_length=64)
            schema.add_field("kind", DataType.VARCHAR, max_length=16)
            idx = self.client.prepare_index_params()
            idx.add_index("vector", index_type="HNSW", metric_type=settings.milvus_metric,
                          params={"M": 16, "efConstruction": 200})
            self.client.create_collection(self.coll, schema=schema, index_params=idx)
        rows = [{"id": ids[i], "vector": vectors[i].tolist(),
                 "subject": metas[i].get("subject", ""), "ref_id": metas[i].get("ref_id", ""),
                 "kind": metas[i].get("kind", "")} for i in range(len(ids))]
        self.client.upsert(self.coll, rows)

    def search(self, qvec, top_k, where=None):
        flt = ""
        if where and "subject" in where:
            subj = where["subject"]
            subj = subj if isinstance(subj, (list, tuple, set)) else [subj]
            flt = "subject in [" + ", ".join(f'"{s}"' for s in subj) + "]"
        res = self.client.search(self.coll, data=[np.asarray(qvec).tolist()], limit=top_k,
                                 filter=flt, output_fields=["subject", "ref_id", "kind"])[0]
        return [(r["id"], float(r["distance"]),
                 {"subject": r["entity"].get("subject"), "ref_id": r["entity"].get("ref_id"),
                  "kind": r["entity"].get("kind")}) for r in res]

    def count(self) -> int:
        return self.client.get_collection_stats(self.coll).get("row_count", 0)


def get_vector_store() -> VectorStore:
    if settings.vector_store == "milvus":
        try:
            return MilvusVectorStore()
        except Exception:
            pass
    return InMemoryVectorStore()
