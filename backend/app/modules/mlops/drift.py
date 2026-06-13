"""特征 / 标签漂移检测（PSI）。

对比「参考窗口」与「当前窗口」的作答日志分布：
  特征漂移：考点分布、难度分布、作答时长分布；
  标签漂移：正确率分布。
用 PSI(Population Stability Index) 量化：<0.1 无漂移，0.1~0.25 轻度，>0.25 严重。
严重漂移 → 触发告警 + 建议重训（接入 pipeline.should_run）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from app.data.problem_bank import BANK
from app.modules.diagnosis.dataset import InteractionRow, LogRepository


def _props_categorical(values: list, categories: list) -> np.ndarray:
    idx = {c: i for i, c in enumerate(categories)}
    cnt = np.zeros(len(categories))
    for v in values:
        if v in idx:
            cnt[idx[v]] += 1
    return cnt / cnt.sum() if cnt.sum() else cnt


def _props_binned(values: list[float], edges: list[float]) -> np.ndarray:
    if not values:
        return np.zeros(len(edges) - 1)
    h, _ = np.histogram(values, bins=edges)
    return h / h.sum() if h.sum() else h


def psi(ref_p: np.ndarray, cur_p: np.ndarray, eps: float = 1e-4) -> float:
    r = np.clip(ref_p, eps, None)
    c = np.clip(cur_p, eps, None)
    return float(np.sum((c - r) * np.log(c / r)))


def severity(value: float) -> str:
    return "none" if value < 0.1 else ("minor" if value < 0.25 else "major")


@dataclass
class DriftReport:
    features: dict = field(default_factory=dict)  # name -> {psi, severity}
    label_psi: float = 0.0
    label_severity: str = "none"
    overall_severity: str = "none"
    drifted: list[str] = field(default_factory=list)
    n_ref: int = 0
    n_cur: int = 0


def _features(rows: list[InteractionRow]):
    concepts, diffs, times, corrects = [], [], [], []
    for r in rows:
        p = BANK.get(r.problem_id)
        if p is None:
            continue
        concepts.append(p.concept_ids[0] if p.concept_ids else "?")
        diffs.append(p.difficulty)
        times.append(r.time_spent_s)
        corrects.append(int(r.correct))
    return concepts, diffs, times, corrects


def detect_drift_from_rows(ref: list[InteractionRow], cur: list[InteractionRow]) -> DriftReport:
    rc, rd, rt, ry = _features(ref)
    cc, cd, ct, cy = _features(cur)
    concepts = BANK.concept_ids
    diff_edges = [0, 0.3, 0.5, 0.7, 1.01]
    time_edges = [0, 30, 60, 120, 300, 100000]

    feats = {
        "concept_dist": psi(_props_categorical(rc, concepts), _props_categorical(cc, concepts)),
        "difficulty_dist": psi(_props_binned(rd, diff_edges), _props_binned(cd, diff_edges)),
        "time_spent_dist": psi(_props_binned(rt, time_edges), _props_binned(ct, time_edges)),
    }
    label = psi(_props_categorical(ry, [0, 1]), _props_categorical(cy, [0, 1]))

    feat_out = {k: {"psi": round(v, 4), "severity": severity(v)} for k, v in feats.items()}
    drifted = [k for k, v in feats.items() if severity(v) != "none"]
    if severity(label) != "none":
        drifted.append("label(correctness)")
    sevs = [severity(v) for v in feats.values()] + [severity(label)]
    overall = "major" if "major" in sevs else ("minor" if "minor" in sevs else "none")
    return DriftReport(features=feat_out, label_psi=round(label, 4),
                       label_severity=severity(label), overall_severity=overall,
                       drifted=drifted, n_ref=len(rc), n_cur=len(cc))


def detect_drift(repo: LogRepository, split_ts: datetime) -> DriftReport:
    """以 split_ts 为界：之前为参考窗口，之后为当前窗口。"""
    ref, cur = [], []
    for row in repo.iter_interactions():
        (cur if row.ts > split_ts else ref).append(row)
    return detect_drift_from_rows(ref, cur)
