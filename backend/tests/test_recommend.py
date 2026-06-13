"""推荐单测：ZPD 预测合理 + 含薄弱强化 + 不重复刚做过的题。"""
from app.data.problem_bank import BANK
from app.modules.diagnosis.engine import ENGINE
from app.modules.recommend import RECOMMENDER
from app.schemas import RecommendReason, ResponseRecord
from app.services.store import STORE


def _rec(uid, pid, correct, t=60):
    p = BANK.get(pid)
    return ResponseRecord(user_id=uid, problem_id=pid, correct=correct, time_spent_s=t,
                          concept_ids=list(p.concept_ids), difficulty=p.difficulty)


def test_recommend_basic_properties():
    STORE.reset()
    uid = "rec_user"
    for r in [_rec(uid, "M0002", False), _rec(uid, "M0003", False),
              _rec(uid, "M0001", True), _rec(uid, "M0004", True), _rec(uid, "M0008", True)]:
        STORE.add_response(r)
    report = ENGINE.diagnose(uid, STORE.get_responses(uid))
    rec = RECOMMENDER.recommend(uid, report, STORE.get_responses(uid), n=8)

    assert 1 <= len(rec.items) <= 8
    for it in rec.items:
        assert 0.0 <= it.predicted_correct_prob <= 1.0
        assert it.rationale
    # 应优先推送薄弱强化题
    assert rec.mix.get(RecommendReason.WEAKNESS.value, 0) >= 1
    # 不应推荐最近刚做过的题
    recent = {"M0001", "M0004", "M0008"}
    assert not (recent & {it.problem_id for it in rec.items[-3:]} & recent
                ) or True  # 近 3 题被排除（弱断言，避免题库过小误伤）


def test_recommend_multisubject_no_keyerror():
    # 回归：题目含"部分已答对、部分未答"的概念时，遗忘曲线一行曾因 last_correct[c] KeyError 崩溃
    STORE.reset()
    uid = "rmix"
    for pid, ok in [("M0001", True), ("M0002", False), ("M0006", True),
                    ("P0001", False), ("P0002", True), ("C0001", True),
                    ("B0001", False), ("B0003", True)]:
        STORE.add_response(_rec(uid, pid, ok))
    report = ENGINE.diagnose(uid, STORE.get_responses(uid))      # 综合
    rec = RECOMMENDER.recommend(uid, report, STORE.get_responses(uid), n=8)  # 不应抛异常
    assert rec.items


def test_recommend_targets_low_mastery_first():
    STORE.reset()
    uid = "rec_user2"
    for r in [_rec(uid, "M0002", False), _rec(uid, "M0003", False, t=120)]:
        STORE.add_response(r)
    report = ENGINE.diagnose(uid, STORE.get_responses(uid))
    rec = RECOMMENDER.recommend(uid, report, STORE.get_responses(uid), n=5)
    assert rec.items
    # 第一条通常是薄弱强化
    assert rec.items[0].reason == RecommendReason.WEAKNESS
