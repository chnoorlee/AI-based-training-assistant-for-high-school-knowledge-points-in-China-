"""主观题批改测试：作文细则评分 + 采分点匹配 + 校准 + 合规。"""
from datetime import datetime

from app.core import compliance
from app.core.config import settings
from app.modules.grading.essay import EssayGrader
from app.modules.grading.subjective import SubjectiveGrader

PROMPT = "阅读材料，围绕'规则与自由'写一篇议论文。"
GOOD = (
    "在我看来，规则与自由并非对立，正是规则保障了真正的自由。\n"
    "首先，规则划定边界，使个体免于彼此侵害。例如交通规则看似约束，实则保障了所有人的通行自由。\n"
    "其次，从辩证的角度看，自由的本质并非为所欲为，而是在规则之内的从容。古人云从心所欲不逾矩，正说明这一点。\n"
    "然而，规则也应随时代发展，因此我们既要敬畏规则，也要推动其完善，透过现象看本质。\n"
    "综上所述，唯有在规则与自由之间保持张力，社会才能既有秩序又有活力，这启示我们应理性看待二者关系。")
BAD = "规则不好。自由最重要。"


def test_good_essay_scores_higher():
    g = EssayGrader()
    good = g.grade(PROMPT, GOOD)
    bad = g.grade(PROMPT, BAD)
    assert 0 <= bad.total <= good.total <= 60
    assert good.total > bad.total
    assert len(good.dimensions) == 3
    assert all(0 <= d.score <= d.max_score for d in good.dimensions)


def test_essay_is_deterministic():
    g = EssayGrader()
    assert g.grade(PROMPT, GOOD).total == g.grade(PROMPT, GOOD).total


def test_essay_content_safety_flags_banned():
    g = EssayGrader()
    r = g.grade(PROMPT, GOOD + "（含暴力等不良内容）")
    assert r.content_safe is False


def test_essay_calibration_shifts_and_clamps():
    base = EssayGrader().grade(PROMPT, GOOD).total
    up = EssayGrader(scale=1.0, offset=10).grade(PROMPT, GOOD).total
    assert up >= base and up <= 60  # 偏移并被夹在满分内


REF = [
    {"id": "p1", "description": "纬度位置决定太阳辐射强弱", "points": 3,
     "keywords": ["纬度", "太阳辐射"]},
    {"id": "p2", "description": "海陆位置形成海洋性与大陆性差异", "points": 3,
     "keywords": ["海陆", "海洋", "大陆"]},
    {"id": "p3", "description": "地形地势影响气温与降水", "points": 2, "keywords": ["地形", "地势"]},
    {"id": "p4", "description": "洋流影响沿岸气候", "points": 2, "keywords": ["洋流"]},
]


def test_subjective_point_matching_partial():
    ans = ("首先，纬度位置决定了太阳辐射的强弱；其次，海陆位置使气候有海洋性与大陆性之分；"
           "再次，地形地势影响气温和降水。")
    r = SubjectiveGrader().grade("影响气候的因素", ans, REF)
    hit = {p.id: p.hit for p in r.points}
    assert hit["p1"] and hit["p2"] and hit["p3"] and not hit["p4"]
    assert r.total == 8.0 and r.full_marks == 10.0
    assert 0 <= r.logic_score <= 5
    assert any("洋流" in s for s in r.suggestions)


def test_subjective_full_marks_when_all_hit():
    ans = ("纬度位置决定太阳辐射；海陆位置形成海洋性大陆性差异；地形地势影响气温降水；洋流影响沿岸气候。")
    r = SubjectiveGrader().grade("影响气候的因素", ans, REF)
    assert r.total == r.full_marks == 10.0


def test_grading_blocked_during_gaokao():
    now = datetime(2026, 6, 8, 12, tzinfo=settings.tz)
    assert not compliance.check("essay_grade", now=now).allowed
    assert not compliance.check("subjective_grade", now=now).allowed
