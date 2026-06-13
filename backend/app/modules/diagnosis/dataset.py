"""数据接入：把真实作答日志转成联合训练所需的训练集。

分层：
  LogRepository（接口）── InMemoryLogRepository（包 STORE，MVP 可跑）
                       └─ SQLLogRepository（MySQL/Mongo 生产实现，留接口）
  build_training_data_from_logs(repo) → TrainingData（与合成集同构，但无真值/Oracle）

真实日志没有真值掌握度 θ_true，评估改用「时序留出」（每个学生留最后一次作答做 next-step 预测）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional, Protocol

import numpy as np

from app.data.problem_bank import BANK


@dataclass
class InteractionRow:
    user_id: str
    problem_id: str
    correct: bool
    ts: datetime
    time_spent_s: float = 0.0


@dataclass
class TrainingData:
    """联合训练的统一输入（合成集与真实日志共用此结构）。"""

    n_students: int
    n_items: int
    n_concepts: int
    train_sequences: list[tuple[int, list[int], list[int]]] = field(default_factory=list)
    test_points: list[tuple] = field(default_factory=list)  # 5 元组（真实）或 6 元组（合成含真值p）
    primary_concept: list[int] = field(default_factory=list)
    item_concepts: list[list[int]] = field(default_factory=list)
    theta_true: Optional[np.ndarray] = None  # 仅合成集有
    student_vocab: list[str] = field(default_factory=list)  # 下标 → 原始 user_id（可追溯）
    n_interactions: int = 0


class LogRepository(Protocol):
    def iter_interactions(self, since: Optional[datetime] = None) -> Iterable[InteractionRow]: ...
    def count_since(self, since: Optional[datetime] = None) -> int: ...
    def latest_ts(self) -> Optional[datetime]: ...


class InMemoryLogRepository:
    """包装内存 STORE 作为「日志源」。生产替换为 SQLLogRepository，接口不变。"""

    def __init__(self, store=None) -> None:
        from app.services.store import STORE
        self.store = store or STORE

    def iter_interactions(self, since: Optional[datetime] = None) -> Iterable[InteractionRow]:
        for uid, recs in self.store.responses.items():
            for r in recs:
                if since is None or r.ts > since:
                    yield InteractionRow(uid, r.problem_id, r.correct, r.ts, r.time_spent_s)

    def count_since(self, since: Optional[datetime] = None) -> int:
        return sum(1 for _ in self.iter_interactions(since))

    def latest_ts(self) -> Optional[datetime]:
        ts = [r.ts for recs in self.store.responses.values() for r in recs]
        return max(ts) if ts else None


class SQLLogRepository:  # pragma: no cover - 生产路径
    """生产日志源（MySQL 结构化 + 可选 Mongo）。

    实现要点：
      - 按 user_id 分区、ts 升序流式读取 responses 表；
      - 大表分批（keyset 分页）避免全量载入；
      - 支持增量：WHERE ts > :since。
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def iter_interactions(self, since=None):
        raise NotImplementedError("配置 DB DSN 并实现：SELECT user_id, problem_id, correct, ts "
                                  "FROM responses WHERE (:since IS NULL OR ts > :since) "
                                  "ORDER BY user_id, ts")

    def count_since(self, since=None):
        raise NotImplementedError

    def latest_ts(self):
        raise NotImplementedError


def build_training_data_from_logs(repo: LogRepository, min_seq_len: int = 2) -> TrainingData:
    """从日志构造训练集：按学生分组、按时间排序，留最后一次作答做评估。"""
    item_index = BANK.problem_index
    n_items, n_concepts = BANK.q_matrix.shape
    item_concepts = [list(np.where(BANK.q_matrix[i] > 0)[0]) for i in range(n_items)]
    primary_concept = [(cs[0] if cs else 0) for cs in item_concepts]

    # 分组（仅保留题库内题目）
    by_user: dict[str, list[InteractionRow]] = {}
    total = 0
    for row in repo.iter_interactions():
        if row.problem_id not in item_index:
            continue
        by_user.setdefault(row.user_id, []).append(row)
        total += 1

    vocab: list[str] = []
    train_sequences, test_points = [], []
    for uid, rows in by_user.items():
        rows.sort(key=lambda r: r.ts)
        if len(rows) < min_seq_len:
            continue
        sid = len(vocab)
        vocab.append(uid)
        items = [item_index[r.problem_id] for r in rows]
        corrects = [int(r.correct) for r in rows]
        train_sequences.append((sid, items[:-1], corrects[:-1]))
        test_points.append((sid, items[:-1], corrects[:-1], items[-1], corrects[-1]))

    return TrainingData(
        n_students=len(vocab), n_items=n_items, n_concepts=n_concepts,
        train_sequences=train_sequences, test_points=test_points,
        primary_concept=primary_concept, item_concepts=item_concepts,
        student_vocab=vocab, n_interactions=total)
