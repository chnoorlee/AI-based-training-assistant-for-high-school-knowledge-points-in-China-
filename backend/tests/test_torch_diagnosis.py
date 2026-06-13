"""PyTorch 版 NeuralCD + DKT 联合训练测试（无 torch 自动跳过，不影响 NumPy 套件）。"""
import numpy as np
import pytest

torch = pytest.importorskip("torch")  # 未装 torch 则整文件跳过

from app.data.problem_bank import BANK  # noqa: E402
from app.modules.diagnosis.engine import DiagnosisEngine  # noqa: E402
from app.modules.diagnosis.joint_trainer import (  # noqa: E402
    TrainConfig, evaluate, save_checkpoint, train_joint,
)
from app.modules.diagnosis.synthetic import generate_synthetic_logs  # noqa: E402
from app.modules.diagnosis.torch_backend import TorchDiagnosisBackend  # noqa: E402
from app.modules.diagnosis.torch_models import (  # noqa: E402
    DKTNet, JointDiagnosisModel, NeuralCDNet, clamp_monotonicity,
)


@pytest.fixture(scope="module")
def trained():
    """小规模联合训练一次，供本模块复用。"""
    diff = BANK.difficulty_vector()
    disc = np.array([BANK.problems[p].discrimination for p in BANK.problem_ids])
    data = generate_synthetic_logs(BANK.q_matrix, diff, disc, n_students=800, seed=1)
    n_items, n_concepts = BANK.q_matrix.shape
    torch.manual_seed(0)  # 关键：在模型初始化前固定 RNG，避免受测试执行顺序影响
    model = JointDiagnosisModel(data.n_students, n_items, n_concepts,
                                torch.tensor(BANK.q_matrix, dtype=torch.float32))
    train_joint(model, data, TrainConfig(epochs=35, seed=1))
    return model, data


def test_model_forward_shapes():
    K, n_items, n_students = 5, 8, 12
    ncd = NeuralCDNet(n_students, n_items, K)
    sid = torch.tensor([0, 1, 2]); iid = torch.tensor([0, 3, 5])
    q = torch.ones(3, K)
    p, hs = ncd(sid, iid, q)
    assert p.shape == (3,) and hs.shape == (3, K)
    assert ((p >= 0) & (p <= 1)).all()

    dkt = DKTNet(K)
    y = dkt(torch.zeros(4, 7, 2 * K))
    assert y.shape == (4, 7, K)
    assert ((y >= 0) & (y <= 1)).all()


def test_joint_training_learns(trained):
    model, data = trained
    m = evaluate(model, data)
    # 显著优于随机，且逼近 Oracle 贝叶斯上限（阈值留足裕度，避免随机性 flaky）
    assert m["ncd_auc"] > 0.54, m
    assert m["dkt_auc"] > 0.54, m
    assert m["oracle_auc"] > 0.62, m
    # 掌握度可恢复：估计画像与真值正相关
    assert m["mastery_recovery_corr"] > 0.20, m


def test_monotonicity_constraint_holds(trained):
    model, _ = trained
    clamp_monotonicity(model)
    for name in ("fc1", "fc2", "fc3"):
        w = getattr(model.ncd, name).weight
        assert (w >= 0).all(), f"{name} 存在负权重，单调性被破坏"


def test_serving_backend_static_and_dynamic(trained, tmp_path):
    model, _ = trained
    path = tmp_path / "ckpt.pt"
    save_checkpoint(model, str(path), list(BANK.concept_ids))
    backend = TorchDiagnosisBackend.load(str(path))
    assert backend.concept_ids == list(BANK.concept_ids)

    # 同一道题：答对者的该知识点掌握度 > 答错者
    item = 0
    concept = BANK.concept_index[BANK.problems[BANK.problem_ids[item]].concept_ids[0]]
    m_right = backend.infer_static([item], [1.0])
    m_wrong = backend.infer_static([item], [0.0])
    assert m_right[concept] > m_wrong[concept]

    dyn = backend.infer_dynamic([concept, concept, concept], [1.0, 1.0, 1.0])
    assert dyn.shape == (backend.K,) and (0 <= dyn).all() and (dyn <= 1).all()


def test_engine_uses_injected_torch_backend(trained, tmp_path):
    model, _ = trained
    path = tmp_path / "ckpt.pt"
    save_checkpoint(model, str(path), list(BANK.concept_ids))
    backend = TorchDiagnosisBackend.load(str(path))
    eng = DiagnosisEngine(torch_backend=backend, auto_load_torch=False)
    assert "torch" in eng.backend_name

    from app.schemas import ResponseRecord

    def rec(pid, ok):
        p = BANK.get(pid)
        return ResponseRecord(user_id="t", problem_id=pid, correct=ok, time_spent_s=60,
                              concept_ids=list(p.concept_ids), difficulty=p.difficulty)

    report = eng.diagnose("t", [rec("M0001", True), rec("M0002", False),
                                rec("M0003", False)])
    assert report.n_responses == 3 and report.concept_mastery
    for cm in report.concept_mastery:
        assert 0.0 <= cm.score <= 1.0
