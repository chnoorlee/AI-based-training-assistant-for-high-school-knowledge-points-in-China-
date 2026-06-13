"""真实 OCR/LLM 客户端集成测试。

用 httpx.MockTransport 对着「契约一致的假服务」在**真实 HTTP 协议层**驱动生产客户端代码
（请求构造/鉴权头/JSON 解析/重试/降级/路由），无需真实 key 与端口。
"""
import httpx
import pytest

from app.core.config import settings
from app.modules.grading.essay_llm import EssayGraderLLM
from app.modules.parsing import HttpEduParser
from app.modules.rag.llm import MockSolverLLM, OpenAICompatibleClient, get_llm
from app.modules.rag.solver import SOLVER
from app.schemas import RevealLevel, SolveRequest
from app.services.store import STORE
from scripts.fake_llm_server import build_mock_transport


def real_llm() -> OpenAICompatibleClient:
    return OpenAICompatibleClient(http_client=httpx.Client(transport=build_mock_transport()))


def err_llm() -> OpenAICompatibleClient:
    t = httpx.MockTransport(lambda req: httpx.Response(500, json={"error": "boom"}))
    return OpenAICompatibleClient(http_client=httpx.Client(transport=t))


# ── LLM 客户端（真实 HTTP）─────────────────────────────────
def test_llm_client_methods_over_http():
    llm = real_llm()
    assert llm.is_real
    assert len(llm.socratic_questions("解方程", ["函数"], [])) == 3
    assert llm.guided_steps("解方程", ["函数"], [])
    sol = llm.full_solution("解方程 x²-1=0", ["函数"], [])
    assert sol["answer"] and sol["knowledge_points"]


def test_llm_complete_json_parses():
    data = real_llm().complete_json("系统", "作文评分，返回 JSON")
    assert isinstance(data, dict) and "scores" in data


def test_llm_retry_then_fallback_on_error():
    llm = err_llm()  # 始终 500
    sol = llm.full_solution("解方程", ["函数"], [])  # 不抛错，降级为方法论步骤
    assert sol["answer"] is None and sol["steps"]


def test_get_llm_defaults_to_mock():
    assert isinstance(get_llm(), MockSolverLLM)  # 默认 backend=mock


# ── 自由输入解题（真实 LLM 路径，苏格拉底门控仍生效）──────────
def test_free_input_full_solution_with_real_llm(monkeypatch):
    monkeypatch.setattr("app.modules.rag.solver.LLM", real_llm())
    # 抬高命中阈值，强制走"自由输入"路径（隔离测试；正常产品命中题库优先用标准解法）
    monkeypatch.setattr("app.modules.rag.solver.MATCH_THRESHOLD", 9.0)
    STORE.reset()
    req = lambda: SolveRequest(user_id="ru", stem="解方程 x²-1=0 的所有实数解",
                               reveal_level=RevealLevel.FULL)
    r0 = SOLVER.solve(req())
    assert r0.reveal_level == RevealLevel.HINT and r0.final_answer is None
    assert len(r0.socratic_questions) == 3            # 来自 LLM
    SOLVER.solve(req())                                # GUIDED
    r2 = SOLVER.solve(req())
    assert r2.reveal_level == RevealLevel.FULL
    assert r2.final_answer and "函数的单调性与奇偶性" in r2.knowledge_points  # 走了 LLM 路径
    assert r2.fact_check.passed                        # 知识点经图谱核验


def test_free_input_mock_does_not_fabricate_answer():
    monkeypatch_llm = MockSolverLLM()
    import app.modules.rag.solver as sv
    old = sv.LLM
    sv.LLM = monkeypatch_llm
    try:
        STORE.reset()
        for _ in range(3):
            r = SOLVER.solve(SolveRequest(user_id="mk", stem="某自由输入题",
                                          reveal_level=RevealLevel.FULL))
        assert r.reveal_level == RevealLevel.FULL and r.final_answer is None  # Mock 不杜撰
    finally:
        sv.LLM = old


# ── 作文批改（真实 LLM）─────────────────────────────────────
def test_essay_grader_llm_uses_model_scores():
    g = EssayGraderLLM(real_llm())
    r = g.grade("规则与自由", "这是一篇关于规则与自由的议论文。")
    assert 0 < r.total <= 60 and len(r.dimensions) == 3
    assert r.grader_backend.startswith("llm")
    # 假服务给每个二级维度 4.2 → 维度分应接近 16.8
    assert any(abs(d.score - 16.8) < 0.5 for d in r.dimensions)


def test_essay_grader_llm_falls_back_on_bad_json():
    g = EssayGraderLLM(err_llm())  # complete_json 会失败
    r = g.grade("题目", "正文")
    assert r.grader_backend == "rubric-fallback" and 0 <= r.total <= 60


# ── OCR 解析（真实 HTTP 网关）────────────────────────────────
def test_http_ocr_parser(monkeypatch):
    monkeypatch.setattr(settings, "ocr_endpoint", "http://fake/ocr/recognize")
    p = HttpEduParser(http_client=httpx.Client(transport=build_mock_transport()))
    parsed = p.parse(text="已知函数 f(x)=x²-1，求其零点。")
    assert parsed.stem and parsed.parse_confidence > 0.9
    assert "MATH_FUNC_PROP" in parsed.concept_ids
    assert parsed.latex_blocks


def test_http_ocr_parser_falls_back_on_error(monkeypatch):
    monkeypatch.setattr(settings, "ocr_endpoint", "http://fake/ocr/recognize")
    t = httpx.MockTransport(lambda req: httpx.Response(500))
    p = HttpEduParser(http_client=httpx.Client(transport=t))
    parsed = p.parse(text="已知函数 f(x)=x²-1，求其零点。")
    assert any("降级" in w for w in parsed.warnings) and parsed.parse_confidence <= 0.5
