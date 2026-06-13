"""错题复习排程算法：SM-2 间隔重复 + 艾宾浩斯遗忘曲线 + 掌握度调制。

- 首次做错 → 进入"学习"态，当日到期（尽快复习）。
- 每次复习按回忆质量更新难度因子 ease 与间隔 interval：答对则间隔按 ease 增长，
  答错则重学（间隔回落、ease 下降）。低掌握度知识点缩短间隔，高掌握度拉长。
- 间隔够长且复习够多次 → "毕业"（移出活跃队列；再错则复活）。
- 复习紧迫度 = 逾期 + 遗忘程度(1-保持率) + 考点权重 + 学习态加权。
纯函数 + 轻量 dataclass，便于单测与序列化。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app.schemas import utcnow

TARGET_RETENTION = 0.90  # 安排在保持率约 90% 时复习
_DECAY = -math.log(TARGET_RETENTION)  # ≈0.105
GRADUATE_INTERVAL = 21.0  # 间隔≥21 天
GRADUATE_REPS = 4  # 且复习≥4 次 → 毕业


@dataclass
class ReviewState:
    problem_id: str
    concept_ids: list[str] = field(default_factory=list)
    ease: float = 2.5
    interval_days: float = 0.0
    repetitions: int = 0
    lapses: int = 0
    status: str = "learning"
    due: datetime = field(default_factory=utcnow)
    last_reviewed: datetime = field(default_factory=utcnow)
    created: datetime = field(default_factory=utcnow)


def initial_state(problem_id: str, concept_ids: list[str],
                  now: Optional[datetime] = None) -> ReviewState:
    """首次做错：当日到期，进入学习态。"""
    now = now or utcnow()
    return ReviewState(problem_id=problem_id, concept_ids=list(concept_ids),
                       ease=2.5, interval_days=0.0, repetitions=0, lapses=1,
                       status="learning", due=now, last_reviewed=now, created=now)


def quality_from_attempt(correct: bool, time_spent_s: float,
                         expected_s: float = 90.0) -> int:
    """把一次复习作答映射为 SM-2 回忆质量 0~5。"""
    if not correct:
        return 2  # 失败（<3 触发重学）
    if time_spent_s and time_spent_s <= expected_s * 0.6:
        return 5  # 又快又准
    if not time_spent_s or time_spent_s <= expected_s * 1.3:
        return 4  # 正常答对
    return 3  # 答对但迟疑


def schedule(state: ReviewState, quality: int, mastery: float = 0.5,
             now: Optional[datetime] = None) -> ReviewState:
    """按回忆质量更新排程（SM-2 改进）。返回更新后的 state（原地）。"""
    now = now or utcnow()
    # ease 更新（SM-2 公式），夹在 [1.3, 3.0]
    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    state.ease = max(1.3, min(3.0, state.ease + delta))

    if quality < 3:  # 重学
        state.repetitions = 0
        state.lapses += 1
        state.interval_days = 1.0
        state.status = "learning"
    else:
        if state.repetitions == 0:
            base = 1.0
        elif state.repetitions == 1:
            base = 3.0
        else:
            base = state.interval_days * state.ease
        state.repetitions += 1
        factor = 0.7 + 0.6 * max(0.0, min(1.0, mastery))  # 低掌握缩短、高掌握拉长
        state.interval_days = max(1.0, min(365.0, round(base * factor, 1)))  # 封顶 1 年
        state.status = ("graduated"
                        if state.interval_days >= GRADUATE_INTERVAL
                        and state.repetitions >= GRADUATE_REPS else "review")

    state.last_reviewed = now
    state.due = now + timedelta(days=state.interval_days)
    return state


def retention(state: ReviewState, now: Optional[datetime] = None) -> float:
    """当前预测记忆保持率 R=exp(-decay·elapsed/interval)（到期时≈0.9，逾期更低）。"""
    now = now or utcnow()
    elapsed = (now - state.last_reviewed).total_seconds() / 86400
    S = max(state.interval_days, 0.5)
    return float(max(0.0, min(1.0, math.exp(-_DECAY * elapsed / S))))


def priority(state: ReviewState, now: Optional[datetime] = None,
             exam_weight: float = 0.5) -> float:
    """复习紧迫度：逾期天数 + 遗忘程度 + 考点权重 + 学习态加权。"""
    now = now or utcnow()
    overdue_days = (now - state.due).total_seconds() / 86400
    r = retention(state, now)
    learn_boost = 2.0 if state.status == "learning" else 0.0
    return round(max(0.0, overdue_days) * 1.0 + (1 - r) * 3.0
                 + exam_weight * 1.0 + learn_boost, 4)


def is_due(state: ReviewState, now: Optional[datetime] = None) -> bool:
    now = now or utcnow()
    return state.status != "graduated" and state.due <= now
