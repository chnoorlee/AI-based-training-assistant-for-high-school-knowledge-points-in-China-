"""真实模考记录与校准。

提交真实模考分时，同时快照模型当时的"原始预测"，据此拟合每科校准偏置（纠正系统性高/低估），
并计算趋势（近几次模考的分数斜率）。内存实现（STORE.mock_exams），接口不变可换 DB。
"""
from __future__ import annotations

from typing import Optional

from app.data.exam_blueprint import subject_total
from app.schemas import MockHistory, MockRecord, utcnow
from app.services.store import STORE


class MockExamBook:
    def __init__(self, store=None) -> None:
        self.store = store or STORE

    def submit(self, user_id: str, exam_name: str, scores: dict[str, float],
               predictor, report, full_marks: Optional[dict] = None,
               section_scores: Optional[dict] = None) -> MockRecord:
        predicted_raw = {s: predictor.predict_subject_raw(report, s)[0] for s in scores}
        rec = {"exam_name": exam_name, "date": utcnow().date().isoformat(),
               "scores": {k: float(v) for k, v in scores.items()},
               "predicted_raw": predicted_raw,
               "sections": {s: {k: float(v) for k, v in d.items()}
                            for s, d in (section_scores or {}).items()}}
        self.store.mock_exams[user_id].append(rec)
        return MockRecord(**rec)

    def latest_sections(self, user_id: str) -> dict[str, dict[str, float]]:
        """最近一次含分题型得分的记录 → {subject: {section_id: 得分}}（按科取最近）。"""
        out: dict[str, dict[str, float]] = {}
        for rec in self.records(user_id):
            for subj, secs in rec.get("sections", {}).items():
                if secs:
                    out[subj] = secs
        return out

    def records(self, user_id: str) -> list[dict]:
        return list(self.store.mock_exams.get(user_id, []))

    def latest_actuals(self, user_id: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for rec in self.records(user_id):  # 后写覆盖 → 取最近
            out.update(rec["scores"])
        return out

    # ── 校准：每科偏置 offset（收缩，少样本更稳）──────────────
    def calibration(self, user_id: str) -> dict[str, dict]:
        pairs: dict[str, list[tuple[float, float]]] = {}
        for rec in self.records(user_id):
            for s, actual in rec["scores"].items():
                raw = rec["predicted_raw"].get(s)
                if raw is not None:
                    pairs.setdefault(s, []).append((raw, actual))
        cal: dict[str, dict] = {}
        for s, ps in pairs.items():
            n = len(ps)
            offset = sum(a - r for r, a in ps) / (n + 1)  # 向 0 收缩，防少样本过拟合
            mae = sum(abs(a - (r + offset)) for r, a in ps) / n
            cal[s] = {"offset": round(offset, 2), "n": n, "mae": round(mae, 2)}
        return cal

    def trend(self, user_id: str) -> dict[str, float]:
        seq: dict[str, list[float]] = {}
        for rec in self.records(user_id):
            for s, v in rec["scores"].items():
                seq.setdefault(s, []).append(float(v))
        return {s: round((v[-1] - v[0]) / (len(v) - 1), 2) for s, v in seq.items() if len(v) >= 2}

    def history(self, user_id: str) -> MockHistory:
        return MockHistory(user_id=user_id,
                           records=[MockRecord(**r) for r in self.records(user_id)],
                           trend=self.trend(user_id), calibration=self.calibration(user_id))


MOCK_BOOK = MockExamBook()
