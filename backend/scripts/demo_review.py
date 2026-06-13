"""智考通 · 错题本智能复习排程演示（间隔重复 + 遗忘曲线）。

运行：cd backend && python scripts/demo_review.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data.knowledge_graph import KG  # noqa: E402
from app.data.problem_bank import BANK  # noqa: E402
from app.modules.review.book import ReviewBook  # noqa: E402
from app.services.store import Store  # noqa: E402


def h(t):
    print("\n" + "═" * 70 + f"\n  {t}\n" + "═" * 70)


def show_queue(book, uid, now):
    q = book.due_queue(uid, limit=10, now=now)
    print(f"  到期 {q.due_count} 题（展示前 {len(q.items)}），按复习紧迫度排序：")
    print(f"    {'题号':<7}{'考点':<14}{'状态':<10}{'间隔(天)':<9}{'保持率':<8}{'紧迫度':<7}")
    for it in q.items:
        cname = KG.name_of(it.concept_ids[0]) if it.concept_ids else "-"
        print(f"    {it.problem_id:<7}{cname[:12]:<14}{it.status.value:<10}"
              f"{it.interval_days:<9}{it.retention:<8.0%}{it.priority:<7.2f}")


def main():
    book = ReviewBook(store=Store())
    uid = "stu"
    day0 = datetime(2026, 5, 1, 20, tzinfo=timezone.utc)
    print("智考通 · 错题本智能复习排程（SM-2 间隔重复 + 艾宾浩斯遗忘曲线 + 掌握度调制）")

    h("① Day 0：做错 4 道题 → 自动入错题本，当日到期")
    for pid in ["M0002", "M0003", "M0007", "M0012"]:
        st = book.record_attempt(uid, pid, correct=False, now=day0)
        print(f"  ✗ {pid}（{KG.name_of(BANK.get(pid).concept_ids[0])}）→ 入册，到期 "
              f"{st.due.date()}，状态 {st.status}")
    show_queue(book, uid, day0)

    h("② Day 0：复习这 4 题（答对推后、答错重学）")
    session = {"M0002": (True, 30), "M0003": (True, 70), "M0007": (False, 120), "M0012": (True, 45)}
    for pid, (ok, t) in session.items():
        it = book.grade(uid, pid, correct=ok, time_spent_s=t, now=day0)
        print(f"  {'✓' if ok else '✗'} {pid} 用时{t}s → 下次到期 {it.due.date()}"
              f"（间隔 {it.interval_days} 天，状态 {it.status.value}，ease {it.ease}）")

    h("③ 未来 7 天复习预测")
    f = book.forecast(uid, days=7, now=day0)
    print(f"  逾期 {f.overdue} 题")
    for d in f.days:
        bar = "█" * d.count
        print(f"    {d.date}  {d.count} 题 {bar}")

    h("④ 多轮跨天复习：把 M0002 练到「毕业」（移出活跃队列）")
    now = day0
    pid = "M0002"
    for rnd in range(1, 7):
        st = book._states(uid)[pid]
        now = st.due + timedelta(hours=2)  # 到期后来复习
        it = book.grade(uid, pid, correct=True, time_spent_s=35, now=now)
        print(f"  第{rnd}次复习@{now.date()} → 间隔 {it.interval_days} 天，"
              f"复习 {it.repetitions} 次，状态 {it.status.value}")
        if it.status == "graduated":
            print(f"  🎓 {pid} 已掌握，移出每日复习队列（再做错会自动复活）")
            break

    h("⑤ 统计概览")
    s = book.stats(uid, now=now)
    print(f"  错题总数 {s.total} | 待复习 {s.due_now} | 学习中 {s.learning} | "
          f"复习中 {s.review} | 已掌握 {s.graduated} | 累计失误 {s.lapses_total} | "
          f"平均保持率 {s.avg_retention:.0%}")

    print("\n" + "═" * 70)
    print("  演示结束。API：GET /review/queue/{uid} · POST /review/grade · "
          "/review/stats · /review/forecast（熔断期仍开放）")
    print("═" * 70)


if __name__ == "__main__":
    main()
