"""智考通 · 变式题生成端到端演示。

运行：cd backend && python scripts/demo_variant.py
流程：合规闸门 → 生成(参数化+情境) → 质量控制 → 人工审核 → 苏格拉底解题回流 → 版权门演示
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import compliance  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.modules.rag.solver import SOLVER  # noqa: E402
from app.modules.variant.generator import GENERATOR  # noqa: E402
from app.modules.variant.quality import run_quality  # noqa: E402
from app.modules.variant.review import VARIANT_STORE  # noqa: E402
from app.modules.variant.templates import TEMPLATES  # noqa: E402
from app.schemas import RevealLevel, VariantGenerateRequest  # noqa: E402


def h(t):
    print("\n" + "═" * 68 + f"\n  {t}\n" + "═" * 68)


def show(v):
    q = v.quality
    print(f"\n[{v.id}] 模板={v.template_id} 情境={v.scenario_category or '—'} "
          f"状态={v.review_status.value}")
    print(f"  题干：{v.problem.stem}")
    if v.problem.options:
        print(f"  选项：{v.problem.options}  答案：{v.problem.answer}")
    else:
        print(f"  答案：{v.problem.answer}")
    print(f"  质量：规则{'✓' if q.rule_passed else '✗'} 安全{'✓' if q.content_safe else '✗'} "
          f"预测难度={q.predicted_difficulty} 区分度={q.predicted_discrimination} "
          f"去重={q.dedup_similarity} 版权={q.copyright_similarity} "
          f"自动门={'通过' if q.auto_passed else '拒绝'}")


def main():
    VARIANT_STORE.reset()
    print("智考通 · 变式题生成（保持考点不变，改参数/情境/设问；答案由符号求解器算出，绝不靠模型现编）")

    h("⓪ 合规闸门：变式题生成属'做新题'，高考期间熔断")
    for label, now in [("平时", datetime(2026, 5, 1, 15, tzinfo=settings.tz)),
                       ("高考期间 6/8", datetime(2026, 6, 8, 15, tzinfo=settings.tz))]:
        s = compliance.check("variant", now=now)
        print(f"· {label:<12} allowed={s.allowed} code={s.code}")

    h("① 以数列题 M0006 为种子生成 3 道变式（套用 10 大类情境库）")
    out1 = GENERATOR.generate(VariantGenerateRequest(user_id="u", problem_id="M0006", count=3),
                              seed=11)
    for v in out1:
        show(v)

    h("② 以解三角形题 M0005 为种子生成 3 道变式（抽象题型，符号求解保正确）")
    out2 = GENERATOR.generate(VariantGenerateRequest(user_id="u", problem_id="M0005", count=3),
                              seed=22)
    for v in out2:
        show(v)

    h("③ 人工审核（一线教师）：审核队列 → 通过/驳回")
    queue = VARIANT_STORE.pending()
    print(f"待审核队列共 {len(queue)} 题")
    v = queue[0]
    VARIANT_STORE.review(v.id, approve=True, reviewer="王老师", note="参数合理、情境得当，准予入库")
    print(f"已审核 {v.id} → {VARIANT_STORE.get(v.id).review_status.value}"
          f"（审核人：{VARIANT_STORE.get(v.id).reviewer}）")
    print(f"当前已通过入库：{len(VARIANT_STORE.approved())} 题")

    h("④ 审核通过的变式题回流：走同一套苏格拉底门控（绝不直接给答案）")
    approved = VARIANT_STORE.approved()[0]
    for label in ["第1次（即便请求完整）", "第2次", "第3次"]:
        r = SOLVER.solve_problem("stu", approved.problem, RevealLevel.FULL)
        print(f"\n▶ {label} → 揭示级别 {r.reveal_level.name}")
        if r.reveal_level == RevealLevel.HINT:
            for i, qq in enumerate(r.socratic_questions, 1):
                print(f"    {i}. {qq}")
            print(f"  答案：{r.final_answer}（如期为空）")
        elif r.reveal_level == RevealLevel.GUIDED:
            for st in r.guided_steps:
                print(f"    - {st}")
            print(f"  答案：{r.final_answer}（仍为空）")
        else:
            print(f"  ✅ 最终答案：{r.final_answer}  幻觉校验通过={r.fact_check.passed}")

    h("⑤ 版权门演示：若生成题与受版权语料高度相似 → 自动拦截")
    rng_fields = TEMPLATES["T_COSINE_LAW"].build({"a": 3, "c": 5, "B": 60}, None, __import__("random").Random(0))
    rep = run_quality(rng_fields, 0.4, 0.5, batch_stems=[], protected_corpus=[rng_fields["stem"]])
    print(f"  题干：{rng_fields['stem']}")
    print(f"  版权相似度={rep.copyright_similarity}（阈值 0.30）→ 自动门={'通过' if rep.auto_passed else '拒绝'}")
    print(f"  原因：{rep.notes}")

    print("\n" + "═" * 68)
    print("  演示结束。API：POST /api/v1/variant/generate | /variant/review/{id} | /variant/solve")
    print("═" * 68)


if __name__ == "__main__":
    main()
