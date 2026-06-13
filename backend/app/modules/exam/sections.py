"""题型级丢分归因 + 限时训练推荐。

把"应试丢分"下钻到卷面区块：按掌握度估各区块应得分 → 与真实得分比 → 定位丢在哪类题、什么原因
→ 开出针对性的限时训练（选择题限时秒杀、压轴最后一问抢分等），并按可挽回分排序。
"""
from __future__ import annotations

from app.data.exam_paper import sections_of
from app.schemas import ExecutionReport, SectionScore, SubjectExecution, TimedDrill

SUB_CN = {"math": "数学", "physics": "物理", "chemistry": "化学", "biology": "生物"}


def attain(tier: str, sm: float) -> float:
    """按难度档，给定学科掌握度 sm，估计该档"应得占比"。"""
    return {
        "易": min(1.0, 0.45 + 0.6 * sm),  # 易题高地板：弱生也该拿大部分
        "中": sm,
        "难": max(0.0, sm * 0.85),
        "压轴": max(0.0, sm * 0.55),       # 压轴即便强生也只拿约一半
    }.get(tier, sm)


def analyze(subject: str, section_got: dict[str, float], sm: float) -> list[SectionScore]:
    out: list[SectionScore] = []
    for sec in sections_of(subject):
        got = section_got.get(sec.id)
        if got is not None:  # 防脏数据：得分夹紧到 [0, 满分]，避免误录入扭曲归因
            got = round(min(max(float(got), 0.0), sec.points), 1)
        expected = round(sec.points * attain(sec.tier, sm), 1)
        loss = round(max(0.0, expected - got), 1) if got is not None else 0.0
        out.append(SectionScore(section_id=sec.id, name=sec.name, qtype=sec.qtype, tier=sec.tier,
                                full=sec.points, got=got, expected=expected, loss=loss,
                                cause=sec.cause))
    return out


def _drill(subject: str, ss: SectionScore) -> TimedDrill:
    cn = SUB_CN.get(subject, subject)
    # 难度档决定可挽回比例：易/中几乎都能补回，压轴只能抢部分
    recov = ss.loss * {"易": 1.0, "中": 0.9, "难": 0.6, "压轴": 0.4}.get(ss.tier, 0.7)
    if ss.qtype == "choice" and ss.tier == "易":
        n, t, goal = 8, 12, "正确率≥90%，又快又准，不在简单题上手滑"
        detail = "限时选择专练：练'扫读关键词+排除法'，把简单分稳稳拿下"
    elif ss.qtype == "choice":
        n, t, goal = 6, 15, "正确率≥70%，掌握难选择的秒杀/特值技巧"
        detail = "难选择限时专练：特值法/排除法/数形结合，压缩单题用时"
    elif ss.qtype == "blank":
        n, t, goal = 6, 18, "计算零失误，规范书写"
        detail = "填空限时专练：重在计算准确与审题，避免会而不对"
    elif ss.tier == "压轴":
        n, t, goal = 3, 25, "只做最后一问，抢到前两步/分类讨论的分"
        detail = "压轴抢分专练：不追求全做对，练'写出可得分的步骤'，按步抢分"
    else:
        n, t, goal = 3, 30, "步骤规范，不丢冤枉分"
        detail = "中档大题限时规范专练：确保会做的题拿满，杜绝跳步失分"
    return TimedDrill(subject=subject, title=f"{cn}·{ss.name} 限时训练", qtype=ss.qtype,
                      tier=ss.tier, n_problems=n, time_limit_min=t, goal=goal, cause=ss.cause,
                      recoverable_points=round(recov, 1), detail=detail)


def execution_report(book, report, predictor) -> ExecutionReport:
    sec_data = book.latest_sections(report.user_id)
    subs: list[SubjectExecution] = []
    drills: list[TimedDrill] = []
    for subject in predictor.subjects_in(report):
        sg = sec_data.get(subject)
        if not sg:
            continue
        raw, full = predictor.predict_subject_raw(report, subject)
        sm = raw / full if full else 0.5
        ss_list = analyze(subject, sg, sm)
        total_loss = round(sum(s.loss for s in ss_list), 1)
        fixable = round(sum(s.loss for s in ss_list if s.tier in ("易", "中")), 1)
        subs.append(SubjectExecution(subject=subject, sections=ss_list,
                                     total_loss=total_loss, fixable_loss=fixable))
        drills += [_drill(subject, s) for s in ss_list if s.loss >= 2.0]
    drills.sort(key=lambda d: -d.recoverable_points)
    note = ("根据分题型得分定位了应试丢分，并开出限时训练；优先补"
            "「易/中档该拿却丢」的分，压轴以抢分为主。" if subs
            else "尚无分题型得分，录入模考时填写各题型得分即可获得精准的限时训练建议。")
    return ExecutionReport(user_id=report.user_id, has_section_data=bool(subs),
                           subjects=subs, drills=drills[:8], note=note)
