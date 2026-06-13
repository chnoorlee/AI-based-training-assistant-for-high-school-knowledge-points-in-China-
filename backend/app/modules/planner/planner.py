"""AI 提分规划师：时间预算下的"提分性价比(分/小时)"最优化 + 倒计时/熔断感知的每日编排。

模型：
  - 提分空间 = 高考权重 × (1-掌握度)。
  - 学习曲线：投入 t 分钟后掌握度 m → 1-(1-m)·e^(-k·t)（凹性、边际递减）；
    k=可学性，低层级考点（记忆/理解）提分更快。
  - 性价比 ROI = 初始边际提分速度 = 权重×(1-m)×k（高分值 + 低掌握 + 易提分 → 最该先补）。
  - 贪心分配：每次把一小段时间给"当前边际提分最大且前置已达标"的考点；
    前置薄弱点对其所解锁的高价值考点有"前置增益"加权，确保先打地基。
  - 编排：按倒计时把投入摊到每天，跨学科交替避免疲劳，每天嵌入当日错题复习；
    高考熔断日仅安排复习。
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Optional

from app.core.config import settings
from app.data.exam_blueprint import concept_weight
from app.data.knowledge_graph import KG
from app.schemas import (
    DiagnosisReport, PlanDay, PlanItem, PlanTask, StudyPlan, Subject, utcnow,
)

_ABIDX = {"memory": 0, "understand": 1, "apply": 2, "analyze": 3, "synthesize": 4, "create": 5}
_K0 = 0.02          # 基础学习速率（每分钟）
_THR = 0.5          # 前置达标阈值
_CAP = 0.92         # 掌握度上限（边际递减到此停止）
_BLOCK = 15         # 分配粒度（分钟）


def _rate(ability: str) -> float:
    return _K0 / (1 + _ABIDX.get(ability, 1) * 0.35)


def _tier(ability: str) -> str:
    i = _ABIDX.get(ability, 1)
    return "易" if i <= 1 else ("中" if i <= 2 else "难")


class StudyPlanner:
    # ── 候选考点（含性价比；可叠加模考反馈各科加权）──────────────
    def _candidates(self, report: DiagnosisReport, subject: str,
                    subject_weights: Optional[dict] = None):
        sw_map = subject_weights or {}
        out = []
        for cm in report.concept_mastery:
            if subject and KG.subject_of(cm.concept_id) != subject:
                continue
            c = KG.get(cm.concept_id)
            if c is None:
                continue
            w = concept_weight(cm.concept_id)
            sw = sw_map.get(c.subject.value, 1.0)
            k = _rate(c.ability.value)
            out.append({
                "id": cm.concept_id, "name": cm.concept_name, "subject": c.subject.value,
                "m0": cm.score, "w": w, "sw": sw, "we": w * sw, "k": k,
                "ability": c.ability.value,
                "roi": round(w * sw * (1 - cm.score) * k * 60, 2),  # 分/小时（含模考加权）
            })
        return out

    # ── 贪心分配 ────────────────────────────────────────────
    def _allocate(self, cands: list[dict], total_minutes: int):
        idx = {c["id"]: c for c in cands}
        state = {c["id"]: c["m0"] for c in cands}
        mins = {c["id"]: 0 for c in cands}
        # 前置（仅限可分配集合内）、后继（被某点门控）
        prereq = {c["id"]: [p for p in KG.prerequisites_of(c["id"]) if p in idx] for c in cands}
        succ = {c["id"]: [] for c in cands}
        for cid, ps in prereq.items():
            for p in ps:
                succ[p].append(cid)

        def unlocked(cid):
            return all(state[p] >= _THR for p in prereq[cid])

        def marginal(cid):
            c = idx[cid]
            own = c["we"] * (1 - state[cid]) * c["k"]  # we=权重×模考加权
            boost = 0.0
            if state[cid] < _THR:  # 还在打地基 → 计入其解锁的高价值后继
                boost = 0.3 * sum(idx[s]["we"] * (1 - state[s]) * idx[s]["k"] for s in succ[cid])
            return own + boost

        remaining = total_minutes
        while remaining > 0:
            cand = [c["id"] for c in cands if state[c["id"]] < _CAP and unlocked(c["id"])]
            if not cand:
                break
            best = max(cand, key=marginal)
            t = min(_BLOCK, remaining)
            m = state[best]
            state[best] = 1 - (1 - m) * math.exp(-idx[best]["k"] * t)
            mins[best] += t
            remaining -= t
        return mins, state

    # ── 主入口 ─────────────────────────────────────────────
    def plan(self, report: DiagnosisReport, daily_minutes: int = 120,
             days_left: Optional[int] = None, subject: str = "", review_due: int = 0,
             preview_days: int = 7, now: Optional[datetime] = None,
             subject_weights: Optional[dict] = None, projection=None,
             timed_drills: Optional[list] = None) -> StudyPlan:
        now = now or settings.now()
        if days_left is None:
            days_left = max(1, (settings.gaokao_blackout_start - now.date()).days)
        days_left = max(1, min(days_left, 200))

        # 每日预留错题复习时间，其余用于攻坚
        rev_per_day = min(int(daily_minutes * 0.4), (review_due or 0) * 5) or int(daily_minutes * 0.15)
        new_per_day = max(20, daily_minutes - rev_per_day)
        total_new = days_left * new_per_day

        cands = self._candidates(report, subject, subject_weights)
        mins, state = self._allocate(cands, total_new)

        # 组装性价比清单
        items: list[PlanItem] = []
        for c in cands:
            gain = round(c["w"] * (state[c["id"]] - c["m0"]), 2)
            items.append(PlanItem(
                concept_id=c["id"], concept_name=c["name"], subject=Subject(c["subject"]),
                mastery=round(c["m0"], 3), exam_weight=c["w"],
                potential_points=round(c["w"] * (1 - c["m0"]), 2), learnability=_tier(c["ability"]),
                roi=c["roi"], allocated_minutes=mins[c["id"]], expected_gain=gain,
                reason=self._reason(c, mins[c["id"]], gain)))
        items.sort(key=lambda i: (-i.expected_gain, -i.roi))
        total_gain = round(sum(i.expected_gain for i in items), 1)
        total_alloc = sum(mins.values())

        days, woven_drills = self._schedule(items, days_left, new_per_day, rev_per_day,
                                            review_due, preview_days, now, timed_drills or [])

        proj_now = projection.total_predicted if projection else 0.0
        proj_full = projection.total_full if projection else 0.0
        score_line = ""
        if projection:
            score_line = (f"当前预计{int(proj_now)}/{int(proj_full)}分"
                          f"{'（已经真实模考校准）' if projection.calibrated else '（待模考校准）'}，")
        proj = (f"{score_line}按此计划投入 ~{total_alloc // 60} 小时，预计再提升约 {total_gain:.0f} 分"
                f"（模型估计，非承诺；坚持执行 + 错题复习是关键）。")

        boosted = [s for s, m in (subject_weights or {}).items() if m > 1.1]
        from app.data.exam_blueprint import EXAM_BLUEPRINT  # noqa: F401 (仅取中文名映射用)
        sub_cn = {"math": "数学", "physics": "物理", "chemistry": "化学", "biology": "生物"}
        fb_note = ("模考反馈：已上调 " + "、".join(sub_cn.get(s, s) for s in boosted)
                   + " 的优先级（弱科/应试丢分/退步）。") if boosted else ""

        return StudyPlan(
            user_id=report.user_id, subject=subject, days_left=days_left,
            daily_minutes=daily_minutes, total_study_minutes=total_alloc,
            expected_score_gain=total_gain, projected_note=proj,
            projected_score_now=round(proj_now, 1), projected_full=round(proj_full, 1),
            mock_calibrated=bool(projection and projection.calibrated), feedback_note=fb_note,
            priorities=[i for i in items if i.allocated_minutes > 0][:12], days=days,
            timed_drills=woven_drills)  # 仅列实际排进计划的限时训练（与每日首项一致）

    def _reason(self, c: dict, minutes: int, gain: float) -> str:
        if minutes == 0:
            return f"高考约{c['w']}分，当前掌握{c['m0']:.0%}，性价比一般，时间紧时可后置。"
        return (f"高考约 {c['w']} 分，当前仅掌握 {c['m0']:.0%}，属「{_tier(c['ability'])}」提分点，"
                f"投入 {minutes} 分钟预计提分 {gain:.1f} 分（性价比 {c['roi']:.1f} 分/小时）。")

    def _schedule(self, items, days_left, new_per_day, rev_per_day, review_due,
                  preview_days, now, drills=None) -> list[PlanDay]:
        drills = list(drills or [])
        # 轮转切块：每考点每轮出 ~30min，跨天分散（交错练习优于集中练）
        pools = [{"id": it.concept_id, "name": it.concept_name, "subject": it.subject.value,
                  "left": it.allocated_minutes} for it in items if it.allocated_minutes > 0]
        chunks = []
        while any(p["left"] > 0 for p in pools):
            for p in pools:
                if p["left"] > 0:
                    t = min(30, p["left"])
                    chunks.append({"id": p["id"], "name": p["name"],
                                   "subject": p["subject"], "min": t})
                    p["left"] -= t
        ci = 0
        di = 0  # 限时训练索引（每天首个任务织入一项，按可挽回分排序）
        woven: list = []  # 实际排进计划的限时训练（用作 plan.timed_drills，确保展示=已排程）
        days: list[PlanDay] = []
        for d in range(min(days_left, preview_days)):
            day_date = (now + timedelta(days=d)).date()
            blackout = settings.gaokao_blackout_start <= day_date <= settings.gaokao_blackout_end
            tasks: list[PlanTask] = []
            if blackout:
                rev_min = 40
                tasks.append(PlanTask(kind="review", minutes=rev_min,
                                      n_problems=max(review_due, 8),
                                      detail="高考熔断期：仅错题本 + 知识点复习，调整心态"))
                days.append(PlanDay(day_index=d, date=day_date.isoformat(), is_blackout=True,
                                    total_minutes=rev_min, tasks=tasks,
                                    note="🔒 高考熔断日：保留错题本/复习，不刷新题"))
                continue
            # 题型级限时训练：每天首个任务织入一项（直击模考暴露的应试丢分）
            used, last_sub = 0, None
            if di < len(drills):
                dr = drills[di]
                di += 1
                woven.append(dr)
                tasks.append(PlanTask(
                    kind="timed_drill", subject=dr.subject, concept_name=dr.title,
                    minutes=dr.time_limit_min, n_problems=dr.n_problems,
                    detail=f"⏱ {dr.title}：{dr.goal}（{dr.n_problems}题/{dr.time_limit_min}min，"
                           f"针对{dr.cause}，预计挽回 {dr.recoverable_points} 分）"))
                used += dr.time_limit_min
                last_sub = dr.subject  # 避免随后第一个攻坚任务与限时训练同科，保持跨科交替
            # 攻坚任务：跨学科交替填满 new_per_day
            while ci < len(chunks) and used + 15 <= new_per_day:
                pick = ci
                for j in range(ci, min(ci + 5, len(chunks))):  # 尽量换学科
                    if chunks[j]["subject"] != last_sub:
                        pick = j
                        break
                ch = chunks.pop(pick)
                tasks.append(PlanTask(kind="learn", concept_id=ch["id"], concept_name=ch["name"],
                                      subject=ch["subject"], minutes=ch["min"],
                                      n_problems=max(1, ch["min"] // 12),
                                      detail=f"攻坚「{ch['name']}」，配套 {max(1, ch['min']//12)} 道变式题"))
                used += ch["min"]
                last_sub = ch["subject"]
            tasks.append(PlanTask(kind="review", minutes=rev_per_day, n_problems=max(review_due, 5),
                                  detail="错题本复习（SM-2 到期题，巩固防遗忘）"))
            days.append(PlanDay(day_index=d, date=day_date.isoformat(),
                                total_minutes=used + rev_per_day, tasks=tasks,
                                note="攻坚 + 错题复习"))
        return days, woven


PLANNER = StudyPlanner()
