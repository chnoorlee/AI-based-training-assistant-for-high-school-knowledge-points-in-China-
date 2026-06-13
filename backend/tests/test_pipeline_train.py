"""流水线训练测试：全量 → 增量热启动 → 版本化/晋升/热加载（无 torch 自动跳过）。"""
import os
from datetime import timedelta

import pytest

torch = pytest.importorskip("torch")

from app.modules.diagnosis.dataset import InMemoryLogRepository  # noqa: E402
from app.modules.diagnosis.pipeline import TrainingPipeline  # noqa: E402
from app.modules.diagnosis.traffic_sim import now_utc, simulate_traffic_to_store  # noqa: E402
from app.services.store import Store  # noqa: E402


def test_full_then_incremental_pipeline(tmp_path):
    store = Store()
    repo = InMemoryLogRepository(store)
    pipe = TrainingPipeline(repo, artifacts_dir=str(tmp_path))
    now = now_utc()

    # 第一批 → 全量训练
    simulate_traffic_to_store(80, now - timedelta(days=2), now - timedelta(days=1),
                              seed=1, store=store)
    r1 = pipe.run(incremental=False, epochs=5)
    assert r1.promoted and "ensemble_auc" in r1.metrics
    assert not r1.incremental and r1.base_version is None
    assert os.path.exists(pipe.served_path) and os.path.exists(pipe.registry_path)
    served_mtime = os.path.getmtime(pipe.served_path)

    # 第二批 → 增量热启动（base = v1）
    t2 = now_utc()
    simulate_traffic_to_store(40, t2, t2 + timedelta(minutes=5), seed=2, store=store)
    r2 = pipe.run(incremental=True, epochs=5)
    assert r2.incremental and r2.base_version == r1.version
    assert r2.n_students > r1.n_students  # 学生表增长
    assert len(pipe._load_registry()) == 2
    # 版本化 checkpoint 落盘
    assert len([f for f in os.listdir(pipe.ckpt_dir) if f.endswith(".pt")]) >= 2
    if r2.promoted:  # 晋升则 served 被原子更新
        assert os.path.getmtime(pipe.served_path) >= served_mtime


def test_served_checkpoint_loadable_by_backend(tmp_path):
    from app.modules.diagnosis.torch_backend import TorchDiagnosisBackend
    from app.data.problem_bank import BANK

    store = Store()
    repo = InMemoryLogRepository(store)
    pipe = TrainingPipeline(repo, artifacts_dir=str(tmp_path))
    now = now_utc()
    simulate_traffic_to_store(150, now - timedelta(days=1), now, seed=5, store=store)
    r = pipe.run(incremental=False, epochs=10)
    assert r.promoted, r.metrics  # 训练量足以越过门控阈值并晋升

    backend = TorchDiagnosisBackend.load(pipe.served_path)
    assert backend.concept_ids == list(BANK.concept_ids)
    m = backend.infer_static([0], [1.0])
    assert m.shape == (len(BANK.concept_ids),) and (0 <= m).all() and (m <= 1).all()


def test_prune_keeps_recent(tmp_path):
    store = Store()
    repo = InMemoryLogRepository(store)
    pipe = TrainingPipeline(repo, artifacts_dir=str(tmp_path))
    now = now_utc()
    simulate_traffic_to_store(40, now - timedelta(days=1), now, seed=7, store=store)
    for _ in range(3):
        pipe.run(incremental=False, epochs=2)
    pipe._prune(keep=2)
    assert len([f for f in os.listdir(pipe.ckpt_dir) if f.endswith(".pt")]) <= 2
