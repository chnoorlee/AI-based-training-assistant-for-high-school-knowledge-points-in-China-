"""数据接入层 + 触发/门控逻辑测试（无需 torch，始终运行）。"""
from datetime import timedelta

from app.modules.diagnosis.dataset import (
    InMemoryLogRepository, build_training_data_from_logs,
)
from app.modules.diagnosis.pipeline import TrainingPipeline
from app.modules.diagnosis.traffic_sim import now_utc, simulate_traffic_to_store
from app.services.store import Store


def _repo_with(n, store=None, **kw):
    store = store or Store()
    now = now_utc()
    simulate_traffic_to_store(n, now - timedelta(days=1), now, store=store, **kw)
    return InMemoryLogRepository(store), store


def test_build_training_data_from_logs():
    repo, _ = _repo_with(6, seed=3)
    data = build_training_data_from_logs(repo)
    assert data.n_students >= 1
    assert len(data.train_sequences) == data.n_students == len(data.student_vocab)
    assert data.n_interactions > 0
    # 真实日志无真值
    assert data.theta_true is None
    # test_point 为 5 元组（无真值概率）
    assert len(data.test_points[0]) == 5
    # 题目数/知识点数与题库一致
    from app.data.problem_bank import BANK
    assert data.n_items == len(BANK.problem_ids)
    assert len(data.primary_concept) == data.n_items


def test_repo_count_and_latest():
    store = Store()
    now = now_utc()
    simulate_traffic_to_store(4, now - timedelta(hours=2), now - timedelta(hours=1),
                              seed=1, store=store)
    repo = InMemoryLogRepository(store)
    total = repo.count_since()
    assert total > 0
    assert repo.count_since(now) == 0           # 之后无新数据
    assert repo.latest_ts() is not None


def test_should_run_logic(tmp_path):
    store = Store()
    repo = InMemoryLogRepository(store)
    pipe = TrainingPipeline(repo, artifacts_dir=str(tmp_path))
    ok, _ = pipe.should_run()
    assert ok  # 首次必跑

    pipe._save_registry([{"version": "v0", "ts": now_utc().isoformat(),
                          "promoted": True, "metrics": {}, "n_students": 0}])
    ok, _ = pipe.should_run(min_new=10, min_interval_hours=9999)
    assert not ok  # 无新数据且未到时间间隔

    t = now_utc()
    simulate_traffic_to_store(5, t, t + timedelta(minutes=5), seed=2, store=store)
    ok, why = pipe.should_run(min_new=10, min_interval_hours=9999)
    assert ok and "新增" in why  # 新数据达阈值


def test_gate_logic(tmp_path):
    pipe = TrainingPipeline(InMemoryLogRepository(Store()), artifacts_dir=str(tmp_path))
    # 首个模型，优于随机 → 晋升
    ok, _ = pipe._gate({"ensemble_auc": 0.70}, None, 0.01, "ensemble_auc")
    assert ok
    # 不优于随机 → 拒绝
    ok, _ = pipe._gate({"ensemble_auc": 0.49}, None, 0.01, "ensemble_auc")
    assert not ok
    # 相比在线退化 → 拒绝（防退化）
    ok, _ = pipe._gate({"ensemble_auc": 0.60}, {"metrics": {"ensemble_auc": 0.70}},
                       0.01, "ensemble_auc")
    assert not ok
    # 不退化 → 晋升
    ok, _ = pipe._gate({"ensemble_auc": 0.71}, {"metrics": {"ensemble_auc": 0.70}},
                       0.01, "ensemble_auc")
    assert ok
