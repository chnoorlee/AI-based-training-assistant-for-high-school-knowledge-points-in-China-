"""智考通 · AI 提分规划师演示（考生最需要的功能）。

回答考生的命门：距高考只剩 N 天，每天就这点时间，先补哪科哪个点最提分？
运行：cd backend && python scripts/demo_planner.py
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
from app.data.knowledge_graph import KG  # noqa: E402
from app.data.problem_bank import BANK  # noqa: E402
from app.modules.diagnosis.engine import ENGINE  # noqa: E402
from app.modules.planner.planner import PLANNER  # noqa: E402
from app.modules.review.book import ReviewBook  # noqa: E402
from app.schemas import ResponseRecord  # noqa: E402
from app.services.store import STORE  # noqa: E402

SUB_CN = {"math": "数学", "physics": "物理", "chemistry": "化学", "biology": "生物"}
SAMPLE = [("M0001", True), ("M0002", False), ("M0003", False), ("M0006", True),
          ("P0001", False), ("P0002", True), ("P0004", False), ("C0001", True),
          ("C0004", False), ("B0001", False), ("B0003", True)]


def h(t):
    print("\n" + "═" * 74 + f"\n  {t}\n" + "═" * 74)


def rec(uid, pid, ok):
    p = BANK.get(pid)
    return ResponseRecord(user_id=uid, problem_id=pid, correct=ok, time_spent_s=60,
                          concept_ids=list(p.concept_ids), difficulty=p.difficulty)


def show_plan(plan):
    print(f"距高考 {plan.days_left} 天 · 每日 {plan.daily_minutes} 分钟 · "
          f"总投入 {plan.total_study_minutes // 60} 小时")
    print(f"📈 {plan.projected_note}")

    h("① 提分性价比排序（先补这些，分/小时最高）")
    print(f"  {'考点':<18}{'科':<5}{'掌握':<6}{'高考分':<7}{'难易':<5}{'性价比':<9}{'投入':<7}{'预计提分'}")
    for it in plan.priorities[:8]:
        print(f"  {it.concept_name[:16]:<18}{SUB_CN[it.subject.value]:<5}{it.mastery:<6.0%}"
              f"{it.exam_weight:<7}{it.learnability:<5}{it.roi:<9.1f}{str(it.allocated_minutes)+'min':<7}"
              f"+{it.expected_gain:.1f}分")

    h(f"② 每日计划（前 {len(plan.days)} 天，跨学科交替 + 错题复习；熔断日仅复习）")
    for d in plan.days:
        tag = " 🔒熔断" if d.is_blackout else ""
        print(f"\n  📅 第{d.day_index + 1}天 {d.date}（{d.total_minutes}分钟）{tag}")
        for t in d.tasks:
            if t.kind == "learn":
                print(f"     · 攻坚 {SUB_CN.get(t.subject, t.subject)}「{t.concept_name}」 "
                      f"{t.minutes}min（{t.n_problems}题）")
            else:
                print(f"     · 复习 {t.detail}（{t.minutes}min，{t.n_problems}题）")


def main():
    STORE.reset()
    uid = "planner_demo"
    for pid, ok in SAMPLE:
        STORE.add_response(rec(uid, pid, ok))
    report = ENGINE.diagnose(uid, STORE.get_responses(uid))
    review_due = ReviewBook().due_queue(uid).due_count

    print("智考通 · AI 提分规划师 —— “距高考还剩这么点时间，我到底先学什么最提分？”")
    print(f"学生：跨四科作答 {report.n_responses} 条，整体掌握度 {report.overall_mastery:.0%}，"
          f"当前到期错题 {review_due} 道")

    h("【场景一】距高考较远（5/20），每日 150 分钟 → 全科攻坚计划")
    show_plan(PLANNER.plan(report, daily_minutes=150, review_due=review_due,
                           now=datetime(2026, 5, 20, 19, tzinfo=settings.tz)))

    h("【场景二】临近高考（6/5）→ 计划自动卡倒计时，熔断日只留复习")
    p2 = PLANNER.plan(report, daily_minutes=120, review_due=review_due,
                      now=datetime(2026, 6, 5, 19, tzinfo=settings.tz))
    print(f"距高考仅 {p2.days_left} 天。每日计划：")
    for d in p2.days:
        tag = " 🔒高考熔断日（仅错题/复习）" if d.is_blackout else ""
        kinds = "、".join(sorted({t.kind for t in d.tasks}))
        print(f"  {d.date}：{d.total_minutes}min（{kinds}）{tag}")

    print("\n" + "═" * 74)
    print("  演示结束。API：POST /api/v1/plan {user_id, daily_minutes, subject?, days_left?}")
    print("═" * 74)


if __name__ == "__main__":
    main()
