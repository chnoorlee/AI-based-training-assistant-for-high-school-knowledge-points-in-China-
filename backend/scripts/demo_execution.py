"""智考通 · 题型级应试丢分 + 限时训练演示。

录入分题型得分 → 定位"丢在哪类题、什么原因" → 开出限时训练 → 织入每日计划。
运行：cd backend && python scripts/demo_execution.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.data.problem_bank import BANK  # noqa: E402
from app.modules.diagnosis.engine import ENGINE  # noqa: E402
from app.modules.exam import feedback  # noqa: E402
from app.modules.exam.mock_store import MockExamBook  # noqa: E402
from app.modules.exam.predictor import PREDICTOR  # noqa: E402
from app.modules.exam.sections import execution_report  # noqa: E402
from app.modules.planner.planner import PLANNER  # noqa: E402
from app.schemas import ResponseRecord  # noqa: E402
from app.services.store import STORE  # noqa: E402

SAMPLE = [("M0001", True), ("M0002", False), ("M0003", False), ("M0006", True),
          ("P0001", False), ("P0002", True), ("C0001", True), ("B0001", False), ("B0003", True)]


def h(t):
    print("\n" + "═" * 76 + f"\n  {t}\n" + "═" * 76)


def main():
    STORE.reset()
    book = MockExamBook(STORE)
    uid = "exec_demo"
    for pid, ok in SAMPLE:
        p = BANK.get(pid)
        STORE.add_response(ResponseRecord(user_id=uid, problem_id=pid, correct=ok, time_spent_s=60,
                                          concept_ids=list(p.concept_ids), difficulty=p.difficulty))
    report = ENGINE.diagnose(uid, STORE.get_responses(uid))

    print("智考通 · 题型级应试丢分 → 限时训练")
    h("① 学生录入一模'分题型得分'（数学：选择压轴/压轴大题失分明显）")
    sections = {"math": {"m_ch_easy": 14, "m_ch_hard": 2, "m_blank": 8,
                         "m_solve_mid": 28, "m_solve_hard": 6},
                "physics": {"p_choice": 18, "p_exp": 8, "p_calc_mid": 14, "p_calc_hard": 4}}
    total = {"math": sum(sections["math"].values()), "physics": sum(sections["physics"].values())}
    print(f"  数学各题型：{sections['math']}（总 {total['math']}/150）")
    print(f"  物理各题型：{sections['physics']}（总 {total['physics']}/110）")
    book.submit(uid, "一模", total, PREDICTOR, report, section_scores=sections)

    h("② 题型级丢分归因（按掌握度应得 vs 实得）")
    rep = execution_report(book, report, PREDICTOR)
    for se in rep.subjects:
        cn = {"math": "数学", "physics": "物理"}[se.subject]
        print(f"\n  【{cn}】总丢分 {se.total_loss} 分，其中易/中档可挽回 {se.fixable_loss} 分")
        print(f"    {'题型':<22}{'档':<5}{'应得':<7}{'实得':<7}{'丢分':<7}{'原因'}")
        for s in se.sections:
            got = s.got if s.got is not None else "—"
            print(f"    {s.name:<22}{s.tier:<5}{s.expected:<7}{str(got):<7}"
                  f"{(str(s.loss) if s.loss else '·'):<7}{s.cause if s.loss else ''}")

    h("③ 限时训练推荐（按可挽回分排序，直击应试丢分）")
    for d in rep.drills:
        print(f"  ⏱ {d.title}：{d.n_problems}题 / 限时{d.time_limit_min}min")
        print(f"      目标：{d.goal}　针对：{d.cause}　预计挽回 {d.recoverable_points} 分")
        print(f"      {d.detail}")

    h("④ 织入每日计划：每天首个任务就是针对性限时训练")
    sw = feedback.subject_weights(book, report, PREDICTOR, uid)
    proj = PREDICTOR.predict(report, book.calibration(uid), book.latest_actuals(uid), sw)
    plan = PLANNER.plan(report, daily_minutes=150, days_left=18, subject_weights=sw,
                        projection=proj, timed_drills=rep.drills,
                        now=datetime(2026, 5, 20, 19, tzinfo=settings.tz))
    for day in plan.days[:3]:
        print(f"\n  📅 第{day.day_index + 1}天 {day.date}")
        for t in day.tasks:
            if t.kind == "timed_drill":
                print(f"     ⏱ {t.concept_name}（{t.minutes}min/{t.n_problems}题）")
            elif t.kind == "learn":
                print(f"     · 攻坚 {t.concept_name}（{t.minutes}min）")
            else:
                print(f"     · 错题复习（{t.minutes}min）")

    print("\n" + "═" * 76)
    print("  演示结束。API：POST /mock（含 section_scores）· GET /execution/{uid} · /plan（自动织入限时训练）")
    print("═" * 76)


if __name__ == "__main__":
    main()
