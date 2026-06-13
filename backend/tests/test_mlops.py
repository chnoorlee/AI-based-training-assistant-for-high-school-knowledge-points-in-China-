"""MLOps 测试：监控告警 + A/B 灰度决策 + PSI 漂移检测（无需 torch）。"""
import random

import numpy as np

from app.data.problem_bank import BANK
from app.modules.diagnosis.dataset import InteractionRow
from app.modules.mlops.ab import ABConfig, ABExperiment
from app.modules.mlops.drift import detect_drift_from_rows, psi
from app.modules.mlops.monitoring import AlertManager, MetricsCollector
from app.schemas import utcnow


# ── 监控 / 告警 ─────────────────────────────────────────────
def test_metrics_snapshot_and_prometheus():
    mc = MetricsCollector()
    for i in range(30):
        mc.record_serving("diagnose", latency_ms=50 + i, model_version="v1",
                          ab_bucket="champion", pred=0.5)
    s = mc.snapshot()
    assert s["total"] == 30 and s["by_kind"]["diagnose"] == 30
    assert s["latency_p95"] >= s["latency_p50"]
    text = mc.prometheus_text()
    assert "zkt_requests_total 30" in text and "zkt_latency_ms" in text


def test_alert_high_latency_and_pred_shift():
    mc = MetricsCollector()
    for _ in range(30):
        mc.record_serving("diagnose", latency_ms=5000, pred=0.95)
    alerts = {a.name for a in AlertManager().evaluate(mc)}
    assert "high_latency" in alerts
    assert "pred_distribution_shift" in alerts  # pred 均值 0.95 偏离 [0.15,0.85]


def test_no_alert_when_healthy():
    mc = MetricsCollector()
    for _ in range(30):
        mc.record_serving("diagnose", latency_ms=80, pred=0.55)
    assert AlertManager().evaluate(mc) == []


# ── A/B 灰度 ────────────────────────────────────────────────
def test_ab_routing_stable_and_proportional():
    exp = ABExperiment(ABConfig(enabled=True, canary_pct=20))
    users = [f"u{i}" for i in range(2000)]
    buckets = [exp.router.assign(u) for u in users]
    # 同一用户稳定
    assert all(exp.router.assign(u) == b for u, b in zip(users[:50], buckets[:50]))
    frac = buckets.count("canary") / len(buckets)
    assert 0.15 < frac < 0.25  # ~20%


def test_ab_decides_rollback_when_canary_worse():
    exp = ABExperiment(ABConfig(enabled=True, canary_pct=50))
    rng = random.Random(0)
    for i in range(300):
        u = f"user{i}"
        b = exp.router.assign(u)
        if b == "champion":
            actual = rng.randint(0, 1)
            pred = 0.9 if actual else 0.1  # 冠军预测准
        else:
            actual = rng.randint(0, 1)
            pred = 0.5  # 挑战者无信息
        exp.record_outcome(u, pred, actual)
    d = exp.decide(min_samples=30)
    assert d["decision"] == "rollback"


def test_ab_holds_when_insufficient_samples():
    exp = ABExperiment(ABConfig(enabled=True, canary_pct=50))
    exp.record_outcome("a", 0.8, 1)
    assert exp.decide(min_samples=100)["decision"] == "hold"


# ── 漂移检测 ────────────────────────────────────────────────
def test_psi_zero_when_identical_and_high_when_shifted():
    ref = np.array([0.25, 0.25, 0.25, 0.25])
    assert psi(ref, ref) < 1e-6
    shifted = np.array([0.85, 0.05, 0.05, 0.05])
    assert psi(ref, shifted) > 0.25


def _rows(pids, corrects, t=60):
    return [InteractionRow(user_id="u", problem_id=p, correct=bool(c), ts=utcnow(),
                           time_spent_s=t) for p, c in zip(pids, corrects)]


def test_detect_drift_flags_concept_and_label_shift():
    # 参考窗口：多考点、正确率约 50%
    ref_pids = ["M0001", "M0002", "M0005", "M0008", "M0011"] * 10
    ref = _rows(ref_pids, [i % 2 for i in range(len(ref_pids))])
    # 当前窗口：全是同一考点且全对 → 考点分布 + 标签都漂移
    cur = _rows(["M0001"] * 50, [1] * 50)
    rep = detect_drift_from_rows(ref, cur)
    assert rep.overall_severity in ("minor", "major")
    assert "label(correctness)" in rep.drifted or "concept_dist" in rep.drifted


def test_no_drift_when_same_distribution():
    pids = ["M0001", "M0002", "M0005", "M0008"] * 12
    corr = [i % 2 for i in range(len(pids))]
    rep = detect_drift_from_rows(_rows(pids, corr), _rows(pids, corr))
    assert rep.overall_severity == "none"
