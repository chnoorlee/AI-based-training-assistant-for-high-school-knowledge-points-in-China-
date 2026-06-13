"""智考通 · MLOps 演示：监控告警 + A/B 灰度 + 漂移检测。

运行：cd backend && python scripts/demo_mlops.py
流程：训练冠军/挑战者 → 灰度路由(诊断埋点) → 监控快照/告警 → A/B 在线对比与决策 → 漂移检测
"""
from __future__ import annotations

import sys
import tempfile
from datetime import timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from app.data.problem_bank import BANK  # noqa: E402
from app.modules.diagnosis.engine import ENGINE  # noqa: E402
from app.modules.diagnosis.joint_trainer import TrainConfig, save_checkpoint, train_joint  # noqa
from app.modules.diagnosis.synthetic import generate_synthetic_logs  # noqa: E402
from app.modules.diagnosis.torch_backend import TorchDiagnosisBackend  # noqa: E402
from app.modules.diagnosis.torch_models import JointDiagnosisModel  # noqa: E402
from app.modules.diagnosis.traffic_sim import now_utc, simulate_traffic_to_store  # noqa
from app.modules.mlops.ab import AB  # noqa: E402
from app.modules.mlops.drift import detect_drift_from_rows  # noqa: E402
from app.modules.mlops.monitoring import ALERTS, METRICS  # noqa: E402
from app.services.store import STORE  # noqa: E402


def h(t):
    print("\n" + "═" * 68 + f"\n  {t}\n" + "═" * 68)


def train_backend(path, n_students, epochs, tag, seed=7):
    diff = BANK.difficulty_vector()
    disc = np.array([BANK.problems[p].discrimination for p in BANK.problem_ids])
    data = generate_synthetic_logs(BANK.q_matrix, diff, disc, n_students=n_students, seed=seed)
    ni, nc = BANK.q_matrix.shape
    torch.manual_seed(0)
    m = JointDiagnosisModel(data.n_students, ni, nc, torch.tensor(BANK.q_matrix, dtype=torch.float32))
    train_joint(m, data, TrainConfig(epochs=epochs))
    save_checkpoint(m, path, list(BANK.concept_ids))
    b = TorchDiagnosisBackend.load(path)
    b.version = tag
    return b, data


def primary(items):
    pc = [list(np.where(BANK.q_matrix[i] > 0)[0]) for i in range(BANK.q_matrix.shape[0])]
    return [(pc[i][0] if pc[i] else 0) for i in items]


def main():
    print("智考通 · MLOps：模型监控告警 / A-B 灰度发布 / 特征-标签漂移检测")
    tmp = Path(tempfile.mkdtemp())

    h("① 训练现网冠军 与 候选挑战者，部署灰度 30%")
    # 同一数据，挑战者训练更充分（现网旧模型欠训 vs 候选新模型充分训练）
    champ, _ = train_backend(str(tmp / "champ.pt"), 500, 3, "champion-v1", seed=7)
    canary, _ = train_backend(str(tmp / "canary.pt"), 500, 25, "canary-v2", seed=7)
    ENGINE.torch_backend = champ
    ENGINE.set_canary(canary, canary_pct=30)
    print(f"  冠军={champ.version} 挑战者={canary.version} 灰度比例=30%（按 user_id 稳定分流）")

    h("② 灰度流量经引擎诊断 → 监控埋点（时延/版本/灰度桶/预测）")
    METRICS.reset()
    STORE.reset()
    simulate_traffic_to_store(60, now_utc() - timedelta(days=1), now_utc(), seed=0)
    for uid in list(STORE.responses.keys())[:60]:
        ENGINE.diagnose(uid, STORE.get_responses(uid))
    s = METRICS.snapshot()
    print(f"  调用量={s['total']} 时延 p50={s['latency_p50']:.1f}ms p95={s['latency_p95']:.1f}ms")
    print(f"  灰度分桶：{s['by_bucket']}  模型版本：{s['by_version']}")
    print("  /metrics(Prometheus) 摘要：")
    for line in METRICS.prometheus_text().splitlines():
        if line and not line.startswith("#"):
            print(f"    {line}")

    h("③ 监控告警评估")
    alerts = ALERTS.evaluate(METRICS)
    print("  告警：" + ("无（指标健康）" if not alerts else ""))
    for a in alerts:
        print(f"   [{a.severity}] {a.name}：{a.message}")

    h("④ 影子评估：两模型在同一批 holdout 流量上离线对比（晋升前把关）→ 决策")
    from app.modules.mlops.ab import _auc
    diff = BANK.difficulty_vector()
    disc = np.array([BANK.problems[p].discrimination for p in BANK.problem_ids])
    holdout = generate_synthetic_logs(BANK.q_matrix, diff, disc, n_students=500, seed=999)
    ys, ch_p, ca_p = [], [], []
    for sid, pre_items, pre_corr, last_item, last_correct, _ in holdout.test_points:
        lc = primary([last_item])[0]
        ch_p.append(float(champ.infer_dynamic(primary(pre_items), pre_corr)[lc]))
        ca_p.append(float(canary.infer_dynamic(primary(pre_items), pre_corr)[lc]))
        ys.append(last_correct)
    ys = np.array(ys)
    ch_auc, ca_auc = _auc(ys, np.array(ch_p)), _auc(ys, np.array(ca_p))
    decision = "PROMOTE（全量上线）" if ca_auc >= ch_auc - 0.005 else "ROLLBACK（保留冠军）"
    print(f"  样本 {len(ys)} 条 | 冠军 {champ.version} AUC={ch_auc:.3f} | 挑战者 {canary.version} AUC={ca_auc:.3f}")
    print(f"  决策：{decision}")
    print("  （线上 A/B 则按灰度桶分别累积真实结果，逻辑见 ABExperiment.decide，已单测覆盖）")

    h("⑤ 特征/标签漂移检测（PSI）")
    from app.modules.diagnosis.dataset import InteractionRow
    ref_pids = ["M0001", "M0002", "M0005", "M0008", "M0011", "M0012"] * 10
    # 当前窗口：温和偏移——更偏难题、正确率与用时上升（贴近真实漂移而非极端）
    cur_pids = ["M0003", "M0007", "M0003", "M0007", "M0001", "M0005"] * 10
    ref = [InteractionRow("u", p, i % 2 == 0, now_utc(), 60) for i, p in enumerate(ref_pids)]
    cur = [InteractionRow("u", p, (i % 4 != 0), now_utc(), 150) for i, p in enumerate(cur_pids)]
    dr = detect_drift_from_rows(ref, cur)
    print(f"  整体严重度：{dr.overall_severity}   漂移项：{dr.drifted}")
    for name, v in dr.features.items():
        print(f"    {name}: PSI={v['psi']}（{v['severity']}）")
    print(f"    label(correctness): PSI={dr.label_psi}（{dr.label_severity}）")
    al = ALERTS.evaluate(METRICS, drift_report=dr)
    print("  漂移联动告警：" + ("、".join(a.name for a in al) if al else "无"))

    # 还原引擎全量（关闭灰度），不影响后续
    ENGINE.set_canary(None, 0)
    print("\n" + "═" * 68)
    print("  演示结束。API：GET /metrics · /monitoring/alerts · /ab/status · POST /ab/config · /drift/report")
    print("═" * 68)


if __name__ == "__main__":
    main()
