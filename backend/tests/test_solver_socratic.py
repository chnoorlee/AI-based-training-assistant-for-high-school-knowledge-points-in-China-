"""解题门控单测：落实「绝不上传即给答案」「先引导后揭示」「完整思维链」。"""
from app.modules.rag.solver import SOLVER
from app.schemas import RevealLevel, SolveRequest
from app.services.store import STORE


def test_first_solve_is_hint_only_even_if_full_requested():
    STORE.reset()
    r = SOLVER.solve(SolveRequest(user_id="u1", problem_id="M0002",
                                  reveal_level=RevealLevel.FULL))
    assert r.reveal_level == RevealLevel.HINT
    assert r.final_answer is None        # 首次绝不给答案
    assert len(r.socratic_questions) >= 3  # 先给 3 个引导问题
    assert r.guided_steps == []


def test_progressive_reveal_to_full():
    STORE.reset()
    uid, pid = "u2", "M0002"
    r0 = SOLVER.solve(SolveRequest(user_id=uid, problem_id=pid, reveal_level=RevealLevel.FULL))
    r1 = SOLVER.solve(SolveRequest(user_id=uid, problem_id=pid, reveal_level=RevealLevel.FULL))
    r2 = SOLVER.solve(SolveRequest(user_id=uid, problem_id=pid, reveal_level=RevealLevel.FULL))

    assert r0.reveal_level == RevealLevel.HINT
    assert r1.reveal_level == RevealLevel.GUIDED
    assert r1.final_answer is None and r1.guided_steps  # 分步但仍不给最终答案
    assert r2.reveal_level == RevealLevel.FULL
    assert r2.final_answer and r2.chain_of_thought       # 完整思维链 + 答案
    assert r2.fact_check.passed                          # 知识点全部命中图谱


def test_knowledge_points_are_verified_against_graph():
    STORE.reset()
    r = SOLVER.solve(SolveRequest(user_id="u3", problem_id="M0010",
                                  reveal_level=RevealLevel.HINT))
    assert r.knowledge_points  # 命中圆锥曲线知识点
    assert r.fact_check.passed and not r.fact_check.unverified_claims
