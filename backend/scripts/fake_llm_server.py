"""契约一致的「假」LLM + OCR 服务器（仅用于本地联调与集成测试）。

作用：在没有真实 API key 的情况下，用与生产**完全相同的 HTTP 契约**驱动真实客户端代码，
验证请求构造、鉴权头、JSON 解析、重试、降级等"生产真正会坏的地方"。

两种用法：
  1) 独立运行：python scripts/fake_llm_server.py  → 起在 :8001，把 .env 指过去即真机联调；
  2) 测试注入：build_mock_transport() 返回 httpx.MockTransport，把它塞进客户端，无需开端口。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.grading.essay import ESSAY_RUBRIC  # noqa: E402
from app.modules.rag.text_utils import HashingEmbedder, tokenize  # noqa: E402

_FAKE_EMB = HashingEmbedder(dim=256)


def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def chat_completion(payload: dict) -> dict:
    """模拟 OpenAI 兼容 /chat/completions。按 prompt 意图返回契约一致的内容。"""
    user = _last_user(payload.get("messages", []))
    json_mode = payload.get("response_format", {}).get("type") == "json_object"

    if json_mode and "作文" in user:  # 作文评分 JSON
        scores = {c.name: 4.2 for crits in ESSAY_RUBRIC.values() for c in crits}
        content = json.dumps({"scores": scores, "strengths": ["立意明确", "结构清晰"],
                              "weaknesses": ["论据可更典型"], "suggestions": ["增加思辨深度"]},
                             ensure_ascii=False)
    elif json_mode:  # 解题完整 JSON（含答案 + 知识点）
        content = json.dumps({
            "steps": ["设方程并移项", "因式分解或求根公式", "求得根并验证"],
            "answer": "x = 1 或 x = -1（示例，由模型给出）",
            "knowledge_points": ["函数的单调性与奇偶性"]}, ensure_ascii=False)
    elif "引导性问题" in user:
        content = ("1. 这道题的已知和所求分别是什么？\n"
                   "2. 它考查哪个知识点？对应的核心公式是哪一个？\n"
                   "3. 你打算先从哪一步入手？")
    elif "不要写出最终答案" in user or "分步" in user:
        content = "明确条件与目标\n选择合适的定理/公式代入\n化简并准备求解（此处暂不给最终答案）"
    else:
        content = "好的，我们一步步来思考这道题。"

    return {"id": "fake-cmpl", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def ocr_recognize(payload: dict) -> dict:
    """模拟 OCR/版面网关。把输入文本回填为题干并给出结构化字段。"""
    text = payload.get("text", "") or "（图片）已知函数 f(x)=x²-1，求其零点。"
    is_choice = any(f"{L}." in text or f"{L}．" in text for L in "ABCD")
    return {"stem": text, "type": "choice" if is_choice else "solution",
            "options": {}, "latex_blocks": ["f(x)=x^{2}-1"],
            "concept_ids": ["MATH_FUNC_PROP"], "difficulty": 0.4,
            "confidence": 0.97, "handwriting_steps": []}


def embeddings_response(payload: dict) -> dict:
    """模拟 OpenAI/TEI 兼容 /embeddings：返回确定性哈希嵌入（保留文本相似性）。"""
    inp = payload.get("input", [])
    if isinstance(inp, str):
        inp = [inp]
    vecs = _FAKE_EMB.embed(inp)
    return {"object": "list", "model": payload.get("model", "fake-bge"),
            "data": [{"object": "embedding", "index": i, "embedding": vecs[i].tolist()}
                     for i in range(len(inp))],
            "usage": {"prompt_tokens": 1, "total_tokens": 1}}


def rerank_response(payload: dict) -> list:
    """模拟 bge-reranker /rerank（TEI 格式）：用与查询的词重叠作相关性分。"""
    query = payload.get("query", "")
    docs = payload.get("texts") or payload.get("documents") or []
    q = set(tokenize(query))
    out = []
    for i, d in enumerate(docs):
        dd = set(tokenize(d))
        score = (len(q & dd) / len(q | dd)) if (q and dd) else 0.0
        out.append({"index": i, "relevance_score": round(score, 4)})
    return out


def build_mock_transport():
    """返回 httpx.MockTransport，按路径分发到上面的假服务（测试用，无需端口）。"""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "fake-model"}]})
        payload = json.loads(request.content or b"{}")
        if path.endswith("/chat/completions"):
            return httpx.Response(200, json=chat_completion(payload))
        if path.endswith("/embeddings"):
            return httpx.Response(200, json=embeddings_response(payload))
        if path.endswith("/rerank"):
            return httpx.Response(200, json=rerank_response(payload))
        if "ocr" in path or path.endswith("/recognize"):
            return httpx.Response(200, json=ocr_recognize(payload))
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def build_app():
    from fastapi import FastAPI, Request
    app = FastAPI(title="智考通 假 LLM/OCR 服务（联调用）")

    @app.get("/v1/models")
    def models():
        return {"data": [{"id": "fake-model"}]}

    @app.post("/v1/chat/completions")
    async def chat(req: Request):
        return chat_completion(await req.json())

    @app.post("/v1/embeddings")
    async def embeddings(req: Request):
        return embeddings_response(await req.json())

    @app.post("/rerank")
    async def rerank(req: Request):
        return rerank_response(await req.json())

    @app.post("/ocr/recognize")
    async def ocr(req: Request):
        return ocr_recognize(await req.json())

    return app


if __name__ == "__main__":
    import uvicorn
    print("假 LLM/OCR 服务启动：http://127.0.0.1:8001  "
          "（设 LLM_BASE_URL=http://127.0.0.1:8001/v1, OCR_ENDPOINT=http://127.0.0.1:8001/ocr/recognize）")
    uvicorn.run(build_app(), host="127.0.0.1", port=8001)
