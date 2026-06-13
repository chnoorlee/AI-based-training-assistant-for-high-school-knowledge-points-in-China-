"""自由输入 / 真实 LLM 输出的安全与幻觉护栏。

- content_safe：价值观/超纲/无关 词机审（生产替换为分类模型 + 人审兜底）。
- verify_knowledge_points：把模型自称涉及的知识点对照知识图谱核验，未命中者标"待人工复核"。
真实 LLM 给出的最终答案，仅在内容安全且知识点核验通过时才放行展示。
"""
from __future__ import annotations

from app.data.knowledge_graph import KG

_BANNED = ["政治敏感", "暴力", "赌博", "色情", "自杀", "毒品"]
_OFFTOPIC_HINT = ["与高考无关", "脑筋急转弯"]
# 超纲方法（高中范围外）
_SUPER = ["洛必达", "泰勒展开", "拉格朗日中值", "微积分基本定理", "线性代数", "矩阵特征值"]


def content_safe(text: str) -> tuple[bool, list[str]]:
    issues = [f"敏感词:{w}" for w in _BANNED if w in text]
    issues += [f"疑似无关:{w}" for w in _OFFTOPIC_HINT if w in text]
    issues += [f"超纲方法:{w}" for w in _SUPER if w in text]
    return (len(issues) == 0), issues


def verify_knowledge_points(names: list[str]) -> tuple[list[str], list[str]]:
    """返回 (已核验, 待复核)。名称与图谱知识点名做包含匹配。"""
    kg_names = [KG.name_of(c) for c in KG.all_ids()]
    verified, unverified = [], []
    for n in names:
        n = (n or "").strip()
        if not n:
            continue
        if any(n in kn or kn in n for kn in kg_names):
            verified.append(n)
        else:
            unverified.append(n)
    return verified, unverified
