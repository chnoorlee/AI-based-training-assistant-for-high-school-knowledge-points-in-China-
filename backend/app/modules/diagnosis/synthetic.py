"""合成学生作答日志（带真值掌握度），用于联合训练与离线评估。

为什么需要合成数据：种子题库仅 14 题、几乎无历史学生，无法直接训练深度模型。
我们用一个「已知真值」的认知过程生成大量可学习、可评估的作答序列：
  - 每个学生有真值掌握度 θ_true（含个体能力 + 知识点偏置 + 先修一致性）；
  - 作答按 2PL-IRT 采样对错；每练一次该知识点掌握略升（学习效应）→ 给 DKT 提供时序信号；
  - 留出每条序列的「最后一次作答」作为 next-step 预测测试点，计算 AUC/ACC，
    并用 θ_true 评估掌握度可恢复性（estimated vs true 的相关性）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SyntheticData:
    n_students: int
    n_items: int
    n_concepts: int
    # 训练：每个学生的前缀序列（去掉最后一次）
    train_sequences: list[tuple[int, list[int], list[int]]] = field(default_factory=list)
    # 评估：(student_id, item_prefix, correct_prefix, last_item, last_correct, last_true_p)
    test_points: list[tuple[int, list[int], list[int], int, int, float]] = field(
        default_factory=list)
    theta_true: np.ndarray | None = None  # (N, K)
    item_concepts: list[list[int]] = field(default_factory=list)  # 每题的知识点下标
    primary_concept: list[int] = field(default_factory=list)      # 每题主知识点下标


def generate_synthetic_logs(
    q_matrix: np.ndarray,
    item_difficulty: np.ndarray,
    item_discrimination: np.ndarray,
    n_students: int = 2000,
    seq_len_range: tuple[int, int] = (40, 90),
    learn_gain: float = 0.015,
    ability_std: float = 1.2,
    slope: float = 2.5,
    seed: int = 7,
) -> SyntheticData:
    rng = np.random.default_rng(seed)
    n_items, n_concepts = q_matrix.shape
    item_concepts = [list(np.where(q_matrix[i] > 0)[0]) for i in range(n_items)]
    primary_concept = [(cs[0] if cs else 0) for cs in item_concepts]

    theta_true = np.zeros((n_students, n_concepts))
    data = SyntheticData(n_students=n_students, n_items=n_items, n_concepts=n_concepts,
                         item_concepts=item_concepts, primary_concept=primary_concept)

    for s in range(n_students):
        ability = rng.normal(0.0, ability_std)  # 个体总体能力（更大方差→更可分）
        concept_bias = rng.normal(0.0, 0.6, size=n_concepts)
        theta = 1 / (1 + np.exp(-(ability + concept_bias)))  # (K,) 真值掌握度
        theta_dyn = theta.copy()

        L = int(rng.integers(seq_len_range[0], seq_len_range[1] + 1))
        items, corrects, ps = [], [], []
        for _ in range(L):
            i = int(rng.integers(0, n_items))
            cs = item_concepts[i] or [primary_concept[i]]
            mastery = float(np.mean([theta_dyn[c] for c in cs]))
            # 2PL-IRT 答对概率（slope 越大越陡→可分性越高）
            z = slope * (0.5 + item_discrimination[i]) * (mastery - item_difficulty[i])
            p = 1 / (1 + np.exp(-z))
            c = int(rng.random() < p)
            items.append(i)
            corrects.append(c)
            ps.append(p)
            for cc in cs:  # 学习效应：练习后该知识点掌握略升
                theta_dyn[cc] += learn_gain * (1 - theta_dyn[cc])

        theta_true[s] = theta_dyn  # 以序列结束时的掌握作为「当前真值」
        if L >= 2:
            data.train_sequences.append((s, items[:-1], corrects[:-1]))
            data.test_points.append((s, items[:-1], corrects[:-1],
                                     items[-1], corrects[-1], ps[-1]))

    data.theta_true = theta_true
    return data
