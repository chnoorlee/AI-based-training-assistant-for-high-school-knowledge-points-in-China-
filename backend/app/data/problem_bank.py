"""题库：内存题目集合 + Q 矩阵构建。

Q 矩阵 Q[i,k]∈{0,1} 表示题目 i 是否考查知识点 k——这是 NeuralCD 的核心输入。
"""
from __future__ import annotations

import numpy as np

from app.data.seed_data import PROBLEMS
from app.data.seed_data_science import PROBLEMS_SCIENCE
from app.schemas import Problem


class ProblemBank:
    def __init__(self, problems: list[dict] | None = None) -> None:
        raw = problems if problems is not None else (PROBLEMS + PROBLEMS_SCIENCE)
        self.problems: dict[str, Problem] = {p["id"]: Problem(**p) for p in raw}
        self.problem_ids: list[str] = list(self.problems.keys())
        # 收集全部知识点（按题库出现顺序稳定排序）
        concept_order: list[str] = []
        for pid in self.problem_ids:
            for cid in self.problems[pid].concept_ids:
                if cid not in concept_order:
                    concept_order.append(cid)
        self.concept_ids: list[str] = concept_order
        self.concept_index: dict[str, int] = {c: i for i, c in enumerate(self.concept_ids)}
        self.problem_index: dict[str, int] = {p: i for i, p in enumerate(self.problem_ids)}
        self._q_matrix = self._build_q_matrix()

    def _build_q_matrix(self) -> np.ndarray:
        n_items, n_concepts = len(self.problem_ids), len(self.concept_ids)
        q = np.zeros((n_items, n_concepts), dtype=np.float64)
        for pid, problem in self.problems.items():
            i = self.problem_index[pid]
            for cid in problem.concept_ids:
                if cid in self.concept_index:
                    q[i, self.concept_index[cid]] = 1.0
        return q

    @property
    def q_matrix(self) -> np.ndarray:
        return self._q_matrix

    def get(self, problem_id: str) -> Problem | None:
        return self.problems.get(problem_id)

    def all(self) -> list[Problem]:
        return list(self.problems.values())

    def by_concept(self, concept_id: str) -> list[Problem]:
        return [p for p in self.problems.values() if concept_id in p.concept_ids]

    def by_subject(self, subject: str) -> list[Problem]:
        return [p for p in self.problems.values() if p.subject.value == subject]

    def subjects(self) -> list[str]:
        seen: list[str] = []
        for p in self.problems.values():
            if p.subject.value not in seen:
                seen.append(p.subject.value)
        return seen

    def concept_ids_for_subject(self, subject: str) -> list[str]:
        out: list[str] = []
        for p in self.by_subject(subject):
            for c in p.concept_ids:
                if c not in out:
                    out.append(c)
        return out

    def difficulty_vector(self) -> np.ndarray:
        return np.array([self.problems[pid].difficulty for pid in self.problem_ids])


# 单例
BANK = ProblemBank()
