"""智考通 · 模考估分 + 真实模考反馈闭环演示。

诊断估分 → 录入真实模考 → 校准预测 + 识别"会做却失分" → 回灌规划重排优先级。
运行：cd backend && python scripts/demo_mock_feedback.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.data.problem_bank import BANK  # noqa: E402
from app.modules.diagnosis.engine import ENGINE  # noqa: E402
from app.modules.exam import feedback  # noqa: E402
from app.modules.exam.mock_store import MockExamBook  # noqa: E402
from app.modules.exam.predictor import PREDICTOR  # noqa: E402
from app.modules.planner.planner import PLANNER  # noqa: E402
from app.schemas import ResponseRecord  # noqa: E402
from app.services.store import STORE  # noqa: E402

SUB_CN = {"math": "数学", "physics": "物理", "chemistry": "化学", "biology": "生物"}
SAMPLE = [("M0001", True), ("M0002", False), ("M0003", False), ("M0006", True),
          ("P0001", False), ("P0002", True), ("P0004", False), ("C0001", True),
          ("C0004", False), ("B0001", False), ("B0003", True)]


def h(t):
    print("\n" + "═" * 74 + f"\n  {t}\n" + "═" * 74)


def show_pred(pred):
    print(f"  预计总分 {pred.total_predicted}/{pred.total_full}（±{pred.band}）— {pred.note}")
    print(f"  {'科目':<6}{'预测':<8}{'真实模考':<10}{'应试缺口':<10}{'规划加权'}")
    for s in pred.subjects:
        a = f"{s.actual}" if s.actual is not None else "—"
        gap = f"+{s.execution_gap}" if s.execution_gap > 0 else f"{s.execution_gap}"
        print(f"  {SUB_CN[s.subject]:<6}{s.predicted:<8}{a:<10}{gap:<10}×{s.priority_multiplier}")


def plan_mix(plan):
    mix = {}
    for it in plan.priorities:
        mix[SUB_CN[it.subject.value]] = mix.get(SUB_CN[it.subject.value], 0) + it.allocated_minutes
    return mix


def main():
    STORE.reset()
    book = MockExamBook(STORE)
    uid = "mock_demo"
    for pid, ok in SAMPLE:
        p = BANK.get(pid)
        STORE.add_response(ResponseRecord(user_id=uid, problem_id=pid, correct=ok, time_spent_s=60,
                                          concept_ids=list(p.concept_ids), difficulty=p.difficulty))
    report = ENGINE.diagnose(uid, STORE.get_responses(uid))
    now = datetime(2026, 5, 20, 19, tzinfo=settings.tz)

    print("智考通 · 模考估分 + 真实模考反馈闭环")
    h("① 仅凭认知诊断的估分（尚无真实模考）")
    pred0 = PREDICTOR.predict(report)
    show_pred(pred0)

    h("② 学生录入真实模考成绩（数学/物理明显低于预测 → 会做却失分）")
    raw_math = PREDICTOR.predict_subject_raw(report, "math")[0]
    raw_phys = PREDICTOR.predict_subject_raw(report, "physics")[0]
    real = {"math": round(raw_math - 28), "physics": round(raw_phys - 22),
            "chemistry": round(PREDICTOR.predict_subject_raw(report, "chemistry")[0] - 4),
            "biology": round(PREDICTOR.predict_subject_raw(report, "biology")[0] - 3)}
    print(f"  一模成绩：{ {SUB_CN[k]: v for k, v in real.items()} }")
    book.submit(uid, "一模", real, PREDICTOR, report)

    h("③ 校准后的估分 + 应试缺口分析")
    an = feedback.analyze(book, report, PREDICTOR, uid)
    pred1 = PREDICTOR.predict(report, book.calibration(uid), book.latest_actuals(uid),
                              {s: a["multiplier"] for s, a in an.items()},
                              {s: a["execution_gap"] for s, a in an.items()})
    show_pred(pred1)
    print("\n  各科诊断：")
    for s, a in an.items():
        if a["actual"] is not None:
            print(f"    {SUB_CN[s]}：{a['note']}")

    h("④ 规划重排：模考反馈把时间更多投向'真实考场最该补'的科目")
    sw = feedback.subject_weights(book, report, PREDICTOR, uid)
    p_before = PLANNER.plan(report, daily_minutes=150, days_left=18, now=now)
    p_after = PLANNER.plan(report, daily_minutes=150, days_left=18, now=now,
                           subject_weights=sw, projection=pred1)
    print(f"  反馈前各科投入(分钟)：{plan_mix(p_before)}")
    print(f"  反馈后各科投入(分钟)：{plan_mix(p_after)}")
    print(f"\n  规划提示：{p_after.feedback_note}")
    print(f"  {p_after.projected_note}")

    print("\n" + "═" * 74)
    print("  演示结束。API：POST /api/v1/mock（录入模考）· GET /score/{uid} · POST /plan（自动含反馈）")
    print("═" * 74)


if __name__ == "__main__":
    main()
