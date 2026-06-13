"""知识追踪：刻画掌握度随作答序列的「时间演化」。

- BKT（Bayesian Knowledge Tracing，Corbett & Anderson 1995）：NumPy 真实在线更新，
  每答一题即更新该知识点的 P(已掌握)，并预测下一题答对概率。轻量、可解释、冷启动友好。
- DKT（Deep Knowledge Tracing，Piech et al. 2015，LSTM）：生产升级路径，已留 stub，
  torch 可用时启用，捕捉跨知识点的长程依赖。

NeuralCD 给「此刻多知识点掌握画像（静态、可解释）」，BKT/DKT 给「掌握随练习的动态趋势」，
二者在 engine 里融合 —— 即 PRD 要求的 NeuralCD + DKT 混合诊断。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BKTParams:
    p_init: float = 0.30   # P(L0)：初始已掌握概率
    p_transit: float = 0.15  # P(T)：一次练习后由「未掌握」转为「掌握」的概率
    p_slip: float = 0.10   # P(S)：已掌握却答错（失误）
    p_guess: float = 0.20  # P(G)：未掌握却蒙对


class BKT:
    """单/多知识点 BKT。对每个知识点维护一条独立的掌握度链。"""

    def __init__(self, params: dict[str, BKTParams] | None = None,
                 default: BKTParams | None = None) -> None:
        self.params = params or {}
        self.default = default or BKTParams()

    def _p(self, skill: str) -> BKTParams:
        return self.params.get(skill, self.default)

    def predict(self, p_known: float, skill: str) -> float:
        """由当前 P(已掌握) 预测下一题答对概率。"""
        pr = self._p(skill)
        return p_known * (1 - pr.p_slip) + (1 - p_known) * pr.p_guess

    def update(self, p_known: float, correct: bool, skill: str) -> float:
        """观测一次作答后，返回更新后的 P(已掌握)。"""
        pr = self._p(skill)
        if correct:
            num = p_known * (1 - pr.p_slip)
            den = num + (1 - p_known) * pr.p_guess
        else:
            num = p_known * pr.p_slip
            den = num + (1 - p_known) * (1 - pr.p_guess)
        posterior = num / den if den > 1e-12 else p_known
        # 学习（转移）
        return posterior + (1 - posterior) * pr.p_transit

    def trace(self, skill: str, outcomes: list[bool]) -> float:
        """喂入某知识点的作答序列，返回最终 P(已掌握)。"""
        p = self._p(skill).p_init
        for c in outcomes:
            p = self.update(p, c, skill)
        return p


class DKTTracer:
    """Deep Knowledge Tracing（LSTM）生产 stub。

    设计（生产实现）：
      输入  x_t = one-hot(2·K)：知识点 × 对错 的编码序列；
      网络  LSTM(hidden=200) → Dense(K) → sigmoid，输出每个知识点下一刻答对概率；
      训练  序列 BCE，仅对「下一题实际作答的知识点」计损失；
      产出  最后时刻隐状态 → 全知识点掌握向量，捕捉 BKT 无法表达的跨点迁移。

    需要 torch；未安装时本类不可用，engine 自动回退到 BKT。
    """

    available = False

    def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - 生产路径
        try:
            import torch  # noqa: F401
            self.available = True
        except Exception:
            self.available = False
        if not self.available:
            raise RuntimeError("DKTTracer 需要 torch；MVP 环境请使用 BKT。")
