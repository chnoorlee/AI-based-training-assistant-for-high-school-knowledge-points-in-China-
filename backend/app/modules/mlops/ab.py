"""A/B 灰度发布（金丝雀）。

把一小部分流量按 user_id 稳定分流到挑战者(canary)模型，在线对比冠军(champion)与挑战者
的预测质量（准确率/Brier/AUC），达到样本量后给出「晋升 / 保持 / 回滚」决策——
新模型先灰度、达标再全量，避免一次性全量带来的风险。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np


def _auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y_true = np.asarray(y_true, float)
    y_score = np.asarray(y_score, float)
    n_pos, n_neg = y_true.sum(), len(y_true) - y_true.sum()
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(y_score, kind="mergesort")
    ranks = np.empty(len(y_score))
    ranks[order] = np.arange(1, len(y_score) + 1)
    return float((ranks[y_true == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


@dataclass
class ABConfig:
    enabled: bool = False
    canary_pct: int = 0  # 0~100
    champion_version: str = "—"
    canary_version: str = "—"


class ABRouter:
    def __init__(self, config: ABConfig) -> None:
        self.config = config

    def assign(self, user_id: str) -> str:
        c = self.config
        if not c.enabled or c.canary_pct <= 0:
            return "champion"
        h = int.from_bytes(hashlib.md5(user_id.encode()).digest()[:4], "big")
        return "canary" if (h % 100) < c.canary_pct else "champion"


@dataclass
class _Bucket:
    preds: list[float] = field(default_factory=list)
    actuals: list[int] = field(default_factory=list)

    def add(self, pred: float, actual: int) -> None:
        self.preds.append(float(pred))
        self.actuals.append(int(actual))

    def stats(self) -> dict:
        n = len(self.actuals)
        if n == 0:
            return {"n": 0, "accuracy": None, "brier": None, "auc": None}
        p = np.array(self.preds)
        a = np.array(self.actuals)
        return {"n": n, "accuracy": float(((p >= 0.5).astype(int) == a).mean()),
                "brier": float(np.mean((p - a) ** 2)), "auc": _auc(a, p)}


class ABExperiment:
    def __init__(self, config: ABConfig | None = None) -> None:
        self.config = config or ABConfig()
        self.router = ABRouter(self.config)
        self.buckets: dict[str, _Bucket] = {"champion": _Bucket(), "canary": _Bucket()}

    def configure(self, enabled: bool, canary_pct: int,
                  champion_version: str = "—", canary_version: str = "—") -> None:
        self.config.enabled = enabled
        self.config.canary_pct = max(0, min(100, canary_pct))
        self.config.champion_version = champion_version
        self.config.canary_version = canary_version

    def record_outcome(self, user_id: str, pred: float, actual: int) -> str:
        bucket = self.router.assign(user_id)
        self.buckets[bucket].add(pred, actual)
        return bucket

    def decide(self, min_samples: int = 100, margin: float = 0.0,
               metric: str = "accuracy") -> dict:
        ch, ca = self.buckets["champion"].stats(), self.buckets["canary"].stats()
        if (ca["n"] < min_samples) or (ch["n"] < min_samples):
            decision, reason = "hold", (
                f"样本不足（champion {ch['n']}, canary {ca['n']} < {min_samples}）")
        else:
            cm, am = ch[metric], ca[metric]
            better = (am >= cm + margin) if metric in ("accuracy", "auc") else (am <= cm - margin)
            worse = (am < cm - max(margin, 0.01)) if metric in ("accuracy", "auc") \
                else (am > cm + max(margin, 0.01))
            if better:
                decision, reason = "promote", f"挑战者 {metric}={am:.3f} ≥ 冠军 {cm:.3f}，建议全量"
            elif worse:
                decision, reason = "rollback", f"挑战者 {metric}={am:.3f} < 冠军 {cm:.3f}，建议回滚"
            else:
                decision, reason = "hold", f"挑战者与冠军 {metric} 相当，继续观察"
        return {"decision": decision, "reason": reason, "champion": ch, "canary": ca,
                "config": self.config.__dict__}

    def report(self, **kw) -> dict:
        return self.decide(**kw)

    def reset(self) -> None:
        self.buckets = {"champion": _Bucket(), "canary": _Bucket()}


AB = ABExperiment()
