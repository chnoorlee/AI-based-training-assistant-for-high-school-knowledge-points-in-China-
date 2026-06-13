"""教育大模型接口层（PRD 2.2）—— 生产级。

- 系统提示词内置「苏格拉底式启发 + 绝不直接给答案 + 不超纲 + 不编造」对齐约束。
- MockSolverLLM：零依赖确定性实现，离线可跑；不杜撰自由输入题的最终答案。
- OpenAICompatibleClient：对接 vLLM / DeepSeek-R1 / Qwen2（OpenAI 兼容端点）。
  生产健壮性：超时、指数退避重试、JSON 结构化输出、LRU 缓存、启动探活并自动降级到 Mock。
  可注入 httpx.Client（便于用 MockTransport 在真实 HTTP 协议层做契约测试）。

切换由 settings.llm_backend 决定（mock | real）；real 不可达时自动回退 Mock，保证可用性。
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import OrderedDict
from typing import Optional, Protocol

from app.core.config import settings

SOCRATIC_SYSTEM_PROMPT = """你是「智考通」高考数学辅导助手，必须严格遵守：
1) 启发优先：学生提问时，先提出 3 个由浅入深的引导性问题，引导其自己发现思路，绝不直接给最终答案。
2) 思维链透明：讲解必须展示完整推理步骤（思维链），让学生看懂"为什么"，而非只给结论。
3) 不超纲、不偏离：只讲高中新课标范围内的数学知识，不引入超纲方法。
4) 不编造：不确定或题干信息不足时，明确说明，不臆造条件或答案。
5) 价值观正确：内容积极正向，符合主流价值观。
输出用简洁中文，公式可用常见数学符号。"""

SOLUTION_SYSTEM_PROMPT = """你是「智考通」高考数学辅导助手。现在学生已经过引导并主动请求完整解答，
请给出严谨、分步的完整解题过程（思维链）与最终答案。要求：步骤清晰、推理正确、不超纲、不编造；
若题干信息不足以求解，请说明缺什么而不要臆造答案。"""


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    is_real: bool

    def socratic_questions(self, stem: str, concept_names: list[str],
                           context: list[str]) -> list[str]: ...

    def guided_steps(self, stem: str, concept_names: list[str],
                     context: list[str]) -> list[str]: ...

    def full_solution(self, stem: str, concept_names: list[str],
                      context: list[str]) -> dict: ...


# ──────────────────────────────────────────────────────────────
# Mock（离线确定性）
# ──────────────────────────────────────────────────────────────
class MockSolverLLM:
    is_real = False

    def socratic_questions(self, stem, concept_names, context):
        topic = concept_names[0] if concept_names else "本题"
        return [
            f"先读题：这道题给了哪些已知条件，要求的目标是什么？它主要考查「{topic}」，你能定位到对应的知识点吗？",
            f"回忆一下，「{topic}」有哪些核心公式或定理？哪一个最可能用得上？",
            "如果把求解过程拆成 2–3 步，你打算第一步先做什么？先动笔写写看。",
        ]

    def guided_steps(self, stem, concept_names, context):
        topic = concept_names[0] if concept_names else "该知识点"
        return [
            f"第一步：明确「{topic}」的适用条件，把题目信息对应到公式的各个量。",
            "第二步：按公式/定理代入并化简，注意符号与定义域（这是最常见的失分点）。",
            "第三步：回代检验，确认结果是否符合题意与取值范围。",
        ]

    def full_solution(self, stem, concept_names, context):
        # Mock 不杜撰自由输入题的最终答案
        return {"steps": self.guided_steps(stem, concept_names, context),
                "answer": None, "knowledge_points": concept_names}


# ──────────────────────────────────────────────────────────────
# 生产：OpenAI 兼容客户端
# ──────────────────────────────────────────────────────────────
class OpenAICompatibleClient:
    is_real = True

    def __init__(self, http_client=None) -> None:
        import httpx
        self._httpx = httpx
        self.base = settings.llm_base_url.rstrip("/")
        self.url = self.base + "/chat/completions"
        self.client = http_client or httpx.Client(timeout=settings.llm_timeout_s)
        self._cache: "OrderedDict[str, str]" = OrderedDict()

    # ── 底层：带重试/缓存的对话 ─────────────────────────────
    def _chat(self, messages: list[dict], json_mode: bool = False,
              max_tokens: int = 800) -> str:
        key = hashlib.md5(
            json.dumps([settings.llm_model, messages, json_mode], ensure_ascii=False)
            .encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        payload = {"model": settings.llm_model, "temperature": settings.llm_temperature,
                   "messages": messages, "max_tokens": max_tokens}
        if json_mode and settings.llm_json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

        last_err: Optional[Exception] = None
        for attempt in range(settings.llm_max_retries + 1):
            try:
                resp = self.client.post(self.url, headers=headers, json=payload,
                                        timeout=settings.llm_timeout_s)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                self._cache[key] = content
                if len(self._cache) > settings.llm_cache_size:
                    self._cache.popitem(last=False)
                return content
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < settings.llm_max_retries:
                    time.sleep(0.2 * (2 ** attempt))  # 指数退避
        raise LLMError(f"LLM 调用失败（重试 {settings.llm_max_retries} 次）：{last_err!r}")

    def complete_text(self, system: str, user: str, max_tokens: int = 800) -> str:
        return self._chat([{"role": "system", "content": system},
                           {"role": "user", "content": user}], max_tokens=max_tokens)

    def complete_json(self, system: str, user: str, max_tokens: int = 1000) -> dict:
        raw = self._chat([{"role": "system", "content": system},
                          {"role": "user", "content": user}], json_mode=True,
                         max_tokens=max_tokens)
        return _extract_json(raw)

    # ── 探活 ───────────────────────────────────────────────
    def health(self) -> bool:
        try:
            r = self.client.get(self.base + "/models", timeout=5.0,
                                headers={"Authorization": f"Bearer {settings.llm_api_key}"})
            return r.status_code < 500
        except Exception:
            try:  # 退化为一次极小对话探活
                self._chat([{"role": "user", "content": "ping"}], max_tokens=1)
                return True
            except Exception:
                return False

    # ── 高层能力（失败即优雅降级到 Mock，保证服务不中断）──────────
    def socratic_questions(self, stem, concept_names, context):
        try:
            ctx = "\n".join(context[:3])
            out = self.complete_text(SOCRATIC_SYSTEM_PROMPT,
                                     f"题目：{stem}\n相关知识点：{concept_names}\n参考资料：{ctx}\n"
                                     f"请只输出 3 个由浅入深的引导性问题，每行一个，不要给答案。")
            qs = [re.sub(r"^[\s\-·•0-9.、)]+", "", ln).strip()
                  for ln in out.splitlines() if ln.strip()]
            return qs[:3] or MockSolverLLM().socratic_questions(stem, concept_names, context)
        except Exception:
            return MockSolverLLM().socratic_questions(stem, concept_names, context)

    def guided_steps(self, stem, concept_names, context):
        try:
            ctx = "\n".join(context[:3])
            out = self.complete_text(SOCRATIC_SYSTEM_PROMPT,
                                     f"题目：{stem}\n相关知识点：{concept_names}\n参考资料：{ctx}\n"
                                     f"请给出分步解题思路（思维链），但**不要写出最终答案数值**，每行一步。")
            steps = [re.sub(r"^[\s\-·•、)]+", "", ln).strip()
                     for ln in out.splitlines() if ln.strip()]
            return steps or MockSolverLLM().guided_steps(stem, concept_names, context)
        except Exception:
            return MockSolverLLM().guided_steps(stem, concept_names, context)

    def full_solution(self, stem, concept_names, context):
        ctx = "\n".join(context[:3])
        try:
            data = self.complete_json(
                SOLUTION_SYSTEM_PROMPT,
                f"题目：{stem}\n相关知识点：{concept_names}\n参考资料：{ctx}\n"
                f"请返回 JSON：{{\"steps\": [完整分步思维链], \"answer\": \"最终答案\", "
                f"\"knowledge_points\": [涉及的高中知识点]}}。若信息不足，answer 填 \"信息不足\"。")
            steps = [str(s) for s in data.get("steps", []) if str(s).strip()]
            ans = data.get("answer")
            kps = [str(k) for k in data.get("knowledge_points", [])] or concept_names
            return {"steps": steps or [str(data)], "answer": ans, "knowledge_points": kps}
        except Exception:  # 降级：落到不依赖网络的 Mock，绝不杜撰答案
            steps = MockSolverLLM().guided_steps(stem, concept_names, context)
            return {"steps": steps, "answer": None, "knowledge_points": concept_names}


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise LLMError("无法从模型输出解析 JSON")


def get_llm(http_client=None) -> LLMClient:
    if settings.llm_backend == "real":
        try:
            client = OpenAICompatibleClient(http_client=http_client)
            if (not settings.llm_health_check) or client.health():
                return client
        except Exception:
            pass
    return MockSolverLLM()


LLM: LLMClient = get_llm()
