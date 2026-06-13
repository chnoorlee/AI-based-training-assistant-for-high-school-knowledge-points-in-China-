"""GraphRAG：图谱感知检索（PRD 2.1 的 GraphRAG 全局推理）。

三步：
  ① 实体链接：把查询嵌入与各知识点描述嵌入比相似度，取 Top-K 作为"入口概念"
     （比旧版的子串前缀匹配更鲁棒，能语义对齐）。
  ② 带边权多跳扩散：从入口沿 先修/后继/同模块/**跨学科** 边扩散，
     relevance = 入口相似度 × decay^hop × 边权积，逐跳衰减、按概念取最大。
  ③ chunk 打分：chunk 的图相关性 = 其知识点在扩散图中的最大 relevance。
这样即使关键词不命中，也能经"先修/跨学科"把相关题目/知识点召回（如三角函数 ↔ 简谐运动）。
"""
from __future__ import annotations

import numpy as np

from app.core.config import settings
from app.data.knowledge_graph import KG

# 边类型权重
_W_PREREQ = 0.7
_W_SUCC = 0.7
_W_MODULE = 0.5
_W_CROSS = 0.6  # 跨学科桥


class GraphRetriever:
    def __init__(self, embedder) -> None:
        self.embedder = embedder
        self.concept_ids = KG.all_ids()
        # 概念描述嵌入（名称 + 模块 + 学科），一次性预计算
        texts = [f"{KG.name_of(c)} {KG.module_of(c)} {KG.subject_of(c)}"
                 for c in self.concept_ids]
        self.cemb = embedder.embed(texts) if self.concept_ids else np.zeros((0, 1))
        self.cidx = {c: i for i, c in enumerate(self.concept_ids)}
        # 反向跨学科边：A 声明 ⇄ B，则 B 也能桥回 A（保证双向、不依赖哪侧声明）
        self._rev_cross: dict[str, list[str]] = {}
        for c in self.concept_ids:
            for x in KG.cross_subject_of(c):
                if x in self.cidx:
                    self._rev_cross.setdefault(x, []).append(c)

    # ── ① 实体链接 ─────────────────────────────────────────
    def link_entities(self, query: str, k: int) -> list[tuple[str, float]]:
        if not self.concept_ids:
            return []
        q = self.embedder.embed([query], is_query=True)[0]
        sims = self.cemb @ q
        order = np.argsort(-sims)[:k]
        return [(self.concept_ids[i], float(max(0.0, sims[i]))) for i in order
                if sims[i] > 0]

    # ── ② 带边权多跳扩散 ────────────────────────────────────
    def _edges(self, c: str) -> list[tuple[str, float]]:
        out: list[tuple[str, float]] = []
        out += [(p, _W_PREREQ) for p in KG.prerequisites_of(c)]
        out += [(s, _W_SUCC) for s in KG.successors_of(c)]
        out += [(m, _W_MODULE) for m in KG.concepts_in_module(KG.module_of(c)) if m != c]
        cross = {x for x in KG.cross_subject_of(c) if x in self.cidx} | set(self._rev_cross.get(c, []))
        out += [(x, _W_CROSS) for x in cross]
        return out

    def expand(self, seeds: list[tuple[str, float]], hops: int, decay: float) -> dict[str, float]:
        rel: dict[str, float] = {}
        for c, s in seeds:
            rel[c] = max(rel.get(c, 0.0), s)
        frontier = list(seeds)
        for _ in range(hops):
            nxt: list[tuple[str, float]] = []
            for c, r in frontier:
                for nbr, w in self._edges(c):
                    nr = r * decay * w
                    if nr > rel.get(nbr, 0.0):
                        rel[nbr] = nr
                        nxt.append((nbr, nr))
            frontier = nxt
        return rel

    # ── ③ chunk 打分 ───────────────────────────────────────
    def relevance(self, query: str) -> dict[str, float]:
        seeds = self.link_entities(query, settings.graphrag_link_top_k)
        return self.expand(seeds, settings.graphrag_hops, settings.graphrag_decay)

    def score_chunks(self, query: str, chunk_concept_ids: list[list[str]]) -> np.ndarray:
        rel = self.relevance(query)
        return np.array([max((rel.get(c, 0.0) for c in cids), default=0.0)
                         for cids in chunk_concept_ids])
