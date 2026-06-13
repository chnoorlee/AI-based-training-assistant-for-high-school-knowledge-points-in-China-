"""错题本智能复习排程测试：SM-2 排程 + 遗忘曲线 + 队列/统计/预测 + 合规。"""
from datetime import datetime, timedelta, timezone

from app.core import compliance
from app.core.config import settings
from app.modules.review.book import ReviewBook
from app.modules.review.scheduler import (
    initial_state, priority, retention, schedule,
)
from app.services.store import Store

T0 = datetime(2026, 5, 1, 10, tzinfo=timezone.utc)


# ── 排程算法 ────────────────────────────────────────────────
def test_initial_state_due_now_learning():
    st = initial_state("M0002", ["MATH_DERIV_EXTREME"], T0)
    assert st.status == "learning" and st.due == T0 and st.repetitions == 0 and st.lapses == 1


def test_correct_grows_interval_wrong_resets():
    st = initial_state("M0002", ["c"], T0)
    schedule(st, quality=4, mastery=0.5, now=T0)
    assert st.repetitions == 1 and st.status == "review" and st.interval_days >= 1
    i1 = st.interval_days
    schedule(st, quality=5, mastery=0.5, now=T0 + timedelta(days=i1))
    assert st.interval_days > i1 and st.repetitions == 2  # 间隔增长
    ease_before = st.ease
    schedule(st, quality=2, mastery=0.5, now=T0 + timedelta(days=30))  # 答错→重学
    assert st.repetitions == 0 and st.status == "learning" and st.interval_days == 1.0
    assert st.lapses == 2 and st.ease < ease_before  # 初始错+重学失败=2 次；ease 下降


def test_ease_bounds():
    st = initial_state("p", ["c"], T0)
    for _ in range(10):
        schedule(st, quality=0, now=T0)  # 连续最差
    assert st.ease >= 1.3
    st2 = initial_state("p2", ["c"], T0)
    for _ in range(20):
        schedule(st2, quality=5, now=T0)
    assert st2.ease <= 3.0


def test_graduation_after_enough_reviews():
    st = initial_state("p", ["c"], T0)
    now = T0
    for _ in range(8):
        schedule(st, quality=5, mastery=1.0, now=now)
        now = st.due
        if st.status == "graduated":
            break
    assert st.status == "graduated" and st.repetitions >= 4 and st.interval_days >= 21


def test_retention_monotonic_decreasing():
    st = initial_state("p", ["c"], T0)
    schedule(st, quality=4, mastery=0.5, now=T0)  # interval≈1
    st.interval_days = 5.0
    st.last_reviewed = T0
    r0 = retention(st, T0)
    r5 = retention(st, T0 + timedelta(days=5))
    r10 = retention(st, T0 + timedelta(days=10))
    assert r0 > r5 > r10 and abs(r5 - 0.90) < 0.02  # 到期时≈90%


def test_priority_overdue_beats_future():
    overdue = initial_state("a", ["c"], T0)
    overdue.due = T0 - timedelta(days=3)
    future = initial_state("b", ["c"], T0)
    future.status = "review"
    future.due = T0 + timedelta(days=3)
    assert priority(overdue, T0) > priority(future, T0)


# ── 管理器 / 接入 ───────────────────────────────────────────
def _book():
    return ReviewBook(store=Store())


def test_wrong_creates_due_item_correct_advances():
    book = _book()
    st = book.record_attempt("u", "M0002", correct=False, now=T0)
    assert st is not None and st.due == T0  # 错题当日到期
    # 命中错题再作答（答对）→ 视为复习并推后
    st2 = book.record_attempt("u", "M0002", correct=True, time_spent_s=40, now=T0)
    assert st2.repetitions == 1 and st2.due > T0
    # 答对一道非错题 → 不排程
    assert book.record_attempt("u", "M0004", correct=True, now=T0) is None


def test_due_queue_sorted_and_capped():
    book = _book()
    for pid in ["M0002", "M0003", "M0007", "M0010", "M0012"]:
        book.record_attempt("u", pid, correct=False, now=T0)
    q = book.due_queue("u", limit=3, now=T0)
    assert q.due_count == 5 and len(q.items) == 3  # 截断
    prios = [it.priority for it in q.items]
    assert prios == sorted(prios, reverse=True)  # 按紧迫度降序


def test_stats_and_forecast():
    book = _book()
    book.record_attempt("u", "M0002", correct=False, now=T0)
    book.record_attempt("u", "M0003", correct=False, now=T0)
    book.grade("u", "M0003", correct=True, time_spent_s=30, now=T0)  # 推到未来
    s = book.stats("u", now=T0)
    assert s.total == 2 and s.due_now >= 1 and s.learning >= 1
    f = book.forecast("u", days=7, now=T0)
    assert len(f.days) == 7 and sum(d.count for d in f.days) >= 1


def test_review_allowed_during_gaokao():
    now = datetime(2026, 6, 8, 12, tzinfo=settings.tz)
    assert compliance.check("review", now=now).allowed  # 错题复习熔断期仍开放
