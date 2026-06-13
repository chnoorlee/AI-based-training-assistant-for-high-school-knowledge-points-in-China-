"""多学科扩展测试：物理/化学/生物 接入 + 按学科诊断/推荐切片 + 跨学科边 + 科学变式正确性。"""
import random
from fractions import Fraction

from app.data.knowledge_graph import KG
from app.data.problem_bank import BANK
from app.modules.diagnosis.engine import ENGINE
from app.modules.recommend import RECOMMENDER
from app.modules.variant.templates import TEMPLATES, frac_str
from app.modules.rag.solver import SOLVER
from app.schemas import RevealLevel, ResponseRecord, SolveRequest, Subject
from app.services.store import STORE


def _rec(uid, pid, ok, t=60):
    p = BANK.get(pid)
    return ResponseRecord(user_id=uid, problem_id=pid, correct=ok, time_spent_s=t,
                          concept_ids=list(p.concept_ids), difficulty=p.difficulty)


# ── 接入 ────────────────────────────────────────────────────
def test_four_subjects_loaded():
    subs = set(KG.subjects())
    assert {"math", "physics", "chemistry", "biology"} <= subs
    for s in ("physics", "chemistry", "biology"):
        assert len(KG.concepts_for_subject(s)) >= 8
        assert len(BANK.by_subject(s)) >= 5
    assert {Subject.PHYSICS, Subject.CHEMISTRY, Subject.BIOLOGY} <= set(Subject)


def test_cross_subject_edges_bidirectional():
    assert "CHEM_EQUILIBRIUM" in KG.cross_subject_of("BIO_PHOTOSYNTHESIS")
    assert "BIO_PHOTOSYNTHESIS" in KG.cross_subject_of("CHEM_EQUILIBRIUM")  # 光合作用-化学平衡
    assert "MATH_TRIG_FUNC" in KG.cross_subject_of("PHY_SHM")               # 简谐运动-三角函数
    assert "MATH_PROB" in KG.cross_subject_of("BIO_GENETICS")               # 遗传-概率


# ── 按学科诊断切片 ──────────────────────────────────────────
def test_diagnosis_is_subject_sliced():
    STORE.reset()
    uid = "ms"
    for r in [_rec(uid, "P0001", False), _rec(uid, "P0004", False),   # 物理错
              _rec(uid, "C0001", True), _rec(uid, "C0004", False),    # 化学
              _rec(uid, "B0001", True)]:                              # 生物
        STORE.add_response(r)

    phys = ENGINE.diagnose(uid, STORE.get_responses(uid), subject="physics")
    assert phys.concept_mastery and all(
        KG.subject_of(cm.concept_id) == "physics" for cm in phys.concept_mastery)
    assert any("PHY_KINEMATICS" == cm.concept_id for cm in phys.concept_mastery)
    assert phys.n_responses == 2  # 仅物理作答

    chem = ENGINE.diagnose(uid, STORE.get_responses(uid), subject="chemistry")
    assert all(KG.subject_of(cm.concept_id) == "chemistry" for cm in chem.concept_mastery)
    assert chem.n_responses == 2

    comp = ENGINE.diagnose(uid, STORE.get_responses(uid))  # 综合
    subs = {KG.subject_of(cm.concept_id) for cm in comp.concept_mastery}
    assert {"physics", "chemistry", "biology"} <= subs


def test_recommend_is_subject_scoped():
    STORE.reset()
    uid = "ms2"
    for r in [_rec(uid, "B0001", False), _rec(uid, "B0003", False)]:
        STORE.add_response(r)
    report = ENGINE.diagnose(uid, STORE.get_responses(uid), subject="biology")
    rec = RECOMMENDER.recommend(uid, report, STORE.get_responses(uid), n=8, subject="biology")
    assert rec.items
    assert all(BANK.get(it.problem_id).subject.value == "biology" for it in rec.items)


def test_cold_start_per_subject():
    ids = ENGINE.build_cold_start_test(30, subject="chemistry")
    assert ids and all(BANK.get(i).subject.value == "chemistry" for i in ids)


# ── 科学变式题数学正确性（独立重算）────────────────────────────
def test_kinematics_variant_correct():
    rng = random.Random(0)
    t = TEMPLATES["T_PHY_KINEMATICS"]
    for _ in range(15):
        p = t.sample_params(rng)
        v0, a, tt = p["v0"], p["a"], p["t"]
        v = v0 + a * tt
        s = v0 * tt + 0.5 * a * tt * tt
        f = t.build(p, None, rng)
        assert f"v={v} m/s" in f["answer"]
        assert (str(int(s)) if s == int(s) else str(s)) in f["answer"]


def test_ohm_variant_correct():
    rng = random.Random(1)
    t = TEMPLATES["T_PHY_OHM"]
    for _ in range(15):
        p = t.sample_params(rng)
        I = Fraction(p["E"], p["R"] + p["r"])
        U = I * p["R"]
        f = t.build(p, None, rng)
        assert f"I={frac_str(I)} A" in f["answer"] and f"U={frac_str(U)} V" in f["answer"]


def test_mole_variant_correct():
    rng = random.Random(2)
    t = TEMPLATES["T_CHEM_MOLE"]
    for _ in range(15):
        p = t.sample_params(rng)
        f = t.build(p, None, rng)
        assert f["answer"] == f"{p['k']} mol。"
        assert f"{p['k'] * p['M']} g" in f["stem"]  # 质量=k×M


def test_genetics_variant_correct():
    rng = random.Random(3)
    t = TEMPLATES["T_BIO_GENETICS"]
    table = {"Aa×Aa": {"显性性状（A_）": Fraction(3, 4), "隐性性状（aa）": Fraction(1, 4),
                       "纯合子（AA或aa）": Fraction(1, 2), "杂合子（Aa）": Fraction(1, 2)},
             "Aa×aa": {"显性性状（A_）": Fraction(1, 2), "隐性性状（aa）": Fraction(1, 2),
                       "纯合子（AA或aa）": Fraction(1, 2), "杂合子（Aa）": Fraction(1, 2)},
             "AA×Aa": {"显性性状（A_）": Fraction(1, 1), "隐性性状（aa）": Fraction(0, 1),
                       "纯合子（AA或aa）": Fraction(1, 2), "杂合子（Aa）": Fraction(1, 2)}}
    for _ in range(20):
        p = t.sample_params(rng)
        f = t.build(p, None, rng)
        assert f["answer"] == f"{frac_str(table[p['cross']][p['q']])}。"


# ── 跨科解题（苏格拉底门控对任意学科生效）────────────────────────
def test_physics_problem_socratic_solve():
    STORE.reset()
    uid = "msolve"
    r0 = SOLVER.solve(SolveRequest(user_id=uid, problem_id="P0001", reveal_level=RevealLevel.FULL))
    assert r0.reveal_level == RevealLevel.HINT and r0.final_answer is None
    SOLVER.solve(SolveRequest(user_id=uid, problem_id="P0001", reveal_level=RevealLevel.FULL))
    r2 = SOLVER.solve(SolveRequest(user_id=uid, problem_id="P0001", reveal_level=RevealLevel.FULL))
    assert r2.reveal_level == RevealLevel.FULL and "v=14 m/s" in r2.final_answer
    assert r2.fact_check.passed
