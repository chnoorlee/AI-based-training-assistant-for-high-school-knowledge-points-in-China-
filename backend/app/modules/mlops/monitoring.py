"""模型服务监控 + 告警。

采集服务事件（诊断/解题/批改的调用量、时延、模型版本、预测分布），
计算指标快照并导出 Prometheus 文本；按规则评估触发告警（时延、预测异常、漂移、训练陈旧、AUC 下跌）。
生产：指标上报 Prometheus + Grafana 看板，告警走 Alertmanager/PagerDuty。
"""
from __future__ import annotations

import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ServingEvent:
    kind: str  # diagnose / solve / grade / recommend
    latency_ms: float
    model_version: str = "—"
    ab_bucket: str = "champion"
    pred: Optional[float] = None  # 预测概率（如有）
    ok: bool = True
    ts: float = field(default_factory=time.time)


class MetricsCollector:
    def __init__(self, maxlen: int = 5000) -> None:
        self.events: deque[ServingEvent] = deque(maxlen=maxlen)

    def record(self, ev: ServingEvent) -> None:
        self.events.append(ev)

    def record_serving(self, kind: str, latency_ms: float, **kw) -> None:
        self.record(ServingEvent(kind=kind, latency_ms=latency_ms, **kw))

    # ── 快照 ───────────────────────────────────────────────
    def snapshot(self) -> dict:
        evs = list(self.events)
        n = len(evs)
        lat = np.array([e.latency_ms for e in evs]) if evs else np.array([0.0])
        preds = [e.pred for e in evs if e.pred is not None]
        errs = sum(1 for e in evs if not e.ok)
        return {
            "total": n,
            "by_kind": dict(Counter(e.kind for e in evs)),
            "by_bucket": dict(Counter(e.ab_bucket for e in evs)),
            "by_version": dict(Counter(e.model_version for e in evs)),
            "latency_p50": float(np.percentile(lat, 50)),
            "latency_p95": float(np.percentile(lat, 95)),
            "latency_max": float(lat.max()),
            "error_rate": (errs / n) if n else 0.0,
            "pred_mean": float(np.mean(preds)) if preds else None,
            "pred_std": float(np.std(preds)) if preds else None,
        }

    def prometheus_text(self) -> str:
        s = self.snapshot()
        lines = [
            "# HELP zkt_requests_total 服务调用总数",
            "# TYPE zkt_requests_total counter",
            f"zkt_requests_total {s['total']}",
            "# HELP zkt_latency_ms 时延分位",
            "# TYPE zkt_latency_ms gauge",
            f'zkt_latency_ms{{q="p50"}} {s["latency_p50"]:.2f}',
            f'zkt_latency_ms{{q="p95"}} {s["latency_p95"]:.2f}',
            f"zkt_error_rate {s['error_rate']:.4f}",
        ]
        for kind, c in s["by_kind"].items():
            lines.append(f'zkt_requests_by_kind{{kind="{kind}"}} {c}')
        for bucket, c in s["by_bucket"].items():
            lines.append(f'zkt_requests_by_bucket{{bucket="{bucket}"}} {c}')
        if s["pred_mean"] is not None:
            lines.append(f"zkt_pred_mean {s['pred_mean']:.4f}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        self.events.clear()


@dataclass
class Alert:
    name: str
    severity: str  # info / warning / critical
    message: str


class AlertManager:
    def __init__(self, latency_p95_ms: float = 2000.0, error_rate: float = 0.02,
                 pred_mean_range: tuple[float, float] = (0.15, 0.85),
                 train_stale_hours: float = 48.0) -> None:
        self.latency_p95_ms = latency_p95_ms
        self.error_rate = error_rate
        self.pred_lo, self.pred_hi = pred_mean_range
        self.train_stale_hours = train_stale_hours

    def evaluate(self, collector: MetricsCollector, drift_report=None,
                 last_train_age_hours: Optional[float] = None,
                 auc_drop: Optional[float] = None) -> list[Alert]:
        s = collector.snapshot()
        alerts: list[Alert] = []
        if s["total"] >= 20:  # 样本足够才判 SLO
            if s["latency_p95"] > self.latency_p95_ms:
                alerts.append(Alert("high_latency", "warning",
                                    f"p95 时延 {s['latency_p95']:.0f}ms > {self.latency_p95_ms:.0f}ms"))
            if s["error_rate"] > self.error_rate:
                alerts.append(Alert("high_error_rate", "critical",
                                    f"错误率 {s['error_rate']:.1%} > {self.error_rate:.1%}"))
            if s["pred_mean"] is not None and not (self.pred_lo <= s["pred_mean"] <= self.pred_hi):
                alerts.append(Alert("pred_distribution_shift", "warning",
                                    f"预测均值 {s['pred_mean']:.2f} 偏离正常区间"
                                    f"[{self.pred_lo},{self.pred_hi}]，疑似分布漂移"))
        if drift_report is not None and getattr(drift_report, "overall_severity", "none") == "major":
            alerts.append(Alert("data_drift", "critical",
                                f"数据漂移严重：{drift_report.drifted}"))
        if last_train_age_hours is not None and last_train_age_hours > self.train_stale_hours:
            alerts.append(Alert("training_stale", "warning",
                                f"模型已 {last_train_age_hours:.0f}h 未更新 > {self.train_stale_hours:.0f}h"))
        if auc_drop is not None and auc_drop > 0.03:
            alerts.append(Alert("auc_regression", "critical",
                                f"在线 AUC 较上版下跌 {auc_drop:.3f}"))
        return alerts


METRICS = MetricsCollector()
ALERTS = AlertManager()
