"""错题本复习管理：把作答接入排程，产出每日复习队列、统计与未来预测。

接入点：
  - 任意作答 record_attempt：题目已在复习表 → 视为一次复习并更新排程；
    否则若答错 → 作为新错题入册（当日到期）。
  - 掌握度：用该生在题目所属知识点上的近期正确率作轻量代理，调制复习间隔。
内存实现（STORE.review_states），生产替换为 DB，接口不变。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.data.problem_bank import BANK
from app.modules.review.scheduler import (
    ReviewState, initial_state, is_due, priority, quality_from_attempt,
    retention, schedule,
)
from app.schemas import (
    ReviewForecast, ReviewForecastDay, ReviewItem, ReviewQueue, ReviewStats, ReviewStatus,
    utcnow,
)
from app.services.store import STORE


class ReviewBook:
    def __init__(self, store=None) -> None:
        self.store = store or STORE

    # ── 掌握度代理：知识点近期正确率 ─────────────────────────
    def _mastery(self, user_id: str, concept_ids: list[str]) -> float:
        resps = self.store.get_responses(user_id)
        rates = []
        for c in concept_ids:
            rel = [r for r in resps if c in (r.concept_ids or [])]
            if rel:
                rates.append(sum(1 for r in rel if r.correct) / len(rel))
        return sum(rates) / len(rates) if rates else 0.5

    def _states(self, user_id: str) -> dict[str, ReviewState]:
        return self.store.review_states[user_id]

    # ── 接入作答 ────────────────────────────────────────────
    def record_attempt(self, user_id: str, problem_id: str, correct: bool,
                       time_spent_s: float = 0.0, now: Optional[datetime] = None
                       ) -> Optional[ReviewState]:
        now = now or utcnow()
        states = self._states(user_id)
        p = BANK.get(problem_id)
        concept_ids = list(p.concept_ids) if p else []

        if problem_id in states:  # 一次复习
            st = states[problem_id]
            q = quality_from_attempt(correct, time_spent_s)
            schedule(st, q, self._mastery(user_id, st.concept_ids), now)
            return st
        if not correct:  # 新错题入册
            st = initial_state(problem_id, concept_ids, now)
            states[problem_id] = st
            return st
        return None  # 答对且非错题，无需排程

    # ── 每日复习队列 ────────────────────────────────────────
    def due_queue(self, user_id: str, limit: int = 20,
                  now: Optional[datetime] = None) -> ReviewQueue:
        now = now or utcnow()
        states = self._states(user_id)
        due = [st for st in states.values() if is_due(st, now)]
        scored = sorted(due, key=lambda s: -priority(s, now, self._weight(s)))
        items = [self._to_item(st, now) for st in scored[:limit]]
        return ReviewQueue(user_id=user_id, as_of=now, due_count=len(due),
                           capacity=limit, items=items)

    def grade(self, user_id: str, problem_id: str, correct: bool,
              time_spent_s: float = 0.0, now: Optional[datetime] = None) -> Optional[ReviewItem]:
        st = self.record_attempt(user_id, problem_id, correct, time_spent_s, now)
        return self._to_item(st, now or utcnow()) if st else None

    # ── 统计与预测 ──────────────────────────────────────────
    def stats(self, user_id: str, now: Optional[datetime] = None) -> ReviewStats:
        now = now or utcnow()
        states = list(self._states(user_id).values())
        active = [s for s in states if s.status != "graduated"]
        rets = [retention(s, now) for s in active]
        return ReviewStats(
            user_id=user_id, total=len(states),
            due_now=sum(1 for s in states if is_due(s, now)),
            learning=sum(1 for s in states if s.status == "learning"),
            review=sum(1 for s in states if s.status == "review"),
            graduated=sum(1 for s in states if s.status == "graduated"),
            lapses_total=sum(s.lapses for s in states),
            avg_retention=round(sum(rets) / len(rets), 3) if rets else 1.0)

    def forecast(self, user_id: str, days: int = 7,
                 now: Optional[datetime] = None) -> ReviewForecast:
        now = now or utcnow()
        today = now.date()
        buckets = {(today + timedelta(days=i)).isoformat(): 0 for i in range(days)}
        overdue = 0
        for st in self._states(user_id).values():
            if st.status == "graduated":
                continue
            d = st.due.date()
            if d < today:
                overdue += 1
            elif d.isoformat() in buckets:
                buckets[d.isoformat()] += 1
        return ReviewForecast(user_id=user_id, overdue=overdue,
                              days=[ReviewForecastDay(date=k, count=v) for k, v in buckets.items()])

    # ── 辅助 ───────────────────────────────────────────────
    def _weight(self, st: ReviewState) -> float:
        p = BANK.get(st.problem_id)
        return p.difficulty if p else 0.5  # 考点权重用难度代理

    def _to_item(self, st: ReviewState, now: datetime) -> ReviewItem:
        p = BANK.get(st.problem_id)
        return ReviewItem(
            problem_id=st.problem_id, concept_ids=st.concept_ids,
            stem=(p.stem if p else ""), status=ReviewStatus(st.status), due=st.due,
            interval_days=st.interval_days, repetitions=st.repetitions, ease=round(st.ease, 2),
            lapses=st.lapses, retention=round(retention(st, now), 3),
            priority=priority(st, now, self._weight(st)), last_reviewed=st.last_reviewed)


REVIEW_BOOK = ReviewBook()
