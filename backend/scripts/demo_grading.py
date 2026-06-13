"""智考通 · 主观题批改演示（作文 + 文综/理综采分点）。

运行：cd backend && python scripts/demo_grading.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.grading.grader import ESSAY, SUBJECTIVE  # noqa: E402


def h(t):
    print("\n" + "═" * 68 + f"\n  {t}\n" + "═" * 68)


PROMPT = "阅读材料，围绕'规则与自由'写一篇不少于800字的议论文。"
ESSAY_TEXT = (
    "在我看来，规则与自由并非对立，正是规则保障了真正的自由。\n"
    "首先，规则划定边界，使个体免于彼此侵害。例如交通规则看似约束，实则保障了所有人通行的自由。\n"
    "其次，从辩证的角度看，自由的本质并非为所欲为，而是在规则之内的从容。古人云从心所欲不逾矩，正说明这一点。\n"
    "然而，规则也应随时代发展，因此我们既要敬畏规则，也要推动其完善，透过现象看本质。\n"
    "综上所述，唯有在规则与自由之间保持张力，社会才能既有秩序又有活力，这启示我们应理性看待二者关系。")


def main():
    print("智考通 · 主观题批改（评分细则透明可解释；生产替换为阅卷样本微调模型）")

    h("① 作文批改（内容/表达/发展等级 3 维 × 4 二级维度，满分 60）")
    r = ESSAY.grade(PROMPT, ESSAY_TEXT)
    print(f"总分：{r.total}/{r.full_marks}（评分核心：{r.grader_backend}，置信带 ±{r.confidence_band}）")
    for d in r.dimensions:
        print(f"  {d.name}（{d.score}/{d.max_score}）：{d.sub_scores}")
        print(f"    {d.comment}")
    print(f"亮点：{r.strengths}")
    print(f"待改进：{r.weaknesses}")
    print("修改建议：")
    for s in r.suggestions:
        print(f"  · {s}")
    print(f"范文指引：{r.exemplar_ref}")

    h("② 文综主观题批改（采分点语义匹配，按点给分 + 逻辑评价）")
    question = "简述影响气候的主要因素。"
    ref = [
        {"id": "p1", "description": "纬度位置决定太阳辐射强弱", "points": 3, "keywords": ["纬度", "太阳辐射"]},
        {"id": "p2", "description": "海陆位置形成海洋性与大陆性差异", "points": 3, "keywords": ["海陆", "海洋", "大陆"]},
        {"id": "p3", "description": "地形地势影响气温与降水", "points": 2, "keywords": ["地形", "地势"]},
        {"id": "p4", "description": "洋流影响沿岸气候", "points": 2, "keywords": ["洋流"]},
    ]
    answer = ("首先，纬度位置决定了太阳辐射的强弱；其次，海陆位置使气候有海洋性与大陆性之分；"
              "再次，地形地势会影响气温和降水。")
    g = SUBJECTIVE.grade(question, answer, ref)
    print(f"学生作答：{answer}")
    print(f"\n得分：{g.total}/{g.full_marks}    逻辑分：{g.logic_score}/5（{g.logic_comment}）")
    print("采分点命中：")
    for p in g.points:
        mark = "✓" if p.hit else "✗"
        print(f"  {mark} [{p.id}] {p.description}（{p.awarded}/{p.points}）"
              f"{'  命中：'+p.matched_text if p.hit else '  —未作答'}")
    print("改进建议：")
    for s in g.suggestions:
        print(f"  · {s}")

    print("\n" + "═" * 68)
    print("  演示结束。API：POST /api/v1/grade/essay | /grade/subjective（高考期间熔断）")
    print("═" * 68)


if __name__ == "__main__":
    main()
