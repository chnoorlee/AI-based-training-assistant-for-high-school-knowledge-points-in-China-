"""智考通 · 真实 OCR/LLM 接入演示（自由输入解题 + 作文批改，走生产客户端）。

为自包含可跑，这里用「契约一致的假服务」(MockTransport) 驱动**真实客户端代码**——
与对接 vLLM/DeepSeek/Qwen、百度/阿里云 OCR 的代码路径完全一致；
生产只需把 .env 的 LLM_BACKEND=real、OCR_ENDPOINT、LLM_BASE_URL 指向真实服务即可。

运行：cd backend && python scripts/demo_real.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

import app.modules.rag.solver as solver_mod  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.modules.grading.essay_llm import EssayGraderLLM  # noqa: E402
from app.modules.parsing import HttpEduParser  # noqa: E402
from app.modules.rag.llm import OpenAICompatibleClient  # noqa: E402
from app.schemas import RevealLevel, SolveRequest  # noqa: E402
from app.services.store import STORE  # noqa: E402
from scripts.fake_llm_server import build_mock_transport  # noqa: E402


def h(t):
    print("\n" + "═" * 68 + f"\n  {t}\n" + "═" * 68)


def main():
    print("智考通 · 真实 OCR/LLM 接入（演示用假服务驱动真实客户端，生产改 .env 即接真机）")
    transport = build_mock_transport()
    real_llm = OpenAICompatibleClient(http_client=httpx.Client(transport=transport))
    print(f"LLM 客户端 is_real={real_llm.is_real}  探活={real_llm.health()}")

    h("① 真实 OCR 网关解析（HttpEduParser，超时/重试/降级）")
    settings.ocr_endpoint = "http://fake/ocr/recognize"
    parser = HttpEduParser(http_client=httpx.Client(transport=transport))
    parsed = parser.parse(text="已知函数 f(x)=x²-1，求其零点。")
    print(f"  题干：{parsed.stem}")
    print(f"  类型={parsed.type.value} 置信={parsed.parse_confidence} "
          f"知识点={parsed.concept_ids} LaTeX={parsed.latex_blocks}")

    h("② 自由输入解题（真实 LLM）——苏格拉底门控 + 幻觉校验仍生效")
    solver_mod.LLM = real_llm                 # 注入真实客户端
    solver_mod.MATCH_THRESHOLD = 9.0          # 演示：强制走自由输入（正常命中题库优先）
    STORE.reset()
    for label in ["第1次（即便请求完整）", "第2次", "第3次"]:
        r = solver_mod.SOLVER.solve(SolveRequest(
            user_id="real_stu", stem="解方程 x²-1=0 的所有实数解", reveal_level=RevealLevel.FULL))
        print(f"\n▶ {label} → {r.reveal_level.name}")
        if r.reveal_level == RevealLevel.HINT:
            for i, q in enumerate(r.socratic_questions, 1):
                print(f"    {i}. {q}")
            print(f"  答案：{r.final_answer}（如期为空）")
        elif r.reveal_level == RevealLevel.GUIDED:
            for s in r.guided_steps:
                print(f"    - {s}")
            print(f"  答案：{r.final_answer}（仍为空）")
        else:
            for s in r.chain_of_thought:
                print(f"    - {s}")
            print(f"  ✅ 最终答案：{r.final_answer}")
            print(f"  幻觉校验：通过={r.fact_check.passed} 已核验={r.fact_check.verified_concepts}")
            print(f"  {r.notice}")

    h("③ 作文批改（真实 LLM）——模型评分 + 细则校验 + 校准 + 兜底")
    grader = EssayGraderLLM(real_llm)
    res = grader.grade("围绕'规则与自由'写一篇议论文", "规则与自由相辅相成……（学生作文正文）")
    print(f"  总分：{res.total}/60（评分核心：{res.grader_backend}）")
    for d in res.dimensions:
        print(f"    {d.name} {d.score}/{d.max_score}：{d.sub_scores}")
    print(f"  亮点：{res.strengths}  建议：{res.suggestions}")

    print("\n" + "═" * 68)
    print("  演示结束。生产接入：.env 设 LLM_BACKEND=real / LLM_BASE_URL / OCR_ENDPOINT")
    print("  本地真机联调：python scripts/fake_llm_server.py 起假服务后照常调用。")
    print("═" * 68)


if __name__ == "__main__":
    main()
