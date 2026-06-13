"""联合训练 NeuralCD + DKT，保存 checkpoint 供引擎自动启用。

运行：
    cd backend
    python scripts/train_diagnosis.py            # 默认 400 学生 / 30 轮
    python scripts/train_diagnosis.py --students 800 --epochs 50

产物：backend/artifacts/diagnosis_joint.pt
之后 DiagnosisEngine 启动会自动检测并切换到 torch 联合模型（无需改任何业务代码）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from app.data.problem_bank import BANK  # noqa: E402
from app.modules.diagnosis.joint_trainer import (  # noqa: E402
    TrainConfig, evaluate, save_checkpoint, train_joint,
)
from app.modules.diagnosis.synthetic import generate_synthetic_logs  # noqa: E402
from app.modules.diagnosis.torch_models import JointDiagnosisModel  # noqa: E402

DEFAULT_CKPT = Path(__file__).resolve().parents[1] / "artifacts" / "diagnosis_joint.pt"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=600)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--lr", type=float, default=0.01)
    ap.add_argument("--alpha", type=float, default=1.0, help="DKT 损失权重")
    ap.add_argument("--beta", type=float, default=0.5, help="一致性损失权重")
    ap.add_argument("--out", type=str, default=str(DEFAULT_CKPT))
    args = ap.parse_args()

    print("智考通 · NeuralCD + DKT 联合训练")
    diff = BANK.difficulty_vector()
    disc = np.array([BANK.problems[p].discrimination for p in BANK.problem_ids])
    n_items, n_concepts = BANK.q_matrix.shape
    print(f"题目 {n_items} | 知识点 {n_concepts}")

    print(f"生成合成作答日志：{args.students} 名学生 ...")
    data = generate_synthetic_logs(BANK.q_matrix, diff, disc, n_students=args.students)
    print(f"训练序列 {len(data.train_sequences)} | 测试点 {len(data.test_points)}")

    torch.manual_seed(0)  # 模型初始化前固定 RNG，保证 checkpoint 可复现
    model = JointDiagnosisModel(data.n_students, n_items, n_concepts,
                                torch.tensor(BANK.q_matrix, dtype=torch.float32))
    cfg = TrainConfig(epochs=args.epochs, lr=args.lr, alpha=args.alpha, beta=args.beta)
    print(f"开始训练（epochs={cfg.epochs}, α={cfg.alpha}, β={cfg.beta}）...")
    train_joint(model, data, cfg, verbose=True)

    m = evaluate(model, data)
    print("\n── 评估（合成集 next-step 预测）──")
    print(f"  NeuralCD : AUC={m['ncd_auc']:.3f}  ACC={m['ncd_acc']:.3f}")
    print(f"  DKT      : AUC={m['dkt_auc']:.3f}  ACC={m['dkt_acc']:.3f}")
    print(f"  集成均值 : AUC={m['ensemble_auc']:.3f}  ACC={m['ensemble_acc']:.3f}")
    print(f"  Oracle   : AUC={m['oracle_auc']:.3f}  （贝叶斯上限：用真值概率，理论天花板）")
    print(f"  掌握度可恢复性 corr(estimated, θ_true) = {m['mastery_recovery_corr']:.3f}")
    print(f"  （模型 AUC 越接近 Oracle、corr 越高，说明越逼近真实能力结构）")

    save_checkpoint(model, args.out, list(BANK.concept_ids))
    print(f"\n✅ 已保存 checkpoint：{args.out}")
    print("   重启服务 / 重新 import 时，DiagnosisEngine 将自动切换到 torch 联合模型。")


if __name__ == "__main__":
    main()
