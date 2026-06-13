"""真实日志驱动的诊断训练流水线 CLI。

用法：
    cd backend
    python scripts/train_pipeline.py --demo            # 两轮增量演示（含模拟流量、注册表、热加载）
    python scripts/train_pipeline.py --once            # 增量训练一次（从 STORE 日志接入）
    python scripts/train_pipeline.py --once --full     # 全量重训一次
    python scripts/train_pipeline.py --simulate 300    # 先灌 300 名学生模拟流量，再增量训练一次
    python scripts/train_pipeline.py --watch --interval 3600 --min-new 200   # 守护：定时按需触发

生产调度见 app/modules/diagnosis/scheduler.py 的 PRODUCTION_SCHEDULING。
"""
from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.diagnosis.dataset import InMemoryLogRepository  # noqa: E402
from app.modules.diagnosis.pipeline import TrainingPipeline  # noqa: E402
from app.modules.diagnosis.scheduler import IntervalScheduler  # noqa: E402
from app.modules.diagnosis.traffic_sim import now_utc, simulate_traffic_to_store  # noqa: E402


def _fmt_metrics(m: dict) -> str:
    keys = [("ensemble_auc", "集成AUC"), ("ncd_auc", "NCD"), ("dkt_auc", "DKT")]
    return "  ".join(f"{label}={m[k]:.3f}" for k, label in keys if k in m)


def _print_registry(pipe: TrainingPipeline) -> None:
    print("\n模型注册表（artifacts/registry.json）：")
    print(f"  {'版本':<22}{'方式':<8}{'集成AUC':<10}{'学生':<7}{'晋升':<6}原因")
    for r in pipe._load_registry():
        mode = "增量" if r.get("incremental") else "全量"
        auc = r.get("metrics", {}).get("ensemble_auc", 0.0)
        print(f"  {r['version']:<22}{mode:<8}{auc:<10.3f}{r['n_students']:<7}"
              f"{'✓' if r['promoted'] else '✗':<6}{r['reason']}")


def run_demo() -> None:
    from app.services.store import STORE
    from app.modules.diagnosis.engine import ENGINE

    print("智考通 · 真实日志训练流水线演示（数据接入 + 增量更新）")
    STORE.reset()
    pipe = TrainingPipeline(InMemoryLogRepository(STORE))
    now = now_utc()

    print("\n[第 1 天] 模拟 300 名学生作答入库 ...")
    n1 = simulate_traffic_to_store(300, now - timedelta(days=2), now - timedelta(days=1),
                                   seed=1, user_prefix="d1")
    print(f"  写入作答 {n1} 条 | 仓库累计 {InMemoryLogRepository(STORE).count_since()} 条")
    print("  → 全量训练 v1 ...")
    r1 = pipe.run(incremental=False)
    print(f"  v1 {r1.version} | {_fmt_metrics(r1.metrics)} | 晋升={r1.promoted}（{r1.reason}）")

    print("\n[第 2 天] 新增 200 名学生作答入库（时间戳在 v1 训练之后）...")
    t2 = now_utc()  # v1 训练已完成；新流量必然晚于上次训练时刻
    n2 = simulate_traffic_to_store(200, t2, t2 + timedelta(minutes=10), seed=2, user_prefix="d2")
    ok, why = pipe.should_run(min_new=100, min_interval_hours=12)
    print(f"  新写入 {n2} 条 | should_run={ok}（{why}）")
    print("  → 增量热启动训练 v2 ...")
    r2 = pipe.run(incremental=True)
    print(f"  v2 {r2.version} | {_fmt_metrics(r2.metrics)} | 晋升={r2.promoted}"
          f" | 热启动自 {r2.base_version}（{r2.reason}）")

    _print_registry(pipe)

    print("\n[服务侧] 引擎热加载新晋升的 checkpoint（无需重启）：")
    before = ENGINE.backend_name
    changed = ENGINE.reload_if_updated()
    print(f"  reload_if_updated={changed} | 后端：{ENGINE.backend_name}")
    # 抽样诊断验证可用
    from app.schemas import ResponseRecord
    from app.data.problem_bank import BANK
    recs = [ResponseRecord(user_id="probe", problem_id=p, correct=(p in ("M0001", "M0004")),
                           concept_ids=list(BANK.get(p).concept_ids), difficulty=BANK.get(p).difficulty)
            for p in ("M0001", "M0004", "M0002", "M0003")]
    rep = ENGINE.diagnose("probe", recs)
    print(f"  抽样诊断：整体掌握度 {rep.overall_mastery:.0%}，"
          f"薄弱 TOP={[c for c in rep.weak_concepts[:3]]}")
    print("\n演示结束。生产用 cron/K8s 调度 `python scripts/train_pipeline.py --once --incremental`。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="两轮增量演示")
    ap.add_argument("--once", action="store_true", help="运行一次")
    ap.add_argument("--full", action="store_true", help="全量重训（默认增量）")
    ap.add_argument("--simulate", type=int, default=0, help="先灌 N 名学生模拟流量")
    ap.add_argument("--watch", action="store_true", help="守护：定时按需触发")
    ap.add_argument("--interval", type=float, default=3600, help="守护检查间隔(秒)")
    ap.add_argument("--min-new", type=int, default=200, help="触发所需最少新增作答")
    ap.add_argument("--min-interval-hours", type=float, default=12.0)
    args = ap.parse_args()

    if args.demo:
        run_demo()
        return

    from app.services.store import STORE
    pipe = TrainingPipeline(InMemoryLogRepository(STORE))

    if args.simulate > 0:
        now = now_utc()
        n = simulate_traffic_to_store(args.simulate, now - timedelta(days=1), now, seed=0)
        print(f"已模拟写入 {n} 条作答。")

    if args.watch:
        sched = IntervalScheduler(pipe, interval_seconds=args.interval, min_new=args.min_new,
                                  min_interval_hours=args.min_interval_hours,
                                  incremental=not args.full,
                                  on_result=lambda r: print(
                                      f"[run] {r.version} 晋升={r.promoted} {_fmt_metrics(r.metrics)}"))
        print(f"守护启动：每 {args.interval:.0f}s 检查一次（Ctrl+C 退出）...")
        sched.start()
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sched.stop()
            print("已停止。")
        return

    # 默认：运行一次
    ok, why = pipe.should_run(args.min_new, args.min_interval_hours)
    print(f"should_run={ok}（{why}）")
    if args.once or ok:
        r = pipe.run(incremental=not args.full)
        print(f"完成：{r.version} 晋升={r.promoted} {_fmt_metrics(r.metrics)}（{r.reason}）")
        _print_registry(pipe)


if __name__ == "__main__":
    main()
