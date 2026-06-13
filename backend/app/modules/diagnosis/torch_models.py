"""PyTorch 版认知诊断模型：NeuralCD（正权重 MLP 交互）+ DKT（LSTM）。

- NeuralCDNet：忠实复现 Wang et al., AAAI'20。学生掌握 hs=σ(student_emb) 可解释；
  交互层用 PosLinear（权重约束非负，保证「掌握度↑ ⇒ 答对概率↑」单调性）。
- DKTNet：忠实复现 Piech et al., NIPS'15。输入 (知识点×对错) 的 2K one-hot 序列，
  LSTM → 每知识点下一刻答对概率。
- JointDiagnosisModel：承载两者 + Q 矩阵 buffer，供联合训练与服务推理。

仅当安装 torch 时被引入；引擎在无 torch 时自动回退到 NumPy 版。
"""
from __future__ import annotations

import torch
import torch.nn as nn


class PosLinear(nn.Linear):
    """非负权重全连接（原文 NoneNegClipper）。

    前向与普通 Linear 相同（保证梯度正常回传），训练每步后由 clamp_monotonicity
    把负权重夹到 0——既维持「掌握度↑ ⇒ 答对概率↑」的单调性，又不像 relu(weight)
    那样在初始化即清零半数权重、阻断梯度。
    """


def clamp_monotonicity(module: nn.Module) -> None:
    """训练每步后调用：把 PosLinear 的负权重夹到 0。"""
    with torch.no_grad():
        for m in module.modules():
            if isinstance(m, PosLinear):
                m.weight.clamp_(min=0.0)


class NeuralCDNet(nn.Module):
    """NeuralCD：学生掌握 hs=σ(student_emb) 可解释；正权重交互层保证单调性。

    与原文的唯一工程差异：隐层激活用 ReLU（同样单调非减，但不饱和），
    避免「3 层 sigmoid + 小正权重」导致的梯度消失，使小样本下也能稳定收敛；
    输出层仍为 sigmoid 给出答对概率。单调性（掌握↑⇒答对↑）不受影响。
    """

    def __init__(self, n_students: int, n_items: int, n_concepts: int,
                 h1: int = 128, h2: int = 64) -> None:
        super().__init__()
        self.n_concepts = n_concepts
        self.student = nn.Embedding(n_students, n_concepts)
        self.k_difficulty = nn.Embedding(n_items, n_concepts)
        self.e_discrimination = nn.Embedding(n_items, 1)
        self.fc1 = PosLinear(n_concepts, h1)
        self.fc2 = PosLinear(h1, h2)
        self.fc3 = PosLinear(h2, 1)
        self.drop = nn.Dropout(0.1)
        # 用 normal(0,1) 初始化，使初始掌握度/难度拉开区分度（σ 后不再挤在 0.5）
        for emb in (self.student, self.k_difficulty, self.e_discrimination):
            nn.init.normal_(emb.weight, mean=0.0, std=1.0)
        for fc in (self.fc1, self.fc2, self.fc3):
            nn.init.constant_(fc.bias, 0.1)  # 正偏置避免 ReLU 死单元

    def _interaction(self, hs: torch.Tensor, item_ids: torch.Tensor,
                     q_rows: torch.Tensor) -> torch.Tensor:
        hdiff = torch.sigmoid(self.k_difficulty(item_ids))      # (B,K)
        hdisc = torch.sigmoid(self.e_discrimination(item_ids))  # (B,1)
        x = q_rows * (hs - hdiff) * hdisc                       # (B,K)
        x = torch.relu(self.fc1(x))
        x = self.drop(x)
        x = torch.relu(self.fc2(x))
        return torch.sigmoid(self.fc3(x)).squeeze(-1)           # (B,)

    def forward(self, student_ids: torch.Tensor, item_ids: torch.Tensor,
                q_rows: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        hs = torch.sigmoid(self.student(student_ids))           # (B,K) 可解释掌握度
        return self._interaction(hs, item_ids, q_rows), hs

    def proficiency(self, student_ids: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.student(student_ids))

    def forward_theta(self, theta: torch.Tensor, item_ids: torch.Tensor,
                      q_rows: torch.Tensor) -> torch.Tensor:
        """服务期：用外部 θ（新学生掌握度，待在线估计）替代 embedding 前向。"""
        hs = torch.sigmoid(theta).unsqueeze(0).expand(item_ids.shape[0], -1)
        return self._interaction(hs, item_ids, q_rows)


class DKTNet(nn.Module):
    def __init__(self, n_concepts: int, hidden: int = 32, dropout: float = 0.2) -> None:
        super().__init__()
        self.n_concepts = n_concepts
        self.in_drop = nn.Dropout(dropout)
        self.lstm = nn.LSTM(2 * n_concepts, hidden, batch_first=True)
        self.out_drop = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden, n_concepts)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x:(B,T,2K) → (B,T,K) 每知识点下一刻答对概率。"""
        h, _ = self.lstm(self.in_drop(x))
        return torch.sigmoid(self.fc(self.out_drop(h)))


def dkt_encode(concepts: list[int], corrects: list[int], n_concepts: int) -> torch.Tensor:
    """把 (知识点, 对错) 序列编码为 (T, 2K)：前 K 维记“答错”，后 K 维记“答对”。"""
    T = len(concepts)
    x = torch.zeros(T, 2 * n_concepts)
    for t, (s, c) in enumerate(zip(concepts, corrects)):
        x[t, s + (n_concepts if c else 0)] = 1.0
    return x


class JointDiagnosisModel(nn.Module):
    """联合模型：NeuralCD + DKT，共享知识点空间与 Q 矩阵。"""

    def __init__(self, n_students: int, n_items: int, n_concepts: int,
                 q_matrix: torch.Tensor, dkt_hidden: int = 32) -> None:
        super().__init__()
        self.n_students, self.n_items, self.n_concepts = n_students, n_items, n_concepts
        self.ncd = NeuralCDNet(n_students, n_items, n_concepts)
        self.dkt = DKTNet(n_concepts, hidden=dkt_hidden)
        self.register_buffer("Q", q_matrix.float())  # (n_items, K)

    def q_rows(self, item_ids: torch.Tensor) -> torch.Tensor:
        return self.Q[item_ids]
