"""模考估分 + 反馈闭环测试：估分、真实模考校准、应试丢分加权、规划重排、趋势。"""
from datetime import datetime

from app.core import compliance
from app.core.config import settings
from app.data.knowledge_graph import KG
from app.data.problem_bank import BANK
from app.modules.diagnosis.engine import ENGINE
from app.modules.exam import feedback
from app.modules.exam.mock_store import MockExamBook
from app.modules.exam.predictor import PREDICTOR
from app.modules.planner.planner import PLANNER
from app.schemas import ResponseRecord
from app.services.store import STORE

SAMPLE = [("M0001", True), ("M0002", False), ("M0003", False), ("M0006", True),
          ("P0001", False), ("P0002", True), ("C0001", True), ("B0001", False), ("B0003", True)]


def _report(uid):
    STORE.reset()
    for pid, ok in SAMPLE:
        p = BANK.get(pid)
        STORE.add_response(ResponseRecord(user_id=uid, problem_id=pid, correct=ok,
                                          time_spent_s=60, concept_ids=list(p.concept_ids),
                                          difficulty=p.difficulty))
    return ENGINE.diagnose(uid, STORE.get_responses(uid))


def test_predict_scales_and_bounds():
    pred = PREDICTOR.predict(_report("s1"))
    assert pred.subjects and 0 <= pred.total_predicted <= pred.total_full
    assert all(0 <= s.predicted <= s.full_marks for s in pred.subjects)
    assert PREDICTOR.predict_subject_raw(_report("s1"), "math")[0] > 0
    assert not pred.calibrated and pred.n_mocks == 0


def test_real_mock_calibrates_overprediction_down():
    r = _report("s2")
    book = MockExamBook(STORE)
    raw = PREDICTOR.predict_subject_raw(r, "math")[0]
    book.submit("s2", "一模", {"math": raw - 30}, PREDICTOR, r)  # 真实模考远低于预测
    cal = book.calibration("s2")
    assert cal["math"]["offset"] < 0 and cal["math"]["n"] == 1
    pred = PREDICTOR.predict(r, calibration=cal)
    ms = next(s for s in pred.subjects if s.subject == "math")
    assert ms.predicted < ms.raw_predicted and pred.calibrated  # 校准后下调


def test_feedback_boosts_underperforming_subject():
    r = _report("s3")
    book = MockExamBook(STORE)
    raw = PREDICTOR.predict_subject_raw(r, "physics")[0]
    book.submit("s3", "一模", {"physics": max(0, raw - 25)}, PREDICTOR, r)  # 会做却失分
    an = feedback.analyze(book, r, PREDICTOR, "s3")
    assert an["physics"]["multiplier"] > 1.0 and an["physics"]["execution_gap"] > 0
    assert "失分" in an["physics"]["note"]
    assert an["biology"]["actual"] is None and an["biology"]["multiplier"] == 1.0  # 没考→不加权


def test_planner_reweights_minutes_toward_boosted_subject():
    r = _report("s4")
    c0 = PLANNER._candidates(r, "")
    c1 = PLANNER._candidates(r, "", {"physics": 1.8})
    m0, _ = PLANNER._allocate(c0, 1500)
    m1, _ = PLANNER._allocate(c1, 1500)
    phys0 = sum(v for cid, v in m0.items() if KG.subject_of(cid) == "physics")
    phys1 = sum(v for cid, v in m1.items() if KG.subject_of(cid) == "physics")
    assert phys1 > phys0  # 模考加权 → 物理获得更多投入


def test_plan_surfaces_calibrated_projection():
    r = _report("s6")
    book = MockExamBook(STORE)
    raw = PREDICTOR.predict_subject_raw(r, "math")[0]
    book.submit("s6", "一模", {"math": raw - 20}, PREDICTOR, r)
    sw = feedback.subject_weights(book, r, PREDICTOR, "s6")
    proj = PREDICTOR.predict(r, book.calibration("s6"), book.latest_actuals("s6"), sw)
    plan = PLANNER.plan(r, daily_minutes=120, days_left=10, subject_weights=sw, projection=proj)
    assert plan.projected_score_now > 0 and plan.mock_calibrated
    assert plan.feedback_note  # 应说明上调了某科优先级


def test_trend_and_history():
    r = _report("s5")
    book = MockExamBook(STORE)
    book.submit("s5", "一模", {"math": 100}, PREDICTOR, r)
    book.submit("s5", "二模", {"math": 90}, PREDICTOR, r)  # 下滑
    assert book.trend("s5")["math"] < 0
    assert len(book.history("s5").records) == 2


def test_mock_allowed_during_gaokao():
    assert compliance.check("review", now=datetime(2026, 6, 8, 12, tzinfo=settings.tz)).allowed
