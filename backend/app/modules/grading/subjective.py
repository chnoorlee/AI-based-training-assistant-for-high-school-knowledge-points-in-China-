"""文综/理综主观题批改（PRD 5.2）：采分点语义匹配按点给分 + 逻辑结构评价。

采分点匹配 = 关键词覆盖 + 文本语义相似度（复用变式题质检的 trigram 相似度，
生产替换为 bge 语义匹配）。逻辑评价基于条理性（连接词）、覆盖度与组织度。
"""
from __future__ import annotations

import re

from app.modules.variant.quality import text_similarity
from app.schemas import ScoringPoint, SubjectiveGradeResult

_CONN = ["首先", "其次", "再次", "然后", "因此", "所以", "综上", "另外", "同时",
         "一方面", "另一方面", "由于", "导致", "从而", "其一", "其二", "①", "②", "③"]


def _sentences(t: str) -> list[str]:
    return [s for s in re.split(r"[。；;\n①②③④⑤、]", t or "") if s.strip()]


def _award(point: dict, answer: str, sentences: list[str]) -> ScoringPoint:
    desc = point.get("description", "")
    kws = point.get("keywords", [])
    pts = float(point.get("points", 0))

    coverage = (sum(1 for k in kws if k in answer) / len(kws)) if kws else 0.0
    sims = [text_similarity(s, desc) for s in sentences] or [0.0]
    sim = max(sims)
    best = sentences[int(max(range(len(sims)), key=lambda i: sims[i]))] if sentences else ""

    if coverage >= 0.6 or sim >= 0.30:
        frac = 1.0
    elif coverage >= 0.3 or sim >= 0.18:
        frac = 0.5
    else:
        frac = 0.0
    awarded = round(pts * frac, 1)
    return ScoringPoint(
        id=point.get("id", desc[:8]), description=desc, points=pts, keywords=kws,
        hit=awarded > 0, similarity=round(sim, 3), awarded=awarded,
        matched_text=(best[:40] if awarded > 0 else ""))


class SubjectiveGrader:
    backend = "semantic-mock"

    def grade(self, question: str, answer: str,
              reference_points: list[dict]) -> SubjectiveGradeResult:
        sentences = _sentences(answer)
        scored = [_award(p, answer, sentences) for p in reference_points]
        total = round(sum(p.awarded for p in scored), 1)
        full = round(sum(float(p.get("points", 0)) for p in reference_points), 1)

        # 逻辑/组织评价（满分 5）
        conn = sum(answer.count(c) for c in _CONN)
        covered = sum(1 for p in scored if p.hit)
        organize = min(1.0, conn / 3)
        coverage_ratio = covered / len(scored) if scored else 0.0
        logic = round(5 * (0.5 * organize + 0.5 * coverage_ratio), 1)
        if conn >= 3 and coverage_ratio >= 0.6:
            logic_comment = "答题分点清晰、条理分明，论证较完整。"
        elif coverage_ratio < 0.5:
            logic_comment = "要点覆盖不足，存在采分点遗漏，建议分点作答、逐点回应设问。"
        else:
            logic_comment = "要点基本覆盖，但条理性不足，建议使用'首先/其次/因此'等增强逻辑。"

        missed = [p.description for p in scored if not p.hit]
        suggestions = []
        if missed:
            suggestions.append("遗漏采分点：" + "；".join(missed[:4]))
        if conn < 2:
            suggestions.append("分点作答（①②③），并用连接词体现论证逻辑。")
        suggestions = suggestions or ["要点齐全、逻辑清晰，继续保持。"]

        return SubjectiveGradeResult(
            total=total, full_marks=full, points=scored, logic_score=logic,
            logic_comment=logic_comment, suggestions=suggestions, grader_backend=self.backend)


GRADER_SUBJECTIVE = SubjectiveGrader()
