"""API 冒烟测试：健康检查 + 端到端作答→诊断 + 高考熔断拦截。"""
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.store import STORE

client = TestClient(app)
BASE = "/api/v1"


def test_health():
    r = client.get(f"{BASE}/health")
    assert r.status_code == 200
    assert r.json()["problems"] > 0 and r.json()["concepts"] > 0


def test_answer_then_diagnosis_flow():
    STORE.reset()
    uid = "api_flow"
    # 选择题按选项判分
    assert client.post(f"{BASE}/answer", json={
        "user_id": uid, "problem_id": "M0001", "selected": "A", "time_spent_s": 40}
    ).json()["correct"] is True
    client.post(f"{BASE}/answer", json={
        "user_id": uid, "problem_id": "M0002", "correct": False, "time_spent_s": 90})
    rep = client.get(f"{BASE}/diagnosis/{uid}")
    assert rep.status_code == 200 and rep.json()["n_responses"] == 2


def test_gaokao_blackout_blocks_solve(monkeypatch):
    today = settings.now().date()
    monkeypatch.setattr(settings, "gaokao_blackout_start", today)
    monkeypatch.setattr(settings, "gaokao_blackout_end", today)
    r = client.post(f"{BASE}/solve", json={
        "user_id": "api_block", "problem_id": "M0002", "reveal_level": 2})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "gaokao_blackout"
    # 错题本不受熔断影响
    assert client.get(f"{BASE}/wrongbook/api_block").status_code == 200
