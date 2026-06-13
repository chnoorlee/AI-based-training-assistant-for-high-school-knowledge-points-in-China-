"""NeuralCD + DKT 联合训练。

联合损失：L = BCE_ncd + α·BCE_dkt + β·Consistency
  - BCE_ncd：NeuralCD 对 (学生,题) 作答的预测；
  - BCE_dkt：DKT 对序列下一题的预测（标准 next-step KT 损失）；
  - Consistency：DKT 在序列末端的「每知识点掌握」与 NeuralCD 学生画像 hs 对齐（仅约束已练知识点）。
    —— 这把「静态可解释画像」与「动态时序趋势」耦合，互相正则，提升一致性与泛化。

评估：next-step 预测 AUC/ACC（NCD 与 DKT 各一），掌握度可恢复性（estimated vs θ_true 相关）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
import torch.nn.functional as F

from app.modules.diagnosis.synthetic import SyntheticData
from app.modules.diagnosis.torch_models import (
    JointDiagnosisModel,
    clamp_monotonicity,
    dkt_encode,
)


def auc_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    n_pos = float(y_true.sum())
    n_neg = float(len(y_true) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(y_score, kind="mergesort")
    ranks = np.empty(len(y_score), dtype=float)
    ranks[order] = np.arange(1, len(y_score) + 1)
    return float((ranks[y_true == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _build_dkt_batch(seqs, primary_concept, K, device):
    """seqs: list[(items, corrects)] → DKT 训练张量。"""
    B = len(seqs)
    lengths = [len(items) for items, _ in seqs]
    Tmax = max(lengths)
    X = torch.zeros(B, Tmax, 2 * K)
    next_skill = torch.zeros(B, Tmax, dtype=torch.long)
    next_correct = torch.zeros(B, Tmax)
    mask = torch.zeros(B, Tmax)
    for b, (items, corrects) in enumerate(seqs):
        concepts = [primary_concept[i] for i in items]
        X[b, : len(items)] = dkt_encode(concepts, corrects, K)
        for t in range(len(items) - 1):  # 预测下一题
            next_skill[b, t] = concepts[t + 1]
            next_correct[b, t] = corrects[t + 1]
            mask[b, t] = 1.0
    lens = torch.tensor(lengths, dtype=torch.long)
    return (X.to(device), lens.to(device), next_skill.to(device),
            next_correct.to(device), mask.to(device))


@dataclass
class TrainConfig:
    epochs: int = 30
    batch_size: int = 32
    lr: float = 0.01
    alpha: float = 1.0   # DKT 损失权重
    beta: float = 0.5    # 一致性损失权重
    device: str = "cpu"
    seed: int = 0


def train_joint(model: JointDiagnosisModel, data: SyntheticData,
                cfg: TrainConfig | None = None, verbose: bool = False) -> dict:
    cfg = cfg or TrainConfig()
    torch.manual_seed(cfg.seed)
    dev = cfg.device
    model.to(dev).train()
    K = model.n_concepts
    pc = data.primary_concept
    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr, weight_decay=1e-5)

    seqs = data.train_sequences
    history: list[dict] = []
    for epoch in range(cfg.epochs):
        perm = np.random.default_rng(cfg.seed + epoch).permutation(len(seqs))
        ep = {"ncd": 0.0, "dkt": 0.0, "cons": 0.0, "n": 0}
        for start in range(0, len(seqs), cfg.batch_size):
            batch = [seqs[i] for i in perm[start:start + cfg.batch_size]]
            sids = [b[0] for b in batch]
            seq_pairs = [(b[1], b[2]) for b in batch]

            # —— DKT 分支 ——
            X, lens, nskill, ncorrect, dmask = _build_dkt_batch(seq_pairs, pc, K, dev)
            y = model.dkt(X)  # (B,T,K)
            pred = y.gather(2, nskill.unsqueeze(-1)).squeeze(-1)  # (B,T)
            denom = dmask.sum().clamp(min=1.0)
            loss_dkt = (F.binary_cross_entropy(pred, ncorrect, reduction="none")
                        * dmask).sum() / denom
            # 序列末端每知识点掌握 (B,K)
            idx = (lens - 1).view(-1, 1, 1).expand(-1, 1, K)
            dkt_final = y.gather(1, idx).squeeze(1)

            # —— NeuralCD 分支（展平全部交互）——
            flat_s, flat_i, flat_c = [], [], []
            practiced = torch.zeros(len(batch), K)
            for bi, (s, (items, corrects)) in enumerate(zip(sids, seq_pairs)):
                for it, c in zip(items, corrects):
                    flat_s.append(s)
                    flat_i.append(it)
                    flat_c.append(float(c))
                    practiced[bi, pc[it]] = 1.0
            si = torch.tensor(flat_s, dtype=torch.long, device=dev)
            ii = torch.tensor(flat_i, dtype=torch.long, device=dev)
            cc = torch.tensor(flat_c, device=dev)
            p_ncd, _ = model.ncd(si, ii, model.q_rows(ii))
            loss_ncd = F.binary_cross_entropy(p_ncd, cc)

            # —— 一致性损失 ——
            sid_t = torch.tensor(sids, dtype=torch.long, device=dev)
            hs_student = model.ncd.proficiency(sid_t)  # (B,K)
            pmask = practiced.to(dev)
            loss_cons = ((dkt_final - hs_student) ** 2 * pmask).sum() / pmask.sum().clamp(min=1.0)

            loss = loss_ncd + cfg.alpha * loss_dkt + cfg.beta * loss_cons
            opt.zero_grad()
            loss.backward()
            opt.step()
            clamp_monotonicity(model)  # 维持 NeuralCD 单调性

            ep["ncd"] += loss_ncd.item() * len(batch)
            ep["dkt"] += loss_dkt.item() * len(batch)
            ep["cons"] += loss_cons.item() * len(batch)
            ep["n"] += len(batch)
        rec = {"epoch": epoch, "loss_ncd": ep["ncd"] / ep["n"],
               "loss_dkt": ep["dkt"] / ep["n"], "loss_cons": ep["cons"] / ep["n"]}
        history.append(rec)
        if verbose and (epoch % 5 == 0 or epoch == cfg.epochs - 1):
            print(f"  epoch {epoch:>3} | ncd {rec['loss_ncd']:.4f} "
                  f"dkt {rec['loss_dkt']:.4f} cons {rec['loss_cons']:.4f}")
    return {"history": history}


@torch.no_grad()
def evaluate(model: JointDiagnosisModel, data: SyntheticData, device: str = "cpu") -> dict:
    model.to(device).eval()
    K = model.n_concepts
    pc = data.primary_concept

    # next-step 预测：NCD
    sids = torch.tensor([t[0] for t in data.test_points], dtype=torch.long, device=device)
    last_items = torch.tensor([t[3] for t in data.test_points], dtype=torch.long, device=device)
    last_correct = np.array([t[4] for t in data.test_points], dtype=float)
    p_ncd, _ = model.ncd(sids, last_items, model.q_rows(last_items))
    p_ncd = p_ncd.cpu().numpy()

    # next-step 预测：DKT（喂前缀，取末端对应知识点）
    seqs = [(t[1], t[2]) for t in data.test_points]
    X, lens, _, _, _ = _build_dkt_batch(seqs, pc, K, device)
    y = model.dkt(X)
    idx = (lens - 1).view(-1, 1, 1).expand(-1, 1, K)
    dkt_final = y.gather(1, idx).squeeze(1).cpu().numpy()  # (B,K)
    p_dkt = np.array([dkt_final[b, pc[data.test_points[b][3]]]
                      for b in range(len(data.test_points))])

    def acc(p):
        return float(((p >= 0.5).astype(float) == last_correct).mean())

    p_ens = 0.5 * (p_ncd + p_dkt)
    out = {"ncd_auc": auc_score(last_correct, p_ncd), "ncd_acc": acc(p_ncd),
           "dkt_auc": auc_score(last_correct, p_dkt), "dkt_acc": acc(p_dkt),
           "ensemble_auc": auc_score(last_correct, p_ens), "ensemble_acc": acc(p_ens),
           "n_test": len(data.test_points)}

    # Oracle 仅在有真值概率时可算（合成集）；真实日志无真值，跳过
    if len(data.test_points[0]) > 5:
        oracle_p = np.array([t[5] for t in data.test_points])
        out["oracle_auc"] = auc_score(last_correct, oracle_p)

    # 掌握度可恢复性仅在有 θ_true 时可算（合成集）
    theta_true = getattr(data, "theta_true", None)
    if theta_true is not None:
        train_sids = sorted({s for s, *_ in data.train_sequences})
        hs = model.ncd.proficiency(
            torch.tensor(train_sids, dtype=torch.long, device=device)).cpu().numpy()
        out["mastery_recovery_corr"] = float(
            np.corrcoef(hs.ravel(), theta_true[train_sids].ravel())[0, 1])
    return out


def save_checkpoint(model: JointDiagnosisModel, path: str, concept_ids: list[str]) -> None:
    import os
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    model.to("cpu")
    torch.save({
        "state_dict": model.state_dict(),
        "n_students": model.n_students, "n_items": model.n_items,
        "n_concepts": model.n_concepts, "dkt_hidden": model.dkt.lstm.hidden_size,
        "q_matrix": model.Q.cpu().tolist(), "concept_ids": concept_ids,
    }, path)
