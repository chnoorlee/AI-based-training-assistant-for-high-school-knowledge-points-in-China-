"""智考通数学 MVP · 端到端演示（进程内跑完整链路，无需起服务）。

运行：
    cd backend
    python scripts/demo.py

演示顺序：合规闸门 → 解析(含手写判错) → 冷启动 → 模拟作答 → 认知诊断 → 苏格拉底解题 → 自适应推荐
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 输出，避免中文/符号编码崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 让 `app` 包可被导入（脚本在 backend/scripts 下）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import compliance  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.data.knowledge_graph import KG  # noqa: E402
from app.data.problem_bank import BANK  # noqa: E402
from app.modules.diagnosis.engine import ENGINE  # noqa: E402
from app.modules.parsing import PARSER  # noqa: E402
from app.modules.rag.solver import SOLVER  # noqa: E402
from app.modules.recommend import RECOMMENDER  # noqa: E402
from app.schemas import RevealLevel, ResponseRecord, SolveRequest  # noqa: E402
from app.services.store import STORE  # noqa: E402


def h(title: str) -> None:
    print("\n" + "═" * 68 + f"\n  {title}\n" + "═" * 68)


def j(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def rec(uid, pid, correct, t=60):
    p = BANK.get(pid)
    return ResponseRecord(user_id=uid, problem_id=pid, correct=correct, time_spent_s=t,
                          concept_ids=list(p.concept_ids), difficulty=p.difficulty)


def main() -> None:
    STORE.reset()
    uid = "demo_student"

    print("智考通 · 基于认知诊断的高考自适应备考助手（数学学科 MVP 演示）")
    print("原则：不押题/不预测原题 · 绝不直接给答案 · 高考熔断 · 防沉迷 · 数据最小化")

    # ── ⓪ 合规闸门 ──────────────────────────────────────────
    h("⓪ 全链路合规闸门（高考熔断 / 防沉迷）")
    for label, now in [
        ("平时 15:00 解题", datetime(2026, 5, 20, 15, tzinfo=settings.tz)),
        ("高考期间 6/8 解题", datetime(2026, 6, 8, 15, tzinfo=settings.tz)),
        ("深夜 23:30 解题", datetime(2026, 5, 20, 23, 30, tzinfo=settings.tz)),
    ]:
        s = compliance.check("solve", used_minutes_today=0, now=now)
        print(f"· {label:<18} → allowed={s.allowed!s:<5} code={s.code}  {s.reason}")
    s = compliance.check("wrongbook", now=datetime(2026, 6, 8, 15, tzinfo=settings.tz))
    print(f"· 高考期间 6/8 错题本    → allowed={s.allowed}（熔断期仍开放）")

    # ── ① 多模态解析（含手写判错）──────────────────────────────
    h("① 多模态解析：上传题目 + 手写过程，结构化输出（统一 JSON）")
    uploaded = ("已知函数 f(x)=x³-3x，求 f(x) 的单调区间与极值。")
    handwriting = [
        {"text": "f'(x)=3x²-3", "region": "answer", "is_error": False},
        {"text": "令 f'(x)=0 得 x=±1", "region": "answer", "is_error": False},
        {"text": "x>1 时 f'(x)<0，单调递减", "region": "answer", "is_error": True,
         "error_type": "concept", "note": "符号判断错误：x>1 时 f'(x)>0 应为递增"},
    ]
    parsed = PARSER.parse(uploaded, handwriting=handwriting)
    j(parsed.model_dump(mode="json"))

    # ── ② 冷启动诊断蓝图 ────────────────────────────────────
    h("② 冷启动诊断测试蓝图（覆盖各模块、难度梯度、~15 分钟）")
    cold = ENGINE.build_cold_start_test(30)
    print(f"题量：{len(cold)}（MVP 种子题有限，生产取 30 题）")
    print("覆盖知识点：",
          "、".join(sorted({KG.name_of(c) for i in cold for c in BANK.get(i).concept_ids})))

    # ── ③ 模拟作答（强：基础/向量；弱：导数/数列综合）──────────────
    h("③ 模拟一名学生作答 8 题（基础扎实，导数与数列综合薄弱）")
    answers = [
        ("M0001", True, 35), ("M0004", True, 30), ("M0008", True, 25),
        ("M0006", True, 50), ("M0014", True, 40),
        ("M0002", False, 95), ("M0003", False, 140), ("M0007", False, 160),
    ]
    for pid, ok, t in answers:
        STORE.add_response(rec(uid, pid, ok, t))
        STORE.add_usage_minutes(uid, t / 60)
        print(f"· {pid} {'✓答对' if ok else '✗答错'}  用时{t}s  "
              f"考点：{'/'.join(KG.name_of(c) for c in BANK.get(pid).concept_ids)}")
    print(f"今日累计用时：{STORE.get_today_usage(uid):.1f} 分钟（防沉迷上限 "
          f"{settings.daily_usage_limit_minutes} 分钟）")

    # ── ④ 认知诊断报告 ──────────────────────────────────────
    h("④ 认知诊断 → 可解释报告")
    print(f"诊断引擎后端：{ENGINE.backend_name}"
          + ("（已加载联合训练 checkpoint）" if ENGINE.torch_backend
             else "（未发现 checkpoint，运行 scripts/train_diagnosis.py 可升级）"))
    report = ENGINE.diagnose(uid, STORE.get_responses(uid))
    print(f"整体掌握度：{report.overall_mastery:.0%}")
    print("\n模块雷达图：")
    for ax in report.radar:
        bar = "█" * int(ax.score * 20)
        print(f"  {ax.module:<10} {ax.score:>5.0%} {bar}")
    print("\n薄弱知识点（按优先级）：")
    for cid in report.weak_concepts[:5]:
        cm = next(c for c in report.concept_mastery if c.concept_id == cid)
        print(f"  · {cm.concept_name:<18} 掌握度 {cm.score:>5.0%}  "
              f"等级 {cm.level.value:<10} 预测答对率 {cm.predicted_correct_prob:.0%}")
    print(f"\n错误类型画像：{report.error_profile}")
    print(f"能力层级画像：{report.ability_profile}")
    print(f"\n解读：{report.explanation}")

    # ── ⑤ 苏格拉底式解题（先引导，后逐级揭示）────────────────────
    h("⑤ 解题：M0002（绝不上传即给答案，强制 引导→分步→完整 三级）")
    for label in ["第 1 次请求（即便请求完整解析）", "第 2 次请求", "第 3 次请求"]:
        r = SOLVER.solve(SolveRequest(user_id=uid, problem_id="M0002",
                                      reveal_level=RevealLevel.FULL))
        print(f"\n▶ {label} → 实际揭示级别：{r.reveal_level.name}")
        if r.reveal_level == RevealLevel.HINT:
            print("  苏格拉底引导问题：")
            for i, q in enumerate(r.socratic_questions, 1):
                print(f"    {i}. {q}")
            print(f"  最终答案：{r.final_answer}（如期为空——禁止直接给答案）")
        elif r.reveal_level == RevealLevel.GUIDED:
            print("  分步思路（暂扣最终答案）：")
            for st in r.guided_steps:
                print(f"    - {st}")
            print(f"  最终答案：{r.final_answer}（仍为空）")
        else:
            print("  完整思维链：")
            for st in r.chain_of_thought:
                print(f"    - {st}")
            print(f"  ✅ 最终答案：{r.final_answer}")
            print(f"  幻觉校验：通过={r.fact_check.passed} "
                  f"已核验知识点={r.fact_check.verified_concepts}")
        print(f"  提示：{r.notice}")

    # ── ⑥ 自适应推荐 ────────────────────────────────────────
    h("⑥ 自适应推荐（ZPD 0.6~0.8 + 70/20/10 + 遗忘曲线）")
    plist = RECOMMENDER.recommend(uid, report, STORE.get_responses(uid), n=10)
    print(f"配比（目标 强化70/巩固20/提高10）：{plist.mix}\n")
    label = {"weakness": "强化", "consolidate": "巩固", "stretch": "提高"}
    for it in plist.items:
        print(f"  [{label.get(it.reason.value, it.reason.value)}] {it.problem_id} "
              f"难度{it.difficulty:.2f} 预测答对率{it.predicted_correct_prob:.0%}  {it.rationale}")

    print("\n" + "═" * 68)
    print("  演示结束。启动 API：uvicorn app.main:app --reload → http://127.0.0.1:8000/docs")
    print("═" * 68)


if __name__ == "__main__":
    main()
