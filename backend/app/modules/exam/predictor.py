"""模考估分：用诊断的模块掌握度 × 高考分值蓝图 估计各科/总分。

预测分 = Σ(模块分值 × 模块掌握度) × 应试折扣；可叠加由真实模考拟合的校准偏置。
"""
from __future__ import annotations

from typing import Optional

from app.data.exam_blueprint import EXAM_BLUEPRINT, subject_total
from app.data.knowledge_graph import KG
from app.schemas import DiagnosisReport, ScorePrediction, SubjectScore

_BASE_EXEC = 0.90  # 应试折扣：即便掌握满，真实考试也会因难度/粗心损失少量


def _module_mastery(report: DiagnosisReport, subject: str) -> dict[str, float]:
    by_mod: dict[str, list[float]] = {}
    for cm in report.concept_mastery:
        if KG.subject_of(cm.concept_id) != subject:
            continue
        by_mod.setdefault(KG.module_of(cm.concept_id), []).append(cm.score)
    return {m: sum(v) / len(v) for m, v in by_mod.items()}


class ScorePredictor:
    def predict_subject_raw(self, report: DiagnosisReport, subject: str) -> tuple[float, float]:
        mm = _module_mastery(report, subject)
        raw = sum(pts * mm.get(mod, 0.5) for mod, pts in EXAM_BLUEPRINT.get(subject, {}).items())
        return round(raw * _BASE_EXEC, 1), subject_total(subject)

    def subjects_in(self, report: DiagnosisReport) -> list[str]:
        present = {KG.subject_of(cm.concept_id) for cm in report.concept_mastery}
        return [s for s in EXAM_BLUEPRINT if s in present]

    def predict(self, report: DiagnosisReport, calibration: Optional[dict] = None,
                actuals: Optional[dict] = None, multipliers: Optional[dict] = None,
                gaps: Optional[dict] = None) -> ScorePrediction:
        calibration = calibration or {}
        subs: list[SubjectScore] = []
        n_mocks = max((c.get("n", 0) for c in calibration.values()), default=0)
        for subject in self.subjects_in(report):
            raw, full = self.predict_subject_raw(report, subject)
            off = calibration.get(subject, {}).get("offset", 0.0)
            pred = round(max(0.0, min(full, raw + off)), 1)
            subs.append(SubjectScore(
                subject=subject, full_marks=full, raw_predicted=raw, predicted=pred,
                actual=(actuals or {}).get(subject),
                execution_gap=round((gaps or {}).get(subject, 0.0), 1),
                priority_multiplier=round((multipliers or {}).get(subject, 1.0), 2)))
        total = round(sum(s.predicted for s in subs), 1)
        total_full = round(sum(s.full_marks for s in subs), 1)
        band = round(total_full * 0.06 / (1 + 0.3 * n_mocks), 1)
        return ScorePrediction(
            user_id=report.user_id, subjects=subs, total_predicted=total, total_full=total_full,
            band=band, calibrated=n_mocks > 0, n_mocks=n_mocks,
            note=(f"已用 {n_mocks} 次真实模考校准预测。" if n_mocks else
                  "尚无真实模考，预测仅基于认知诊断；录入模考成绩后将自动校准。"))


PREDICTOR = ScorePredictor()
