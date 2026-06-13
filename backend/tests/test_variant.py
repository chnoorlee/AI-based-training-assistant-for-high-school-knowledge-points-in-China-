"""变式题生成测试：数学正确性（独立重算）+ 质量门 + 审核流 + 苏格拉底回流。"""
import math
import random
from fractions import Fraction

from app.modules.variant import quality
from app.modules.variant.generator import GENERATOR
from app.modules.variant.quality import run_quality
from app.modules.variant.review import VARIANT_STORE
from app.modules.variant.templates import TEMPLATES, simplify_sqrt
from app.modules.rag.solver import SOLVER
from app.schemas import RevealLevel, VariantGenerateRequest, VariantReviewStatus


def _eval_radical(s: str) -> float:
    s = s.replace("。", "").strip()
    if "/" in s:
        num, den = s.split("/")
        return _eval_radical(num) / _eval_radical(den)
    if "√" in s:
        left, right = s.split("√")
        coef = float(left) if left else 1.0
        return coef * math.sqrt(float(right))
    return float(s)


# ── 数学正确性：对每个模板独立重算验证 ─────────────────────────
def test_deriv_extremum_correct():
    rng = random.Random(0)
    t = TEMPLATES["T_DERIV_EXTREMUM"]
    for _ in range(20):
        p = t.sample_params(rng)
        k, b = p["k"], p["b"]
        assert b == 3 * k * k
        f = lambda x: x ** 3 - b * x
        fp = lambda x: 3 * x * x - b
        assert abs(fp(k)) < 1e-9 and abs(fp(-k)) < 1e-9          # ±k 是驻点
        fields = t.build(p, None, rng)
        assert str(f(-k)) in fields["answer"]                    # 极大值 2k³
        assert str(f(k)) in fields["answer"]                     # 极小值 -2k³


def test_arith_sum_correct():
    rng = random.Random(1)
    t = TEMPLATES["T_ARITH_SUM"]
    for _ in range(20):
        p = t.sample_params(rng)
        a1, d = p["a1"], p["d"]
        for n in range(1, 7):  # 公式 == 直接求和
            direct = sum(a1 + i * d for i in range(n))
            formula = n * (2 * a1 + (n - 1) * d) / 2
            assert direct == formula
        fields = t.build(p, None, rng)
        assert f"n(2×{a1}+(n-1)×{d})/2" in fields["answer"]


def test_cosine_law_correct():
    rng = random.Random(2)
    t = TEMPLATES["T_COSINE_LAW"]
    cosv = {60: 0.5, 90: 0.0, 120: -0.5}
    for _ in range(30):
        p = t.sample_params(rng)
        a, c, B = p["a"], p["c"], p["B"]
        b2 = a * a + c * c - 2 * a * c * cosv[B]
        assert abs(b2 - round(b2)) < 1e-9
        fields = t.build(p, None, rng)
        assert fields["answer"] == f"b={simplify_sqrt(round(b2))}。"


def test_amgm_min_correct():
    rng = random.Random(3)
    t = TEMPLATES["T_AMGM_MIN"]
    for _ in range(20):
        p = t.sample_params(rng)
        k = p["k"]
        fields = t.build(p, None, rng)
        assert fields["type"] == "choice"
        ans_val = fields["options"][fields["answer"]]
        assert abs(_eval_radical(ans_val) - 2 * math.sqrt(k)) < 1e-6   # 最小值=2√k
        assert len(set(fields["options"].values())) == len(fields["options"])  # 选项互异


def test_classic_prob_correct():
    rng = random.Random(4)
    t = TEMPLATES["T_CLASSIC_PROB"]
    for _ in range(20):
        p = t.sample_params(rng)
        g, b = p["good"], p["bad"]
        expect = Fraction(g * b, math.comb(g + b, 2))
        fields = t.build(p, None, rng)
        s = f"{expect.numerator}/{expect.denominator}" if expect.denominator != 1 else str(expect.numerator)
        assert s in fields["answer"]


