"""内存数据存储（生产替换点：MySQL 结构化 + MongoDB 非结构化）。

只存与学习相关的数据：用户档案、作答记录、用量、错题本——践行「数据最小化」。
单进程、单例；演示与单测足够。生产换成仓储层即可，接口保持不变。
"""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import date
from typing import Optional

from app.schemas import ResponseRecord, utcnow


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.users: dict[str, dict] = {}
        self.responses: dict[str, list[ResponseRecord]] = defaultdict(list)
        # usage[user_id][YYYY-MM-DD] = 累计分钟
        self.usage: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.wrongbook: dict[str, list[str]] = defaultdict(list)  # 错题本：题目 id
        # 监护：parent_id -> [child_user_id]；child -> 设置
        self.guardianship: dict[str, dict] = {}
        # 解题进度门控：(user_id, problem_id) -> 已揭示的最高级别（强制「先引导后揭示」）
        self.solve_progress: dict[tuple[str, str], int] = {}
        # 错题复习排程：user_id -> {problem_id -> ReviewState}
        self.review_states: dict[str, dict] = defaultdict(dict)
        # 真实模考记录：user_id -> [dict(exam_name, date, scores, predicted_raw)]
        self.mock_exams: dict[str, list[dict]] = defaultdict(list)

    # ── 用户 ───────────────────────────────────────────────
    def ensure_user(self, user_id: str, grade: str = "高三", is_minor: bool = True) -> dict:
        with self._lock:
            if user_id not in self.users:
                self.users[user_id] = {
                    "user_id": user_id, "grade": grade, "is_minor": is_minor,
                    "created_at": utcnow(),
                }
            return self.users[user_id]

    # ── 作答记录 ────────────────────────────────────────────
    def add_response(self, rec: ResponseRecord) -> None:
        with self._lock:
            self.ensure_user(rec.user_id)
            self.responses[rec.user_id].append(rec)
            if not rec.correct and rec.problem_id not in self.wrongbook[rec.user_id]:
                self.wrongbook[rec.user_id].append(rec.problem_id)

    def get_responses(self, user_id: str) -> list[ResponseRecord]:
        return list(self.responses.get(user_id, []))

    def n_responses(self, user_id: str) -> int:
        return len(self.responses.get(user_id, []))

    def get_wrongbook(self, user_id: str) -> list[str]:
        return list(self.wrongbook.get(user_id, []))

    # ── 用量（防沉迷）────────────────────────────────────────
    def add_usage_minutes(self, user_id: str, minutes: float, day: Optional[date] = None) -> None:
        day = day or utcnow().date()
        with self._lock:
            self.usage[user_id][day.isoformat()] += minutes

    def get_today_usage(self, user_id: str, day: Optional[date] = None) -> float:
        day = day or utcnow().date()
        return self.usage.get(user_id, {}).get(day.isoformat(), 0.0)

    # ── 解题进度门控 ────────────────────────────────────────
    def get_solve_level(self, user_id: str, problem_id: str) -> int:
        return self.solve_progress.get((user_id, problem_id), -1)

    def set_solve_level(self, user_id: str, problem_id: str, level: int) -> None:
        with self._lock:
            key = (user_id, problem_id)
            self.solve_progress[key] = max(self.solve_progress.get(key, -1), level)

    # ── 监护（家长端）───────────────────────────────────────
    def set_guardian_setting(self, child_user_id: str, **settings) -> None:
        with self._lock:
            self.guardianship.setdefault(child_user_id, {}).update(settings)

    def get_guardian_setting(self, child_user_id: str) -> dict:
        return dict(self.guardianship.get(child_user_id, {}))

    # ── 测试辅助 ────────────────────────────────────────────
    def reset(self) -> None:
        with self._lock:
            self.users.clear()
            self.responses.clear()
            self.usage.clear()
            self.wrongbook.clear()
            self.guardianship.clear()
            self.solve_progress.clear()
            self.review_states.clear()
            self.mock_exams.clear()


# 单例
STORE = Store()
