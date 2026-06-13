"""真实大模型作文批改（生产级）。

把作文 + 评分细则喂给微调教育大模型，要求按二级维度返回 JSON 分数与评语；
随后做**严格校验**：分数按细则上限夹紧、缺失项回退到 rubric 检测器、整体失败兜底到 rubric 评分，
再叠加校准（scale/offset）与内容安全。既享受大模型的语义理解，又有确定性护栏与可解释性。
"""
from __future__ import annotations

from app.modules.grading.essay import ESSAY_RUBRIC, EXEMPLARS, EssayGrader, d_healthy
from app.modules.rag.guards import content_safe
from app.schemas import DimensionScore, EssayGradeResult

_SYS = """你是经验丰富的高考语文阅卷老师，必须严格依据评分细则按二级维度打分，
分数客观、可解释；不拔高、不压分。只输出 JSON，不要多余文字。"""


class EssayGraderLLM:
    def __init__(self, llm, scale: float = 1.0, offset: float = 0.0) -> None:
        self.llm = llm
        self.scale, self.offset = scale, offset
        self.fallback = EssayGrader(scale, offset)
        self.backend = f"llm:{getattr(llm, 'is_real', False) and 'real' or 'mock'}"

    def grade(self, prompt: str, text: str, genre: str = "议论文") -> EssayGradeResult:
        try:
            return self._grade_llm(prompt, text, genre)
        except Exception:
            r = self.fallback.grade(prompt, text, genre)
            r.grader_backend = "rubric-fallback"
            return r

    def _grade_llm(self, prompt: str, text: str, genre: str) -> EssayGradeResult:
        # 列出细则供模型遵循
        rubric_lines = []
        for dim, crits in ESSAY_RUBRIC.items():
            for c in crits:
                rubric_lines.append(f"{dim}/{c.name}（满分{c.max_score}）")
        user = (f"作文题：{prompt}\n文体：{genre}\n学生作文：\n{text}\n\n"
                f"请按以下二级维度各打分（0~满分），并返回 JSON：\n"
                f"细则：{rubric_lines}\n"
                f'格式：{{"scores": {{"二级维度名": 分数, ...}}, '
                f'"strengths": [..], "weaknesses": [..], "suggestions": [..]}}')
        data = self.llm.complete_json(_SYS, user)
        scores = data.get("scores", {}) if isinstance(data, dict) else {}

        safe, _ = content_safe(text)
        dims: list[DimensionScore] = []
        for dim, crits in ESSAY_RUBRIC.items():
            subs: dict[str, float] = {}
            for c in crits:
                raw = scores.get(c.name)
                if isinstance(raw, (int, float)):
                    sc = max(0.0, min(float(c.max_score), float(raw)))  # 按上限夹紧
                else:  # 缺失项回退到 rubric 检测器
                    sc = round(max(0.0, min(1.0, c.detector(text, prompt))) * c.max_score, 1)
                if c.name == "思想健康" and not safe:
                    sc = min(sc, 1.0)  # 内容不安全强制压分
                subs[c.name] = round(sc, 1)
            dims.append(DimensionScore(name=dim, max_score=sum(c.max_score for c in crits),
                                       score=round(sum(subs.values()), 1), sub_scores=subs,
                                       comment=f"{dim}维度由教育大模型评分并经细则校验。"))
        total = max(0.0, min(60.0, round(sum(d.score for d in dims) * self.scale + self.offset, 1)))
        return EssayGradeResult(
            total=total, dimensions=dims,
            strengths=list(data.get("strengths", []))[:6] or ["（见各维度得分）"],
            weaknesses=list(data.get("weaknesses", []))[:6] or ["（见各维度得分）"],
            suggestions=list(data.get("suggestions", []))[:5] or ["对照范文打磨论证与文采"],
            exemplar_ref=EXEMPLARS.get(genre, ""), content_safe=safe,
            grader_backend=self.backend)
