"""增量更新调度。

MVP：依赖最少的 IntervalScheduler（后台线程，按间隔检查 should_run 再触发 run）。
生产：用 cron / Airflow / K8s CronJob 调度，命令即 `python scripts/train_pipeline.py --once --incremental`。
本文件同时给出生产调度的推荐配置（见 PRODUCTION_SCHEDULING）。
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from app.modules.diagnosis.pipeline import RunResult, TrainingPipeline

PRODUCTION_SCHEDULING = """\
# 生产调度推荐
# 1) K8s CronJob（每日 03:00 增量；每周日全量重训）
#    schedule: "0 3 * * *"   command: python scripts/train_pipeline.py --once --incremental
#    schedule: "0 4 * * 0"   command: python scripts/train_pipeline.py --once --full
# 2) Airflow DAG：ingest >> train(incremental) >> evaluate >> gate >> promote >> notify
# 3) 触发式：作答量达阈值时由消息队列触发（should_run(min_new=...) 控制）
# 监控：把每次 RunResult.metrics 上报 Prometheus，AUC 跌破阈值或连续 N 次未晋升时告警。
"""


class IntervalScheduler:
    """每 interval_seconds 调用一次 should_run，满足则触发 pipeline.run。"""

    def __init__(self, pipeline: TrainingPipeline, interval_seconds: float = 3600,
                 min_new: int = 200, min_interval_hours: float = 12.0,
                 incremental: bool = True,
                 on_result: Callable[[RunResult], None] | None = None) -> None:
        self.pipeline = pipeline
        self.interval = interval_seconds
        self.min_new = min_new
        self.min_interval_hours = min_interval_hours
        self.incremental = incremental
        self.on_result = on_result
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> RunResult | None:
        ok, reason = self.pipeline.should_run(self.min_new, self.min_interval_hours)
        if not ok:
            return None
        result = self.pipeline.run(incremental=self.incremental)
        if self.on_result:
            self.on_result(result)
        return result

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:  # 调度不因单次失败而中断
                print(f"[scheduler] run 失败：{e!r}")
            self._stop.wait(self.interval)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
