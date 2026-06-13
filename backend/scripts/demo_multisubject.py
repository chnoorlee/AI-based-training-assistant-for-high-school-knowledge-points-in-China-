"""智考通 · 多学科扩展演示（物理 / 化学 / 生物 + 跨学科关联）。

运行：cd backend && python scripts/demo_multisubject.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import random  # noqa: E402

from app.data.knowledge_graph import KG  # noqa: E402
from app.data.problem_bank import BANK  # noqa: E402
from app.modules.diagnosis.engine import ENGINE  # noqa: E402
from app.modules.recommend import RECOMMENDER  # noqa: E402
from app.modules.variant.templates import TEMPLATES  # noqa: E402
from app.modules.rag.solver import SOLVER  # noqa: E402
from app.schemas import RevealLevel, ResponseRecord, SolveRequest  # noqa: E402
from app.services.store import STORE  # noqa: E402

SUB_CN = {"math": "数学", "physics": "物理", "chemistry": "化学", "biology": "生物"}


def h(t):
    print("\n" + "═" * 70 + f"\n  {t}\n" + "═" * 70)


def rec(uid, pid, ok, t=60):
    p = BANK.get(pid)
    return ResponseRecord(user_id=uid, problem_id=pid, correct=ok, time_spent_s=t,
                          concept_ids=list(p.concept_ids), difficulty=p.difficulty)


def main():
    print("智考通 · 多学科扩展（数学 + 物理 + 化学 + 生物，统一图谱 + 跨学科关联）")

    h("① 学科概览（统一知识图谱 + 题库）")
    for s in KG.subjects():
        print(f"  {SUB_CN[s]:<4}：知识点 {len(KG.concepts_for_subject(s)):>2} | "
              f"题目 {len(BANK.by_subject(s)):>2} | 模块 {KG.modules_for_subject(s)}")

    h("② 跨学科知识关联（规格书示例）")
    for a in ["BIO_PHOTOSYNTHESIS", "PHY_SHM", "BIO_GENETICS", "PHY_CIRCUIT"]:
        for b in KG.cross_subject_of(a):
            print(f"  {KG.name_of(a)}（{SUB_CN[KG.subject_of(a)]}） ⇄ "
                  f"{KG.name_of(b)}（{SUB_CN[KG.subject_of(b)]}）")

    h("③ 一名学生跨学科作答 → 按学科分别诊断（互不串味）")
    uid = "ms_stu"
    STORE.reset()
    answers = [("P0001", False), ("P0004", False), ("P0002", True),     # 物理：运动学弱
               ("C0001", True), ("C0002", True), ("C0004", False),      # 化学：平衡弱
               ("B0001", False), ("B0003", True)]                       # 生物：遗传弱
    for pid, ok in answers:
        STORE.add_response(rec(uid, pid, ok))
    for s in ["physics", "chemistry", "biology"]:
        r = ENGINE.diagnose(uid, STORE.get_responses(uid), subject=s)
        print(f"\n  【{SUB_CN[s]}】整体掌握度 {r.overall_mastery:.0%}（{r.n_responses} 条作答）")
        for ax in r.radar:
            bar = "█" * int(ax.score * 16)
            print(f"    {ax.module:<8} {ax.score:>4.0%} {bar}")
        if r.weak_concepts:
            print(f"    薄弱：{[KG.name_of(c) for c in r.weak_concepts[:3]]}")

    h("④ 按学科自适应推荐（物理）")
    report = ENGINE.diagnose(uid, STORE.get_responses(uid), subject="physics")
    plist = RECOMMENDER.recommend(uid, report, STORE.get_responses(uid), n=5, subject="physics")
    for it in plist.items:
        print(f"  [{it.reason.value}] {it.problem_id}（{KG.name_of(it.concept_ids[0])}）"
              f"预计答对率 {it.predicted_correct_prob:.0%}")

    h("⑤ 三科变式题生成（符号求解保证正确）")
    rng = random.Random(7)
    for tid in ["T_PHY_KINEMATICS", "T_PHY_OHM", "T_CHEM_MOLE", "T_BIO_GENETICS"]:
        t = TEMPLATES[tid]
        f = t.build(t.sample_params(rng), None, rng)
        print(f"  [{SUB_CN[KG.subject_of(f['concept_ids'][0])]}] {f['stem']}")
        print(f"        答案：{f['answer']}")

    h("⑥ 跨学科解题：物理题同样走苏格拉底门控（绝不直接给答案）")
    STORE.reset()
    for label in ["第1次", "第2次", "第3次"]:
        r = SOLVER.solve(SolveRequest(user_id="ps", problem_id="P0003",
                                      reveal_level=RevealLevel.FULL))
        tag = r.reveal_level.name
        if r.reveal_level == RevealLevel.FULL:
            print(f"  {label}({tag})：✅ {r.final_answer}  幻觉校验={r.fact_check.passed}")
        else:
            print(f"  {label}({tag})：{'引导问题×'+str(len(r.socratic_questions)) if tag=='HINT' else '分步(无答案)'}，答案={r.final_answer}")

    print("\n" + "═" * 70)
    print("  演示结束。API：GET /subjects · /diagnosis/{uid}?subject=physics · "
          "/recommend/{uid}?subject=chemistry · /diagnosis/cold-start?subject=biology")
    print("═" * 70)


if __name__ == "__main__":
    main()
