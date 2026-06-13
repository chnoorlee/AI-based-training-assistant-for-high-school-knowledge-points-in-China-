"""批改门面：默认确定性 rubric 评分；真实 LLM 可用时热插拔为大模型评分（同 grade 接口）。"""
from __future__ import annotations

from app.modules.grading.essay import GRADER_ESSAY
from app.modules.grading.subjective import GRADER_SUBJECTIVE


def get_essay_grader():
    from app.modules.rag.llm import LLM
    if getattr(LLM, "is_real", False) and hasattr(LLM, "complete_json"):
        from app.modules.grading.essay_llm import EssayGraderLLM
        return EssayGraderLLM(LLM)
    return GRADER_ESSAY


def get_subjective_grader():
    return GRADER_SUBJECTIVE


ESSAY = get_essay_grader()
SUBJECTIVE = get_subjective_grader()
