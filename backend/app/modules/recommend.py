"""④ 自适应习题推荐（PRD 4.1）。

三大原则全部落地：
  - 最近发展区（ZPD）：优先推送预测答对概率落在 0.6~0.8 的题（跳一跳够得着）。
  - 配比 70/20/10：薄弱强化 / 巩固复习 / 拓展提高。
  - 遗忘曲线：对已掌握知识点按 Ebbinghaus 保持率 R=exp(-Δt/S) 判定是否到期复习。
预测答对概率复用 NeuralCD（与诊断同源，保证一致性）。每完成 5 题应触发一次重算。
"""
from __future__ import annotations

import math

import numpy as np

from app.data.knowledge_graph import KG
from app.data.problem_bank import BANK
from app.modules.diagnosis.engine import ENGINE
from app.schemas import (
    DiagnosisReport,
    RecommendItem,
    RecommendList,
    RecommendReason,
    ResponseRecord,
    utcnow,
)

ZPD_LOW, ZPD_HIGH, ZPD_TARGET = 0.60, 0.80, 0.70
MIX = {RecommendReason.WEAKNESS: 0.70, RecommendReason.CONSOLIDATE: 0.20,
       RecommendReason.STRETCH: 0.10}


def _retention(mastery: float, days: float) -> float:
    """Ebbinghaus 保持率：掌握越牢，记忆稳定度 S 越大，遗忘越慢。"""
    S = 1.0 + 9.0 * mastery
    return math.exp(-days / S)


class Recommender:
    def _mastery_vector(self, report: DiagnosisReport) -> np.ndarray:
        score = {cm.concept_id: cm.score for cm in report.concept_mastery}
        return np.array([score.get(c, 0.5) for c in BANK.concept_ids])

    def recommend(self, user_id: str, report: DiagnosisReport,
                  responses: list[ResponseRecord], n: int = 10,
                  subject: str = "") -> RecommendList:
        mastery = self._mastery_vector(report)
        cscore = {cm.concept_id: cm.score for cm in report.concept_mastery}
        # 学科范围：显式指定 > 学生已作答学科 > 全部
        if subject:
            subjects = {subject}
        elif responses:
            subjects = {BANK.get(r.problem_id).subject.value
                        for r in responses if BANK.get(r.problem_id)}
        else:
            subjects = None

        # 各知识点最近一次「答对」时间（用于遗忘曲线）
        last_correct: dict[str, datetime] = {}
        for r in responses:
            if r.correct:
                for c in (r.concept_ids or []):
                    last_correct[c] = max(last_correct.get(c, r.ts), r.ts)
        recent = {r.problem_id for r in responses[-3:]}  # 避免立刻重复刚做过的题
        now = utcnow()

        pools: dict[RecommendReason, list[RecommendItem]] = {
            RecommendReason.WEAKNESS: [], RecommendReason.CONSOLIDATE: [],
            RecommendReason.STRETCH: []}

        for p in BANK.all():
            if p.id in recent:
                continue
            if subjects is not None and p.subject.value not in subjects:
                continue  # 按学科范围过滤
            i = BANK.problem_index[p.id]
            prob = ENGINE.ncd.predict_prob_for_mastery(mastery, i)
            cs = [cscore.get(c, 0.5) for c in p.concept_ids]
            min_c = min(cs) if cs else 0.5

            if min_c < 0.60:
                reason = RecommendReason.WEAKNESS
                key = min_c  # 越弱越优先
                rationale = (f"针对薄弱点「{KG.name_of(p.concept_ids[0])}」"
                             f"（掌握度 {min_c:.0%}），预计答对率 {prob:.0%}。")
            elif min_c >= 0.80:
                reason = RecommendReason.STRETCH
                key = abs(prob - ZPD_TARGET)
                rationale = f"该模块已较熟练，推送提高题拓展能力，预计答对率 {prob:.0%}。"
            else:
                reason = RecommendReason.CONSOLIDATE
                # 遗忘曲线：距上次答对的天数 → 保持率，越低越该复习
                _gaps = [(now - last_correct[c]).total_seconds() / 86400
                         for c in p.concept_ids if c in last_correct]
                days = max(_gaps) if _gaps else 0.0
                R = _retention(min_c, days)
                key = R  # 保持率越低越优先
                rationale = (f"巩固「{KG.name_of(p.concept_ids[0])}」，"
                             f"记忆保持率约 {R:.0%}，预计答对率 {prob:.0%}。")

            in_zpd = ZPD_LOW <= prob <= ZPD_HIGH
            pools[reason].append((key, in_zpd, RecommendItem(
                problem_id=p.id, concept_ids=p.concept_ids, difficulty=p.difficulty,
                reason=reason, predicted_correct_prob=round(prob, 4), rationale=rationale)))

        # 各池排序：ZPD 内优先，再按 key 升序
        for reason, lst in pools.items():
            lst.sort(key=lambda t: (not t[1], t[0]))

        # 配比 70/20/10，短缺则向薄弱倾斜补足
        quota = {r: round(MIX[r] * n) for r in MIX}
        quota[RecommendReason.WEAKNESS] = n - quota[RecommendReason.CONSOLIDATE] \
            - quota[RecommendReason.STRETCH]
        order = [RecommendReason.WEAKNESS, RecommendReason.CONSOLIDATE, RecommendReason.STRETCH]
        chosen: list[RecommendItem] = []
        used: set[str] = set()
        for r in order:
            for _, _, item in pools[r][:quota[r]]:
                if item.problem_id not in used:
                    chosen.append(item)
                    used.add(item.problem_id)
        # 补足到 n（从所有池剩余里按优先级）
        if len(chosen) < n:
            leftover = sorted(
                [t for r in order for t in pools[r] if t[2].problem_id not in used],
                key=lambda t: (not t[1], t[0]))
            for _, _, item in leftover:
                if len(chosen) >= n:
                    break
                if item.problem_id not in used:
                    chosen.append(item)
                    used.add(item.problem_id)

        mix_count: dict[str, int] = {}
        for item in chosen:
            mix_count[item.reason.value] = mix_count.get(item.reason.value, 0) + 1
        return RecommendList(user_id=user_id, items=chosen[:n], mix=mix_count)


RECOMMENDER = Recommender()
