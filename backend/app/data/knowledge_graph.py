"""内存知识图谱（生产替换点：NebulaGraph）。

提供：节点查询、先修链、模块聚合、跨学科关联、邻居扩散——供 GraphRAG 与诊断/推荐使用。
接口刻意贴近图数据库语义（neighbors / prerequisites_of / shortest deps），便于平滑迁移。
"""
from __future__ import annotations

from collections import defaultdict, deque

from app.data.seed_data import CONCEPTS
from app.data.seed_data_science import CONCEPTS_SCIENCE
from app.schemas import Concept


class KnowledgeGraph:
    def __init__(self, concepts: list[dict] | None = None) -> None:
        raw = concepts if concepts is not None else (CONCEPTS + CONCEPTS_SCIENCE)
        self.concepts: dict[str, Concept] = {c["id"]: Concept(**c) for c in raw}
        # 邻接：先修 -> 后继（反向 prereq）
        self._successors: dict[str, list[str]] = defaultdict(list)
        for cid, c in self.concepts.items():
            for p in c.prereq_ids:
                self._successors[p].append(cid)

    # ── 基础查询 ────────────────────────────────────────────
    def get(self, concept_id: str) -> Concept | None:
        return self.concepts.get(concept_id)

    def name_of(self, concept_id: str) -> str:
        c = self.concepts.get(concept_id)
        return c.name if c else concept_id

    def all_ids(self) -> list[str]:
        return list(self.concepts.keys())

    def modules(self) -> list[str]:
        seen: list[str] = []
        for c in self.concepts.values():
            if c.module not in seen:
                seen.append(c.module)
        return seen

    # ── 学科切片 ────────────────────────────────────────────
    def subjects(self) -> list[str]:
        seen: list[str] = []
        for c in self.concepts.values():
            if c.subject.value not in seen:
                seen.append(c.subject.value)
        return seen

    def subject_of(self, concept_id: str) -> str:
        c = self.concepts.get(concept_id)
        return c.subject.value if c else "math"

    def concepts_for_subject(self, subject: str) -> list[str]:
        return [cid for cid, c in self.concepts.items() if c.subject.value == subject]

    def modules_for_subject(self, subject: str) -> list[str]:
        seen: list[str] = []
        for c in self.concepts.values():
            if c.subject.value == subject and c.module not in seen:
                seen.append(c.module)
        return seen

    def concepts_in_module(self, module: str) -> list[str]:
        return [cid for cid, c in self.concepts.items() if c.module == module]

    def module_of(self, concept_id: str) -> str:
        c = self.concepts.get(concept_id)
        return c.module if c else ""

    # ── 图关系 ─────────────────────────────────────────────
    def prerequisites_of(self, concept_id: str) -> list[str]:
        c = self.concepts.get(concept_id)
        return list(c.prereq_ids) if c else []

    def successors_of(self, concept_id: str) -> list[str]:
        return list(self._successors.get(concept_id, []))

    def cross_subject_of(self, concept_id: str) -> list[str]:
        c = self.concepts.get(concept_id)
        return list(c.cross_subject_ids) if c else []

    def all_prerequisites(self, concept_id: str) -> list[str]:
        """递归全部先修（含间接），用于「补短板要先补哪些前置」。"""
        out: list[str] = []
        seen: set[str] = set()
        q: deque[str] = deque(self.prerequisites_of(concept_id))
        while q:
            cur = q.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            q.extend(self.prerequisites_of(cur))
        return out

    def neighbors(self, concept_id: str, hops: int = 1) -> list[str]:
        """图扩散：先修 + 后继 + 同模块（GraphRAG 全局推理用）。"""
        frontier = {concept_id}
        visited = {concept_id}
        for _ in range(hops):
            nxt: set[str] = set()
            for cid in frontier:
                nxt.update(self.prerequisites_of(cid))
                nxt.update(self.successors_of(cid))
                nxt.update(self.concepts_in_module(self.module_of(cid)))
            nxt -= visited
            visited |= nxt
            frontier = nxt
        visited.discard(concept_id)
        return list(visited)


# 单例
KG = KnowledgeGraph()
