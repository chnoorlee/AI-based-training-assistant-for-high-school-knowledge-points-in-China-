"""AI 提分规划师测试：考点权重 + 性价比排序 + 预算/学习曲线 + 前置打地基 + 倒计时熔断。"""
from datetime import datetime

from app.core import compliance
from app.core.config import settings
from app.data.exam_blueprint import concept_weight, subject_total
from app.modules.diagnosis.engine import ENGINE
from app.modules.planner.planner import PLANNER
from app.schemas import ResponseRecord
from app.services.store import STORE
from app.data.problem_bank import BANK

SAMPLE = [("M0001", True), ("M0002", False), ("M0003", False), ("M0006", True),
          ("P0001", False), ("P0002", True), ("C0001", True), ("C0004", False),
          ("B0001", False), ("B0003", True)]


def _rec(uid, pid, ok):
    p = BANK.get(pid)
    return ResponseRecord(user_id=uid, problem_id=pid, correct=ok, time_spent_s=60,
                          concept_ids=list(p.concept_ids), difficulty=p.difficulty)


def _report(uid, subject=""):
    STORE.reset()
    for pid, ok in SAMPLE:
        STORE.add_response(_rec(uid, pid, ok))
    return ENGINE.diagnose(uid, STORE.get_responses(uid), subject=subject)


def test_blueprint_weights():
    assert subject_total("math") == 150 and subject_total("biology") == 90
    # 解析几何(22分/2点=11) > 复数(5分/1点=5)
    assert concept_weight("MATH_CONIC") > concept_weight("MATH_COMPLEX") > 0


def test_plan_prioritizes_high_value_and_sorts_by_gain():
    plan = PLANNER.plan(_report("p1"), daily_minutes=120, days_left=10)
    assert plan.priorities and plan.expected_score_gain > 0
    gains = [i.expected_gain for i in plan.priorities]
    assert gains == sorted(gains, reverse=True)            # 按预计提分降序
    assert plan.total_study_minutes <= 10 * 120
    assert plan.priorities[0].roi > 0 and plan.priorities[0].allocated_minutes > 0


def test_allocation_respects_budget_and_curve():
    cands = PLANNER._candidates(_report("p2"), "")
    mins, state = PLANNER._allocate(cands, 600)
    assert sum(mins.values()) <= 600
    for c in cands:
        assert state[c["id"]] >= c["m0"] - 1e-9 and state[c["id"]] <= 0.93  # 不降、有上限


def test_prereq_foundation_gets_time():
    # 限定数学以排除跨学科竞争，直接看分配：先修 DERIV_MONO 应先被抬升，再解锁 DERIV_EXTREME
    cands = PLANNER._candidates(_report("p3", subject="math"), "math")
    mins, state = PLANNER._allocate(cands, 800)
    assert mins.get("MATH_DERIV_MONO", 0) > 0            # 地基（先修）获得投入
    assert state["MATH_DERIV_MONO"] >= 0.5              # 被抬过达标线
    assert mins.get("MATH_DERIV_EXTREME", 0) > 0        # 解锁后主攻也获得投入


def test_plan_countdown_and_blackout_review_only():
    plan = PLANNER.plan(_report("p4"), daily_minutes=120, days_left=7, review_due=3,
                        now=datetime(2026, 6, 5, 8, tzinfo=settings.tz))
    assert len(plan.days) <= 7
    blackout = [d for d in plan.days if d.is_blackout]
    assert blackout                                         # 6/7–6/10 落在预览窗口
    for d in blackout:
        assert d.tasks and all(t.kind == "review" for t in d.tasks)  # 熔断日仅复习
    normal = [d for d in plan.days if not d.is_blackout]
    assert any(t.kind == "learn" for t in normal[0].tasks)  # 普通日有攻坚任务
    assert any(t.kind == "review" for t in normal[0].tasks)  # 也嵌入错题复习


def test_plan_auto_days_left_from_gaokao():
    plan = PLANNER.plan(_report("p5"), daily_minutes=120,
                        now=datetime(2026, 5, 1, 8, tzinfo=settings.tz))
    assert plan.days_left == (settings.gaokao_blackout_start - datetime(2026, 5, 1).date()).days


def test_plan_allowed_during_gaokao():
    assert compliance.check("review", now=datetime(2026, 6, 8, 12, tzinfo=settings.tz)).allowed
