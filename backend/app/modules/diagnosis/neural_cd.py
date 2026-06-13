"""NeuralCD —— 神经认知诊断（NumPy 真实实现，可训练，零深度学习框架依赖）。

参考 Wang et al., AAAI'20《Neural Cognitive Diagnosis for Intelligent Education Systems》。

核心思想：
  - 学生在每个知识点上的掌握度 A_sk ∈ (0,1)（可解释，直接喂雷达图）。
  - 题目对知识点的难度 B_ik、区分度 D_i（由 IRT 标定，本骨架取种子题已标定值）。
  - 交互：z = γ·Σ_k Q_ik·D_i·(A_sk - B_ik)，P(答对)=σ(z)。掌握度高于难度 → 答对概率高。

工程取舍：
  - 题目参数（难度/区分度）来自离线标定，作为已知输入；
  - 学生掌握度向量 θ（A=σ(θ)）在「服务期」由梯度下降做 MAP 估计——这就是真实的训练过程，
    几条作答即可收敛，天然支持冷启动与增量更新。
  - 生产可平滑升级为原文「正权重 MLP 交互层」与 θ/B/D 联合训练（PyTorch），接口不变。
"""
from __future__ import annotations

import numpy as np


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


class NeuralCD:
    def __init__(self, q_matrix: np.ndarray, item_difficulty: np.ndarray,
                 item_discrimination: np.ndarray, gamma: float = 4.0) -> None:
        """
        q_matrix:            (M, K) 题目-知识点关联矩阵 {0,1}
        item_difficulty:     (M,)   每题难度 0~1
        item_discrimination: (M,)   每题区分度 0~1
        gamma:               斜率，控制概率对「掌握度-难度差」的敏感度
        """
        self.Q = np.asarray(q_matrix, dtype=np.float64)
        self.M, self.K = self.Q.shape
        self.gamma = float(gamma)
        # B_ik：把每题难度铺到它考查的知识点上（仅 Q=1 处有意义）
        diff = np.asarray(item_difficulty, dtype=np.float64).reshape(-1, 1)
        self.B = self.Q * diff  # (M, K)
        self.D = np.asarray(item_discrimination, dtype=np.float64).reshape(-1)  # (M,)

    # ── 预测 ───────────────────────────────────────────────
    def predict_prob(self, theta: np.ndarray, item_idx: int) -> float:
        a = _sigmoid(theta)  # (K,)
        contrib = self.Q[item_idx] * self.D[item_idx] * (a - self.B[item_idx])
        return float(_sigmoid(self.gamma * contrib.sum()))

    def predict_prob_for_mastery(self, mastery: np.ndarray, item_idx: int) -> float:
        """直接用掌握度向量 A（而非 θ）预测，便于推荐模块复用。"""
        a = np.clip(np.asarray(mastery, dtype=np.float64), 1e-4, 1 - 1e-4)
        contrib = self.Q[item_idx] * self.D[item_idx] * (a - self.B[item_idx])
        return float(_sigmoid(self.gamma * contrib.sum()))

    # ── 估计学生掌握度（= 训练）─────────────────────────────
    def estimate_student(self, item_indices: list[int], outcomes: list[float],
                         n_iter: int = 400, lr: float = 0.5, reg: float = 0.05
                         ) -> np.ndarray:
        """给定该生作答（题目下标 + 0/1 对错），梯度下降估计掌握度向量 A（长度 K）。

        最小化 BCE + L2 先验（无证据的知识点回归到 0.5「未知」）。返回 A=σ(θ)。
        """
        theta = np.zeros(self.K, dtype=np.float64)
        if not item_indices:
            return _sigmoid(theta)

        idx = np.asarray(item_indices, dtype=int)
        ys = np.asarray(outcomes, dtype=np.float64)
        Qs = self.Q[idx]          # (R, K)
        Ds = self.D[idx]          # (R,)
        Bs = self.B[idx]          # (R, K)
        R = len(idx)

        for _ in range(n_iter):
            a = _sigmoid(theta)                                   # (K,)
            z = self.gamma * (Qs * Ds[:, None] * (a[None, :] - Bs)).sum(axis=1)  # (R,)
            p = _sigmoid(z)                                       # (R,)
            coef = (p - ys) * self.gamma                          # (R,)
            grad = (coef[:, None] * Qs * Ds[:, None]).sum(axis=0) * (a * (1 - a))
            grad += reg * theta                                  # L2 先验
            theta -= lr * grad / R

        return _sigmoid(theta)