def test_ellipse_ecc_correct():
    rng = random.Random(5)
    t = TEMPLATES["T_ELLIPSE_ECC"]
    for _ in range(20):
        p = t.sample_params(rng)
        A, B = p["A"], p["B"]
        e_true = math.sqrt(A - B) / math.sqrt(A)
        fields = t.build(p, None, rng)
        e_str = fields["answer"].replace("e=", "").replace("。", "")
        assert abs(_eval_radical(e_str) - e_true) < 1e-6


# ── 质量控制门 ───────────────────────────────────────────────
def test_rule_check_rejects_superceiling_concept():
    ok, issues = quality.rule_check({"concept_ids": ["MATH_FAKE"], "stem": "x", "answer": "1"})
    assert not ok and any("超纲" in i for i in issues)


def test_copyright_gate_blocks_near_duplicate():
    rng = random.Random(0)
    fields = TEMPLATES["T_COSINE_LAW"].build({"a": 3, "c": 5, "B": 60}, None, rng)
    # 把生成题干注入"受版权语料" → 版权相似度应触顶并拦截
    rep = run_quality(fields, 0.4, 0.5, batch_stems=[],
                      protected_corpus=[fields["stem"]])
    assert rep.copyright_similarity > 0.30 and not rep.auto_passed


def test_content_safety_flags_banned():
    safe, issues = quality.content_safety({"stem": "用洛必达法则求极限", "answer": "0"})
    assert not safe and issues


# ── 生成 + 审核流 ────────────────────────────────────────────
def test_generate_produces_valid_pending_variants():
    VARIANT_STORE.reset()
    req = VariantGenerateRequest(user_id="t", problem_id="M0002", count=3)
    out = GENERATOR.generate(req, seed=1)
    pend = [v for v in out if v.review_status == VariantReviewStatus.PENDING]
    assert len(pend) >= 1
    for v in pend:
        assert v.problem.stem and v.problem.answer
        assert len(v.problem.socratic_questions) >= 3 and v.problem.solution_steps
        assert 0.1 <= v.problem.difficulty <= 0.95
        from app.data.knowledge_graph import KG
        assert all(KG.get(c) for c in v.problem.concept_ids)  # 无超纲
    assert VARIANT_STORE.pending()  # 已入审核队列


def test_review_flow_and_socratic_resolve():
    VARIANT_STORE.reset()
    out = GENERATOR.generate(VariantGenerateRequest(user_id="t", count=4), seed=7)
    pending = VARIANT_STORE.pending()
    assert pending
    v = pending[0]
    approved = VARIANT_STORE.review(v.id, True, reviewer="师老师", note="可用")
    assert approved.review_status == VariantReviewStatus.APPROVED
    # 再次审核同一题（已非 pending）不应改变
    again = VARIANT_STORE.review(v.id, False, reviewer="x")
    assert again.review_status == VariantReviewStatus.APPROVED

    # 审核通过的变式题走苏格拉底门控：首次仅引导、无答案；逐级到完整给答案
    r0 = SOLVER.solve_problem("u", approved.problem, RevealLevel.FULL)
    assert r0.reveal_level == RevealLevel.HINT and r0.final_answer is None
    assert len(r0.socratic_questions) >= 3
    SOLVER.solve_problem("u", approved.problem, RevealLevel.FULL)  # GUIDED
    r2 = SOLVER.solve_problem("u", approved.problem, RevealLevel.FULL)
    assert r2.reveal_level == RevealLevel.FULL and r2.final_answer
    assert r2.fact_check.passed


def test_variant_blocked_during_gaokao():
    from datetime import datetime
    from app.core import compliance
    from app.core.config import settings
    s = compliance.check("variant", now=datetime(2026, 6, 8, 12, tzinfo=settings.tz))
    assert not s.allowed and s.code == "gaokao_blackout"
