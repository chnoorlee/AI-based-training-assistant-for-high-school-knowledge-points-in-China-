"""认知诊断单测：NeuralCD 可学习 + 引擎能定位薄弱点。"""
import numpy as np

from app.data.problem_bank import BANK
from app.modules.diagnosis.engine import ENGINE
from app.modules.diagnosis.neural_cd import NeuralCD
from app.schemas import ResponseRecord
from app.services.store import STORE


def _rec(uid, pid, correct, t=60):
    p = BANK.get(pid)
    return ResponseRecord(user_id=uid, problem_id=pid, correct=correct, time_spent_s=t,
                          concept_ids=list(p.concept_ids), difficulty=p.difficulty)


def test_neuralcd_learns_from_outcome():
    Q = np.array([[1.0]])
    m = NeuralCD(Q, np.array([0.5]), np.array([0.8]))
    a_wrong = m.estimate_student([0], [0.0])
    a_right = m.estimate_student([0], [1.0])
    assert a_right[0] > a_wrong[0]
    assert (m.predict_prob_for_mastery(a_right, 0)
            > m.predict_prob_for_mastery(a_wrong, 0))


def test_engine_identifies_derivative_weakness():
    STORE.reset()
    uid = "stu_diag"
    recs = [_rec(uid, "M0001", True), _rec(uid, "M0004", True), _rec(uid, "M0008", True),
            _rec(uid, "M0002", False), _rec(uid, "M0003", False, t=130)]
    for r in recs:
        STORE.add_response(r)
    report = ENGINE.diagnose(uid, STORE.get_responses(uid))

    assert report.n_responses == 5
    assert any("DERIV" in c for c in report.weak_concepts)  # 导数被判薄弱
    assert report.radar and report.error_profile  # 雷达图 + 错误画像非空
    assert report.explanation
    for cm in report.concept_mastery:
        assert 0.0 <= cm.score <= 1.0 and 0.0 <= cm.predicted_correct_prob <= 1.0


def test_cold_start_blueprint_covers_modules():
    ids = ENGINE.build_cold_start_test(30)
    assert len(ids) == len(set(ids))  # 不重复
    covered = {c for i in ids for c in BANK.get(i).concept_ids}
    assert len(covered) >= 10  # 覆盖足够多知识点
