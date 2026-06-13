"""PyTorch 诊断服务后端：加载联合训练 checkpoint，为线上学生做推理。

两类掌握度：
  - 静态（NeuralCD）：新学生不在 embedding 表中，固定训练好的题目参数与正权重交互网络，
    用 Adam 在线估计该生掌握度 θ（MAP）——几条作答即可，天然冷启动/增量。
  - 动态（DKT）：把该生作答序列喂入 LSTM，取末端每知识点答对概率作为动态掌握。

引擎按需调用；torch 不可用或无 checkpoint 时，load_if_available 返回 None，引擎回退 NumPy 版。
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

DEFAULT_CKPT = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                            "artifacts", "diagnosis_joint.pt")


class TorchDiagnosisBackend:
    def __init__(self, model, concept_ids: list[str]) -> None:
        import torch
        self._torch = torch
        self.model = model.eval()
        self.concept_ids = concept_ids
        self.cidx = {c: i for i, c in enumerate(concept_ids)}
        self.K = model.n_concepts
        self.path: Optional[str] = None
        self.mtime: Optional[float] = None
        self.version: str = "torch"

    # ── 加载 ───────────────────────────────────────────────
    @classmethod
    def load(cls, path: str = DEFAULT_CKPT) -> "TorchDiagnosisBackend":
        import torch

        from app.modules.diagnosis.torch_models import JointDiagnosisModel

        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        Q = torch.tensor(ckpt["q_matrix"], dtype=torch.float32)
        model = JointDiagnosisModel(ckpt["n_students"], ckpt["n_items"],
                                    ckpt["n_concepts"], Q, dkt_hidden=ckpt["dkt_hidden"])
        model.load_state_dict(ckpt["state_dict"])
        inst = cls(model, ckpt["concept_ids"])
        inst.path = path
        inst.mtime = os.path.getmtime(path)
        inst.version = os.path.basename(path)
        return inst

    @classmethod
    def load_if_available(cls, path: str = DEFAULT_CKPT) -> Optional["TorchDiagnosisBackend"]:
        try:
            import torch  # noqa: F401
        except Exception:
            return None
        if not os.path.exists(path):
            return None
        try:
            return cls.load(path)
        except Exception:
            return None

    # ── 静态掌握度（NeuralCD 在线 θ 估计）──────────────────────
    def infer_static(self, item_indices: list[int], outcomes: list[float],
                     n_iter: int = 200, lr: float = 0.1, reg: float = 0.02) -> np.ndarray:
        torch = self._torch
        if not item_indices:
            return np.full(self.K, 0.5)
        theta = torch.zeros(self.K, requires_grad=True)
        ii = torch.tensor(item_indices, dtype=torch.long)
        ys = torch.tensor(outcomes, dtype=torch.float32)
        q_rows = self.model.q_rows(ii)
        opt = torch.optim.Adam([theta], lr=lr)
        for p in self.model.parameters():
            p.requires_grad_(False)
        for _ in range(n_iter):
            p = self.model.ncd.forward_theta(theta, ii, q_rows)
            loss = torch.nn.functional.binary_cross_entropy(p, ys) + reg * theta.pow(2).sum()
            opt.zero_grad()
            loss.backward()
            opt.step()
        return torch.sigmoid(theta).detach().cpu().numpy()

    # ── 动态掌握度（DKT 序列推理）────────────────────────────
    def infer_dynamic(self, concept_indices: list[int], outcomes: list[float]) -> np.ndarray:
        torch = self._torch
        from app.modules.diagnosis.torch_models import dkt_encode
        if not concept_indices:
            return np.full(self.K, 0.5)
        X = dkt_encode(concept_indices, [int(c) for c in outcomes], self.K).unsqueeze(0)
        with torch.no_grad():
            y = self.model.dkt(X)  # (1,T,K)
        return y[0, -1].cpu().numpy()
