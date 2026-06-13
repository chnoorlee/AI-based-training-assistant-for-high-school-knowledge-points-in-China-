"""认知诊断训练流水线：真实日志驱动 + 增量更新 + 安全晋升。

一次 run 的全流程：
  接入(LogRepository) → 构造训练集 → [增量则热启动] → 联合训练 → 评估(时序留出 AUC/ACC)
  → 门控(不退化才晋升) → 版本化保存 → 原子切换 served checkpoint → 写注册表 → 剪枝旧版本

热启动（增量）：只迁移「服务期真正用到的共享参数」(题目难度/区分度、交互网络、DKT)，
学生 embedding 每轮按当前学生表重置——因为线上诊断用在线 θ 估计，不依赖训练期的学生 embedding。

torch 仅在 run/_build_model 内惰性导入；should_run / 注册表读取无需 torch。
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.data.problem_bank import BANK
from app.modules.diagnosis.dataset import (
    LogRepository, TrainingData, build_training_data_from_logs,
)

_ARTIFACTS = os.path.join(os.path.dirname(__file__), "..", "..", "..", "artifacts")


@dataclass
class RunResult:
    version: str
    promoted: bool
    reason: str
    metrics: dict = field(default_factory=dict)
    n_interactions: int = 0
    n_students: int = 0
    base_version: Optional[str] = None
    incremental: bool = False
    ts: str = ""


class TrainingPipeline:
    def __init__(self, repo: LogRepository, artifacts_dir: str = _ARTIFACTS,
                 served_name: str = "diagnosis_joint.pt") -> None:
        self.repo = repo
        self.dir = os.path.abspath(artifacts_dir)
        self.ckpt_dir = os.path.join(self.dir, "checkpoints")
        self.served_path = os.path.join(self.dir, served_name)
        self.registry_path = os.path.join(self.dir, "registry.json")
        os.makedirs(self.ckpt_dir, exist_ok=True)

    # ── 注册表 ─────────────────────────────────────────────
    def _load_registry(self) -> list[dict]:
        if not os.path.exists(self.registry_path):
            return []
        with open(self.registry_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_registry(self, runs: list[dict]) -> None:
        tmp = self.registry_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(runs, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.registry_path)

    def last_run(self) -> Optional[dict]:
        runs = self._load_registry()
        return runs[-1] if runs else None

    def last_promoted(self) -> Optional[dict]:
        for r in reversed(self._load_registry()):
            if r.get("promoted"):
                return r
        return None

    # ── 触发策略 ────────────────────────────────────────────
    def should_run(self, min_new: int = 200, min_interval_hours: float = 12.0
                   ) -> tuple[bool, str]:
        last = self.last_run()
        if last is None:
            return True, "首次训练（无历史）"
        last_ts = datetime.fromisoformat(last["ts"])
        new = self.repo.count_since(last_ts)
        if new >= min_new:
            return True, f"新增作答 {new} ≥ 阈值 {min_new}"
        elapsed_h = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
        if elapsed_h >= min_interval_hours:
            return True, f"距上次 {elapsed_h:.1f}h ≥ {min_interval_hours}h"
        return False, f"未达触发条件（新增 {new}，距上次 {elapsed_h:.1f}h）"

    # ── 训练一次 ────────────────────────────────────────────
    def run(self, incremental: bool = True, epochs: Optional[int] = None,
            lr: Optional[float] = None, bootstrap_if_empty: bool = True,
            gate_epsilon: float = 0.01, primary: str = "ensemble_auc") -> RunResult:
        import torch

        from app.modules.diagnosis.joint_trainer import (
            TrainConfig, evaluate, save_checkpoint, train_joint,
        )
        from app.modules.diagnosis.torch_models import JointDiagnosisModel

        data = build_training_data_from_logs(self.repo)
        bootstrapped = False
        if data.n_students < 10 and bootstrap_if_empty:
            from app.modules.diagnosis.synthetic import generate_synthetic_logs
            import numpy as np
            diff = BANK.difficulty_vector()
            disc = np.array([BANK.problems[p].discrimination for p in BANK.problem_ids])
            data = generate_synthetic_logs(BANK.q_matrix, diff, disc, n_students=300)
            bootstrapped = True

        n_items, n_concepts = BANK.q_matrix.shape
        torch.manual_seed(0)
        model = JointDiagnosisModel(max(data.n_students, 1), n_items, n_concepts,
                                    torch.tensor(BANK.q_matrix, dtype=torch.float32))

        base = self.last_promoted()
        base_version = base["version"] if base else None
        do_incremental = incremental and base is not None and os.path.exists(self.served_path)
        if do_incremental:
            self._warm_start(model, self.served_path)
            ep = epochs if epochs is not None else 15
            cfg = TrainConfig(epochs=ep, lr=lr if lr is not None else 0.005)
        else:
            ep = epochs if epochs is not None else 40
            cfg = TrainConfig(epochs=ep, lr=lr if lr is not None else 0.01)

        train_joint(model, data, cfg)
        metrics = evaluate(model, data)

        version = (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                   + f"-{len(self._load_registry())}")
        versioned = os.path.join(self.ckpt_dir, f"diagnosis_joint_{version}.pt")
        save_checkpoint(model, versioned, list(BANK.concept_ids))

        promoted, reason = self._gate(metrics, base, gate_epsilon, primary)
        if promoted:
            self._atomic_promote(versioned)
        self._prune(keep=5)

        result = RunResult(
            version=version, promoted=promoted, reason=reason, metrics=metrics,
            n_interactions=data.n_interactions, n_students=data.n_students,
            base_version=base_version if do_incremental else None,
            incremental=do_incremental,
            ts=datetime.now(timezone.utc).isoformat())
        runs = self._load_registry()
        entry = asdict(result)
        entry["bootstrapped"] = bootstrapped
        runs.append(entry)
        self._save_registry(runs)
        return result

    # ── 门控 ───────────────────────────────────────────────
    def _gate(self, metrics: dict, base: Optional[dict], eps: float,
              primary: str) -> tuple[bool, str]:
        cur = metrics.get(primary, 0.0)
        if cur <= 0.5:
            return False, f"{primary}={cur:.3f} 未优于随机，拒绝晋升"
        if base is None:
            return True, f"首个模型，{primary}={cur:.3f}，晋升"
        prev = base.get("metrics", {}).get(primary, 0.0)
        if cur >= prev - eps:
            return True, f"{primary}={cur:.3f} ≥ 在线 {prev:.3f}-{eps}，晋升"
        return False, f"{primary}={cur:.3f} < 在线 {prev:.3f}-{eps}，保留旧模型（防退化）"

    # ── 热启动：迁移共享参数（排除学生 embedding）──────────────
    def _warm_start(self, model, base_ckpt: str) -> None:
        import torch
        sd = torch.load(base_ckpt, map_location="cpu", weights_only=False)["state_dict"]
        transfer = {k: v for k, v in sd.items() if not k.startswith("ncd.student")}
        model.load_state_dict(transfer, strict=False)

    # ── 原子切换 served checkpoint ──────────────────────────
    def _atomic_promote(self, versioned: str) -> None:
        tmp = self.served_path + ".tmp"
        shutil.copyfile(versioned, tmp)
        os.replace(tmp, self.served_path)  # 同盘原子替换，服务侧不会读到半成品

    def _prune(self, keep: int = 5) -> None:
        files = [os.path.join(self.ckpt_dir, f) for f in os.listdir(self.ckpt_dir)
                 if f.endswith(".pt")]
        files.sort(key=os.path.getmtime, reverse=True)
        for f in files[keep:]:
            try:
                os.remove(f)
            except OSError:
                pass
