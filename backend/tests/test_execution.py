"""题型级应试丢分 + 限时训练测试。"""
from datetime import datetime

from app.core import compliance
from app.core.config import settings
from app.data.problem_bank import BANK
from app.modules.diagnosis.engine import ENGINE
from app.modules.exam.mock_store import MockExamBook
from app.modules.exam.predictor import PREDICTOR
from app.modules.exam.sections import analyze, attain, execution_report
from app.modules.planner.planner import PLANNER
from app.schemas import ResponseRecord, TimedDrill
from app.services.store import STORE

SAMPLE = [("M0001", True), ("M0002", False), ("P0001", False), ("C0001", True), ("B0001", False)]


def _report(uid):
    STORE.reset()
    for pid, ok in SAMPLE:
        p = BANK.get(pid)
        STORE.add_response(ResponseRecord(user_id=uid, problem_id=pid, correct=ok,
                                          time_spent_s=60, concept_ids=list(p.concept_ids),
                                          difficulty=p.difficulty))
    return ENGINE.diagnose(uid, STORE.get_responses(uid))


def test_attain_ordering():
    sm = 0.6
    assert attain("易", sm) > attain("中", sm) >= attain("难", sm) > attain("压轴", sm)


def test_analyze_section_loss():
    ss = analyze("math", {"m_ch_easy": 15, "m_solve_hard": 5}, sm=0.7)
    easy = next(s for s in ss if s.section_id == "m_ch_easy")
    assert easy.expected > 15 and easy.loss == round(easy.expected - 15, 1) and easy.tier == "易"
    blank = next(s for s in ss if s.section_id == "m_blank")
    assert blank.got is None and blank.loss == 0.0  # 未填的区块不计丢分


def test_execution_report_and_drills_sorted():
    r = _report("e1")
    book = MockExamBook(STORE)
    book.submit("e1", "一模", {"math": 60}, PREDICTOR, r, section_scores={
        "math": {"m_ch_easy": 10, "m_ch_hard": 2, "m_blank": 6, "m_solve_mid": 18, "m_solve_hard": 3}})
    rep = execution_report(book, r, PREDICTOR)
    assert rep.has_section_data and rep.subjects and rep.drills
    recs = [d.recoverable_points for d in rep.drills]
    assert recs == sorted(recs, reverse=True)              # 按可挽回分降序
    assert any(d.qtype == "choice" for d in rep.drills)    # 含选择题限时训练
    # 易档可挽回≈丢分、压轴可挽回<丢分
    sec = {s.section_id: s for s in rep.subjects[0].sections}
    easy_drill = next((d for d in rep.drills if d.tier == "易"), None)
    if easy_drill:
        assert easy_drill.recoverable_points >= sec["m_ch_easy"].loss * 0.9


def test_section_score_clamped_to_full():
    # 脏数据：30 分的选择题误填 999 → 夹到满分、丢分为 0，不扭曲归因
    ss = analyze("math", {"m_ch_easy": 999, "m_blank": -5}, sm=0.7)
    easy = next(s for s in ss if s.section_id == "m_ch_easy")
    blank = next(s for s in ss if s.section_id == "m_blank")
    assert easy.got == easy.full and easy.loss == 0.0
    assert blank.got == 0.0 and blank.loss == round(blank.expected, 1)


def test_no_section_data_returns_hint():
    r = _report("e3")
    book = MockExamBook(STORE)
    book.submit("e3", "一模", {"math": 90}, PREDICTOR, r)  # 只给总分，无题型
    rep = execution_report(book, r, PREDICTOR)
    assert not rep.has_section_data and not rep.drills and "录入" in rep.note


def test_planner_weaves_timed_drill_as_first_task():
    r = _report("e2")
    dr = TimedDrill(subject="math", title="数学·选择题(基础) 限时训练", qtype="choice", tier="易",
                    n_problems=8, time_limit_min=12, goal="正确率≥90%", cause="审题/手滑",
                    recoverable_points=5.0)
    plan = PLANNER.plan(r, daily_minutes=120, days_left=5, timed_drills=[dr],
                        now=datetime(2026, 5, 1, 8, tzinfo=settings.tz))
    assert plan.timed_drills and plan.timed_drills[0].title == dr.title
    assert plan.days[0].tasks[0].kind == "timed_drill"     # 每天首个任务即限时训练
    assert plan.days[0].tasks[0].minutes == 12


def test_timed_drills_listed_equals_woven():
    # 限时训练多于可排天数时，plan.timed_drills 必须正好等于「实际排进计划」的那些（展示=已排程）
    r = _report("e5")
    drills = [TimedDrill(subject="math", title=f"训练{i}", qtype="choice", tier="易",
                         n_problems=8, time_limit_min=12, goal="g", cause="c",
                         recoverable_points=float(10 - i)) for i in range(5)]
    plan = PLANNER.plan(r, daily_minutes=120, days_left=2, timed_drills=drills,
                        now=datetime(2026, 5, 1, 8, tzinfo=settings.tz))
    woven = [t.concept_name for d in plan.days for t in d.tasks if t.kind == "timed_drill"]
    assert len(plan.timed_drills) == 2                       # 只有 2 天 → 只排 2 项
    assert [d.title for d in plan.timed_drills] == woven     # 列表与每日首项严格一致


def test_execution_allowed_during_gaokao():
    assert compliance.check("review", now=datetime(2026, 6, 8, 12, tzinfo=settings.tz)).allowed
