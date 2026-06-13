"""② 混合检索：BM25（关键词）+ Dense（bge 向量）+ GraphRAG（图谱推理）三路融合（PRD 2.1）。

权重默认 0.3 / 0.4 / 0.3（settings）。Dense 走真实嵌入 + 向量库（默认内存真实余弦，
可切 bge-http + Milvus）；GraphRAG 走实体链接 + 带边权多跳扩散。各路 min-max 归一后线性加权。
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from app.core.config import settings
from app.data.knowledge_graph import KG
from app.data.problem_bank import BANK
from app.modules.rag.embeddings import get_embedder
from app.modules.rag.graphrag import GraphRetriever
from app.modules.rag.text_utils import minmax, tokenize  # noqa: F401  (tokenize re-exported)
from app.modules.rag.vectorstore import get_vector_store


class BM25:
    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.N = len(corpus_tokens)
        self.doc_len = np.array([len(d) for d in corpus_tokens], dtype=float)
        self.avgdl = float(self.doc_len.mean()) if self.N else 0.0
        df: Counter = Counter()
        for d in corpus_tokens:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.tf = [Counter(d) for d in corpus_tokens]

    def scores(self, query_tokens: list[str]) -> np.ndarray:
        s = np.zeros(self.N)
        for i in range(self.N):
            dl = self.doc_len[i] or 1.0
            for t in query_tokens:
                if t not in self.idf:
                    continue
                f = self.tf[i].get(t, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                s[i] += self.idf[t] * f * (self.k1 + 1) / denom
        return s


@dataclass
class Chunk:
    id: str
    text: str
    kind: str  # "problem" | "concept"
    ref_id: str
    subject: str = "math"
    concept_ids: list[str] = field(default_factory=list)


class HybridRetriever:
    def __init__(self) -> None:
        self.embedder = get_embedder()
        self.chunks: list[Chunk] = self._build_chunks()
        self._tokens = [tokenize(c.text) for c in self.chunks]
        self.bm25 = BM25(self._tokens)
        # Dense：嵌入所有 chunk（passage）→ 灌入向量库
        emb = self.embedder.embed([c.text for c in self.chunks])
        self.store = get_vector_store()
        self.store.upsert([c.id for c in self.chunks], emb,
                          [{"subject": c.subject, "kind": c.kind, "ref_id": c.ref_id}
                           for c in self.chunks])
        self._cid_index = {c.id: i for i, c in enumerate(self.chunks)}
        # GraphRAG
        self.graph = GraphRetriever(self.embedder)

    def _build_chunks(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for p in BANK.all():
            names = "；".join(KG.name_of(c) for c in p.concept_ids)
            text = f"{p.stem} {' '.join(p.solution_steps)} 知识点：{names}"
            chunks.append(Chunk(id=f"prob::{p.id}", text=text, kind="problem",
                                ref_id=p.id, subject=p.subject.value,
                                concept_ids=list(p.concept_ids)))
        for cid in KG.all_ids():
            c = KG.get(cid)
            text = f"{c.name} 所属模块：{c.module} 学科：{c.subject.value} 能力：{c.ability.value}"
            chunks.append(Chunk(id=f"concept::{cid}", text=text, kind="concept",
                                ref_id=cid, subject=c.subject.value, concept_ids=[cid]))
        return chunks

    def _dense_scores(self, query: str) -> np.ndarray:
        qvec = self.embedder.embed([query], is_query=True)[0]
        hits = self.store.search(qvec, top_k=len(self.chunks))
        arr = np.zeros(len(self.chunks))
        for cid, sim, _ in hits:
            if cid in self._cid_index:
                arr[self._cid_index[cid]] = max(0.0, sim)  # 余弦∈[-1,1]，负相关视为 0
        return arr

    def retrieve(self, query: str, top_k: int = 10,
                 subject: str = "") -> list[tuple[Chunk, float]]:
        bm25 = minmax(self.bm25.scores(tokenize(query)))
        dense = minmax(self._dense_scores(query))
        graph = minmax(self.graph.score_chunks(query, [c.concept_ids for c in self.chunks]))
        fused = (settings.retrieval_weight_bm25 * bm25
                 + settings.retrieval_weight_dense * dense
                 + settings.retrieval_weight_graph * graph)
        if subject:  # 学科过滤
            for i, c in enumerate(self.chunks):
                if c.subject != subject:
                    fused[i] = -1.0
        order = np.argsort(-fused)[:top_k]
        return [(self.chunks[i], float(fused[i])) for i in order if fused[i] > -1.0]


RETRIEVER = HybridRetriever()
